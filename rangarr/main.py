"""Rangarr entry point.

Orchestrates automated media searches across multiple *arr instances by fetching
missing and upgrade-eligible items, dispatching search commands with configurable
delays, and repeating at scheduled intervals.
"""

import datetime
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from rangarr.clients.arr import ArrClient
from rangarr.clients.arr import LidarrClient
from rangarr.clients.arr import RadarrClient
from rangarr.clients.arr import SonarrClient
from rangarr.config_parser import SETTINGS_SCHEMA
from rangarr.config_parser import get_setting_default
from rangarr.config_parser import load_config
from rangarr.config_parser import load_config_from_env
from rangarr.config_parser import parse_active_hours

if 'TZ' not in os.environ:
    os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'):
        time.tzset()

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z',
    stream=sys.stdout,
)
logging.Formatter.converter = time.localtime
logger = logging.getLogger(__name__)

_CLIENT_MAP: dict[str, type[ArrClient]] = {
    'lidarr': LidarrClient,
    'radarr': RadarrClient,
    'sonarr': SonarrClient,
}

_SEARCH_ORDER_LABELS: dict[str, str] = {
    'alphabetical_ascending': 'Alphabetical (Ascending)',
    'alphabetical_descending': 'Alphabetical (Descending)',
    'last_added_ascending': 'Last Added (Ascending)',
    'last_added_descending': 'Last Added (Descending)',
    'last_searched_ascending': 'Last Searched (Ascending)',
    'last_searched_descending': 'Last Searched (Descending)',
    'random': 'Random',
    'release_date_ascending': 'Release Date (Ascending)',
    'release_date_descending': 'Release Date (Descending)',
}


def _batch_display_str(batch: int) -> str:
    """Convert a batch size integer to its display string."""
    return {0: 'Disabled', -1: 'Unlimited'}.get(batch, str(batch))


def _calculate_batch(global_batch: int, weight_share: float) -> int:
    """Calculate batch size from global setting and instance weight share."""
    if global_batch in (0, -1):
        return global_batch
    return max(1, int(round(global_batch * weight_share)))


def _calculate_eta(item_count: int, stagger_seconds: int) -> str:
    """Calculate and format estimated time for batch processing."""
    result = ''
    if stagger_seconds > 0:
        eta = datetime.timedelta(seconds=item_count * stagger_seconds)
        result = f' (1 every {stagger_seconds} seconds, ETA: {eta})'
    return result


def _format_batch_info(client_name: str, ids: list[tuple[int, str, str]], stagger_seconds: int) -> str:
    """Format batch processing info message with counts and ETA."""
    missing_count = sum(1 for _, reason, _ in ids if reason == 'missing')
    upgrade_count = sum(1 for _, reason, _ in ids if reason == 'upgrade')
    eta_str = _calculate_eta(len(ids), stagger_seconds)
    result = f'[{client_name}] Triggering search for {len(ids)} item(s){eta_str}: {missing_count} missing, {upgrade_count} upgrade.'
    return result


def _get_setting(settings: dict, key: str) -> Any:
    """Return setting value, falling back to its schema default."""
    return settings.get(key, get_setting_default(key))


def _is_within_active_hours(start: datetime.time, end: datetime.time, now: datetime.time) -> bool:
    """Return True if now falls within the configured active hours window."""
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def _load_config_from_paths(config_paths: list[str]) -> dict | None:
    """Attempt to load configuration from a list of possible paths."""
    config = None
    error_message = None

    for config_path in config_paths:
        if Path(config_path).is_file():
            try:
                config = load_config(config_path)
                logger.info(f'Loaded configuration from: {config_path}')
                error_message = None
                break
            except ValueError as error:
                error_message = f'Configuration error in {config_path}: {error}'
                break
            except FileNotFoundError:
                continue

    if error_message:
        logger.error(error_message)
    elif config is None:
        logger.error('No config.yaml found. Copy config.example.yaml to config.yaml and fill in your instance details.')

    return config


def _log_rangarr_start(active_clients: list[Any], settings: dict) -> None:
    """Log startup information for Rangarr."""
    global_missing = _get_setting(settings, 'missing_batch_size')
    global_upgrade = _get_setting(settings, 'upgrade_batch_size')
    retry_days = _get_setting(settings, 'retry_interval_days')
    stagger_seconds = _get_setting(settings, 'stagger_interval_seconds')
    dry_run = _get_setting(settings, 'dry_run')
    active_hours = _get_setting(settings, 'active_hours')

    missing_str = _batch_display_str(global_missing)
    upgrade_str = _batch_display_str(global_upgrade)
    retry_str = 'Disabled' if retry_days == 0 else f'{retry_days} Days'
    raw_order = _get_setting(settings, 'search_order')
    search_order_str = _SEARCH_ORDER_LABELS.get(raw_order, raw_order.capitalize())
    dry_run_str = ' (DRY RUN ENABLED)' if dry_run else ''
    active_hours_str = active_hours if active_hours else 'All hours'

    logger.info(
        f'Rangarr started{dry_run_str} | '
        f'Instances: {len(active_clients)} active | '
        f'Run Interval: {_get_setting(settings, "run_interval_minutes")} Minutes | '
        f'Missing Batch: {missing_str} | '
        f'Upgrade Batch: {upgrade_str} | '
        f'Search Stagger: {stagger_seconds} Seconds | '
        f'Search Order: {search_order_str} | '
        f'Retry Interval: {retry_str} | '
        f'Active Hours: {active_hours_str}'
    )


def _run_search_cycle(active_clients: list[Any], settings: dict) -> None:
    """Run a single search cycle across all active clients."""
    logger.info('--- Starting search cycle ---')

    global_missing = _get_setting(settings, 'missing_batch_size')
    global_upgrade = _get_setting(settings, 'upgrade_batch_size')
    stagger_seconds = _get_setting(settings, 'stagger_interval_seconds')

    total_weight = sum(client.weight for client in active_clients)

    for client in active_clients:
        weight_share = client.weight / total_weight if total_weight > 0 else 0

        client_missing = _calculate_batch(global_missing, weight_share)
        client_upgrade = _calculate_batch(global_upgrade, weight_share)

        if client_missing == 0 and client_upgrade == 0:
            logger.info(f'[{client.name}] Missing and upgrade items disabled, skipping.')
            continue

        if client_missing == 0:
            logger.info(f'[{client.name}] Missing items disabled for this cycle.')
        if client_upgrade == 0:
            logger.info(f'[{client.name}] Upgrade items disabled for this cycle.')

        ids = client.get_media_to_search(client_missing, client_upgrade)
        if not ids:
            logger.info(f'[{client.name}] No media to search this cycle.')
            continue

        logger.info(_format_batch_info(client.name, ids, stagger_seconds))
        client.trigger_search(ids)


def _seconds_until_window_open(start: datetime.time, now: datetime.time, today: datetime.date | None = None) -> int:
    """Return the number of seconds until the active hours window next opens."""
    date = today if today is not None else datetime.date.today()
    start_dt = datetime.datetime.combine(date, start)
    now_dt = datetime.datetime.combine(date, now)
    if start_dt <= now_dt:
        start_dt += datetime.timedelta(days=1)
    return int((start_dt - now_dt).total_seconds())


def build_arr_clients(
    instances_config: dict,
    settings: dict,
    client_registry: dict[str, type[ArrClient]] | None = None,
) -> list[ArrClient]:
    """Instantiate all *arr clients declared in the config.

    Args:
        instances_config: The ``instances`` section of the config dict.
        settings: The ``settings`` section of the config dict.
        client_registry: Optional client type registry (defaults to _CLIENT_MAP).

    Returns:
        Flat list of instantiated *arr client objects.
    """
    registry = client_registry if client_registry is not None else _CLIENT_MAP
    clients: list[ArrClient] = []
    for arr_type, client_class in registry.items():
        for instance in instances_config.get(arr_type, []):
            instance_overrides = {key: instance[key] for key in SETTINGS_SCHEMA if key in instance}
            client_settings = {**settings, **instance_overrides}
            client = client_class(
                name=instance['name'],
                url=instance['url'],
                api_key=instance['api_key'],
                settings=client_settings,
                weight=instance.get('weight', 1.0),
            )
            clients.append(client)
            logger.info(f'Registered {arr_type.capitalize()} instance: {instance["name"]} (Weight: {client.weight})')
    return clients


def run() -> None:
    """Load configuration and start the search loop.

    Reads the configuration file or environment variables, instantiates
    the *arr clients, and enters an infinite loop to run periodic searches
    based on the configured intervals.
    """
    config_source = os.environ.get('RANGARR_CONFIG_SOURCE', 'file').lower()
    if config_source == 'env':
        logger.info('Loading configuration from environment variables.')
        try:
            config = load_config_from_env()
        except ValueError as error:
            logger.error(f'Configuration error from environment: {error}')
            config = None
    else:
        if config_source != 'file':
            logger.warning(
                f"Unrecognized RANGARR_CONFIG_SOURCE value '{config_source}'. Expected 'file' or 'env'. Falling back to file mode."
            )
        config = _load_config_from_paths(['config/config.yaml', 'config.yaml'])

    if not config:
        sys.exit(1)

    settings = config.get('global_settings', {})
    active_clients = build_arr_clients(config.get('instances', {}), settings)

    if not active_clients:
        logger.warning("No *arr instances are configured. Add at least one entry under 'instances' to begin.")
        sys.exit(1)

    _log_rangarr_start(active_clients, settings)

    run_interval_seconds = _get_setting(settings, 'run_interval_minutes') * 60
    active_hours = _get_setting(settings, 'active_hours')
    parsed_window = parse_active_hours(active_hours) if active_hours else None

    while True:
        if parsed_window:
            start_time, end_time = parsed_window
            now = datetime.datetime.now().time()
            if not _is_within_active_hours(start_time, end_time, now):
                secs = _seconds_until_window_open(start_time, now)
                logger.info(f'Outside active hours ({active_hours}). Sleeping {secs}s until window opens.')
                time.sleep(secs)
                continue
        _run_search_cycle(active_clients, settings)
        logger.info(f'--- Cycle complete. Sleeping for {_get_setting(settings, "run_interval_minutes")}m. ---')
        time.sleep(run_interval_seconds)


if __name__ == '__main__':
    run()

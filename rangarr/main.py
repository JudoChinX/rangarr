"""Rangarr entry point.

Orchestrates automated media searches across multiple *arr instances by fetching
missing and upgrade-eligible items, dispatching search commands with configurable
delays, and repeating at scheduled intervals.
"""

import datetime
import logging
import math
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

_MAX_CONNECTION_ATTEMPTS: int = 3
_MIN_SLEEP_SECONDS: float = 1.0
_RETRY_DELAY_SECONDS: int = 10

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

type MediaItem = tuple[int | str, str, str]


def _allocate_slots(
    limit: int,
    client_backlogs: dict[Any, list[MediaItem]],
) -> list[tuple[Any, MediaItem]]:
    """Allocate global search slots using weighted round-robin distribution."""
    winners: list[tuple[Any, MediaItem]] = []
    pools = {client: list(items) for client, items in client_backlogs.items() if items}

    if limit == 0 or not pools:
        return []

    sorted_clients = sorted(
        pools.keys(),
        key=lambda clt: (-getattr(clt, 'weight', 1.0), getattr(clt, 'name', '')),
    )

    while pools and (limit == -1 or len(winners) < limit):
        for client in list(sorted_clients):
            if client not in pools:
                continue
            weight = getattr(client, 'weight', 1.0)
            # Fractional weights affect sort order but not turn count; truncate to int.
            turns = max(1, int(weight))
            for _ in range(turns):
                if limit != -1 and len(winners) >= limit:
                    break
                if pools[client]:
                    winners.append((client, pools[client].pop(0)))
                if not pools[client]:
                    del pools[client]
                    break
            if limit != -1 and len(winners) >= limit:
                break
    return winners


def _batch_display_str(batch: int) -> str:
    """Convert a batch size integer to its display string."""
    return {0: 'Disabled', -1: 'Unlimited'}.get(batch, str(batch))


def _build_final_queue(
    allocated_missing: list[tuple[Any, MediaItem]],
    allocated_upgrade: list[tuple[Any, MediaItem]],
    interleave_instances: bool,
    interleave_types: bool,
) -> list[tuple[Any, MediaItem]]:
    """Build the ordered execution queue from allocated missing and upgrade slots."""
    final_queue: list[tuple[Any, MediaItem]] = []
    if interleave_types and interleave_instances:
        for idx in range(max(len(allocated_missing), len(allocated_upgrade))):
            if idx < len(allocated_missing):
                final_queue.append(allocated_missing[idx])
            if idx < len(allocated_upgrade):
                final_queue.append(allocated_upgrade[idx])
    elif interleave_types:
        for client in _clients_in_allocation_order(allocated_missing, allocated_upgrade):
            cli_missing = [(clt, item) for clt, item in allocated_missing if clt is client]
            cli_upgrade = [(clt, item) for clt, item in allocated_upgrade if clt is client]
            for idx in range(max(len(cli_missing), len(cli_upgrade))):
                if idx < len(cli_missing):
                    final_queue.append(cli_missing[idx])
                if idx < len(cli_upgrade):
                    final_queue.append(cli_upgrade[idx])
    elif interleave_instances:
        final_queue = allocated_missing + allocated_upgrade
    else:
        for client in _clients_in_allocation_order(allocated_missing, allocated_upgrade):
            cli_missing = [(clt, item) for clt, item in allocated_missing if clt is client]
            cli_upgrade = [(clt, item) for clt, item in allocated_upgrade if clt is client]
            final_queue.extend(cli_missing)
            final_queue.extend(cli_upgrade)
    return final_queue


def _calculate_eta(item_count: int, stagger_seconds: int) -> str:
    """Return a formatted ETA string for a staggered batch, or empty string if stagger is disabled."""
    if stagger_seconds <= 0 or item_count <= 1:
        return ''
    eta = datetime.timedelta(seconds=(item_count - 1) * stagger_seconds)
    return f' (1 every {stagger_seconds} seconds, ETA: {eta})'


def _clients_in_allocation_order(
    allocated_missing: list[tuple[Any, MediaItem]],
    allocated_upgrade: list[tuple[Any, MediaItem]],
) -> list[Any]:
    """Return unique clients in the order they first appear across allocated slots."""
    seen: set[Any] = set()
    clients: list[Any] = []
    for client, _ in allocated_missing + allocated_upgrade:
        if client not in seen:
            clients.append(client)
            seen.add(client)
    return clients


def _format_cycle_complete_log(
    ran_missing: bool,
    ran_upgrade: bool,
    next_missing_secs: float,
    next_upgrade_secs: float,
) -> str:
    """Format the end-of-cycle log message with which types ran and next scheduled times."""
    types = []
    if ran_missing:
        types.append('missing')
    if ran_upgrade:
        types.append('upgrade')
    ran_str = ', '.join(types)
    next_missing_m = max(0, math.ceil(next_missing_secs / 60))
    next_upgrade_m = max(0, math.ceil(next_upgrade_secs / 60))
    return f'--- Cycle complete ({ran_str}). Next: missing in {next_missing_m}m, upgrade in {next_upgrade_m}m. ---'


def _format_retry_interval_str(
    retry_days: int,
    retry_missing: int | None,
    retry_upgrade: int | None,
) -> str:
    """Format the retry interval display string with optional per-type overrides."""
    global_retry_str = 'Disabled' if retry_days == 0 else f'{retry_days} Days'
    if retry_missing is not None or retry_upgrade is not None:
        missing_retry_str = (
            ('Disabled' if retry_missing == 0 else f'{retry_missing} Days')
            if retry_missing is not None
            else global_retry_str
        )
        upgrade_retry_str = (
            ('Disabled' if retry_upgrade == 0 else f'{retry_upgrade} Days')
            if retry_upgrade is not None
            else global_retry_str
        )
        return f'Global: {global_retry_str}, Missing: {missing_retry_str}, Upgrade: {upgrade_retry_str}'
    return global_retry_str


def _format_run_interval_str(
    run_interval_m: int,
    run_interval_missing_m: int | None,
    run_interval_upgrade_m: int | None,
) -> str:
    """Format the run interval display string with optional per-type overrides."""
    if run_interval_missing_m is not None or run_interval_upgrade_m is not None:
        eff_missing_m = run_interval_missing_m if run_interval_missing_m is not None else run_interval_m
        eff_upgrade_m = run_interval_upgrade_m if run_interval_upgrade_m is not None else run_interval_m
        return f'{run_interval_m}m (Missing: {eff_missing_m}m, Upgrade: {eff_upgrade_m}m)'
    return f'{run_interval_m}m'


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


def _log_rangarr_start(active_clients: list[ArrClient], settings: dict) -> None:
    """Log startup information for Rangarr."""
    global_missing = _get_setting(settings, 'missing_batch_size')
    global_upgrade = _get_setting(settings, 'upgrade_batch_size')
    stagger_seconds = _get_setting(settings, 'stagger_interval_seconds')
    dry_run = _get_setting(settings, 'dry_run')
    active_hours = _get_setting(settings, 'active_hours')
    interleave_instances = _get_setting(settings, 'interleave_instances')
    interleave_types = _get_setting(settings, 'interleave_types')

    retry_str = _format_retry_interval_str(
        _get_setting(settings, 'retry_interval_days'),
        _get_setting(settings, 'retry_interval_days_missing'),
        _get_setting(settings, 'retry_interval_days_upgrade'),
    )
    raw_order = _get_setting(settings, 'search_order')
    search_order_str = _SEARCH_ORDER_LABELS.get(raw_order, raw_order.capitalize())
    dry_run_str = ' (DRY RUN ENABLED)' if dry_run else ''
    active_hours_str = active_hours if active_hours else 'All hours'
    interleave_instances_str = 'Yes' if interleave_instances else 'No'
    interleave_types_str = 'Yes' if interleave_types else 'No'
    interval_str = _format_run_interval_str(
        _get_setting(settings, 'run_interval_minutes'),
        _get_setting(settings, 'run_interval_minutes_missing'),
        _get_setting(settings, 'run_interval_minutes_upgrade'),
    )

    logger.info(
        f'Rangarr started{dry_run_str} | '
        f'Instances: {len(active_clients)} active | '
        f'Run Interval: {interval_str} | '
        f'Missing Batch: {_batch_display_str(global_missing)} | '
        f'Upgrade Batch: {_batch_display_str(global_upgrade)} | '
        f'Search Stagger: {stagger_seconds} Seconds | '
        f'Search Order: {search_order_str} | '
        f'Retry Interval: {retry_str} | '
        f'Active Hours: {active_hours_str} | '
        f'Interleave Instances: {interleave_instances_str} | '
        f'Interleave Types: {interleave_types_str}'
    )


def _resolve_interval_secs(settings: dict, specific_key: str) -> float:
    """Return per-type interval in seconds, falling back to the global interval."""
    override = _get_setting(settings, specific_key)
    resolved_minutes = override if override is not None else _get_setting(settings, 'run_interval_minutes')
    return resolved_minutes * 60


def _run_search_cycle(
    active_clients: list[ArrClient],
    settings: dict,
    *,
    run_missing: bool = True,
    run_upgrade: bool = True,
) -> None:
    """Run a single search cycle across all active clients using global allocation."""
    logger.info('--- Starting search cycle ---')

    global_missing = _get_setting(settings, 'missing_batch_size') if run_missing else 0
    global_upgrade = _get_setting(settings, 'upgrade_batch_size') if run_upgrade else 0
    stagger_seconds = _get_setting(settings, 'stagger_interval_seconds')
    interleave_instances = _get_setting(settings, 'interleave_instances')
    interleave_types = _get_setting(settings, 'interleave_types')

    missing_pools: dict[ArrClient, list[MediaItem]] = {}
    upgrade_pools: dict[ArrClient, list[MediaItem]] = {}

    for client in active_clients:
        candidates = client.get_media_to_search(global_missing, global_upgrade)

        m_items = [item for item in candidates if item[1] == 'missing']
        u_items = [item for item in candidates if item[1] == 'upgrade']

        if m_items:
            missing_pools[client] = m_items
        if u_items:
            upgrade_pools[client] = u_items

    allocated_missing = _allocate_slots(global_missing, missing_pools)
    allocated_upgrade = _allocate_slots(global_upgrade, upgrade_pools)
    final_queue = _build_final_queue(allocated_missing, allocated_upgrade, interleave_instances, interleave_types)

    if not final_queue:
        logger.info('No media to search this cycle across all instances.')
        return

    logger.info(f'Total search batch: {len(final_queue)} item(s){_calculate_eta(len(final_queue), stagger_seconds)}')

    for index, (client, item) in enumerate(final_queue, start=1):
        client.trigger_search([item], index=index, total=len(final_queue))

        if stagger_seconds > 0 and index < len(final_queue):
            logger.debug(f'Staggering next search by {stagger_seconds}s.')
            time.sleep(stagger_seconds)


def _seconds_until_window_open(start: datetime.time, now: datetime.time, today: datetime.date | None = None) -> int:
    """Return the number of seconds until the active hours window next opens."""
    date = today if today is not None else datetime.date.today()
    start_dt = datetime.datetime.combine(date, start)
    now_dt = datetime.datetime.combine(date, now)
    if start_dt <= now_dt:
        start_dt += datetime.timedelta(days=1)
    return math.ceil((start_dt - now_dt).total_seconds())


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
    built_clients = build_arr_clients(config.get('instances', {}), settings)

    if not built_clients:
        logger.warning("No *arr instances are configured. Add at least one entry under 'instances' to begin.")
        sys.exit(1)

    active_clients = verify_arr_clients(built_clients)
    if not active_clients:
        logger.error('All configured *arr instances failed to connect. Check network connectivity and instance URLs.')
        sys.exit(1)

    _log_rangarr_start(active_clients, settings)

    missing_interval_secs = _resolve_interval_secs(settings, 'run_interval_minutes_missing')
    upgrade_interval_secs = _resolve_interval_secs(settings, 'run_interval_minutes_upgrade')
    active_hours = _get_setting(settings, 'active_hours')
    parsed_window = parse_active_hours(active_hours) if active_hours else None

    last_missing_run = -math.inf
    last_upgrade_run = -math.inf

    while True:
        if parsed_window:
            start_time, end_time = parsed_window
            now = datetime.datetime.now().time()
            if not _is_within_active_hours(start_time, end_time, now):
                secs = _seconds_until_window_open(start_time, now)
                logger.info(f'Outside active hours ({active_hours}). Sleeping {secs}s until window opens.')
                time.sleep(secs)
                continue

        now = time.monotonic()
        run_missing = (now - last_missing_run) >= missing_interval_secs
        run_upgrade = (now - last_upgrade_run) >= upgrade_interval_secs

        if run_missing:
            last_missing_run = now
        if run_upgrade:
            last_upgrade_run = now

        _run_search_cycle(active_clients, settings, run_missing=run_missing, run_upgrade=run_upgrade)

        now = time.monotonic()
        logger.info(
            _format_cycle_complete_log(
                run_missing,
                run_upgrade,
                missing_interval_secs - (now - last_missing_run),
                upgrade_interval_secs - (now - last_upgrade_run),
            )
        )
        time.sleep(
            max(
                _MIN_SLEEP_SECONDS,
                min(
                    missing_interval_secs - (now - last_missing_run),
                    upgrade_interval_secs - (now - last_upgrade_run),
                ),
            )
        )


def verify_arr_clients(clients: list[ArrClient]) -> list[ArrClient]:
    """Verify connectivity to each client, retrying before dropping unreachable ones.

    Args:
        clients: List of *arr clients to verify.

    Returns:
        Filtered list of clients that successfully connected within the retry limit.
    """
    verified: list[ArrClient] = []
    for client in clients:
        connected = False
        for attempt in range(1, _MAX_CONNECTION_ATTEMPTS + 1):
            if client.check_connection():
                if attempt > 1:
                    logger.info(f'[{client.name}] Connected on attempt {attempt}/{_MAX_CONNECTION_ATTEMPTS}.')
                connected = True
                break
            if attempt < _MAX_CONNECTION_ATTEMPTS:
                logger.warning(
                    f'[{client.name}] Connection attempt {attempt}/{_MAX_CONNECTION_ATTEMPTS} failed. '
                    f'Retrying in {_RETRY_DELAY_SECONDS}s...'
                )
                time.sleep(_RETRY_DELAY_SECONDS)
            else:
                logger.error(
                    f'[{client.name}] Could not connect after {_MAX_CONNECTION_ATTEMPTS} attempts. Skipping instance.'
                )
        if connected:
            verified.append(client)
    return verified


if __name__ == '__main__':
    run()

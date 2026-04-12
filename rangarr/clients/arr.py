"""*arr API clients: base class with pagination, and app-specific subclasses."""

import datetime
import logging
import random
import time
from abc import ABC
from abc import abstractmethod
from typing import override

import requests

logger = logging.getLogger(__name__)

type MediaItem = tuple[int, str, str]


class ArrClient(ABC):
    """Abstract base class for *arr application clients."""

    ENDPOINT_WANTED_MISSING = '/api/v3/wanted/missing'
    ENDPOINT_WANTED_CUTOFF = '/api/v3/wanted/cutoff'
    ENDPOINT_COMMAND = '/api/v3/command'

    def __init__(
        self,
        name: str,
        url: str,
        api_key: str,
        settings: dict,
        weight: float = 1.0,
    ) -> None:
        """Initialize the base *arr client.

        Args:
            name: Human-readable name for the client instance.
            url: Base URL of the *arr service API.
            api_key: Secret API key for authentication.
            settings: Dictionary of configuration settings.
            weight: Relative priority of this client instance.
        """
        self.name = name
        self.url = url.rstrip('/')
        self.settings = settings
        self.weight = weight
        self.stagger_seconds = self.settings.get('stagger_interval_seconds', 30)
        self.search_order = self.settings.get('search_order', 'last_searched_ascending')
        self.retry_interval_days = self.settings.get('retry_interval_days', 30)
        if not self.url.lower().startswith('https://'):
            logger.warning(
                f"Client '{name}' is using a non-HTTPS URL ({self.url}). API keys will be transmitted in plaintext."
            )
        self.session = requests.Session()
        self.session.headers.update({'X-Api-Key': api_key, 'Content-Type': 'application/json'})

        self.dry_run = self.settings.get('dry_run', False)
        self.missing_cursor: int = 1
        self.upgrade_cursor: int = 1
        self.missing_buffer: list[dict] = []
        self.upgrade_buffer: list[dict] = []

    @property
    @abstractmethod
    def _command_name(self) -> str:
        """Return the API command name for searches (e.g. 'MoviesSearch')."""

    def _extract_item(self, record: dict, reason: str) -> MediaItem:
        """Extract (id, reason, title) tuple from record."""
        record_id = record['id']
        title = self._get_record_title(record)
        return (record_id, reason, title)

    def _extra_fetch_params(self) -> dict[str, str]:
        """Return additional parameterss to include in fetch requests."""
        return {}

    def _fetch_batch(self, endpoint: str, page: int, page_size: int) -> list[dict]:
        """Fetch single page of records."""
        url = f'{self.url}{endpoint}'
        result = []
        sort_key, sort_direction = self._get_sort_params()
        params = {
            **self._extra_fetch_params(),
            'sortKey': sort_key,
            'sortDirection': sort_direction,
            'page': page,
            'pageSize': page_size,
        }
        try:
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            result = response.json().get('records', [])
        except requests.RequestException as error:
            logger.error(f'[{self.name}] Failed to fetch {endpoint} (page {page}): {error}')
        return result

    def _fetch_unlimited(self, endpoint: str) -> list[dict]:
        """Fetch all available records across all pages."""
        url = f'{self.url}{endpoint}'
        result = []
        current_page = 1
        page_size = 1000
        sort_key, sort_direction = self._get_sort_params()
        base_params = {
            **self._extra_fetch_params(),
            'sortKey': sort_key,
            'sortDirection': sort_direction,
        }

        while True:
            params = {
                **base_params,
                'page': current_page,
                'pageSize': page_size,
            }
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                records = response.json().get('records', [])
                result.extend(records)
                if len(records) < page_size:
                    break
                current_page += 1
            except requests.RequestException as error:
                logger.error(f'[{self.name}] Failed to fetch unlimited {endpoint}: {error}')
                break
        return result

    def _fetch_wanted(self, endpoint: str, page: int, batch_size: int) -> list[dict]:
        """Fetch wanted items based on batch size."""
        result = []
        if batch_size == 0:
            result = self._fetch_unlimited(endpoint)
        else:
            result = self._fetch_batch(endpoint, page, batch_size)
        return result

    @abstractmethod
    def _get_record_title(self, record: dict) -> str:
        """Extract a human-readable title from the API response record."""

    def _get_sort_params(self) -> tuple[str, str]:
        """Return the API sort key and direction for the configured search order."""
        if self.search_order in ('last_searched_ascending', 'last_searched_descending'):
            sort_key = 'lastSearchTime'
        elif self.search_order in ('last_added_ascending', 'last_added_descending'):
            sort_key = 'dateAdded'
        elif self.search_order in ('release_date_ascending', 'release_date_descending'):
            sort_key = 'releaseDate'
        else:
            sort_key = 'title'
        sort_direction = 'descending' if self.search_order.endswith('_descending') else 'ascending'
        return sort_key, sort_direction

    def _get_target_media(
        self,
        endpoint: str,
        target_batch_size: int,
        cursor_attr: str,
        buffer_attr: str,
        reason: str,
        seen: set[int],
        check_availability: bool = False,
    ) -> list[MediaItem]:
        """Fetch and process records until the target batch size is met (or backlog exhausted)."""
        items: list[MediaItem] = []

        if target_batch_size != 0:
            last_searched = self.search_order in ('last_searched_ascending', 'last_searched_descending')
            last_added = self.search_order in ('last_added_ascending', 'last_added_descending')
            unlimited_mode = target_batch_size == -1 or self.search_order == 'random' or last_searched or last_added

            if unlimited_mode:
                logger.debug(f'[{self.name}] {endpoint}: unlimited fetch triggered.')
                setattr(self, buffer_attr, [])
                records = self._fetch_wanted(endpoint, 1, 0)  # 0 triggers unlimited fetch internally
                if self.search_order == 'random':
                    random.shuffle(records)

                for record in records:
                    if 0 < target_batch_size <= len(items):
                        break
                    item = self._process_record(record, reason, seen, check_availability)
                    if item:
                        items.append(item)
            else:
                buffer: list[dict] = getattr(self, buffer_attr)
                cursor: int = getattr(self, cursor_attr)

                while len(items) < target_batch_size:
                    if not buffer:
                        records = self._fetch_wanted(endpoint, cursor, target_batch_size)
                        if not records:
                            logger.debug(f'[{self.name}] {endpoint}: end of backlog at cursor {cursor}, resetting.')
                            cursor = 1
                            break
                        buffer.extend(records)
                        cursor += 1

                    record = buffer.pop(0)
                    item = self._process_record(record, reason, seen, check_availability)
                    if item:
                        items.append(item)

                setattr(self, cursor_attr, cursor)

        return items

    @property
    @abstractmethod
    def _id_field(self) -> str:
        """Return the API payload ID field name for searches (e.g. 'movieIds')."""

    def _interleave_items(
        self,
        missing_items: list[MediaItem],
        upgrade_items: list[MediaItem],
    ) -> list[MediaItem]:
        """Proportionally interleave missing and upgrade items."""
        total_missing = len(missing_items)
        total_upgrade = len(upgrade_items)
        total = total_missing + total_upgrade
        result = []

        missing_index = 0
        upgrade_index = 0

        for current_index in range(total):
            missing_ratio = total_missing / total if total > 0 else 0
            current_missing_ratio = missing_index / (current_index + 1)

            if missing_index < total_missing and (
                upgrade_index >= total_upgrade or current_missing_ratio < missing_ratio
            ):
                result.append(missing_items[missing_index])
                missing_index += 1
            elif upgrade_index < total_upgrade:
                result.append(upgrade_items[upgrade_index])
                upgrade_index += 1

        return result

    @abstractmethod
    def _is_available(self, record: dict) -> bool:
        """Determine if a media item is actually released and available."""

    def _is_date_past(self, date_str: str | None) -> bool:
        """Return True if the given ISO date string is in the past."""
        result = False
        if date_str:
            now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
            result = date_str <= now
        return result

    def _is_within_retry_window(self, record: dict) -> bool:
        """Return True if the item was last searched within the retry window."""
        last_search = record.get('lastSearchTime')
        result = False
        if self.retry_interval_days > 0 and last_search:
            last_search_dt = datetime.datetime.fromisoformat(last_search.replace('Z', '+00:00'))
            cutoff_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=self.retry_interval_days)
            result = last_search_dt > cutoff_time
        return result

    def _process_record(
        self,
        record: dict,
        reason: str,
        seen: set[int],
        check_availability: bool = False,
    ) -> MediaItem | None:
        """Process a single record, returning a MediaItem if available and outside retry window."""
        record_id = record.get('id')
        item = None

        if record_id is not None and record_id not in seen:
            if check_availability and not self._is_available(record):
                title = self._get_record_title(record)
                logger.debug(f'[{self.name}] Skipping {reason} item (not yet available): {title}')
            elif self._is_within_retry_window(record):
                title = self._get_record_title(record)
                last_search = record.get('lastSearchTime', 'Unknown')
                logger.debug(
                    f'[{self.name}] Skipping {reason} item (within retry window, last searched: {last_search}): {title}'
                )
            else:
                seen.add(record_id)
                item = self._extract_item(record, reason)

        return item

    def _trigger_single(self, item_id: int, reason: str, title: str, index: int, total: int) -> None:
        """Dispatch a search command for a single media item."""
        if self.dry_run:
            logger.info(f'[{self.name}] [DRY RUN] Would search ({reason}): {title} ({index}/{total})')
        else:
            url = f'{self.url}{self.ENDPOINT_COMMAND}'
            payload = {'name': self._command_name, self._id_field: [item_id]}
            try:
                response = self.session.post(url, json=payload, timeout=15)
                response.raise_for_status()
                logger.info(f'[{self.name}] Searching ({reason}): {title} ({index}/{total})')
            except requests.RequestException as error:
                logger.error(
                    f'[{self.name}] Failed to trigger {self._command_name} for {title} (ID: {item_id}): {error}'
                )

    def get_media_to_search(self, missing_batch_size: int, upgrade_batch_size: int) -> list[MediaItem]:
        """Build a deduplicated list of missing and upgrade media items to search.

        Args:
            missing_batch_size: Maximum number of missing items to return.
            upgrade_batch_size: Maximum number of upgrade items to return.

        Returns:
            Ordered list of MediaItems to search.
        """
        seen: set[int] = set()

        missing_items = self._get_target_media(
            self.ENDPOINT_WANTED_MISSING,
            missing_batch_size,
            'missing_cursor',
            'missing_buffer',
            'missing',
            seen,
            check_availability=True,
        )

        upgrade_items = self._get_target_media(
            self.ENDPOINT_WANTED_CUTOFF,
            upgrade_batch_size,
            'upgrade_cursor',
            'upgrade_buffer',
            'upgrade',
            seen,
            check_availability=False,
        )

        merged = self._interleave_items(missing_items, upgrade_items)

        if self.search_order == 'random':
            random.shuffle(merged)

        return merged

    def trigger_search(self, items: list[MediaItem]) -> None:
        """Dispatch a staggered search command for each media item.

        Args:
            items: Ordered list of MediaItems to search.
        """
        for index, (item_id, reason, title) in enumerate(items, start=1):
            self._trigger_single(item_id, reason, title, index, len(items))
            if self.stagger_seconds > 0 and index < len(items):
                logger.debug(f'[{self.name}] Staggering next search by {self.stagger_seconds}s.')
                time.sleep(self.stagger_seconds)


class LidarrClient(ArrClient):
    """Lidarr API client."""

    ENDPOINT_WANTED_MISSING = '/api/v1/wanted/missing'
    ENDPOINT_WANTED_CUTOFF = '/api/v1/wanted/cutoff'
    ENDPOINT_COMMAND = '/api/v1/command'

    @property
    @override
    def _command_name(self) -> str:
        return 'AlbumSearch'

    @property
    @override
    def _id_field(self) -> str:
        return 'albumIds'

    @override
    def _get_record_title(self, record: dict) -> str:
        artist_name = record.get('artist', {}).get('artistName', 'Unknown Artist')
        album_title = record.get('title', 'Unknown Album')
        return f'{artist_name} - {album_title}'

    @override
    def _is_available(self, record: dict) -> bool:
        return self._is_date_past(record.get('releaseDate'))


class RadarrClient(ArrClient):
    """Radarr API client."""

    @property
    @override
    def _command_name(self) -> str:
        return 'MoviesSearch'

    @property
    @override
    def _id_field(self) -> str:
        return 'movieIds'

    @override
    def _get_record_title(self, record: dict) -> str:
        return record.get('title', f'Movie {record.get("id", "Unknown")}')

    @override
    def _is_available(self, record: dict) -> bool:
        return record.get('isAvailable', True)


class SonarrClient(ArrClient):
    """Sonarr API client."""

    @property
    @override
    def _command_name(self) -> str:
        return 'EpisodeSearch'

    @override
    def _extra_fetch_params(self) -> dict[str, str]:
        return {'includeSeries': 'true'}

    @override
    def _get_record_title(self, record: dict) -> str:
        series_title = record.get('series', {}).get('title', 'Unknown Series')
        season = record.get('seasonNumber', 0)
        episode = record.get('episodeNumber', 0)
        episode_title = record.get('title', 'Unknown Episode')
        return f'{series_title} - S{season:02d}E{episode:02d} - {episode_title}'

    def _get_season_number(self, record: dict) -> int | None:
        """Return the season number from an episode record."""
        return record.get('seasonNumber')

    def _get_season_title(self, record: dict, season_number: int) -> str:
        """Return a human-readable title for a season search."""
        series_title = record.get('series', {}).get('title', 'Unknown Series')
        return f'{series_title} - Season {season_number:02d}'

    def _get_series_id(self, record: dict) -> int | None:
        """Return the series ID from an episode record."""
        return record.get('series', {}).get('id')

    @property
    @override
    def _id_field(self) -> str:
        return 'episodeIds'

    @override
    def _is_available(self, record: dict) -> bool:
        return self._is_date_past(record.get('airDateUtc'))

    def __init__(
        self,
        name: str,
        url: str,
        api_key: str,
        settings: dict,
        weight: float = 1.0,
    ) -> None:
        """Initialize the Sonarr client.

        Args:
            name: Human-readable name for the client instance.
            url: Base URL of the Sonarr service API.
            api_key: Secret API key for authentication.
            settings: Dictionary of configuration settings.
            weight: Relative priority of this client instance.
        """
        super().__init__(name, url, api_key, settings, weight)
        self.season_packs: bool = self.settings.get('season_packs', False)
        self._season_pack_items: list[tuple[int, int, str, str]] = []

    @override
    def get_media_to_search(self, missing_batch_size: int, upgrade_batch_size: int) -> list[MediaItem]:
        if not self.season_packs:
            return super().get_media_to_search(missing_batch_size, upgrade_batch_size)

        self._season_pack_items = []
        seen_seasons: set[tuple[int, int]] = set()

        missing_records = self._fetch_unlimited(self.ENDPOINT_WANTED_MISSING)
        for record in missing_records:
            if not self._is_available(record):
                continue
            if self._is_within_retry_window(record):
                continue
            series_id = self._get_series_id(record)
            season_number = self._get_season_number(record)
            if series_id is None or season_number is None:
                continue
            key = (series_id, season_number)
            if key not in seen_seasons:
                seen_seasons.add(key)
                title = self._get_season_title(record, season_number)
                self._season_pack_items.append((series_id, season_number, 'missing', title))

        upgrade_records = self._fetch_unlimited(self.ENDPOINT_WANTED_CUTOFF)
        for record in upgrade_records:
            # Availability check intentionally omitted for upgrades (matches base class behaviour).
            if self._is_within_retry_window(record):
                continue
            series_id = self._get_series_id(record)
            season_number = self._get_season_number(record)
            if series_id is None or season_number is None:
                continue
            key = (series_id, season_number)
            if key not in seen_seasons:
                seen_seasons.add(key)
                title = self._get_season_title(record, season_number)
                self._season_pack_items.append((series_id, season_number, 'upgrade', title))

        return [(series_id, reason, title) for series_id, unused_season, reason, title in self._season_pack_items]

    @override
    def trigger_search(self, items: list[MediaItem]) -> None:
        if not self.season_packs:
            super().trigger_search(items)
            return

        total = len(self._season_pack_items)
        for index, (series_id, season_number, reason, title) in enumerate(self._season_pack_items, start=1):
            if self.dry_run:
                logger.info(f'[{self.name}] [DRY RUN] Would search ({reason}): {title} ({index}/{total})')
            else:
                url = f'{self.url}{self.ENDPOINT_COMMAND}'
                payload = {'name': 'SeasonSearch', 'seriesId': series_id, 'seasonNumber': season_number}
                try:
                    response = self.session.post(url, json=payload, timeout=15)
                    response.raise_for_status()
                    logger.info(f'[{self.name}] Searching ({reason}): {title} ({index}/{total})')
                except requests.RequestException as error:
                    logger.error(
                        f'[{self.name}] Failed to trigger SeasonSearch for {title} '
                        f'(Series: {series_id}, Season: {season_number}): {error}'
                    )

            if self.stagger_seconds > 0 and index < total:
                logger.debug(f'[{self.name}] Staggering next search by {self.stagger_seconds}s.')
                time.sleep(self.stagger_seconds)

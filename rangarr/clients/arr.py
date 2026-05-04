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

type MediaItem = tuple[int | str, str, str]


class ArrClient(ABC):
    """Abstract base class for *arr application clients."""

    ENDPOINT_COMMAND = '/api/v3/command'
    ENDPOINT_QUALITY_PROFILE = '/api/v3/qualityprofile'
    ENDPOINT_TAG = '/api/v3/tag'
    ENDPOINT_WANTED_CUTOFF = '/api/v3/wanted/cutoff'
    ENDPOINT_WANTED_MISSING = '/api/v3/wanted/missing'

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
        self.retry_interval_days = self.settings.get('retry_interval_days', 30)
        self.retry_interval_days_missing = self.settings.get('retry_interval_days_missing')
        self.retry_interval_days_upgrade = self.settings.get('retry_interval_days_upgrade')
        self.stagger_seconds = self.settings.get('stagger_interval_seconds', 30)
        self.search_order = self.settings.get('search_order', 'last_searched_ascending')
        if not self.url.lower().startswith('https://'):
            logger.warning(
                f"Client '{name}' is using a non-HTTPS URL ({self.url}). API keys will be transmitted in plaintext."
            )
        self.session = requests.Session()
        self.session.headers.update({'X-Api-Key': api_key, 'Content-Type': 'application/json'})

        self.dry_run = self.settings.get('dry_run', False)
        self._include_tag_ids: set[int] = set()
        self._exclude_tag_ids: set[int] = set()
        self._resolve_tag_ids()

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
        """Return additional parameters injected into every ``_fetch_unlimited`` request."""
        return {'monitored': 'true'}

    def _fetch_list(self, endpoint: str, params: dict[str, str | int | list[int]] | None = None) -> list[dict]:
        """Fetch all records from a non-paginated list endpoint."""
        url = f'{self.url}{endpoint}'
        try:
            response = self.session.get(url, params=params or {}, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            logger.error(f'[{self.name}] Failed to fetch {endpoint}: {error}')
            return []

    def _fetch_quality_profile_cutoffs(self) -> dict[int, int]:
        """Return {profileId: cutoffFormatScore} for profiles where cutoffFormatScore > 0."""
        profiles = self._fetch_list(self.ENDPOINT_QUALITY_PROFILE)
        return {
            profile['id']: profile['cutoffFormatScore']
            for profile in profiles
            if profile.get('cutoffFormatScore', 0) > 0
        }

    def _fetch_unlimited(self, endpoint: str) -> list[dict]:
        """Fetch all available records across all pages."""
        url = f'{self.url}{endpoint}'
        result = []
        current_page = 1
        page_size = 1000

        while True:
            params = {
                **self._extra_fetch_params(),
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

    def _get_custom_format_score_unmet_records(self) -> list[dict]:
        """Orchestrate the supplemental custom format score upgrade pass."""
        profile_cutoffs = self._fetch_quality_profile_cutoffs()
        if not profile_cutoffs:
            return []
        return self._get_custom_format_upgrade_records(profile_cutoffs)

    def _get_custom_format_upgrade_records(self, _profile_cutoffs: dict[int, int]) -> list[dict]:
        """Return records for items where customFormatScore falls below the profile cutoff."""
        return []

    @abstractmethod
    def _get_record_tags(self, record: dict) -> list[int]:
        """Return the list of tag IDs from a record."""

    @abstractmethod
    def _get_record_title(self, record: dict) -> str:
        """Extract a human-readable title from the API response record."""

    @abstractmethod
    def _get_release_date(self, record: dict) -> str:
        """Return the release date string for client-side sorting, or '' if absent."""

    def _get_target_media(
        self,
        endpoint: str,
        target_batch_size: int,
        reason: str,
        seen: set[int],
        check_availability: bool = False,
    ) -> list[MediaItem]:
        """Fetch and process records until the target batch size is met (or backlog exhausted)."""
        items: list[MediaItem] = []

        if target_batch_size != 0:
            records = self._fetch_unlimited(endpoint)
            self._sort_records_client_side(records)

            for record in records:
                if 0 < target_batch_size <= len(items):
                    break
                item = self._process_record(record, reason, seen, check_availability)
                if item:
                    items.append(item)

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

    def _is_tag_filtered_out(self, record: dict) -> bool:
        """Return True if the record should be excluded by tag filtering rules."""
        record_tag_ids = set(self._get_record_tags(record))
        return bool(
            (self._exclude_tag_ids and record_tag_ids & self._exclude_tag_ids)
            or (self._include_tag_ids and not record_tag_ids & self._include_tag_ids)
        )

    def _is_within_retry_window(self, record: dict, reason: str) -> bool:
        """Return True if the item was last searched within the retry window."""
        last_search = record.get('lastSearchTime')
        result = False
        interval = self.retry_interval_days
        if reason == 'missing' and self.retry_interval_days_missing is not None:
            interval = self.retry_interval_days_missing
        elif reason == 'upgrade' and self.retry_interval_days_upgrade is not None:
            interval = self.retry_interval_days_upgrade
        if interval > 0 and last_search:
            last_search_dt = datetime.datetime.fromisoformat(last_search)
            cutoff_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=interval)
            result = last_search_dt > cutoff_time
        return result

    def _process_record(
        self,
        record: dict,
        reason: str,
        seen: set[int],
        check_availability: bool = False,
    ) -> MediaItem | None:
        """Process a single record, applying tag, availability, and retry-window filters."""
        record_id = record.get('id')
        item = None

        if record_id is not None and record_id not in seen:
            if self._is_tag_filtered_out(record):
                title = self._get_record_title(record)
                logger.debug(f'[{self.name}] Skipping {reason} item (tag filter): {title}')
            elif check_availability and not self._is_available(record):
                title = self._get_record_title(record)
                logger.debug(f'[{self.name}] Skipping {reason} item (not yet available): {title}')
            elif self._is_within_retry_window(record, reason):
                title = self._get_record_title(record)
                last_search = record.get('lastSearchTime', 'Unknown')
                logger.debug(
                    f'[{self.name}] Skipping {reason} item (within retry window, last searched: {last_search}): {title}'
                )
            else:
                seen.add(record_id)
                item = self._extract_item(record, reason)

        return item

    def _resolve_tag_ids(self) -> None:
        """Fetch instance tags and resolve configured tag names to IDs."""
        include_names = self.settings.get('include_tags', [])
        exclude_names = self.settings.get('exclude_tags', [])

        if include_names or exclude_names:
            url = f'{self.url}{self.ENDPOINT_TAG}'
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                tag_map = {tag['label'].lower(): tag['id'] for tag in response.json()}
                self._include_tag_ids = self._resolve_tag_names(tag_map, include_names)
                self._exclude_tag_ids = self._resolve_tag_names(tag_map, exclude_names)
            except requests.RequestException as err:
                logger.error(f'[{self.name}] Failed to fetch tags, tag filtering disabled: {err}')

    def _resolve_tag_names(self, tag_map: dict[str, int], names: list[str]) -> set[int]:
        """Resolve tag names to IDs, logging a warning for any unrecognised name."""
        result: set[int] = set()
        for name in names:
            tag_id = tag_map.get(name.lower())
            if tag_id is None:
                logger.warning(f'[{self.name}] Tag not found, ignoring: {name}')
            else:
                result.add(tag_id)
        return result

    def _sort_records_client_side(self, records: list[dict]) -> None:
        """Sort records in-place according to the configured search order."""
        sort_keys = {
            'alphabetical': self._get_record_title,
            'last_added': lambda rec: rec.get('dateAdded') or '',
            'last_searched': lambda rec: rec.get('lastSearchTime') or '',
            'release_date': self._get_release_date,
        }
        if self.search_order != 'random':
            base = self.search_order.rsplit('_', 1)[0]
            reverse = self.search_order.endswith('_descending')
            records.sort(key=sort_keys[base], reverse=reverse)

    def _trigger_single(self, item_id: int | str, reason: str, title: str, index: int, total: int) -> None:
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

    def check_connection(self) -> bool:
        """Return True if the tag endpoint is reachable, False on any network error."""
        url = f'{self.url}{self.ENDPOINT_TAG}'
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            return True
        except requests.RequestException:
            return False

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
            'missing',
            seen,
            check_availability=True,
        )

        upgrade_items = self._get_target_media(
            self.ENDPOINT_WANTED_CUTOFF,
            upgrade_batch_size,
            'upgrade',
            seen,
        )

        if upgrade_batch_size != 0:
            supplemental = self._get_custom_format_score_unmet_records()
            self._sort_records_client_side(supplemental)
            for record in supplemental:
                if 0 < upgrade_batch_size <= len(upgrade_items):
                    break
                item = self._process_record(record, 'upgrade', seen)
                if item:
                    upgrade_items.append(item)

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

    ENDPOINT_COMMAND = '/api/v1/command'
    ENDPOINT_TAG = '/api/v1/tag'
    ENDPOINT_WANTED_CUTOFF = '/api/v1/wanted/cutoff'
    ENDPOINT_WANTED_MISSING = '/api/v1/wanted/missing'

    @property
    @override
    def _command_name(self) -> str:
        return 'AlbumSearch'

    @override
    def _fetch_quality_profile_cutoffs(self) -> dict[int, int]:
        return {}

    @property
    @override
    def _id_field(self) -> str:
        return 'albumIds'

    @override
    def _get_record_tags(self, record: dict) -> list[int]:
        return record.get('tags', [])

    @override
    def _get_record_title(self, record: dict) -> str:
        artist_name = record.get('artist', {}).get('artistName', 'Unknown Artist')
        album_title = record.get('title', 'Unknown Album')
        return f'{artist_name} - {album_title}'

    @override
    def _get_release_date(self, record: dict) -> str:
        return record.get('releaseDate') or ''

    @override
    def _is_available(self, record: dict) -> bool:
        return self._is_date_past(record.get('releaseDate'))


class RadarrClient(ArrClient):
    """Radarr API client."""

    ENDPOINT_MOVIE = '/api/v3/movie'
    ENDPOINT_MOVIE_FILE = '/api/v3/moviefile'
    MOVIE_FILE_BATCH_SIZE = 100

    @property
    @override
    def _command_name(self) -> str:
        return 'MoviesSearch'

    def _fetch_movie_file_scores(self, file_ids: list[int]) -> dict[int, int]:
        """Return {fileId: customFormatScore} for the given movie file IDs."""
        scores: dict[int, int] = {}
        for batch_start in range(0, len(file_ids), self.MOVIE_FILE_BATCH_SIZE):
            batch = file_ids[batch_start : batch_start + self.MOVIE_FILE_BATCH_SIZE]
            movie_files = self._fetch_list(self.ENDPOINT_MOVIE_FILE, {'movieFileIds': batch})
            for mfile in movie_files:
                score = mfile.get('customFormatScore')
                scores[mfile['id']] = score if score is not None else 0
        return scores

    @override
    def _get_custom_format_upgrade_records(self, profile_cutoffs: dict[int, int]) -> list[dict]:
        movies = self._fetch_list(self.ENDPOINT_MOVIE)
        candidates: dict[int, tuple[dict, int]] = {}
        for movie in movies:
            if not movie.get('monitored', False):
                continue
            cutoff_score = profile_cutoffs.get(movie.get('qualityProfileId', -1), 0)
            file_id = movie.get('movieFileId')
            if cutoff_score > 0 and file_id:
                candidates[file_id] = (movie, cutoff_score)
        result: list[dict] = []
        if candidates:
            scores = self._fetch_movie_file_scores(list(candidates.keys()))
            result = [
                movie for file_id, (movie, cutoff_score) in candidates.items() if scores.get(file_id, 0) < cutoff_score
            ]
        return result

    @override
    def _get_record_tags(self, record: dict) -> list[int]:
        return record.get('tags', [])

    @override
    def _get_record_title(self, record: dict) -> str:
        return record.get('title', f'Movie {record.get("id", "Unknown")}')

    @override
    def _get_release_date(self, record: dict) -> str:
        return record.get('releaseDate') or ''

    @property
    @override
    def _id_field(self) -> str:
        return 'movieIds'

    @override
    def _is_available(self, record: dict) -> bool:
        return record.get('isAvailable', True)


class SonarrClient(ArrClient):
    """Sonarr API client."""

    ENDPOINT_EPISODE = '/api/v3/episode'
    ENDPOINT_EPISODE_FILE = '/api/v3/episodefile'
    ENDPOINT_SERIES = '/api/v3/series'
    SEASON_ID_PREFIX = 'season:'

    @override
    def __init__(
        self,
        name: str,
        url: str,
        api_key: str,
        settings: dict,
        weight: float = 1.0,
    ) -> None:
        super().__init__(name, url, api_key, settings, weight)
        self.season_packs: bool = self.settings.get('season_packs', False)

    def _collect_season_pack_records(
        self,
        records: list[dict],
        batch_size: int,
        reason: str,
        seen_seasons: set[tuple[int, int]],
        check_availability: bool,
        season_air_status: dict[tuple[int, int], str | None],
    ) -> list[MediaItem]:
        """Build a list of season-pack or individual-episode MediaItems from the given episode records."""
        items: list[MediaItem] = []
        for record in records:
            if 0 < batch_size <= len(items):
                break
            if self._is_tag_filtered_out(record):
                continue
            if check_availability and not self._is_available(record):
                continue
            if self._is_within_retry_window(record, reason):
                continue
            series_id = self._get_series_id(record)
            season_number = self._get_season_number(record)
            if series_id is None or season_number is None:
                continue
            key = (series_id, season_number)
            if key in seen_seasons:
                continue
            if self._is_season_still_airing(series_id, season_number, season_air_status):
                title = self._get_record_title(record)
                record_id = record.get('id')
                if record_id:
                    items.append((record_id, reason, title))
                continue
            seen_seasons.add(key)
            title = self._get_season_title(record, season_number)
            items.append((f'{self.SEASON_ID_PREFIX}{series_id}:{season_number}', reason, title))
        return items

    @property
    @override
    def _command_name(self) -> str:
        return 'EpisodeSearch'

    @override
    def _extra_fetch_params(self) -> dict[str, str]:
        return {'includeSeries': 'true', 'monitored': 'true'}

    def _fetch_episode_file_scores(self, series_id: int, cutoff_score: int) -> set[int]:
        """Return episode file IDs where customFormatScore is below cutoff_score."""
        episode_files = self._fetch_list(self.ENDPOINT_EPISODE_FILE, {'seriesId': series_id})
        return {
            episode_file['id']
            for episode_file in episode_files
            if episode_file.get('customFormatScore', 0) < cutoff_score
        }

    def _fetch_season_air_status(self) -> dict[tuple[int, int], str | None]:
        """Return {(series_id, season_number): nextAiring} for every season across all series."""
        series_list = self._fetch_list(self.ENDPOINT_SERIES)
        result: dict[tuple[int, int], str | None] = {}
        for series in series_list:
            series_id = series.get('id')
            for season in series.get('seasons', []):
                season_number = season.get('seasonNumber')
                if series_id is None or season_number is None:
                    continue
                next_airing = season.get('statistics', {}).get('nextAiring')
                result[(series_id, season_number)] = next_airing
        return result

    @override
    def _get_custom_format_upgrade_records(self, profile_cutoffs: dict[int, int]) -> list[dict]:
        series_list = self._fetch_list(self.ENDPOINT_SERIES)
        result = []
        for series in series_list:
            if not series.get('monitored', False):
                continue
            cutoff_score = profile_cutoffs.get(series.get('qualityProfileId', -1), 0)
            if cutoff_score > 0:
                low_score_file_ids = self._fetch_episode_file_scores(series['id'], cutoff_score)
                if low_score_file_ids:
                    episodes = self._fetch_list(self.ENDPOINT_EPISODE, {'seriesId': series['id'], 'hasFile': 'true'})
                    for episode in episodes:
                        if not episode.get('monitored', False):
                            continue
                        if episode.get('episodeFileId', -1) in low_score_file_ids:
                            episode['series'] = series
                            result.append(episode)
        return result

    @override
    def _get_record_tags(self, record: dict) -> list[int]:
        return record.get('series', {}).get('tags', [])

    @override
    def _get_record_title(self, record: dict) -> str:
        series_title = record.get('series', {}).get('title', 'Unknown Series')
        season = record.get('seasonNumber', 0)
        episode = record.get('episodeNumber', 0)
        episode_title = record.get('title', 'Unknown Episode')
        return f'{series_title} - S{season:02d}E{episode:02d} - {episode_title}'

    @override
    def _get_release_date(self, record: dict) -> str:
        return record.get('airDateUtc') or ''

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

    def _is_season_still_airing(
        self,
        series_id: int,
        season_number: int,
        season_air_status: dict[tuple[int, int], str | None],
    ) -> bool:
        """Return True if the season has upcoming episodes scheduled; False otherwise (fail open)."""
        next_airing = season_air_status.get((series_id, season_number))
        return bool(next_airing and not self._is_date_past(next_airing))

    @override
    def _trigger_single(self, item_id: int | str, reason: str, title: str, index: int, total: int) -> None:
        if not (isinstance(item_id, str) and item_id.startswith(self.SEASON_ID_PREFIX)):
            super()._trigger_single(item_id, reason, title, index, total)
            return
        _, series_id_str, season_str = item_id.split(':')
        series_id = int(series_id_str)
        season_number = int(season_str)
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

    @override
    def get_media_to_search(self, missing_batch_size: int, upgrade_batch_size: int) -> list[MediaItem]:
        if not self.season_packs:
            return super().get_media_to_search(missing_batch_size, upgrade_batch_size)

        seen_seasons: set[tuple[int, int]] = set()
        season_air_status = self._fetch_season_air_status()
        missing_items: list[MediaItem] = []
        upgrade_items: list[MediaItem] = []

        if missing_batch_size != 0:
            missing_records = self._fetch_unlimited(self.ENDPOINT_WANTED_MISSING)
            self._sort_records_client_side(missing_records)
            missing_items = self._collect_season_pack_records(
                missing_records, missing_batch_size, 'missing', seen_seasons, True, season_air_status
            )

        if upgrade_batch_size != 0:
            upgrade_records = self._fetch_unlimited(self.ENDPOINT_WANTED_CUTOFF)
            self._sort_records_client_side(upgrade_records)
            upgrade_items = self._collect_season_pack_records(
                upgrade_records, upgrade_batch_size, 'upgrade', seen_seasons, False, season_air_status
            )

            upgrades_so_far = len(upgrade_items)
            remaining = max(0, upgrade_batch_size - upgrades_so_far) if upgrade_batch_size > 0 else upgrade_batch_size
            if remaining != 0:
                supplemental = self._get_custom_format_score_unmet_records()
                self._sort_records_client_side(supplemental)
                upgrade_items += self._collect_season_pack_records(
                    supplemental, remaining, 'upgrade', seen_seasons, False, season_air_status
                )

        merged = self._interleave_items(missing_items, upgrade_items)

        if self.search_order == 'random':
            random.shuffle(merged)

        return merged

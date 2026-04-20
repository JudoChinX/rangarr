"""Test data builders for creating clean, reusable test fixtures."""

import datetime
from typing import Any
from typing import Self
from unittest.mock import MagicMock

from rangarr.clients.arr import ArrClient
from rangarr.clients.arr import LidarrClient
from rangarr.clients.arr import RadarrClient
from rangarr.clients.arr import SonarrClient


class _RecordBuilder:
    """Base builder with fields common to all *arr record types."""

    _data: dict[str, Any]

    def added_long_ago(self) -> Self:
        """Set date added to 30 days ago."""
        now = datetime.datetime.now(datetime.UTC)
        self._data['dateAdded'] = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
        return self

    def added_recently(self) -> Self:
        """Set date added to 1 day ago."""
        now = datetime.datetime.now(datetime.UTC)
        self._data['dateAdded'] = (now - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        return self

    def build(self) -> dict[str, Any]:
        """Build and return the record dictionary."""
        return self._data.copy()

    def searched_long_ago(self) -> Self:
        """Set last search time to 30 days ago."""
        now = datetime.datetime.now(datetime.UTC)
        self._data['lastSearchTime'] = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
        return self

    def searched_recently(self) -> Self:
        """Set last search time to 1 day ago."""
        now = datetime.datetime.now(datetime.UTC)
        self._data['lastSearchTime'] = (now - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        return self

    def with_id(self, record_id: int) -> Self:
        """Set the record ID."""
        self._data['id'] = record_id
        return self

    def with_release_date(self, date_str: str) -> Self:
        """Set the release date field."""
        self._data['releaseDate'] = date_str
        return self

    def with_tags(self, tag_ids: list[int]) -> Self:
        """Set the record tag IDs."""
        self._data['tags'] = tag_ids
        return self

    def with_title(self, title: str) -> Self:
        """Set the record title."""
        self._data['title'] = title
        return self


class RadarrRecordBuilder(_RecordBuilder):
    """Builder for Radarr API response records."""

    def __init__(self) -> None:
        """Initialize builder with default Radarr record."""
        self._data: dict[str, Any] = {'id': 1, 'title': 'Test Movie', 'isAvailable': True}

    def available(self) -> Self:
        """Mark record as available."""
        self._data['isAvailable'] = True
        return self

    def unavailable(self) -> Self:
        """Mark record as unavailable."""
        self._data['isAvailable'] = False
        return self


class SonarrRecordBuilder(_RecordBuilder):
    """Builder for Sonarr API response records."""

    def __init__(self) -> None:
        """Initialize builder with default Sonarr record."""
        self._data: dict[str, Any] = {
            'id': 1,
            'title': 'Test Episode',
            'series': {'title': 'Test Series'},
            'seasonNumber': 1,
            'episodeNumber': 1,
            'airDateUtc': '2020-01-01T00:00:00Z',
        }

    def aired(self) -> Self:
        """Set air date to past (available)."""
        self._data['airDateUtc'] = '2020-01-01T00:00:00Z'
        return self

    def not_aired(self) -> Self:
        """Set air date to future (not available)."""
        self._data['airDateUtc'] = '2030-01-01T00:00:00Z'
        return self

    def with_episode(self, season: int, episode: int) -> Self:
        """Set season and episode numbers."""
        self._data['seasonNumber'] = season
        self._data['episodeNumber'] = episode
        return self

    def with_series(self, series_title: str) -> Self:
        """Set the series title."""
        self._data['series']['title'] = series_title
        return self

    def with_series_id(self, series_id: int) -> Self:
        """Set the series ID."""
        self._data['series']['id'] = series_id
        return self

    def with_tags(self, tag_ids: list[int]) -> Self:
        """Set the series tag IDs."""
        self._data['series']['tags'] = tag_ids
        return self

    def without_season_number(self) -> Self:
        """Remove seasonNumber from the record."""
        del self._data['seasonNumber']
        return self


class LidarrRecordBuilder(_RecordBuilder):
    """Builder for Lidarr API response records."""

    def __init__(self) -> None:
        """Initialize builder with default Lidarr record."""
        self._data: dict[str, Any] = {
            'id': 1,
            'title': 'Test Album',
            'artist': {'artistName': 'Test Artist'},
            'releaseDate': '2020-01-01T00:00:00Z',
        }

    def not_released(self) -> Self:
        """Set release date to future (not available)."""
        self._data['releaseDate'] = '2030-01-01T00:00:00Z'
        return self

    def released(self) -> Self:
        """Set release date to past (available)."""
        self._data['releaseDate'] = '2020-01-01T00:00:00Z'
        return self

    def with_artist(self, artist_name: str) -> Self:
        """Set the artist name."""
        self._data['artist']['artistName'] = artist_name
        return self


class ClientBuilder:
    """Builder for test client instances."""

    def __init__(self, client_class: type[ArrClient] = RadarrClient) -> None:
        """Initialize builder with default client settings."""
        self._class = client_class
        self._name = 'test'
        self._url = 'http://test'
        self._api_key = 'testkey'
        self._settings: dict[str, Any] = {}

    def build(self) -> ArrClient:
        """Build and return the client instance."""
        return self._class(name=self._name, url=self._url, api_key=self._api_key, settings=self._settings)

    def lidarr(self) -> 'ClientBuilder':
        """Set client class to LidarrClient."""
        self._class = LidarrClient
        return self

    def radarr(self) -> 'ClientBuilder':
        """Set client class to RadarrClient."""
        self._class = RadarrClient
        return self

    def sonarr(self) -> 'ClientBuilder':
        """Set client class to SonarrClient."""
        self._class = SonarrClient
        return self

    def with_exclude_tags(self, *names: str) -> 'ClientBuilder':
        """Set exclude_tags in client settings."""
        self._settings['exclude_tags'] = list(names)
        return self

    def with_include_tags(self, *names: str) -> 'ClientBuilder':
        """Set include_tags in client settings."""
        self._settings['include_tags'] = list(names)
        return self

    def with_name(self, name: str) -> 'ClientBuilder':
        """Set the client name."""
        self._name = name
        return self

    def with_settings(self, **settings: Any) -> 'ClientBuilder':
        """Set client settings."""
        self._settings = settings
        return self


def mock_fetch_unlimited_factory(missing_records: list[dict], upgrade_records: list[dict]) -> Any:
    """Create mock _fetch_unlimited function for testing."""

    def mock_fetch(endpoint: str) -> list[dict]:
        records = missing_records if 'missing' in endpoint else upgrade_records
        return records.copy()

    return mock_fetch


def mock_http_response(data: Any) -> Any:
    """Create mock HTTP response object."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = data
    return mock_resp


def mock_session_get_factory(missing_records: list[dict], upgrade_records: list[dict]) -> Any:
    """Create a session.get mock that routes records by URL and returns empty on page > 1."""

    def mock_get(url: str, *_args: Any, **kwargs: Any) -> Any:
        page = kwargs.get('params', {}).get('page', 1)
        if page > 1:
            records = []
        elif 'missing' in url:
            records = missing_records.copy()
        else:
            records = upgrade_records.copy()
        return mock_http_response({'records': records})

    return mock_get


def mock_tag_api(tags: list[dict]) -> Any:
    """Create a mock HTTP response for the tag API endpoint."""
    return mock_http_response(tags)

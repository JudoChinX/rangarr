"""Tests for client-side record sorting in _get_target_media."""

from unittest.mock import patch

import pytest

from rangarr.clients.arr import LidarrClient
from rangarr.clients.arr import RadarrClient
from rangarr.clients.arr import SonarrClient
from tests.builders import ClientBuilder
from tests.builders import RadarrRecordBuilder

_CLIENT_MAP: dict[str, type[RadarrClient] | type[SonarrClient] | type[LidarrClient]] = {
    'radarr': RadarrClient,
    'sonarr': SonarrClient,
    'lidarr': LidarrClient,
}

_get_release_date_cases = {
    'radarr_returns_release_date_field': {
        'client_class': 'radarr',
        'record': {'releaseDate': '2023-06-15'},
        'expected': '2023-06-15',
    },
    'lidarr_returns_release_date_field': {
        'client_class': 'lidarr',
        'record': {'releaseDate': '2023-06-15T00:00:00Z'},
        'expected': '2023-06-15T00:00:00Z',
    },
    'sonarr_returns_air_date_utc_field': {
        'client_class': 'sonarr',
        'record': {'airDateUtc': '2023-06-15T00:00:00Z'},
        'expected': '2023-06-15T00:00:00Z',
    },
    'returns_empty_string_when_field_absent': {
        'client_class': 'radarr',
        'record': {},
        'expected': '',
    },
}


@pytest.mark.parametrize(
    'client_class, record, expected',
    [(case['client_class'], case['record'], case['expected']) for case in _get_release_date_cases.values()],
    ids=list(_get_release_date_cases.keys()),
)
def test_get_release_date(client_class: str, record: dict, expected: str) -> None:
    """Test that _get_release_date returns the correct field value per Arr type."""
    client = _CLIENT_MAP[client_class](name='test', url='https://test', api_key='testkey', settings={})
    assert client._get_release_date(record) == expected  # pylint: disable=protected-access


_get_target_media_sort_cases = {
    'last_searched_ascending_sorts_oldest_first': {
        'search_order': 'last_searched_ascending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('A Movie').searched_long_ago().build(),
            RadarrRecordBuilder().with_id(2).with_title('B Movie').searched_recently().build(),
            RadarrRecordBuilder().with_id(3).with_title('C Movie').build(),
        ],
        'expected_ids': [3, 1, 2],
    },
    'last_searched_descending_sorts_newest_first': {
        'search_order': 'last_searched_descending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('A Movie').searched_long_ago().build(),
            RadarrRecordBuilder().with_id(2).with_title('B Movie').searched_recently().build(),
            RadarrRecordBuilder().with_id(3).with_title('C Movie').build(),
        ],
        'expected_ids': [2, 1, 3],
    },
    'last_added_ascending_sorts_oldest_first': {
        'search_order': 'last_added_ascending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('A Movie').added_long_ago().build(),
            RadarrRecordBuilder().with_id(2).with_title('B Movie').added_recently().build(),
            RadarrRecordBuilder().with_id(3).with_title('C Movie').build(),
        ],
        'expected_ids': [3, 1, 2],
    },
    'last_added_descending_sorts_newest_first': {
        'search_order': 'last_added_descending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('A Movie').added_long_ago().build(),
            RadarrRecordBuilder().with_id(2).with_title('B Movie').added_recently().build(),
            RadarrRecordBuilder().with_id(3).with_title('C Movie').build(),
        ],
        'expected_ids': [2, 1, 3],
    },
    'alphabetical_ascending_sorts_by_title': {
        'search_order': 'alphabetical_ascending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('Zebra Movie').available().build(),
            RadarrRecordBuilder().with_id(2).with_title('Alpha Movie').available().build(),
            RadarrRecordBuilder().with_id(3).with_title('Middle Movie').available().build(),
        ],
        'expected_ids': [2, 3, 1],
    },
    'alphabetical_descending_sorts_by_title_reverse': {
        'search_order': 'alphabetical_descending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('Zebra Movie').available().build(),
            RadarrRecordBuilder().with_id(2).with_title('Alpha Movie').available().build(),
            RadarrRecordBuilder().with_id(3).with_title('Middle Movie').available().build(),
        ],
        'expected_ids': [1, 3, 2],
    },
    'release_date_ascending_sorts_oldest_first': {
        'search_order': 'release_date_ascending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('A Movie').available().with_release_date('2023-06-01').build(),
            RadarrRecordBuilder().with_id(2).with_title('B Movie').available().with_release_date('2021-01-01').build(),
            RadarrRecordBuilder().with_id(3).with_title('C Movie').available().build(),
        ],
        'expected_ids': [3, 2, 1],
    },
    'release_date_descending_sorts_newest_first': {
        'search_order': 'release_date_descending',
        'records': [
            RadarrRecordBuilder().with_id(1).with_title('A Movie').available().with_release_date('2023-06-01').build(),
            RadarrRecordBuilder().with_id(2).with_title('B Movie').available().with_release_date('2021-01-01').build(),
            RadarrRecordBuilder().with_id(3).with_title('C Movie').available().build(),
        ],
        'expected_ids': [1, 2, 3],
    },
}


@pytest.mark.parametrize(
    'search_order, records, expected_ids',
    [(case['search_order'], case['records'], case['expected_ids']) for case in _get_target_media_sort_cases.values()],
    ids=list(_get_target_media_sort_cases.keys()),
)
def test_get_target_media_client_side_sort(
    search_order: str,
    records: list,
    expected_ids: list,
) -> None:
    """Test that all search orders sort records client-side, independent of API sort."""
    client = (
        ClientBuilder()
        .radarr()
        .with_settings(
            search_order=search_order,
            retry_interval_days=0,
        )
        .build()
    )

    with patch.object(client, '_fetch_unlimited', return_value=records):
        result = client._get_target_media(  # pylint: disable=protected-access
            endpoint='movie/wanted/missing',
            target_batch_size=len(records),
            reason='missing',
            seen=set(),
        )

    assert [item[0] for item in result] == expected_ids

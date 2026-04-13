"""Tests for arr.py client implementations and retry logic."""

import datetime
import logging
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from rangarr.clients.arr import LidarrClient
from rangarr.clients.arr import RadarrClient
from rangarr.clients.arr import SonarrClient
from tests.builders import ClientBuilder
from tests.builders import LidarrRecordBuilder
from tests.builders import RadarrRecordBuilder
from tests.builders import SonarrRecordBuilder
from tests.builders import mock_fetch_wanted_factory
from tests.builders import mock_http_response
from tests.builders import mock_session_get_factory

_now = datetime.datetime.now(datetime.UTC)
_RECENT = (_now - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
_OLD = (_now - datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')

_client_map: dict[str, type[RadarrClient] | type[SonarrClient] | type[LidarrClient]] = {
    'radarr': RadarrClient,
    'sonarr': SonarrClient,
    'lidarr': LidarrClient,
}


_cursor_cases = {
    'advances_missing_cursor_on_full_page': {
        'missing_batch_size': 3,
        'upgrade_batch_size': 3,
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'expected_missing_cursor': 2,
        'expected_upgrade_cursor': 1,
        'search_order': 'alphabetical_ascending',
    },
    'resets_missing_cursor_at_end_of_backlog': {
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 3)],
        'upgrade_records': [],
        'expected_missing_cursor': 1,
        'expected_upgrade_cursor': 1,
        'search_order': 'alphabetical_descending',
    },
    'advances_upgrade_cursor_on_full_page': {
        'missing_batch_size': 3,
        'upgrade_batch_size': 3,
        'missing_records': [],
        'upgrade_records': [{'id': num, 'title': f'Upgrade {num}', 'isAvailable': True} for num in range(1, 4)],
        'expected_missing_cursor': 1,
        'expected_upgrade_cursor': 2,
        'search_order': 'alphabetical_ascending',
    },
}


@pytest.mark.parametrize(
    'missing_batch_size, upgrade_batch_size, missing_records, upgrade_records, expected_missing_cursor, expected_upgrade_cursor, search_order',
    [
        (
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case['missing_records'],
            case['upgrade_records'],
            case['expected_missing_cursor'],
            case['expected_upgrade_cursor'],
            case['search_order'],
        )
        for case in _cursor_cases.values()
    ],
    ids=list(_cursor_cases.keys()),
)
def test_arr_client_cursor_management(
    missing_batch_size: Any,
    upgrade_batch_size: Any,
    missing_records: Any,
    upgrade_records: Any,
    expected_missing_cursor: Any,
    expected_upgrade_cursor: Any,
    search_order: Any,
) -> None:
    """Test cursor advancement and reset logic in get_media_to_search simulating HTTP requests."""
    client = RadarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'retry_interval_days': 0, 'search_order': search_order},
    )

    client.session.get = MagicMock(side_effect=mock_session_get_factory(missing_records, upgrade_records))

    client.get_media_to_search(
        missing_batch_size=missing_batch_size,
        upgrade_batch_size=upgrade_batch_size,
    )

    assert client.missing_cursor == expected_missing_cursor
    assert client.upgrade_cursor == expected_upgrade_cursor


@pytest.mark.parametrize('client_class', ['radarr', 'sonarr', 'lidarr'])
def test_arr_client_dry_run(caplog: pytest.LogCaptureFixture, client_class: str) -> None:
    """Test that dry_run mode prevents POST requests and logs instead."""
    client = _client_map[client_class](
        name='TestClient',
        url='http://test',
        api_key='testkey',
        settings={'dry_run': True, 'stagger_interval_seconds': 0},
    )
    client.session.post = MagicMock()

    with caplog.at_level(logging.INFO):
        client.trigger_search([(123, 'missing', 'Dry Run Item')])

    client.session.post.assert_not_called()
    assert 'Would search (missing): Dry Run' in caplog.text
    assert '[DRY RUN]' in caplog.text


_fetch_wanted_cases = {
    'batch_mode_returns_records_from_api': {
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'session_responses': [
            {'records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)]},
            {'records': []},
        ],
        'raises_exception': False,
        'expected_result_count': 3,
    },
    'unlimited_mode_returns_all_records': {
        'missing_batch_size': -1,
        'upgrade_batch_size': 5,
        'session_responses': [
            {'records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 6)]},
            {'records': []},
        ],
        'raises_exception': False,
        'expected_result_count': 5,
    },
    'handles_request_exception_and_returns_empty': {
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'session_responses': None,
        'raises_exception': True,
        'expected_result_count': 0,
    },
    'unlimited_mode_fetches_multiple_pages': {
        'missing_batch_size': -1,
        'upgrade_batch_size': 5,
        'session_responses': [
            {'records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1000)]},
            {'records': [{'id': 1000, 'title': 'Missing 1000', 'isAvailable': True}]},
            {'records': []},
        ],
        'raises_exception': False,
        'expected_result_count': 1001,
    },
    'unlimited_mode_handles_exception_in_loop': {
        'missing_batch_size': -1,
        'upgrade_batch_size': 5,
        'session_responses': None,
        'raises_exception': 'unlimited',
        'expected_result_count': 0,
    },
}


@pytest.mark.parametrize(
    'missing_batch_size, upgrade_batch_size, session_responses, raises_exception, expected_result_count',
    [
        (
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case['session_responses'],
            case['raises_exception'],
            case['expected_result_count'],
        )
        for case in _fetch_wanted_cases.values()
    ],
    ids=list(_fetch_wanted_cases.keys()),
)
def test_arr_client_fetch_wanted(
    missing_batch_size: Any,
    upgrade_batch_size: Any,
    session_responses: Any,
    raises_exception: Any,
    expected_result_count: Any,
) -> None:
    """Test _fetch_wanted via get_media_to_search with mocked HTTP session."""
    client = RadarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'retry_interval_days': 0},
    )

    if raises_exception is True:
        # Batch mode exception: all calls raise.
        client.session.get = MagicMock(side_effect=requests.RequestException('Network error'))
    elif raises_exception == 'unlimited':
        # Unlimited mode exception: first call (missing unlimited) raises, second (upgrade batch) returns empty.
        client.session.get = MagicMock(
            side_effect=[
                requests.RequestException('Network error'),
                mock_http_response({'records': []}),
            ]
        )
    else:

        def mock_get(*_args: Any, **_kwargs: Any) -> Any:
            try:
                data = next(resp_iter)
            except StopIteration:
                data = {'records': []}
            return mock_http_response(data)

        resp_iter = iter(session_responses or [])
        client.session.get = MagicMock(side_effect=mock_get)

    results = client.get_media_to_search(
        missing_batch_size=missing_batch_size,
        upgrade_batch_size=upgrade_batch_size,
    )
    assert len(results) == expected_result_count


_processing_pipeline_cases = {
    'radarr_filters_unavailable_missing_item': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            RadarrRecordBuilder().with_id(1).with_title('Available Movie').available().build(),
            RadarrRecordBuilder().with_id(2).with_title('Unavailable Movie').unavailable().build(),
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1],
        'expected_title': None,
    },
    'upgrade_items_skip_availability_check': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [],
        'upgrade_records': [
            RadarrRecordBuilder().with_id(5).with_title('Unavailable But Upgradeable').unavailable().build(),
        ],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [5],
        'expected_title': None,
    },
    'filters_item_within_retry_window': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 7},
        'missing_records': [
            RadarrRecordBuilder().with_id(1).with_title('Recent').available().searched_recently().build(),
            RadarrRecordBuilder().with_id(2).with_title('Old').available().searched_long_ago().build(),
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [2],
        'expected_title': None,
    },
    'passes_item_with_retry_interval_disabled': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            {
                'id': 1,
                'title': 'Movie A',
                'isAvailable': True,
                'lastSearchTime': '2026-03-16T00:00:00Z',
            },
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1],
        'expected_title': None,
    },
    'deduplicates_same_id_across_missing_and_upgrade': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            {'id': 1, 'title': 'Shared Movie', 'isAvailable': True},
        ],
        'upgrade_records': [
            {'id': 1, 'title': 'Shared Movie', 'isAvailable': True},
            {'id': 2, 'title': 'Unique Upgrade', 'isAvailable': True},
        ],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1, 2],
        'expected_title': None,
    },
    'interleaves_missing_and_upgrade_proportionally': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [{'id': num + 10, 'title': f'Upgrade {num}', 'isAvailable': True} for num in range(1, 4)],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        # Proportional interleave: 3 missing + 3 upgrade, 50/50 ratio.
        # → missing[0], upgrade[0], missing[1], upgrade[1], missing[2], upgrade[2].
        'expected_ids': [1, 11, 2, 12, 3, 13],
        'expected_title': None,
    },
    'sonarr_filters_not_yet_aired_episode': {
        'client_class': 'sonarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_title('Past Episode')
            .with_series('Series A')
            .with_episode(1, 1)
            .aired()
            .build(),
            SonarrRecordBuilder()
            .with_id(2)
            .with_title('Future Episode')
            .with_series('Series A')
            .with_episode(1, 2)
            .not_aired()
            .build(),
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1],
        'expected_title': None,
    },
    'upgrade_item_within_retry_window_is_filtered': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 7},
        'missing_records': [],
        'upgrade_records': [
            RadarrRecordBuilder().with_id(10).with_title('Recent Upgrade').available().searched_recently().build(),
            RadarrRecordBuilder().with_id(11).with_title('Old Upgrade').available().searched_long_ago().build(),
        ],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [11],
        'expected_title': None,
    },
    'sonarr_formats_title_as_series_season_episode': {
        'client_class': 'sonarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_title('Pilot')
            .with_series('Test Series')
            .with_episode(1, 5)
            .aired()
            .build(),
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1],
        'expected_title': 'Test Series - S01E05 - Pilot',
    },
    'lidarr_filters_unreleased_album': {
        'client_class': 'lidarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            LidarrRecordBuilder().with_id(1).with_title('Released Album').with_artist('Test Artist').released().build(),
            LidarrRecordBuilder()
            .with_id(2)
            .with_title('Future Album')
            .with_artist('Test Artist')
            .not_released()
            .build(),
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1],
        'expected_title': None,
    },
    'lidarr_formats_title_as_artist_album': {
        'client_class': 'lidarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            LidarrRecordBuilder()
            .with_id(1)
            .with_title('Dark Side of the Moon')
            .with_artist('Pink Floyd')
            .released()
            .build(),
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1],
        'expected_title': 'Pink Floyd - Dark Side of the Moon',
    },
    'lidarr_handles_missing_release_date': {
        'client_class': 'lidarr',
        'settings': {'retry_interval_days': 0},
        'missing_records': [
            {
                'id': 1,
                'title': 'Unknown Release',
                'artist': {'artistName': 'Unknown Artist'},
            },
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [],
        'expected_title': None,
    },
}


@pytest.mark.parametrize(
    'client_class, settings, missing_records, upgrade_records, missing_batch_size, upgrade_batch_size, expected_ids, expected_title',
    [
        (
            case['client_class'],
            case['settings'],
            case['missing_records'],
            case['upgrade_records'],
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case['expected_ids'],
            case.get('expected_title'),
        )
        for case in _processing_pipeline_cases.values()
    ],
    ids=list(_processing_pipeline_cases.keys()),
)
def test_arr_client_processing_pipeline(
    client_class: Any,
    settings: Any,
    missing_records: Any,
    upgrade_records: Any,
    missing_batch_size: Any,
    upgrade_batch_size: Any,
    expected_ids: Any,
    expected_title: Any,
) -> None:
    """Test private processing pipeline via get_media_to_search.

    Exercises: _process_records, _is_within_retry_window, _is_available,
    _get_record_title, _interleave_items.
    """
    client = _client_map[client_class](name='test', url='http://test', api_key='testkey', settings=settings)
    mock_fetch = mock_fetch_wanted_factory(missing_records, upgrade_records)

    with patch.object(client, '_fetch_wanted', side_effect=mock_fetch):
        results = client.get_media_to_search(
            missing_batch_size=missing_batch_size,
            upgrade_batch_size=upgrade_batch_size,
        )

    result_ids = [item_id for item_id, reason, title in results]
    assert result_ids == expected_ids

    if expected_title is not None:
        result_titles = [title for item_id, reason, title in results]
        assert expected_title in result_titles


_search_order_cases = {
    'alphabetical_ascending_sends_correct_params': {
        'settings': {'search_order': 'alphabetical_ascending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'title',
        'expected_sort_direction': 'ascending',
    },
    'alphabetical_descending_sends_correct_params': {
        'settings': {'search_order': 'alphabetical_descending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'title',
        'expected_sort_direction': 'descending',
    },
    'last_searched_ascending_sends_correct_params': {
        'settings': {'search_order': 'last_searched_ascending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'lastSearchTime',
        'expected_sort_direction': 'ascending',
    },
    'last_searched_descending_sends_correct_params': {
        'settings': {'search_order': 'last_searched_descending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'lastSearchTime',
        'expected_sort_direction': 'descending',
    },
    'last_added_ascending_sends_correct_params': {
        'settings': {'search_order': 'last_added_ascending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'dateAdded',
        'expected_sort_direction': 'ascending',
    },
    'last_added_descending_sends_correct_params': {
        'settings': {'search_order': 'last_added_descending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'dateAdded',
        'expected_sort_direction': 'descending',
    },
    'release_date_ascending_sends_correct_params': {
        'settings': {'search_order': 'release_date_ascending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'releaseDate',
        'expected_sort_direction': 'ascending',
    },
    'release_date_descending_sends_correct_params': {
        'settings': {'search_order': 'release_date_descending', 'retry_interval_days': 0},
        'missing_batch_size': 5,
        'expected_sort_key': 'releaseDate',
        'expected_sort_direction': 'descending',
    },
}


@pytest.mark.parametrize(
    'settings, missing_batch_size, expected_sort_key, expected_sort_direction',
    [
        (
            case['settings'],
            case['missing_batch_size'],
            case['expected_sort_key'],
            case['expected_sort_direction'],
        )
        for case in _search_order_cases.values()
    ],
    ids=list(_search_order_cases.keys()),
)
def test_arr_client_search_order_parameters(
    settings: Any,
    missing_batch_size: Any,
    expected_sort_key: Any,
    expected_sort_direction: Any,
) -> None:
    """Test that search order settings send correct sort parameters to API."""
    client = RadarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings=settings,
    )

    def mock_get(_url: str, *_args: Any, **kwargs: Any) -> Any:
        params = kwargs.get('params', {})
        assert params.get('sortKey') == expected_sort_key
        assert params.get('sortDirection') == expected_sort_direction
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {'records': []}
        return mock_resp

    client.session.get = MagicMock(side_effect=mock_get)
    client.get_media_to_search(missing_batch_size=missing_batch_size, upgrade_batch_size=0)
    client.session.get.assert_called()


_test_cases = {
    'get_media_random_order_slices_batches': {
        'settings': {'search_order': 'random', 'retry_interval_days': 7},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 101)],
        'upgrade_records': [{'id': num, 'title': f'Upgrade {num}', 'isAvailable': True} for num in range(101, 201)],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 10,
    },
    'get_media_last_searched_ascending_unlimited_fetch': {
        'settings': {'search_order': 'last_searched_ascending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'get_media_last_searched_descending_unlimited_fetch': {
        'settings': {'search_order': 'last_searched_descending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'get_media_last_added_ascending_unlimited_fetch': {
        'settings': {'search_order': 'last_added_ascending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'get_media_last_added_descending_unlimited_fetch': {
        'settings': {'search_order': 'last_added_descending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'trigger_search_dispatches_all_items': {
        'settings': {'stagger_interval_seconds': 0},
        'items': [(1, 'missing', 'Movie A'), (2, 'upgrade', 'Movie B')],
        'expected_post_count': 2,
    },
    'trigger_search_no_items': {
        'settings': {'stagger_interval_seconds': 5},
        'items': [],
        'expected_post_count': 0,
    },
    'trigger_search_handles_request_exception_and_continues': {
        'settings': {'stagger_interval_seconds': 0},
        'items': [(1, 'missing', 'Error Movie'), (2, 'upgrade', 'Success Movie')],
        'expected_post_count': 2,
        'raises_exception_for_id': 1,
    },
}


@pytest.mark.parametrize(
    'settings, missing_records, upgrade_records, missing_batch_size, upgrade_batch_size, '
    'expected_result_len, items, expected_post_count, raises_exception_for_id',
    [
        (
            case.get('settings'),
            case.get('missing_records'),
            case.get('upgrade_records'),
            case.get('missing_batch_size'),
            case.get('upgrade_batch_size'),
            case.get('expected_result_len'),
            case.get('items'),
            case.get('expected_post_count'),
            case.get('raises_exception_for_id'),
        )
        for case in _test_cases.values()
    ],
    ids=list(_test_cases.keys()),
)
def test_arr_client_public_api(
    settings: Any,
    missing_records: Any,
    upgrade_records: Any,
    missing_batch_size: Any,
    upgrade_batch_size: Any,
    expected_result_len: Any,
    items: Any,
    expected_post_count: Any,
    raises_exception_for_id: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test ArrClient public API: get_media_to_search and trigger_search."""
    client = RadarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings=settings,
    )

    if missing_records is not None:
        client.session.get = MagicMock(side_effect=mock_session_get_factory(missing_records, upgrade_records))

        results = client.get_media_to_search(
            missing_batch_size=missing_batch_size,
            upgrade_batch_size=upgrade_batch_size,
        )
        if expected_result_len is not None:
            assert len(results) == expected_result_len

    if items is not None:

        def mock_post(_url: str, *_args: Any, **kwargs: Any) -> Any:
            json_payload = kwargs.get('json', {})
            if raises_exception_for_id and json_payload.get('movieIds') == [raises_exception_for_id]:
                raise requests.RequestException('Network error')
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        client.session.post = MagicMock(side_effect=mock_post)
        with patch('time.sleep'):
            client.trigger_search(items)
            assert client.session.post.call_count == expected_post_count
            if raises_exception_for_id:
                assert 'Failed to trigger MoviesSearch' in caplog.text


@pytest.mark.parametrize(
    'input_url,expected_url',
    [
        ('http://test:7878/', 'http://test:7878'),
        ('http://test:7878///', 'http://test:7878'),
    ],
)
def test_arr_client_strips_trailing_slash(input_url: str, expected_url: str) -> None:
    """Test that URL trailing slashes are stripped during initialization."""
    client = RadarrClient(
        name='TestRadarr',
        url=input_url,
        api_key='testkey',
        settings={},
    )
    assert client.url == expected_url


_https_warning_cases = {
    'warns_on_http_url': {
        'url': 'http://test:7878',
        'expect_warning': True,
    },
    'warns_on_http_url_uppercase_scheme': {
        'url': 'HTTP://test:7878',
        'expect_warning': True,
    },
    'no_warning_on_https_url': {
        'url': 'https://test:7878',
        'expect_warning': False,
    },
    'no_warning_on_https_url_uppercase_scheme': {
        'url': 'HTTPS://test:7878',
        'expect_warning': False,
    },
}


@pytest.mark.parametrize(
    'url, expect_warning',
    [(case['url'], case['expect_warning']) for case in _https_warning_cases.values()],
    ids=list(_https_warning_cases.keys()),
)
def test_arr_client_warns_on_non_https_url(
    url: str,
    expect_warning: bool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a WARNING is emitted when the URL does not use HTTPS."""
    with caplog.at_level(logging.WARNING):
        RadarrClient(name='TestRadarr', url=url, api_key='testkey', settings={})

    warning_emitted = 'API keys will be transmitted in plaintext' in caplog.text
    assert warning_emitted == expect_warning


def test_sonarr_client_reads_season_packs_setting() -> None:
    """Test that SonarrClient reads season_packs from settings."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={'season_packs': True})
    assert client.season_packs is True


def test_sonarr_client_season_packs_defaults_to_false() -> None:
    """Test that SonarrClient defaults season_packs to False when absent from settings."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={})
    assert client.season_packs is False


_trigger_single_cases = {
    'radarr_posts_movies_search_payload': {
        'client_class': 'radarr',
        'item': (42, 'missing', 'Test Movie'),
        'expected_payload': {'name': 'MoviesSearch', 'movieIds': [42]},
        'raises_exception': False,
    },
    'sonarr_posts_episode_search_payload': {
        'client_class': 'sonarr',
        'item': (99, 'upgrade', 'Test Episode'),
        'expected_payload': {'name': 'EpisodeSearch', 'episodeIds': [99]},
        'raises_exception': False,
    },
    'lidarr_posts_album_search_payload': {
        'client_class': 'lidarr',
        'item': (77, 'missing', 'Test Album'),
        'expected_payload': {'name': 'AlbumSearch', 'albumIds': [77]},
        'raises_exception': False,
    },
    'handles_post_exception_without_propagating': {
        'client_class': 'radarr',
        'item': (1, 'missing', 'Movie A'),
        'expected_payload': None,
        'raises_exception': True,
    },
    'sonarr_handles_post_exception_without_propagating': {
        'client_class': 'sonarr',
        'item': (1, 'missing', 'Episode A'),
        'expected_payload': None,
        'raises_exception': True,
    },
    'lidarr_handles_post_exception_without_propagating': {
        'client_class': 'lidarr',
        'item': (1, 'missing', 'Album A'),
        'expected_payload': None,
        'raises_exception': True,
    },
}


@pytest.mark.parametrize(
    'client_class, item, expected_payload, raises_exception',
    [
        (
            case['client_class'],
            case['item'],
            case['expected_payload'],
            case['raises_exception'],
        )
        for case in _trigger_single_cases.values()
    ],
    ids=list(_trigger_single_cases.keys()),
)
def test_arr_client_trigger_single(client_class: Any, item: Any, expected_payload: Any, raises_exception: Any) -> None:
    """Test _trigger_single implementations via trigger_search with mocked HTTP session."""
    client = _client_map[client_class](
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'stagger_interval_seconds': 0},
    )

    if raises_exception:
        client.session.post = MagicMock(side_effect=requests.RequestException('Server error'))
    else:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        client.session.post = MagicMock(return_value=mock_resp)

    client.trigger_search([item])  # Must not raise even on exception.

    client.session.post.assert_called_once()
    if expected_payload is not None:
        expected_url = 'http://test/api/v1/command' if client_class == 'lidarr' else 'http://test/api/v3/command'
        client.session.post.assert_called_once_with(
            expected_url,
            json=expected_payload,
            timeout=15,
        )


_get_target_media_cases = {
    'disabled': {
        'search_order': 'last_searched_ascending',
        'target_batch_size': 0,
        'fetch_wanted_records': [],
        'expected_result_len': 0,
        'expected_fetch_called': False,
    },
    'unlimited': {
        'search_order': 'alphabetical_ascending',
        'target_batch_size': -1,
        'fetch_wanted_records': [
            RadarrRecordBuilder().with_id(1).with_title('Movie One').available().build(),
            RadarrRecordBuilder().with_id(2).with_title('Movie Two').available().build(),
        ],
        'expected_result_len': 2,
        'expected_fetch_called': True,
    },
}


@pytest.mark.parametrize(
    'search_order, target_batch_size, fetch_wanted_records, expected_result_len, expected_fetch_called',
    [
        (
            case['search_order'],
            case['target_batch_size'],
            case['fetch_wanted_records'],
            case['expected_result_len'],
            case['expected_fetch_called'],
        )
        for case in _get_target_media_cases.values()
    ],
    ids=list(_get_target_media_cases.keys()),
)
def test_get_target_media_modes(
    search_order: str,
    target_batch_size: int,
    fetch_wanted_records: list,
    expected_result_len: int,
    expected_fetch_called: bool,
) -> None:
    """Test _get_target_media disabled and unlimited modes."""
    client = ClientBuilder().radarr().with_settings(search_order=search_order).build()

    with patch.object(client, '_fetch_wanted', return_value=fetch_wanted_records) as mock_fetch:
        result = client._get_target_media(  # pylint: disable=protected-access
            endpoint='movie/wanted/missing',
            target_batch_size=target_batch_size,
            cursor_attr='missing_cursor',
            buffer_attr='missing_buffer',
            reason='missing',
            seen=set(),
        )

    assert len(result) == expected_result_len
    if expected_fetch_called:
        mock_fetch.assert_called_once()
    else:
        mock_fetch.assert_not_called()


_include_series_param_cases = {
    'sonarr_sends_include_series': {
        'client_class': 'sonarr',
        'expect_include_series': True,
    },
    'radarr_omits_include_series': {
        'client_class': 'radarr',
        'expect_include_series': False,
    },
    'lidarr_omits_include_series': {
        'client_class': 'lidarr',
        'expect_include_series': False,
    },
}


@pytest.mark.parametrize(
    'client_class, expect_include_series',
    [(case['client_class'], case['expect_include_series']) for case in _include_series_param_cases.values()],
    ids=list(_include_series_param_cases.keys()),
)
def test_fetch_include_series_param(client_class: str, expect_include_series: bool) -> None:
    """Test that only SonarrClient sends includeSeries in fetch params."""
    client = _client_map[client_class](
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'retry_interval_days': 0, 'search_order': 'alphabetical_ascending'},
    )

    def mock_get(_url: str, *_args: Any, **kwargs: Any) -> Any:
        params = kwargs.get('params', {})
        if expect_include_series:
            assert params.get('includeSeries') == 'true'
        else:
            assert 'includeSeries' not in params
        return mock_http_response({'records': []})

    client.session.get = MagicMock(side_effect=mock_get)
    client.get_media_to_search(missing_batch_size=1, upgrade_batch_size=0)
    client.session.get.assert_called()

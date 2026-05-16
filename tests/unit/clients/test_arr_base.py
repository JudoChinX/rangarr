"""Tests shared across all ArrClient implementations (Radarr, Sonarr, Lidarr)."""

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
from tests.builders import QualityProfileBuilder
from tests.builders import RadarrRecordBuilder
from tests.builders import SonarrRecordBuilder
from tests.builders import mock_fetch_unlimited_factory
from tests.builders import mock_http_response
from tests.builders import mock_session_get_factory
from tests.conftest import FIXED_NOW

_CLIENT_MAP: dict[str, type[RadarrClient] | type[SonarrClient] | type[LidarrClient]] = {
    'radarr': RadarrClient,
    'sonarr': SonarrClient,
    'lidarr': LidarrClient,
}


_arr_client_dry_run_cases = {
    'lidarr': {'client_class': 'lidarr'},
    'radarr': {'client_class': 'radarr'},
    'sonarr': {'client_class': 'sonarr'},
}


@pytest.mark.parametrize(
    'client_class',
    [case['client_class'] for case in _arr_client_dry_run_cases.values()],
    ids=list(_arr_client_dry_run_cases.keys()),
)
def test_arr_client_dry_run(caplog: pytest.LogCaptureFixture, client_class: str) -> None:
    """Test that dry_run mode prevents POST requests and logs instead."""
    client = _CLIENT_MAP[client_class](
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


_arr_client_get_media_cases = {
    'get_media_last_added_ascending': {
        'settings': {'search_order': 'last_added_ascending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'get_media_last_added_descending': {
        'settings': {'search_order': 'last_added_descending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'get_media_last_searched_ascending': {
        'settings': {'search_order': 'last_searched_ascending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'get_media_last_searched_descending': {
        'settings': {'search_order': 'last_searched_descending', 'retry_interval_days': 0},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 4)],
        'upgrade_records': [],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 3,
    },
    'get_media_random_order_slices_batches': {
        'settings': {'search_order': 'random', 'retry_interval_days': 7},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 101)],
        'upgrade_records': [{'id': num, 'title': f'Upgrade {num}', 'isAvailable': True} for num in range(101, 201)],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 10,
    },
}


@pytest.mark.parametrize(
    'settings, missing_records, upgrade_records, missing_batch_size, upgrade_batch_size, expected_result_len',
    [
        (
            case['settings'],
            case['missing_records'],
            case['upgrade_records'],
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case['expected_result_len'],
        )
        for case in _arr_client_get_media_cases.values()
    ],
    ids=list(_arr_client_get_media_cases.keys()),
)
def test_arr_client_get_media(
    settings: Any,
    missing_records: Any,
    upgrade_records: Any,
    missing_batch_size: Any,
    upgrade_batch_size: Any,
    expected_result_len: Any,
) -> None:
    """Test ArrClient.get_media_to_search returns the expected number of items."""
    client = RadarrClient(name='test', url='http://test', api_key='testkey', settings=settings)
    client.session.get = MagicMock(side_effect=mock_session_get_factory(missing_records, upgrade_records))
    results = client.get_media_to_search(
        missing_batch_size=missing_batch_size,
        upgrade_batch_size=upgrade_batch_size,
    )
    assert len(results) == expected_result_len


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
    'missing_override_disables_retry_for_missing': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 30, 'retry_interval_days_missing': 0},
        'missing_records': [
            RadarrRecordBuilder().with_id(1).with_title('Recent Movie').available().searched_recently().build(),
        ],
        'upgrade_records': [],
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'expected_ids': [1],
        'expected_title': None,
    },
    'upgrade_override_extends_retry_for_upgrade': {
        'client_class': 'radarr',
        'settings': {'retry_interval_days': 30, 'retry_interval_days_upgrade': 60},
        'missing_records': [],
        'upgrade_records': [
            RadarrRecordBuilder().with_id(2).with_title('Old Upgrade').available().searched_long_ago().build(),
        ],
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
    client = _CLIENT_MAP[client_class](name='test', url='http://test', api_key='testkey', settings=settings)
    client.session.get = MagicMock(return_value=mock_http_response([]))
    mock_fetch = mock_fetch_unlimited_factory(missing_records, upgrade_records)

    with patch.object(client, '_fetch_unlimited', side_effect=mock_fetch):
        results = client.get_media_to_search(
            missing_batch_size=missing_batch_size,
            upgrade_batch_size=upgrade_batch_size,
        )

    result_ids = [item_id for item_id, reason, title in results]
    assert result_ids == expected_ids

    if expected_title is not None:
        result_titles = [title for item_id, reason, title in results]
        assert expected_title in result_titles


_arr_client_strips_trailing_slash_cases = {
    'multiple_trailing_slashes': {
        'input_url': 'http://test:7878///',
        'expected_url': 'http://test:7878',
    },
    'single_trailing_slash': {
        'input_url': 'http://test:7878/',
        'expected_url': 'http://test:7878',
    },
}


@pytest.mark.parametrize(
    'input_url, expected_url',
    [(case['input_url'], case['expected_url']) for case in _arr_client_strips_trailing_slash_cases.values()],
    ids=list(_arr_client_strips_trailing_slash_cases.keys()),
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


_arr_client_trigger_search_cases = {
    'trigger_search_dispatches_all_items': {
        'settings': {'stagger_interval_seconds': 0},
        'items': [(1, 'missing', 'Movie A'), (2, 'upgrade', 'Movie B')],
        'expected_post_count': 2,
        'raises_exception_for_id': None,
    },
    'trigger_search_handles_request_exception_and_continues': {
        'settings': {'stagger_interval_seconds': 0},
        'items': [(1, 'missing', 'Error Movie'), (2, 'upgrade', 'Success Movie')],
        'expected_post_count': 2,
        'raises_exception_for_id': 1,
    },
    'trigger_search_no_items': {
        'settings': {'stagger_interval_seconds': 5},
        'items': [],
        'expected_post_count': 0,
        'raises_exception_for_id': None,
    },
}


@pytest.mark.parametrize(
    'settings, items, expected_post_count, raises_exception_for_id',
    [
        (
            case['settings'],
            case['items'],
            case['expected_post_count'],
            case['raises_exception_for_id'],
        )
        for case in _arr_client_trigger_search_cases.values()
    ],
    ids=list(_arr_client_trigger_search_cases.keys()),
)
def test_arr_client_trigger_search(
    settings: Any,
    items: Any,
    expected_post_count: Any,
    raises_exception_for_id: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test ArrClient.trigger_search dispatches the correct number of POST requests."""
    client = RadarrClient(name='test', url='http://test', api_key='testkey', settings=settings)

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
    client = _CLIENT_MAP[client_class](
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


_check_connection_cases = {
    'success': {
        'raises': None,
        'expected': True,
    },
    'connection_error': {
        'raises': requests.ConnectionError('Connection refused'),
        'expected': False,
    },
    'http_error': {
        'raises': requests.HTTPError('401 Unauthorized'),
        'expected': False,
    },
    'timeout': {
        'raises': requests.Timeout('timed out'),
        'expected': False,
    },
}


@pytest.mark.parametrize(
    'raises, expected',
    [(case['raises'], case['expected']) for case in _check_connection_cases.values()],
    ids=list(_check_connection_cases.keys()),
)
def test_check_connection(raises: requests.RequestException | None, expected: bool) -> None:
    """Test check_connection returns True on success and False on any RequestException."""
    client = ClientBuilder().radarr().build()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None

    if raises is not None:
        client.session.get = MagicMock(side_effect=raises)
    else:
        client.session.get = MagicMock(return_value=mock_response)

    assert client.check_connection() == expected

    if raises is None:
        client.session.get.assert_called_once_with('http://test/api/v3/tag', timeout=15)
        mock_response.raise_for_status.assert_called_once()


def test_fetch_does_not_send_sort_params() -> None:
    """Test that API fetch calls do not include sortKey or sortDirection parameters."""
    client = ClientBuilder().radarr().with_settings(search_order='last_searched_ascending').build()
    captured: dict = {}

    def mock_get(_url: str, *_args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs.get('params', {}))
        return mock_http_response({'records': []})

    client.session.get = MagicMock(side_effect=mock_get)
    client.get_media_to_search(missing_batch_size=1, upgrade_batch_size=0)

    assert 'sortKey' not in captured
    assert 'sortDirection' not in captured


_fetch_extra_params_cases = {
    'sonarr_sends_include_series_and_monitored': {
        'client_class': 'sonarr',
        'expect_include_series': True,
    },
    'radarr_omits_include_series_sends_monitored': {
        'client_class': 'radarr',
        'expect_include_series': False,
    },
    'lidarr_omits_include_series_sends_monitored': {
        'client_class': 'lidarr',
        'expect_include_series': False,
    },
}


@pytest.mark.parametrize(
    'client_class, expect_include_series',
    [(case['client_class'], case['expect_include_series']) for case in _fetch_extra_params_cases.values()],
    ids=list(_fetch_extra_params_cases.keys()),
)
def test_fetch_extra_params(client_class: str, expect_include_series: bool) -> None:
    """Test that all clients send monitored=true and only Sonarr sends includeSeries."""
    client = _CLIENT_MAP[client_class](
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'retry_interval_days': 0, 'search_order': 'alphabetical_ascending'},
    )

    def mock_get(_url: str, *_args: Any, **kwargs: Any) -> Any:
        params = kwargs.get('params', {})
        assert params.get('monitored') == 'true'
        if expect_include_series:
            assert params.get('includeSeries') == 'true'
        else:
            assert 'includeSeries' not in params
        return mock_http_response({'records': []})

    client.session.get = MagicMock(side_effect=mock_get)
    client.get_media_to_search(missing_batch_size=1, upgrade_batch_size=0)
    client.session.get.assert_called()


def test_fetch_list_returns_empty_on_request_exception() -> None:
    """Test _fetch_list returns [] and logs an error when a RequestException is raised."""
    client = ClientBuilder().radarr().build()
    client.session.get = MagicMock(side_effect=requests.RequestException('timeout'))
    result = client._fetch_list('/api/v3/movie')
    assert result == []


_fetch_quality_profile_cutoffs_cases = {
    'returns_profiles_with_nonzero_cutoff_score': {
        'client_class': 'radarr',
        'profiles': [
            QualityProfileBuilder().with_id(1).with_cutoff_score(100).build(),
            QualityProfileBuilder().with_id(2).with_cutoff_score(0).build(),
            QualityProfileBuilder().with_id(3).with_cutoff_score(200).build(),
        ],
        'expected': {1: 100, 3: 200},
        'raises_exception': False,
    },
    'returns_empty_when_all_scores_are_zero': {
        'client_class': 'radarr',
        'profiles': [
            QualityProfileBuilder().with_id(1).with_cutoff_score(0).build(),
        ],
        'expected': {},
        'raises_exception': False,
    },
    'returns_empty_on_fetch_error': {
        'client_class': 'radarr',
        'profiles': [],
        'expected': {},
        'raises_exception': True,
    },
}


@pytest.mark.parametrize(
    'client_class, profiles, expected, raises_exception',
    [
        (
            case['client_class'],
            case['profiles'],
            case['expected'],
            case['raises_exception'],
        )
        for case in _fetch_quality_profile_cutoffs_cases.values()
    ],
    ids=list(_fetch_quality_profile_cutoffs_cases.keys()),
)
def test_fetch_quality_profile_cutoffs(
    client_class: Any,
    profiles: Any,
    expected: Any,
    raises_exception: bool,
) -> None:
    """Test _fetch_quality_profile_cutoffs returns only profiles with cutoffFormatScore > 0."""
    client = _CLIENT_MAP[client_class](name='test', url='http://test', api_key='testkey', settings={})
    if raises_exception:
        client.session.get = MagicMock(side_effect=requests.RequestException('error'))
    else:
        client.session.get = MagicMock(return_value=mock_http_response(profiles))
    result = client._fetch_quality_profile_cutoffs()
    assert result == expected


def test_fetch_unlimited_returns_empty_on_request_exception() -> None:
    """Test _fetch_unlimited returns [] and logs an error when a RequestException is raised."""
    client = ClientBuilder().radarr().build()
    client.session.get = MagicMock(side_effect=requests.RequestException('timeout'))
    result = client._fetch_unlimited('/api/v3/wanted/missing')
    assert result == []


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

    with patch.object(client, '_fetch_unlimited', return_value=fetch_wanted_records) as mock_fetch:
        result = client._get_target_media(
            endpoint='movie/wanted/missing',
            target_batch_size=target_batch_size,
            reason='missing',
            seen=set(),
        )

    assert len(result) == expected_result_len
    if expected_fetch_called:
        mock_fetch.assert_called_once()
    else:
        mock_fetch.assert_not_called()


_is_within_retry_window_override_cases = {
    'missing_override_selects_tighter_interval': {
        'settings': {'retry_interval_days': 30, 'retry_interval_days_missing': 7, 'retry_interval_days_upgrade': 14},
        'last_search_time': (FIXED_NOW - datetime.timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'reason': 'missing',
        'expected': False,
    },
    'upgrade_override_selects_broader_interval': {
        'settings': {'retry_interval_days': 30, 'retry_interval_days_missing': 7, 'retry_interval_days_upgrade': 14},
        'last_search_time': (FIXED_NOW - datetime.timedelta(days=10)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'reason': 'upgrade',
        'expected': True,
    },
    'override_none_falls_back_to_base': {
        'settings': {'retry_interval_days': 30, 'retry_interval_days_missing': None},
        'last_search_time': (FIXED_NOW - datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'reason': 'missing',
        'expected': True,
    },
}


@pytest.mark.parametrize(
    'settings, last_search_time, reason, expected',
    [
        (case['settings'], case['last_search_time'], case['reason'], case['expected'])
        for case in _is_within_retry_window_override_cases.values()
    ],
    ids=list(_is_within_retry_window_override_cases.keys()),
)
def test_is_within_retry_window_override(
    settings: dict,
    last_search_time: str,
    reason: str,
    expected: bool,
) -> None:
    """Test _is_within_retry_window selects the correct interval based on reason."""
    client = RadarrClient(name='test', url='http://test', api_key='testkey', settings=settings)
    record = {'id': 1, 'lastSearchTime': last_search_time}
    result = client._is_within_retry_window(record, reason)
    assert result == expected

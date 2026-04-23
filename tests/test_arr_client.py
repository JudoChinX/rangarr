"""Tests for arr.py client implementations and retry logic."""
# pylint: disable=too-many-lines

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
from tests.builders import RadarrMovieFileRecordBuilder
from tests.builders import RadarrMovieRecordBuilder
from tests.builders import RadarrRecordBuilder
from tests.builders import SonarrEpisodeFileRecordBuilder
from tests.builders import SonarrRecordBuilder
from tests.builders import SonarrSeriesRecordBuilder
from tests.builders import mock_fetch_list_factory
from tests.builders import mock_fetch_unlimited_factory
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


_test_cases = {
    'get_media_random_order_slices_batches': {
        'settings': {'search_order': 'random', 'retry_interval_days': 7},
        'missing_records': [{'id': num, 'title': f'Missing {num}', 'isAvailable': True} for num in range(1, 101)],
        'upgrade_records': [{'id': num, 'title': f'Upgrade {num}', 'isAvailable': True} for num in range(101, 201)],
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'expected_result_len': 10,
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
    client = _client_map[client_class](name='test', url='http://test', api_key='testkey', settings={})
    if raises_exception:
        client.session.get = MagicMock(side_effect=requests.RequestException('error'))
    else:
        client.session.get = MagicMock(return_value=mock_http_response(profiles))
    result = client._fetch_quality_profile_cutoffs()  # pylint: disable=protected-access
    assert result == expected


def test_lidarr_fetch_quality_profile_cutoffs_returns_empty() -> None:
    """Test LidarrClient._fetch_quality_profile_cutoffs always returns {} without HTTP calls."""
    client = ClientBuilder().lidarr().build()
    client.session.get = MagicMock()
    result = client._fetch_quality_profile_cutoffs()  # pylint: disable=protected-access
    assert result == {}
    client.session.get.assert_not_called()


def test_sonarr_client_reads_season_packs_setting() -> None:
    """Test that SonarrClient reads season_packs from settings."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={'season_packs': True})
    assert client.season_packs is True


def test_sonarr_client_season_packs_defaults_to_false() -> None:
    """Test that SonarrClient defaults season_packs to False when absent from settings."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={})
    assert client.season_packs is False


def test_fetch_season_air_status_builds_lookup() -> None:
    """Test _fetch_season_air_status returns {(series_id, season_number): nextAiring} for all seasons."""
    client = ClientBuilder().sonarr().build()
    series_list = [
        SonarrSeriesRecordBuilder()
        .with_id(1)
        .with_seasons([
            {'seasonNumber': 1, 'statistics': {'nextAiring': '2030-01-01T00:00:00Z'}},
            {'seasonNumber': 2, 'statistics': {'nextAiring': None}},
        ])
        .build(),
        SonarrSeriesRecordBuilder()
        .with_id(2)
        .with_seasons([
            {'seasonNumber': 1},
        ])
        .build(),
    ]
    with patch.object(client, '_fetch_list', return_value=series_list) as mock_fetch:
        result = client._fetch_season_air_status()  # pylint: disable=protected-access

    mock_fetch.assert_called_once_with(client.ENDPOINT_SERIES)
    assert result == {
        (1, 1): '2030-01-01T00:00:00Z',
        (1, 2): None,
        (2, 1): None,
    }


_is_season_still_airing_cases = {
    'returns_true_when_next_airing_is_future': {
        'season_air_status': {(1, 1): '2030-01-01T00:00:00Z'},
        'series_id': 1,
        'season_number': 1,
        'expected': True,
    },
    'returns_false_when_next_airing_is_past': {
        'season_air_status': {(1, 1): '2020-01-01T00:00:00Z'},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'returns_false_when_next_airing_is_none': {
        'season_air_status': {(1, 1): None},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'returns_false_when_key_absent': {
        'season_air_status': {},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
}


@pytest.mark.parametrize(
    'season_air_status, series_id, season_number, expected',
    [
        (case['season_air_status'], case['series_id'], case['season_number'], case['expected'])
        for case in _is_season_still_airing_cases.values()
    ],
    ids=list(_is_season_still_airing_cases.keys()),
)
def test_is_season_still_airing(season_air_status: dict, series_id: int, season_number: int, expected: bool) -> None:
    """Test _is_season_still_airing returns True only when nextAiring is a future date."""
    client = ClientBuilder().sonarr().build()
    result = client._is_season_still_airing(series_id, season_number, season_air_status)  # pylint: disable=protected-access
    assert result == expected


_season_pack_unaired_filter_cases = {
    'missing_path_skips_season_still_airing': {
        'missing_batch_size': 10,
        'upgrade_batch_size': 0,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [],
        'supplemental_records': [],
        'season_air_status': {(10, 1): '2030-01-01T00:00:00Z'},
        'expected_ids': [],
    },
    'upgrade_path_skips_season_still_airing': {
        'missing_batch_size': 0,
        'upgrade_batch_size': 10,
        'missing_records': [],
        'upgrade_records': [
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show B')
            .with_series_id(20)
            .with_episode(2, 1)
            .aired()
            .build(),
        ],
        'supplemental_records': [],
        'season_air_status': {(20, 2): '2030-01-01T00:00:00Z'},
        'expected_ids': [],
    },
    'completed_season_is_included': {
        'missing_batch_size': 10,
        'upgrade_batch_size': 0,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(3)
            .with_series('Show C')
            .with_series_id(30)
            .with_episode(3, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [],
        'supplemental_records': [],
        'season_air_status': {(30, 3): None},
        'expected_ids': [30],
    },
    'supplemental_path_skips_season_still_airing': {
        'missing_batch_size': 0,
        'upgrade_batch_size': 10,
        'missing_records': [],
        'upgrade_records': [],
        'supplemental_records': [
            SonarrRecordBuilder()
            .with_id(4)
            .with_series('Show D')
            .with_series_id(40)
            .with_episode(4, 1)
            .aired()
            .build(),
        ],
        'season_air_status': {(40, 4): '2030-01-01T00:00:00Z'},
        'expected_ids': [],
    },
}


@pytest.mark.parametrize(
    'missing_batch_size, upgrade_batch_size, missing_records, upgrade_records, supplemental_records, season_air_status, expected_ids',
    [
        (
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case['missing_records'],
            case['upgrade_records'],
            case['supplemental_records'],
            case['season_air_status'],
            case['expected_ids'],
        )
        for case in _season_pack_unaired_filter_cases.values()
    ],
    ids=list(_season_pack_unaired_filter_cases.keys()),
)
def test_season_pack_skips_unaired_seasons(
    missing_batch_size: int,
    upgrade_batch_size: int,
    missing_records: list,
    upgrade_records: list,
    supplemental_records: list,
    season_air_status: dict,
    expected_ids: list,
) -> None:
    """Test season pack collection skips seasons where nextAiring is in the future."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()

    def fake_fetch_unlimited(endpoint: str) -> list[dict]:
        if 'missing' in endpoint:
            return missing_records
        return upgrade_records

    with (
        patch.object(client, '_fetch_unlimited', side_effect=fake_fetch_unlimited),
        patch.object(client, '_fetch_season_air_status', return_value=season_air_status),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(
            missing_batch_size=missing_batch_size,
            upgrade_batch_size=upgrade_batch_size,
        )

    result_ids = [item_id for item_id, _, _ in results]
    assert result_ids == expected_ids


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

    with patch.object(client, '_fetch_unlimited', return_value=fetch_wanted_records) as mock_fetch:
        result = client._get_target_media(  # pylint: disable=protected-access
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
    client = _client_map[client_class](
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


def test_supplemental_early_exit_when_no_cutoff_profiles() -> None:
    """Test _get_custom_format_score_unmet_records returns [] without any media fetch when profiles empty."""
    client = ClientBuilder().radarr().build()
    with (
        patch.object(client, '_fetch_quality_profile_cutoffs', return_value={}),
        patch.object(client, '_fetch_list') as mock_fetch_list,
    ):
        result = client._get_custom_format_score_unmet_records()  # pylint: disable=protected-access
    assert result == []
    mock_fetch_list.assert_not_called()


def test_supplemental_upgrade_skipped_when_upgrade_batch_disabled() -> None:
    """Test supplemental pass is not invoked when upgrade_batch_size is 0."""
    client = ClientBuilder().radarr().build()
    with (
        patch.object(client, '_fetch_unlimited', return_value=[]),
        patch.object(client, '_get_custom_format_score_unmet_records') as mock_sup,
    ):
        client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=0)
    mock_sup.assert_not_called()


def test_supplemental_upgrades_added_to_get_media_to_search() -> None:
    """Test supplemental records are merged into the upgrade pool by get_media_to_search."""
    client = ClientBuilder().radarr().with_settings(retry_interval_days=0).build()
    cutoff_records = [RadarrRecordBuilder().with_id(10).with_title('Cutoff Movie').available().build()]
    supplemental_records = [
        RadarrMovieRecordBuilder()
        .with_id(20)
        .with_title('Supplemental Movie')
        .with_profile(1)
        .with_score(0)
        .available()
        .build(),
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=cutoff_records),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)
    result_ids = [item_id for item_id, _, _ in results]
    assert 10 in result_ids
    assert 20 in result_ids


def test_supplemental_upgrade_batch_size_respected() -> None:
    """Test upgrade_batch_size limits the combined /wanted/cutoff and supplemental results."""
    client = ClientBuilder().radarr().with_settings(retry_interval_days=0).build()
    cutoff_records = [
        RadarrRecordBuilder().with_id(num).with_title(f'Cutoff {num}').available().build() for num in range(1, 4)
    ]
    supplemental_records = [
        RadarrMovieRecordBuilder()
        .with_id(num + 10)
        .with_title(f'Sup {num}')
        .with_profile(1)
        .with_score(0)
        .available()
        .build()
        for num in range(1, 4)
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=cutoff_records),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=3)
    assert len(results) == 3


def test_supplemental_upgrade_deduplicates_against_cutoff_results() -> None:
    """Test an item in both /wanted/cutoff and supplemental results appears only once."""
    client = ClientBuilder().radarr().with_settings(retry_interval_days=0).build()
    cutoff_records = [RadarrRecordBuilder().with_id(1).with_title('Shared Movie').available().build()]
    supplemental_records = [
        RadarrMovieRecordBuilder()
        .with_id(1)
        .with_title('Shared Movie')
        .with_profile(1)
        .with_score(0)
        .available()
        .build(),
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=cutoff_records),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)
    result_ids = [item_id for item_id, _, _ in results]
    assert result_ids.count(1) == 1


def test_supplemental_upgrade_retry_window_filter_applied() -> None:
    """Test retry window filter is applied to supplemental records."""
    client = ClientBuilder().radarr().with_settings(retry_interval_days=7).build()
    supplemental_records = [
        RadarrMovieRecordBuilder().with_id(1).with_profile(1).with_score(0).available().searched_recently().build(),
        RadarrMovieRecordBuilder().with_id(2).with_profile(1).with_score(0).available().searched_long_ago().build(),
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=[]),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)
    result_ids = [item_id for item_id, _, _ in results]
    assert 1 not in result_ids
    assert 2 in result_ids


def test_supplemental_upgrade_tag_filter_applied() -> None:
    """Test tag filter is applied to supplemental records."""
    tag_data = [{'id': 99, 'label': 'skip'}]
    with patch.object(requests.Session, 'get', return_value=mock_http_response(tag_data)):
        client = ClientBuilder().radarr().with_exclude_tags('skip').build()
    supplemental_records = [
        RadarrMovieRecordBuilder().with_id(1).with_profile(1).with_score(0).available().with_tags([99]).build(),
        RadarrMovieRecordBuilder().with_id(2).with_profile(1).with_score(0).available().build(),
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=[]),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)
    result_ids = [item_id for item_id, _, _ in results]
    assert 1 not in result_ids
    assert 2 in result_ids


_radarr_custom_format_cases = {
    'finds_movie_below_cutoff_score': {
        'profile_cutoffs': {1: 100},
        'movies': [
            RadarrMovieRecordBuilder().with_id(1).with_profile(1).available().build(),
            RadarrMovieRecordBuilder().with_id(2).with_profile(1).with_movie_file_id(2).available().build(),
        ],
        'movie_files': [
            RadarrMovieFileRecordBuilder().with_id(1).with_score(50).build(),
            RadarrMovieFileRecordBuilder().with_id(2).with_score(150).build(),
        ],
        'expected_ids': [1],
    },
    'skips_movie_without_movie_file': {
        'profile_cutoffs': {1: 100},
        'movies': [
            RadarrMovieRecordBuilder().with_id(1).with_profile(1).without_movie_file().available().build(),
        ],
        'movie_files': [],
        'expected_ids': [],
    },
    'skips_movie_on_untracked_profile': {
        'profile_cutoffs': {1: 100},
        'movies': [
            RadarrMovieRecordBuilder().with_id(1).with_profile(2).available().build(),
        ],
        'movie_files': [],
        'expected_ids': [],
    },
    'skips_movie_at_or_above_cutoff_score': {
        'profile_cutoffs': {1: 100},
        'movies': [
            RadarrMovieRecordBuilder().with_id(1).with_profile(1).available().build(),
        ],
        'movie_files': [
            RadarrMovieFileRecordBuilder().with_id(1).with_score(100).build(),
        ],
        'expected_ids': [],
    },
}


@pytest.mark.parametrize(
    'profile_cutoffs, movies, movie_files, expected_ids',
    [
        (case['profile_cutoffs'], case['movies'], case['movie_files'], case['expected_ids'])
        for case in _radarr_custom_format_cases.values()
    ],
    ids=list(_radarr_custom_format_cases.keys()),
)
def test_radarr_get_custom_format_upgrade_records(
    profile_cutoffs: Any, movies: Any, movie_files: Any, expected_ids: Any
) -> None:
    """Test RadarrClient._get_custom_format_upgrade_records filters by customFormatScore."""
    client = ClientBuilder().radarr().build()
    with patch.object(
        client, '_fetch_list', side_effect=mock_fetch_list_factory({'moviefile': movie_files, 'movie': movies})
    ):
        result = client._get_custom_format_upgrade_records(profile_cutoffs)  # pylint: disable=protected-access
    assert [rec['id'] for rec in result] == expected_ids


_fetch_movie_file_scores_cases = {
    'returns_scores_by_file_id': {
        'file_ids': [1, 2],
        'movie_files': [
            RadarrMovieFileRecordBuilder().with_id(1).with_score(50).build(),
            RadarrMovieFileRecordBuilder().with_id(2).with_score(150).build(),
        ],
        'expected': {1: 50, 2: 150},
    },
    'returns_zero_for_none_score': {
        'file_ids': [1],
        'movie_files': [{'id': 1, 'movieId': 1, 'customFormatScore': None}],
        'expected': {1: 0},
    },
    'returns_empty_for_no_ids': {
        'file_ids': [],
        'movie_files': [],
        'expected': {},
    },
}


@pytest.mark.parametrize(
    'file_ids, movie_files, expected',
    [(case['file_ids'], case['movie_files'], case['expected']) for case in _fetch_movie_file_scores_cases.values()],
    ids=list(_fetch_movie_file_scores_cases.keys()),
)
def test_fetch_movie_file_scores(file_ids: Any, movie_files: Any, expected: Any) -> None:
    """Test RadarrClient._fetch_movie_file_scores returns {fileId: score} map."""
    client = ClientBuilder().radarr().build()
    with patch.object(client, '_fetch_list', return_value=movie_files):
        result = client._fetch_movie_file_scores(file_ids)  # pylint: disable=protected-access
    assert result == expected


def test_fetch_movie_file_scores_batches_requests_above_batch_limit() -> None:
    """Test _fetch_movie_file_scores makes two HTTP calls when given more than 100 file IDs."""
    client = ClientBuilder().radarr().build()
    file_ids = list(range(1, 102))

    def fake_fetch_list(_endpoint: str, params: Any = None) -> list[dict[str, Any]]:
        ids = params.get('movieFileIds', []) if params else []
        return [{'id': file_id, 'customFormatScore': 0} for file_id in ids]

    with patch.object(client, '_fetch_list', side_effect=fake_fetch_list) as mock_fetch:
        result = client._fetch_movie_file_scores(file_ids)  # pylint: disable=protected-access

    assert mock_fetch.call_count == 2
    assert len(result) == 101


def test_fetch_list_returns_empty_on_request_exception() -> None:
    """Test _fetch_list returns [] and logs an error when a RequestException is raised."""
    client = ClientBuilder().radarr().build()
    client.session.get = MagicMock(side_effect=requests.RequestException('timeout'))
    result = client._fetch_list('/api/v3/movie')  # pylint: disable=protected-access
    assert result == []


def test_sonarr_supplemental_finds_episode_with_low_score_file() -> None:
    """Test SonarrClient._get_custom_format_upgrade_records returns episodes with low-score files."""
    client = ClientBuilder().sonarr().with_settings(retry_interval_days=0).build()
    profile_cutoffs = {1: 100}
    series_list = [SonarrSeriesRecordBuilder().with_id(1).with_profile(1).with_title('Test Series').build()]
    episode_files = [
        SonarrEpisodeFileRecordBuilder().with_id(10).with_series_id(1).with_score(50).with_episode_ids([100]).build(),
    ]
    episodes = [
        SonarrRecordBuilder()
        .with_id(100)
        .with_series('Test Series')
        .with_series_id(1)
        .with_episode(1, 1)
        .aired()
        .with_episode_file_id(10)
        .build(),
    ]
    mock_fetch = mock_fetch_list_factory({'episodefile': episode_files, 'episode': episodes, 'series': series_list})

    with patch.object(client, '_fetch_list', side_effect=mock_fetch):
        result = client._get_custom_format_upgrade_records(profile_cutoffs)  # pylint: disable=protected-access

    assert [rec['id'] for rec in result] == [100]


def test_sonarr_supplemental_skips_series_on_untracked_profile() -> None:
    """Test SonarrClient._get_custom_format_upgrade_records skips series with untracked profiles."""
    client = ClientBuilder().sonarr().build()
    profile_cutoffs = {1: 100}
    series_list = [SonarrSeriesRecordBuilder().with_id(1).with_profile(2).build()]
    mock_fetch = mock_fetch_list_factory({'series': series_list})

    with patch.object(client, '_fetch_list', side_effect=mock_fetch) as mock_fl:
        result = client._get_custom_format_upgrade_records(profile_cutoffs)  # pylint: disable=protected-access

    assert result == []
    episode_file_calls = [call for call in mock_fl.call_args_list if 'episodefile' in str(call)]
    assert len(episode_file_calls) == 0


def test_sonarr_supplemental_skips_series_when_all_files_meet_cutoff() -> None:
    """Test SonarrClient._get_custom_format_upgrade_records skips series where all files meet cutoff."""
    client = ClientBuilder().sonarr().build()
    profile_cutoffs = {1: 100}
    series_list = [SonarrSeriesRecordBuilder().with_id(1).with_profile(1).build()]
    episode_files = [
        SonarrEpisodeFileRecordBuilder().with_id(10).with_series_id(1).with_score(150).with_episode_ids([100]).build(),
    ]
    mock_fetch = mock_fetch_list_factory({'episodefile': episode_files, 'series': series_list})

    with patch.object(client, '_fetch_list', side_effect=mock_fetch):
        result = client._get_custom_format_upgrade_records(profile_cutoffs)  # pylint: disable=protected-access

    assert result == []


def test_sonarr_supplemental_injects_series_into_episode_record() -> None:
    """Test SonarrClient._get_custom_format_upgrade_records injects series data into returned episodes."""
    client = ClientBuilder().sonarr().build()
    profile_cutoffs = {1: 100}
    series_list = [SonarrSeriesRecordBuilder().with_id(1).with_profile(1).with_title('My Show').build()]
    episode_files = [
        SonarrEpisodeFileRecordBuilder().with_id(10).with_series_id(1).with_score(0).with_episode_ids([100]).build(),
    ]
    episodes = [
        SonarrRecordBuilder()
        .with_id(100)
        .with_series('My Show')
        .with_series_id(1)
        .with_episode(1, 1)
        .aired()
        .with_episode_file_id(10)
        .build(),
    ]
    mock_fetch = mock_fetch_list_factory({'episodefile': episode_files, 'episode': episodes, 'series': series_list})

    with patch.object(client, '_fetch_list', side_effect=mock_fetch):
        result = client._get_custom_format_upgrade_records(profile_cutoffs)  # pylint: disable=protected-access

    assert result[0]['series']['id'] == 1
    assert result[0]['series']['title'] == 'My Show'


def test_sonarr_season_pack_supplemental_appended_to_items() -> None:
    """Test supplemental season pairs are added to _season_pack_items in season_packs mode."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    cutoff_records = [
        SonarrRecordBuilder().with_id(1).with_series('Show A').with_series_id(10).with_episode(1, 1).aired().build()
    ]
    supplemental_records = [
        SonarrRecordBuilder().with_id(2).with_series('Show B').with_series_id(20).with_episode(2, 1).aired().build()
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=cutoff_records),
        patch.object(client, '_fetch_season_air_status', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)

    result_ids = [item_id for item_id, _, _ in results]
    assert 10 in result_ids
    assert 20 in result_ids


def test_sonarr_season_pack_supplemental_respects_upgrade_batch_size() -> None:
    """Test upgrade_batch_size limits total seasons from /wanted/cutoff + supplemental combined."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    cutoff_records = [
        SonarrRecordBuilder()
        .with_id(num)
        .with_series(f'Show {num}')
        .with_series_id(num * 10)
        .with_episode(1, 1)
        .aired()
        .build()
        for num in range(1, 4)
    ]
    supplemental_records = [
        SonarrRecordBuilder()
        .with_id(num + 10)
        .with_series(f'Sup {num}')
        .with_series_id((num + 10) * 10)
        .with_episode(1, 1)
        .aired()
        .build()
        for num in range(1, 4)
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=cutoff_records),
        patch.object(client, '_fetch_season_air_status', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=3)

    assert len(results) == 3


def test_sonarr_season_pack_supplemental_deduplicates_seen_seasons() -> None:
    """Test a (series, season) pair already in /wanted/cutoff is not added again from supplemental."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    shared_record = (
        SonarrRecordBuilder().with_id(1).with_series('Show A').with_series_id(10).with_episode(1, 1).aired().build()
    )
    with (
        patch.object(client, '_fetch_unlimited', return_value=[shared_record]),
        patch.object(client, '_fetch_season_air_status', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[shared_record]),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)

    result_ids = [item_id for item_id, _, _ in results]
    assert result_ids.count(10) == 1


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

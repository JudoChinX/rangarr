"""Tests specific to the SonarrClient implementation."""

import logging
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from rangarr.clients.arr import SonarrClient
from tests.builders import ClientBuilder
from tests.builders import SonarrEpisodeFileRecordBuilder
from tests.builders import SonarrRecordBuilder
from tests.builders import SonarrSeriesRecordBuilder
from tests.builders import mock_fetch_list_factory


def test_collect_season_pack_records_returns_individual_for_airing_season() -> None:
    """Test _collect_season_pack_records returns episode MediaItems when the season is still airing."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    records = [
        SonarrRecordBuilder().with_id(99).with_series('Show A').with_series_id(10).with_episode(1, 1).aired().build(),
    ]
    seen_seasons: set[tuple[int, int]] = set()
    season_metadata = {(10, 1): {'next_airing': '2030-01-01T00:00:00Z', 'monitored_count': 8}}

    result = client._collect_season_pack_records(  # pylint: disable=protected-access
        records, 10, 'missing', seen_seasons, True, season_metadata, {}
    )

    assert result == [(99, 'missing', 'Show A - S01E01 - Test Episode')]


def test_collect_season_pack_records_returns_season_item() -> None:
    """Test _collect_season_pack_records returns a ``season:`` string ID MediaItem for completed seasons."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    records = [
        SonarrRecordBuilder().with_id(1).with_series('Show A').with_series_id(10).with_episode(1, 1).aired().build(),
    ]
    seen_seasons: set[tuple[int, int]] = set()

    result = client._collect_season_pack_records(  # pylint: disable=protected-access
        records, 10, 'missing', seen_seasons, True, {}, {}
    )

    assert result == [('season:10:1', 'missing', 'Show A - Season 01')]


def test_fetch_season_metadata_builds_lookup() -> None:
    """Test _fetch_season_metadata returns {(series_id, season_number): meta_dict} for all seasons."""
    client = ClientBuilder().sonarr().build()
    series_list = [
        SonarrSeriesRecordBuilder()
        .with_id(1)
        .with_seasons([
            {'seasonNumber': 1, 'statistics': {'nextAiring': '2030-01-01T00:00:00Z', 'episodeCount': 8}},
            {'seasonNumber': 2, 'statistics': {'nextAiring': None, 'episodeCount': 13}},
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
        result = client._fetch_season_metadata()  # pylint: disable=protected-access

    mock_fetch.assert_called_once_with(client.ENDPOINT_SERIES)
    assert result == {
        (1, 1): {'next_airing': '2030-01-01T00:00:00Z', 'monitored_count': 8},
        (1, 2): {'next_airing': None, 'monitored_count': 13},
        (2, 1): {'next_airing': None, 'monitored_count': 0},
    }


def test_fetch_season_metadata_skips_records_with_none_id_or_missing_season() -> None:
    """Test _fetch_season_metadata skips series with no id and seasons with no seasonNumber."""
    client = ClientBuilder().sonarr().build()
    series_list = [
        {'seasons': [{'seasonNumber': 1}]},
        {'id': 2, 'seasons': [{'statistics': {'nextAiring': '2030-01-01T00:00:00Z', 'episodeCount': 5}}]},
        {
            'id': 3,
            'seasons': [{'seasonNumber': 1, 'statistics': {'nextAiring': '2030-06-01T00:00:00Z', 'episodeCount': 10}}],
        },
    ]
    with patch.object(client, '_fetch_list', return_value=series_list):
        result = client._fetch_season_metadata()  # pylint: disable=protected-access
    assert result == {(3, 1): {'next_airing': '2030-06-01T00:00:00Z', 'monitored_count': 10}}


_is_season_still_airing_cases = {
    'returns_true_when_next_airing_is_future': {
        'season_metadata': {(1, 1): {'next_airing': '2030-01-01T00:00:00Z', 'monitored_count': 8}},
        'series_id': 1,
        'season_number': 1,
        'expected': True,
    },
    'returns_false_when_next_airing_is_past': {
        'season_metadata': {(1, 1): {'next_airing': '2020-01-01T00:00:00Z', 'monitored_count': 8}},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'returns_false_when_next_airing_is_none': {
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 8}},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'returns_false_when_key_absent': {
        'season_metadata': {},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
}


@pytest.mark.parametrize(
    'season_metadata, series_id, season_number, expected',
    [
        (case['season_metadata'], case['series_id'], case['season_number'], case['expected'])
        for case in _is_season_still_airing_cases.values()
    ],
    ids=list(_is_season_still_airing_cases.keys()),
)
def test_is_season_still_airing(season_metadata: dict, series_id: int, season_number: int, expected: bool) -> None:
    """Test _is_season_still_airing returns True only when nextAiring is a future date."""
    client = ClientBuilder().sonarr().build()
    result = client._is_season_still_airing(series_id, season_number, season_metadata)  # pylint: disable=protected-access
    assert result == expected


_meets_season_pack_threshold_cases = {
    'true_always_passes': {
        'season_packs': True,
        'season_record_counts': {(1, 1): 1},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': True,
    },
    'int_threshold_met': {
        'season_packs': 3,
        'season_record_counts': {(1, 1): 3},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': True,
    },
    'int_threshold_exceeded': {
        'season_packs': 3,
        'season_record_counts': {(1, 1): 5},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': True,
    },
    'int_threshold_not_met': {
        'season_packs': 3,
        'season_record_counts': {(1, 1): 2},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'int_threshold_season_not_in_counts': {
        'season_packs': 3,
        'season_record_counts': {},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'float_threshold_met': {
        'season_packs': 0.5,
        'season_record_counts': {(1, 1): 5},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': True,
    },
    'float_threshold_exceeded': {
        'season_packs': 0.5,
        'season_record_counts': {(1, 1): 8},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': True,
    },
    'float_threshold_not_met': {
        'season_packs': 0.5,
        'season_record_counts': {(1, 1): 4},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 10}},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'float_threshold_monitored_count_zero': {
        'season_packs': 0.5,
        'season_record_counts': {(1, 1): 5},
        'season_metadata': {(1, 1): {'next_airing': None, 'monitored_count': 0}},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
    'float_threshold_season_not_in_metadata': {
        'season_packs': 0.5,
        'season_record_counts': {(1, 1): 5},
        'season_metadata': {},
        'series_id': 1,
        'season_number': 1,
        'expected': False,
    },
}


@pytest.mark.parametrize(
    'season_packs, season_record_counts, season_metadata, series_id, season_number, expected',
    [
        (
            case['season_packs'],
            case['season_record_counts'],
            case['season_metadata'],
            case['series_id'],
            case['season_number'],
            case['expected'],
        )
        for case in _meets_season_pack_threshold_cases.values()
    ],
    ids=list(_meets_season_pack_threshold_cases.keys()),
)
def test_meets_season_pack_threshold(
    season_packs: bool | int | float,
    season_record_counts: dict[tuple[int, int], int],
    season_metadata: dict[tuple[int, int], dict],
    series_id: int,
    season_number: int,
    expected: bool,
) -> None:
    """Test _meets_season_pack_threshold returns True only when the threshold is satisfied."""
    client = ClientBuilder().sonarr().with_settings(season_packs=season_packs, retry_interval_days=0).build()
    result = client._meets_season_pack_threshold(  # pylint: disable=protected-access
        series_id, season_number, season_record_counts, season_metadata
    )
    assert result == expected


_tally_season_records_cases = {
    'counts_episodes_per_season': {
        'records': [
            SonarrRecordBuilder().with_id(1).with_series_id(10).with_episode(1, 1).build(),
            SonarrRecordBuilder().with_id(2).with_series_id(10).with_episode(1, 2).build(),
            SonarrRecordBuilder().with_id(3).with_series_id(10).with_episode(2, 1).build(),
            SonarrRecordBuilder().with_id(4).with_series_id(20).with_episode(1, 1).build(),
        ],
        'expected': {(10, 1): 2, (10, 2): 1, (20, 1): 1},
    },
    'skips_records_with_no_series_id': {
        'records': [
            SonarrRecordBuilder().with_id(1).with_episode(1, 1).build(),
        ],
        'expected': {},
    },
    'skips_records_with_no_season_number': {
        'records': [
            SonarrRecordBuilder().with_id(1).with_series_id(10).with_episode(1, 1).without_season_number().build(),
        ],
        'expected': {},
    },
    'returns_empty_for_no_records': {
        'records': [],
        'expected': {},
    },
}


@pytest.mark.parametrize(
    'records, expected',
    [(case['records'], case['expected']) for case in _tally_season_records_cases.values()],
    ids=list(_tally_season_records_cases.keys()),
)
def test_tally_season_records(records: list, expected: dict) -> None:
    """Test _tally_season_records counts episode records per (series_id, season_number)."""
    client = ClientBuilder().sonarr().build()
    result = client._tally_season_records(records)  # pylint: disable=protected-access
    assert result == expected


_season_pack_unaired_filter_cases = {
    'missing_path_falls_back_to_individual_for_airing_season': {
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
        'season_metadata': {(10, 1): {'next_airing': '2030-01-01T00:00:00Z', 'monitored_count': 8}},
        'expected_ids': [1],
    },
    'upgrade_path_falls_back_to_individual_for_airing_season': {
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
        'season_metadata': {(20, 2): {'next_airing': '2030-01-01T00:00:00Z', 'monitored_count': 8}},
        'expected_ids': [2],
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
        'season_metadata': {(30, 3): {'next_airing': None, 'monitored_count': 13}},
        'expected_ids': ['season:30:3'],
    },
    'supplemental_path_falls_back_to_individual_for_airing_season': {
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
        'season_metadata': {(40, 4): {'next_airing': '2030-01-01T00:00:00Z', 'monitored_count': 8}},
        'expected_ids': [4],
    },
}


@pytest.mark.parametrize(
    'missing_batch_size, upgrade_batch_size, missing_records, upgrade_records, supplemental_records, season_metadata, expected_ids',
    [
        (
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case['missing_records'],
            case['upgrade_records'],
            case['supplemental_records'],
            case['season_metadata'],
            case['expected_ids'],
        )
        for case in _season_pack_unaired_filter_cases.values()
    ],
    ids=list(_season_pack_unaired_filter_cases.keys()),
)
def test_season_pack_falls_back_to_individual_for_airing_seasons(
    missing_batch_size: int,
    upgrade_batch_size: int,
    missing_records: list,
    upgrade_records: list,
    supplemental_records: list,
    season_metadata: dict,
    expected_ids: list,
) -> None:
    """Test season pack collection falls back to individual episodes for airing seasons."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()

    def fake_fetch_unlimited(endpoint: str) -> list[dict]:
        if 'missing' in endpoint:
            return missing_records
        return upgrade_records

    with (
        patch.object(client, '_fetch_unlimited', side_effect=fake_fetch_unlimited),
        patch.object(client, '_fetch_season_metadata', return_value=season_metadata),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(
            missing_batch_size=missing_batch_size,
            upgrade_batch_size=upgrade_batch_size,
        )

    result_ids = [item_id for item_id, _, _ in results]
    assert result_ids == expected_ids


def test_sonarr_client_reads_season_packs_setting() -> None:
    """Test that SonarrClient reads season_packs from settings."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={'season_packs': True})
    assert client.season_packs is True


def test_sonarr_client_reads_season_packs_int_setting() -> None:
    """Test that SonarrClient stores an integer season_packs value."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={'season_packs': 3})
    assert client.season_packs == 3


def test_sonarr_client_reads_season_packs_float_setting() -> None:
    """Test that SonarrClient stores a float season_packs value."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={'season_packs': 0.3})
    assert client.season_packs == 0.3


def test_sonarr_client_season_packs_defaults_to_false() -> None:
    """Test that SonarrClient defaults season_packs to False when absent from settings."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={})
    assert client.season_packs is False


def test_sonarr_season_pack_cross_pass_deduplication_preserves_reason() -> None:
    """Test that a season in both missing and upgrade endpoints appears once with reason='missing'."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    shared_record = (
        SonarrRecordBuilder().with_id(1).with_series('Show A').with_series_id(10).with_episode(1, 1).aired().build()
    )
    upgrade_only_record = (
        SonarrRecordBuilder().with_id(2).with_series('Show B').with_series_id(20).with_episode(1, 1).aired().build()
    )

    def mock_fetch_unlimited(endpoint: str) -> list[dict]:
        if 'missing' in endpoint:
            return [shared_record]
        return [shared_record, upgrade_only_record]

    with (
        patch.object(client, '_fetch_unlimited', side_effect=mock_fetch_unlimited),
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[]),
    ):
        results = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=10)

    assert [(item_id, reason) for item_id, reason, _ in results] == [
        ('season:10:1', 'missing'),
        ('season:20:1', 'upgrade'),
    ]


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
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)

    result_ids = [item_id for item_id, _, _ in results]
    assert 'season:10:1' in result_ids
    assert 'season:20:2' in result_ids


def test_sonarr_season_pack_supplemental_deduplicates_seen_seasons() -> None:
    """Test a (series, season) pair already in /wanted/cutoff is not added again from supplemental."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    shared_record = (
        SonarrRecordBuilder().with_id(1).with_series('Show A').with_series_id(10).with_episode(1, 1).aired().build()
    )
    with (
        patch.object(client, '_fetch_unlimited', return_value=[shared_record]),
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[shared_record]),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=10)

    result_ids = [item_id for item_id, _, _ in results]
    assert result_ids.count('season:10:1') == 1


def test_sonarr_season_pack_supplemental_interleaves_with_missing() -> None:
    """Test that supplemental upgrade records are interleaved proportionally with missing items."""
    client = ClientBuilder().sonarr().with_settings(season_packs=True, retry_interval_days=0).build()
    missing_records = [
        SonarrRecordBuilder().with_id(1).with_series('Show A').with_series_id(10).with_episode(1, 1).aired().build(),
        SonarrRecordBuilder().with_id(2).with_series('Show B').with_series_id(20).with_episode(1, 1).aired().build(),
    ]
    upgrade_records = [
        SonarrRecordBuilder().with_id(3).with_series('Show C').with_series_id(30).with_episode(1, 1).aired().build(),
    ]
    supplemental_records = [
        SonarrRecordBuilder().with_id(4).with_series('Show D').with_series_id(40).with_episode(1, 1).aired().build(),
    ]

    def mock_fetch_unlimited(endpoint: str) -> list[dict]:
        if 'missing' in endpoint:
            return missing_records
        return upgrade_records

    with (
        patch.object(client, '_fetch_unlimited', side_effect=mock_fetch_unlimited),
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=10)

    assert [(item_id, reason) for item_id, reason, _ in results] == [
        ('season:10:1', 'missing'),
        ('season:30:1', 'upgrade'),
        ('season:20:1', 'missing'),
        ('season:40:1', 'upgrade'),
    ]


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
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=supplemental_records),
    ):
        results = client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=3)

    assert len(results) == 3


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


def test_sonarr_supplemental_skips_unmonitored_episodes() -> None:
    """Test SonarrClient._get_custom_format_upgrade_records skips unmonitored episodes."""
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
        .unmonitored()
        .build(),
    ]
    mock_fetch = mock_fetch_list_factory({'episodefile': episode_files, 'episode': episodes, 'series': series_list})

    with patch.object(client, '_fetch_list', side_effect=mock_fetch):
        result = client._get_custom_format_upgrade_records(profile_cutoffs)  # pylint: disable=protected-access

    assert [rec['id'] for rec in result] == []


def test_sonarr_supplemental_skips_unmonitored_series() -> None:
    """Test SonarrClient._get_custom_format_upgrade_records skips unmonitored series."""
    client = ClientBuilder().sonarr().with_settings(retry_interval_days=0).build()
    profile_cutoffs = {1: 100}
    series_list = [
        SonarrSeriesRecordBuilder().with_id(1).with_profile(1).with_title('Test Series').unmonitored().build()
    ]
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

    assert [rec['id'] for rec in result] == []


def test_sonarr_trigger_single_episode_delegates_to_base() -> None:
    """Test _trigger_single dispatches EpisodeSearch for integer IDs via super()."""
    client = ClientBuilder().sonarr().with_settings(stagger_interval_seconds=0).build()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    client.session.post = MagicMock(return_value=mock_resp)

    client._trigger_single(100, 'missing', 'Show B - S02E01 - Title', 1, 1)  # pylint: disable=protected-access

    client.session.post.assert_called_once()
    assert client.session.post.call_args.args[0] == 'http://test/api/v3/command'
    assert client.session.post.call_args.kwargs['json'] == {'name': 'EpisodeSearch', 'episodeIds': [100]}


def test_sonarr_trigger_single_season_pack_dry_run(caplog: pytest.LogCaptureFixture) -> None:
    """Test _trigger_single logs DRY RUN and makes no POST when dry_run is True."""
    client = ClientBuilder().sonarr().with_settings(dry_run=True, stagger_interval_seconds=0).build()
    client.session.post = MagicMock()

    with caplog.at_level(logging.INFO):
        client._trigger_single('season:10:1', 'missing', 'Show A - Season 01', 1, 1)  # pylint: disable=protected-access

    client.session.post.assert_not_called()
    assert 'DRY RUN' in caplog.text


def test_sonarr_trigger_single_season_pack_handles_request_exception(caplog: pytest.LogCaptureFixture) -> None:
    """Test _trigger_single logs a SeasonSearch error and does not raise on RequestException."""
    client = ClientBuilder().sonarr().with_settings(stagger_interval_seconds=0).build()
    client.session.post = MagicMock(side_effect=requests.RequestException('timeout'))

    with caplog.at_level(logging.ERROR):
        client._trigger_single('season:10:1', 'missing', 'Show A - Season 01', 1, 1)  # pylint: disable=protected-access

    assert 'Failed to trigger SeasonSearch' in caplog.text


def test_sonarr_trigger_single_season_pack_posts_season_search() -> None:
    """Test _trigger_single dispatches SeasonSearch with correct seriesId and seasonNumber."""
    client = ClientBuilder().sonarr().with_settings(stagger_interval_seconds=0).build()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    client.session.post = MagicMock(return_value=mock_resp)

    client._trigger_single('season:10:1', 'missing', 'Show A - Season 01', 1, 1)  # pylint: disable=protected-access

    client.session.post.assert_called_once()
    assert client.session.post.call_args.kwargs['json'] == {
        'name': 'SeasonSearch',
        'seriesId': 10,
        'seasonNumber': 1,
    }

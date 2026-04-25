"""Tests specific to the SonarrClient implementation."""

from unittest.mock import patch

import pytest

from rangarr.clients.arr import SonarrClient
from tests.builders import ClientBuilder
from tests.builders import SonarrEpisodeFileRecordBuilder
from tests.builders import SonarrRecordBuilder
from tests.builders import SonarrSeriesRecordBuilder
from tests.builders import mock_fetch_list_factory


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
        'season_air_status': {(10, 1): '2030-01-01T00:00:00Z'},
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
        'season_air_status': {(20, 2): '2030-01-01T00:00:00Z'},
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
        'season_air_status': {(30, 3): None},
        'expected_ids': [30],
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
        'season_air_status': {(40, 4): '2030-01-01T00:00:00Z'},
        'expected_ids': [4],
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
def test_season_pack_falls_back_to_individual_for_airing_seasons(
    missing_batch_size: int,
    upgrade_batch_size: int,
    missing_records: list,
    upgrade_records: list,
    supplemental_records: list,
    season_air_status: dict,
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
        patch.object(client, '_fetch_season_air_status', return_value=season_air_status),
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


def test_sonarr_client_season_packs_defaults_to_false() -> None:
    """Test that SonarrClient defaults season_packs to False when absent from settings."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings={})
    assert client.season_packs is False


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

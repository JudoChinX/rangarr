"""Tests specific to the RadarrClient implementation."""

from typing import Any
from unittest.mock import patch

import pytest
import requests

from tests.builders import ClientBuilder
from tests.builders import RadarrMovieFileRecordBuilder
from tests.builders import RadarrMovieRecordBuilder
from tests.builders import RadarrRecordBuilder
from tests.builders import mock_fetch_list_factory
from tests.builders import mock_http_response

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
        result = client._fetch_movie_file_scores(file_ids)
    assert result == expected


def test_fetch_movie_file_scores_batches_requests_above_batch_limit() -> None:
    """Test _fetch_movie_file_scores makes two HTTP calls when given more than 100 file IDs."""
    client = ClientBuilder().radarr().build()
    file_ids = list(range(1, 102))

    def fake_fetch_list(_endpoint: str, params: Any = None) -> list[dict[str, Any]]:
        ids = params.get('movieFileIds', []) if params else []
        return [{'id': file_id, 'customFormatScore': 0} for file_id in ids]

    with patch.object(client, '_fetch_list', side_effect=fake_fetch_list) as mock_fetch:
        result = client._fetch_movie_file_scores(file_ids)
    assert mock_fetch.call_count == 2
    assert len(result) == 101


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
    'skips_movie_on_untracked_profile': {
        'profile_cutoffs': {1: 100},
        'movies': [
            RadarrMovieRecordBuilder().with_id(1).with_profile(2).available().build(),
        ],
        'movie_files': [],
        'expected_ids': [],
    },
    'skips_movie_without_movie_file': {
        'profile_cutoffs': {1: 100},
        'movies': [
            RadarrMovieRecordBuilder().with_id(1).with_profile(1).without_movie_file().available().build(),
        ],
        'movie_files': [],
        'expected_ids': [],
    },
    'skips_unmonitored_movie': {
        'profile_cutoffs': {1: 100},
        'movies': [
            RadarrMovieRecordBuilder().with_id(1).with_profile(1).unmonitored().available().build(),
        ],
        'movie_files': [
            RadarrMovieFileRecordBuilder().with_id(1).with_score(50).build(),
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
        result = client._get_custom_format_upgrade_records(profile_cutoffs)
    assert [rec['id'] for rec in result] == expected_ids


def test_supplemental_early_exit_when_no_cutoff_profiles() -> None:
    """Test _get_custom_format_score_unmet_records returns [] without any media fetch when profiles empty."""
    client = ClientBuilder().radarr().build()
    with (
        patch.object(client, '_fetch_quality_profile_cutoffs', return_value={}),
        patch.object(client, '_fetch_list') as mock_fetch_list,
    ):
        result = client._get_custom_format_score_unmet_records()
    assert result == []
    mock_fetch_list.assert_not_called()


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


def test_supplemental_upgrade_skipped_when_upgrade_batch_disabled() -> None:
    """Test supplemental pass is not invoked when upgrade_batch_size is 0."""
    client = ClientBuilder().radarr().build()
    with (
        patch.object(client, '_fetch_unlimited', return_value=[]),
        patch.object(client, '_get_custom_format_score_unmet_records') as mock_sup,
    ):
        client.get_media_to_search(missing_batch_size=0, upgrade_batch_size=0)
    mock_sup.assert_not_called()


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

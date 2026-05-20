"""Tests specific to the WhisparrClient implementation."""

from unittest.mock import patch

import pytest

from rangarr.clients.arr import WhisparrClient
from tests.builders import ClientBuilder
from tests.builders import SonarrRecordBuilder

_get_record_title_cases = {
    'full_record_returns_performer_and_scene_title': {
        'record': SonarrRecordBuilder().with_series('Test Performer').with_title('Test Scene').build(),
        'expected': 'Test Performer - Test Scene',
    },
    'missing_series_falls_back_to_unknown_performer': {
        'record': {'title': 'Test Scene'},
        'expected': 'Unknown Performer - Test Scene',
    },
    'missing_title_key_falls_back_to_unknown_scene': {
        'record': {'series': {'title': 'Test Performer'}},
        'expected': 'Test Performer - Unknown Scene',
    },
}

_get_release_date_cases = {
    'returns_release_date_when_present': {
        'record': {'releaseDate': '2025-06-26'},
        'expected': '2025-06-26',
    },
    'returns_empty_string_when_absent': {
        'record': {},
        'expected': '',
    },
    'returns_empty_string_for_none_value': {
        'record': {'releaseDate': None},
        'expected': '',
    },
}

_get_season_title_cases = {
    'full_record_zero_pads_single_digit_season': {
        'record': SonarrRecordBuilder().with_series('Test Performer').build(),
        'season_number': 3,
        'expected': 'Test Performer - Season 03',
    },
    'full_record_two_digit_season_not_padded': {
        'record': SonarrRecordBuilder().with_series('Test Performer').build(),
        'season_number': 12,
        'expected': 'Test Performer - Season 12',
    },
    'missing_series_falls_back_to_unknown_performer': {
        'record': {'title': 'Test Scene'},
        'season_number': 1,
        'expected': 'Unknown Performer - Season 01',
    },
}

_is_available_cases = {
    'past_release_date_is_available': {
        'record': {'releaseDate': '2025-01-01'},
        'expected': True,
    },
    'future_release_date_is_not_available': {
        'record': {'releaseDate': '2027-01-01'},
        'expected': False,
    },
    'missing_release_date_is_not_available': {
        'record': {},
        'expected': False,
    },
}


def test_get_media_to_search_returns_released_scenes() -> None:
    """Test get_media_to_search returns scenes whose releaseDate is in the past."""
    client = ClientBuilder().whisparr().with_settings(retry_interval_days=0).build()
    missing_records = [
        {
            'id': 1,
            'title': 'Past Scene',
            'series': {'id': 10, 'title': 'Test Performer', 'tags': []},
            'seasonNumber': 1,
            'episodeNumber': 1,
            'releaseDate': '2025-01-01',
            'monitored': True,
        },
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=missing_records),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[]),
    ):
        items = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=0)
    assert len(items) == 1
    assert items[0][2] == 'Test Performer - Past Scene'


@pytest.mark.parametrize(
    'record, expected',
    [(case['record'], case['expected']) for case in _get_record_title_cases.values()],
    ids=list(_get_record_title_cases.keys()),
)
def test_get_record_title(record: dict, expected: str) -> None:
    """Test _get_record_title formats performer and scene title correctly."""
    client = ClientBuilder().whisparr().build()
    result = client._get_record_title(record)
    assert result == expected


@pytest.mark.parametrize(
    'record, expected',
    [(case['record'], case['expected']) for case in _get_release_date_cases.values()],
    ids=list(_get_release_date_cases.keys()),
)
def test_get_release_date(record: dict, expected: str) -> None:
    """Test _get_release_date returns the releaseDate field used for sort ordering."""
    client = ClientBuilder().whisparr().build()
    assert client._get_release_date(record) == expected


@pytest.mark.parametrize(
    'record, season_number, expected',
    [(case['record'], case['season_number'], case['expected']) for case in _get_season_title_cases.values()],
    ids=list(_get_season_title_cases.keys()),
)
def test_get_season_title(record: dict, season_number: int, expected: str) -> None:
    """Test _get_season_title formats performer and zero-padded season number correctly."""
    client = ClientBuilder().whisparr().build()
    result = client._get_season_title(record, season_number)
    assert result == expected


@pytest.mark.parametrize(
    'record, expected',
    [(case['record'], case['expected']) for case in _is_available_cases.values()],
    ids=list(_is_available_cases.keys()),
)
def test_is_available(record: dict, expected: bool) -> None:
    """Test _is_available uses releaseDate to determine whether a scene has been released."""
    client = ClientBuilder().whisparr().build()
    assert client._is_available(record) == expected


def test_whisparr_client_inherits_sonarr_season_packs_default() -> None:
    """Test WhisparrClient inherits SonarrClient and defaults season_packs to False."""
    client = WhisparrClient(name='test', url='http://test', api_key='testkey', settings={})
    assert client.season_packs is False


def test_whisparr_client_reads_season_packs_setting() -> None:
    """Test WhisparrClient inherits season_packs setting from SonarrClient."""
    client = WhisparrClient(name='test', url='http://test', api_key='testkey', settings={'season_packs': True})
    assert client.season_packs is True

"""Tests specific to the WhisparrV3Client implementation."""

from unittest.mock import patch

import pytest

from rangarr.clients.arr import RadarrClient
from rangarr.clients.arr import WhisparrV3Client
from tests.builders import ClientBuilder
from tests.builders import WhisparrV3RecordBuilder


def test_get_media_to_search_excludes_unavailable_scenes() -> None:
    """Test get_media_to_search excludes scenes where isAvailable is False."""
    client = ClientBuilder().whisparr_v3().with_settings(retry_interval_days=0).build()
    missing_records = [
        WhisparrV3RecordBuilder().unavailable().build(),
    ]
    with (
        patch.object(client, '_fetch_unlimited', return_value=missing_records),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[]),
    ):
        items = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=0)
    assert len(items) == 0


def test_get_media_to_search_returns_available_scenes() -> None:
    """Test get_media_to_search returns scenes where isAvailable is True."""
    client = ClientBuilder().whisparr_v3().with_settings(retry_interval_days=0).build()
    missing_records = [WhisparrV3RecordBuilder().build()]
    with (
        patch.object(client, '_fetch_unlimited', return_value=missing_records),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[]),
    ):
        items = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=0)
    assert len(items) == 1
    assert items[0][2] == 'Test Studio - Test Scene'


_get_record_title_cases = {
    'full_record_returns_studio_and_scene_title': {
        'record': {'id': 1, 'title': 'Test Scene', 'studioTitle': 'Test Studio'},
        'expected': 'Test Studio - Test Scene',
    },
    'missing_studio_title_falls_back_to_unknown_studio': {
        'record': {'id': 1, 'title': 'Test Scene'},
        'expected': 'Unknown Studio - Test Scene',
    },
    'missing_title_falls_back_to_scene_id': {
        'record': {'id': 42, 'studioTitle': 'Test Studio'},
        'expected': 'Test Studio - Scene 42',
    },
    'missing_both_uses_all_fallbacks': {
        'record': {'id': 7},
        'expected': 'Unknown Studio - Scene 7',
    },
}


@pytest.mark.parametrize(
    'record, expected',
    [(case['record'], case['expected']) for case in _get_record_title_cases.values()],
    ids=list(_get_record_title_cases.keys()),
)
def test_get_record_title(record: dict, expected: str) -> None:
    """Test _get_record_title formats studio and scene title correctly."""
    client = ClientBuilder().whisparr_v3().build()
    result = client._get_record_title(record)
    assert result == expected


def test_whisparr_v3_client_instantiates_as_radarr_subclass() -> None:
    """Test WhisparrV3Client instantiates and is a RadarrClient subclass."""
    client = WhisparrV3Client(name='test', url='http://test', api_key='testkey', settings={})
    assert isinstance(client, RadarrClient)

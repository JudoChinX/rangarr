"""Tests for SonarrClient season pack search behaviour."""

import logging
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from rangarr.clients.arr import SonarrClient
from tests.builders import SonarrRecordBuilder

_season_pack_get_media_cases = {
    'season_packs_disabled_delegates_to_base': {
        'settings': {'season_packs': False, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
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
        'expected_season_pack_items': [],
        'expected_media_item_ids': [1],
        'expected_fetch_call_count': None,
    },
    'groups_missing_episodes_by_season': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 2)
            .aired()
            .build(),
            SonarrRecordBuilder()
            .with_id(3)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(2, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [],
        'expected_season_pack_items': [
            (10, 1, 'missing', 'Show A - Season 01'),
            (10, 2, 'missing', 'Show A - Season 02'),
        ],
        'expected_media_item_ids': [10, 10],
        'expected_fetch_call_count': None,
    },
    'deduplicates_same_season_across_missing_and_upgrade': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 2)
            .aired()
            .build(),
        ],
        'expected_season_pack_items': [
            (10, 1, 'missing', 'Show A - Season 01'),
        ],
        'expected_media_item_ids': [10],
        'expected_fetch_call_count': None,
    },
    'skips_unavailable_episodes': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .not_aired()
            .build(),
        ],
        'upgrade_records': [],
        'expected_season_pack_items': [],
        'expected_media_item_ids': [],
        'expected_fetch_call_count': None,
    },
    'skips_episodes_within_retry_window': {
        'settings': {'season_packs': True, 'retry_interval_days': 7},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .searched_recently()
            .build(),
        ],
        'upgrade_records': [],
        'expected_season_pack_items': [],
        'expected_media_item_ids': [],
        'expected_fetch_call_count': None,
    },
    'skips_record_with_missing_series_id': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder().with_id(1).with_series('Show A').with_episode(1, 1).aired().build(),
        ],
        'upgrade_records': [],
        'expected_season_pack_items': [],
        'expected_media_item_ids': [],
        'expected_fetch_call_count': None,
    },
    'skips_record_with_missing_season_number': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .without_season_number()
            .build(),
        ],
        'upgrade_records': [],
        'expected_season_pack_items': [],
        'expected_media_item_ids': [],
        'expected_fetch_call_count': None,
    },
    'returns_media_items_with_correct_reasons_for_logging': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show B')
            .with_series_id(20)
            .with_episode(2, 1)
            .aired()
            .build(),
        ],
        'expected_season_pack_items': [
            (10, 1, 'missing', 'Show A - Season 01'),
            (20, 2, 'upgrade', 'Show B - Season 02'),
        ],
        'expected_media_item_ids': [10, 20],
        'expected_fetch_call_count': None,
    },
    'missing_disabled_skips_missing': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 0,
        'upgrade_batch_size': 10,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show B')
            .with_series_id(20)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'expected_season_pack_items': [
            (20, 1, 'upgrade', 'Show B - Season 01'),
        ],
        'expected_media_item_ids': [20],
        'expected_fetch_call_count': 1,
    },
    'upgrade_disabled_skips_upgrades': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
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
        'upgrade_records': [
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show B')
            .with_series_id(20)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'expected_season_pack_items': [
            (10, 1, 'missing', 'Show A - Season 01'),
        ],
        'expected_media_item_ids': [10],
        'expected_fetch_call_count': 1,
    },
    'both_disabled_returns_empty': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 0,
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
        'upgrade_records': [
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show B')
            .with_series_id(20)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'expected_season_pack_items': [],
        'expected_media_item_ids': [],
        'expected_fetch_call_count': 0,
    },
    'missing_batch_size_limits_missing_seasons': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 1,
        'upgrade_batch_size': 10,
        'missing_records': [  # limit=1 keeps first season encountered; season 1 comes before season 2
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(2, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [],
        'expected_season_pack_items': [
            (10, 1, 'missing', 'Show A - Season 01'),
        ],
        'expected_media_item_ids': [10],
        'expected_fetch_call_count': None,
    },
    'upgrade_batch_size_limits_upgrade_seasons': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': 10,
        'upgrade_batch_size': 1,
        'missing_records': [],
        'upgrade_records': [  # limit=1 keeps first season encountered; season 1 comes before season 2
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(2, 1)
            .aired()
            .build(),
        ],
        'expected_season_pack_items': [
            (10, 1, 'upgrade', 'Show A - Season 01'),
        ],
        'expected_media_item_ids': [10],
        'expected_fetch_call_count': None,
    },
    'unlimited_batch_size_collects_all_seasons': {
        'settings': {'season_packs': True, 'retry_interval_days': 0},
        'missing_batch_size': -1,
        'upgrade_batch_size': -1,
        'missing_records': [
            SonarrRecordBuilder()
            .with_id(1)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(1, 1)
            .aired()
            .build(),
            SonarrRecordBuilder()
            .with_id(2)
            .with_series('Show A')
            .with_series_id(10)
            .with_episode(2, 1)
            .aired()
            .build(),
        ],
        'upgrade_records': [
            SonarrRecordBuilder()
            .with_id(3)
            .with_series('Show B')
            .with_series_id(20)
            .with_episode(1, 1)
            .aired()
            .build(),
        ],
        'expected_season_pack_items': [
            (10, 1, 'missing', 'Show A - Season 01'),
            (10, 2, 'missing', 'Show A - Season 02'),
            (20, 1, 'upgrade', 'Show B - Season 01'),
        ],
        'expected_media_item_ids': [10, 10, 20],
        'expected_fetch_call_count': None,
    },
}


@pytest.mark.parametrize(
    'settings, missing_batch_size, upgrade_batch_size, missing_records, upgrade_records, expected_season_pack_items, expected_media_item_ids, expected_fetch_call_count',
    [
        (
            case['settings'],
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case['missing_records'],
            case['upgrade_records'],
            case['expected_season_pack_items'],
            case['expected_media_item_ids'],
            case['expected_fetch_call_count'],
        )
        for case in _season_pack_get_media_cases.values()
    ],
    ids=list(_season_pack_get_media_cases.keys()),
)
def test_sonarr_season_pack_get_media_to_search(
    settings: Any,
    missing_batch_size: Any,
    upgrade_batch_size: Any,
    missing_records: Any,
    upgrade_records: Any,
    expected_season_pack_items: Any,
    expected_media_item_ids: Any,
    expected_fetch_call_count: Any,
) -> None:
    """Test SonarrClient.get_media_to_search season pack path."""
    client = SonarrClient(name='test', url='http://test', api_key='testkey', settings=settings)

    def mock_fetch_unlimited(endpoint: str) -> list[dict]:
        if 'missing' in endpoint:
            return missing_records.copy()
        return upgrade_records.copy()

    with patch.object(client, '_fetch_unlimited', side_effect=mock_fetch_unlimited) as mock_fetch:
        result = client.get_media_to_search(
            missing_batch_size=missing_batch_size, upgrade_batch_size=upgrade_batch_size
        )

    assert [item_id for item_id, unused_reason, unused_title in result] == expected_media_item_ids
    assert client._season_pack_items == expected_season_pack_items  # pylint: disable=protected-access
    if expected_fetch_call_count is not None:
        assert mock_fetch.call_count == expected_fetch_call_count


def test_sonarr_season_pack_trigger_search_posts_correct_payload() -> None:
    """Test that trigger_search posts SeasonSearch with seriesId and seasonNumber."""
    client = SonarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'season_packs': True, 'stagger_interval_seconds': 0},
    )
    client._season_pack_items = [(10, 1, 'missing', 'Show A - Season 01')]  # pylint: disable=protected-access

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    client.session.post = MagicMock(return_value=mock_resp)

    client.trigger_search([(10, 'missing', 'Show A - Season 01')])

    client.session.post.assert_called_once()
    call_args = client.session.post.call_args
    assert call_args.args[0] == 'http://test/api/v3/command'
    assert call_args.kwargs['json'] == {'name': 'SeasonSearch', 'seriesId': 10, 'seasonNumber': 1}


def test_sonarr_season_pack_trigger_search_handles_request_exception() -> None:
    """Test that trigger_search logs errors and does not propagate RequestException."""
    client = SonarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'season_packs': True, 'stagger_interval_seconds': 0},
    )
    client._season_pack_items = [(10, 1, 'missing', 'Show A - Season 01')]  # pylint: disable=protected-access
    client.session.post = MagicMock(side_effect=requests.RequestException('timeout'))

    client.trigger_search([(10, 'missing', 'Show A - Season 01')])

    client.session.post.assert_called_once()


def test_sonarr_season_pack_trigger_search_dry_run(caplog: pytest.LogCaptureFixture) -> None:
    """Test that trigger_search logs DRY RUN message and does not POST when dry_run is True."""
    client = SonarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'season_packs': True, 'stagger_interval_seconds': 0, 'dry_run': True},
    )
    client._season_pack_items = [(10, 1, 'missing', 'Show A - Season 01')]  # pylint: disable=protected-access
    client.session.post = MagicMock()

    with caplog.at_level(logging.INFO):
        client.trigger_search([(10, 'missing', 'Show A - Season 01')])

    client.session.post.assert_not_called()
    assert 'DRY RUN' in caplog.text


def test_sonarr_season_pack_trigger_search_applies_stagger_between_items() -> None:
    """Test that trigger_search sleeps between season searches when stagger_interval_seconds > 0."""
    client = SonarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'season_packs': True, 'stagger_interval_seconds': 5},
    )
    client._season_pack_items = [  # pylint: disable=protected-access
        (10, 1, 'missing', 'Show A - Season 01'),
        (10, 2, 'missing', 'Show A - Season 02'),
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    client.session.post = MagicMock(return_value=mock_resp)

    with patch('time.sleep') as mock_sleep:
        client.trigger_search([(10, 'missing', 'Show A - Season 01'), (10, 'missing', 'Show A - Season 02')])

    mock_sleep.assert_called_once_with(5)


def test_sonarr_season_pack_skips_series_with_excluded_tag() -> None:
    """Test that season-pack mode skips series whose tag is in the exclude set."""
    client = SonarrClient(
        name='test',
        url='http://test',
        api_key='testkey',
        settings={'season_packs': True, 'retry_interval_days': 0},
    )
    client._exclude_tag_ids = {5}  # pylint: disable=protected-access

    missing_records = [
        SonarrRecordBuilder()
        .with_id(1)
        .with_series('Show A')
        .with_series_id(10)
        .with_episode(1, 1)
        .with_tags([5])
        .aired()
        .build(),
        SonarrRecordBuilder().with_id(2).with_series('Show B').with_series_id(20).with_episode(1, 1).aired().build(),
    ]

    def mock_fetch_unlimited(endpoint: str) -> list[dict]:
        if 'missing' in endpoint:
            return missing_records.copy()
        return []

    with patch.object(client, '_fetch_unlimited', side_effect=mock_fetch_unlimited):
        result = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=10)

    item_ids = [item_id for item_id, unused_reason, unused_title in result]
    assert item_ids == [20]
    assert client._season_pack_items == [(20, 1, 'missing', 'Show B - Season 01')]  # pylint: disable=protected-access

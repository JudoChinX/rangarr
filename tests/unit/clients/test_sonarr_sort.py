"""Tests for Sonarr season pack sorting and search order behaviour."""

from unittest.mock import patch

from tests.builders import ClientBuilder
from tests.builders import SonarrRecordBuilder


def test_sonarr_season_packs_interleaves_missing_and_upgrade() -> None:
    """Test that SonarrClient interleaves missing and upgrade items when season_packs is enabled."""
    client = (
        ClientBuilder()
        .sonarr()
        .with_settings(
            season_packs=True,
            search_order='last_searched_ascending',
            retry_interval_days=0,
        )
        .build()
    )

    missing_records = [
        SonarrRecordBuilder()
        .with_id(1)
        .with_series('Show A')
        .with_series_id(10)
        .with_episode(1, 1)
        .aired()
        .searched_long_ago()
        .build(),
        SonarrRecordBuilder()
        .with_id(2)
        .with_series('Show B')
        .with_series_id(20)
        .with_episode(1, 1)
        .aired()
        .searched_long_ago()
        .build(),
    ]
    upgrade_records = [
        SonarrRecordBuilder()
        .with_id(3)
        .with_series('Show C')
        .with_series_id(30)
        .with_episode(1, 1)
        .aired()
        .searched_long_ago()
        .build(),
        SonarrRecordBuilder()
        .with_id(4)
        .with_series('Show D')
        .with_series_id(40)
        .with_episode(1, 1)
        .aired()
        .searched_long_ago()
        .build(),
    ]

    def mock_fetch_unlimited(endpoint: str) -> list[dict]:
        if 'missing' in endpoint:
            return missing_records
        return upgrade_records

    with (
        patch.object(client, '_fetch_unlimited', side_effect=mock_fetch_unlimited),
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[]),
    ):
        results = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=10)

    result_ids = [item_id for item_id, _, _ in results]
    reasons = [reason for _, reason, _ in results]

    assert reasons == ['missing', 'upgrade', 'missing', 'upgrade']
    assert result_ids == ['season:10:1', 'season:30:1', 'season:20:1', 'season:40:1']


def test_sonarr_season_packs_respects_random_order() -> None:
    """Test that SonarrClient shuffles the merged list when search_order is 'random'."""
    client = (
        ClientBuilder()
        .sonarr()
        .with_settings(
            season_packs=True,
            search_order='random',
            retry_interval_days=0,
        )
        .build()
    )

    records = [
        SonarrRecordBuilder()
        .with_id(num)
        .with_series(f'Show {num}')
        .with_series_id(num * 10)
        .with_episode(1, 1)
        .aired()
        .build()
        for num in range(1, 6)
    ]

    with (
        patch.object(client, '_fetch_unlimited', return_value=records),
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[]),
        patch('random.shuffle') as mock_shuffle,
    ):
        client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=0)

    mock_shuffle.assert_called_once()


def test_sonarr_season_packs_respects_search_order() -> None:
    """Test that SonarrClient respects search_order when season_packs is enabled."""
    client = (
        ClientBuilder()
        .sonarr()
        .with_settings(
            season_packs=True,
            search_order='last_searched_ascending',
            retry_interval_days=0,
        )
        .build()
    )

    records = [
        SonarrRecordBuilder()
        .with_id(1)
        .with_series('Show A')
        .with_series_id(10)
        .with_episode(1, 1)
        .aired()
        .searched_recently()
        .build(),
        SonarrRecordBuilder()
        .with_id(2)
        .with_series('Show B')
        .with_series_id(20)
        .with_episode(2, 1)
        .aired()
        .searched_long_ago()
        .build(),
    ]

    with (
        patch.object(client, '_fetch_unlimited', return_value=records),
        patch.object(client, '_fetch_season_metadata', return_value={}),
        patch.object(client, '_get_custom_format_score_unmet_records', return_value=[]),
    ):
        results = client.get_media_to_search(missing_batch_size=10, upgrade_batch_size=0)

    result_ids = [item_id for item_id, _, _ in results]

    assert result_ids == ['season:20:2', 'season:10:1']

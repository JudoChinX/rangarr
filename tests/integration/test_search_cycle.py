"""System tests for the full search cycle flow."""
# pylint: disable=redefined-outer-name

import logging
from unittest.mock import MagicMock

import pytest

from rangarr.main import _run_search_cycle


@pytest.fixture
def radarr_client() -> MagicMock:
    """Create a mock Radarr client for search cycle testing."""
    client = MagicMock()
    client.name = 'RealRadarr'
    client.weight = 1.0
    client.get_media_to_search.return_value = [
        (101, 'missing', 'Movie A'),
        (102, 'upgrade', 'Movie B'),
    ]
    return client


@pytest.fixture
def sonarr_client() -> MagicMock:
    """Create a mock Sonarr client for search cycle testing."""
    client = MagicMock()
    client.name = 'RealSonarr'
    client.weight = 1.0
    client.get_media_to_search.return_value = [
        (201, 'missing', 'Show A S01E01'),
    ]
    return client


@pytest.fixture
def system_config() -> dict[str, object]:
    """Provide minimal settings for a system search cycle test."""
    return {
        'missing_batch_size': 5,
        'upgrade_batch_size': 5,
        'stagger_interval_seconds': 0,
    }


def test_search_cycle_dispatches_searches(
    radarr_client: MagicMock,
    sonarr_client: MagicMock,
    system_config: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that _run_search_cycle logs expected messages and triggers a search per client."""
    active_clients = [radarr_client, sonarr_client]

    with caplog.at_level(logging.INFO):
        _run_search_cycle(active_clients, system_config)

    assert '--- Starting search cycle ---' in caplog.text
    assert 'Total search batch: 3 item(s)' in caplog.text

    assert radarr_client.trigger_search.call_count == 2
    sonarr_client.trigger_search.assert_called_once()

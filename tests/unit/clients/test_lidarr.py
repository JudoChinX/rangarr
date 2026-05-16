"""Tests specific to the LidarrClient implementation."""

from unittest.mock import MagicMock

from tests.builders import ClientBuilder


def test_lidarr_fetch_quality_profile_cutoffs_returns_empty() -> None:
    """Test LidarrClient._fetch_quality_profile_cutoffs always returns {} without HTTP calls."""
    client = ClientBuilder().lidarr().build()
    client.session.get = MagicMock()
    result = client._fetch_quality_profile_cutoffs()
    assert result == {}
    client.session.get.assert_not_called()

"""Shared pytest fixtures for unit tests."""

from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_client() -> Mock:
    """Create a mock ArrClient for testing."""
    client = Mock()
    client.name = 'test-instance'
    client.weight = 1.0
    client.get_media_to_search = Mock(return_value=[])
    client.trigger_search = Mock()
    return client

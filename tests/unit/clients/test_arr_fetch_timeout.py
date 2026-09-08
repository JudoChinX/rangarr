"""Tests for the fetch_timeout setting in ArrClient API calls."""

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from rangarr.clients.arr import ArrClient
from rangarr.clients.arr import RadarrClient
from rangarr.clients.arr import SonarrClient
from tests.builders import ClientBuilder
from tests.builders import mock_tag_api

_fetch_timeout_cases = {
    'default_timeout': {
        'timeout': None,
        'expected_timeout': 30,
    },
    'custom_timeout': {
        'timeout': 120,
        'expected_timeout': 120,
    },
}


def _build_client(timeout: int | None) -> ArrClient:
    """Build a Radarr client with or without an explicit fetch_timeout."""
    builder = ClientBuilder(RadarrClient)
    if timeout is not None:
        builder = builder.with_settings(fetch_timeout=timeout)
    return builder.build()


def test_check_connection_uses_fixed_request_timeout() -> None:
    """Test that the connection probe uses the fixed REQUEST_TIMEOUT, not fetch_timeout."""
    client = _build_client(120)
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, 'get', return_value=mock_resp) as mock_get:
        client.check_connection()

    assert mock_get.call_args_list[0].kwargs['timeout'] == ArrClient.REQUEST_TIMEOUT


@pytest.mark.parametrize(
    'timeout, expected_timeout',
    [(case['timeout'], case['expected_timeout']) for case in _fetch_timeout_cases.values()],
    ids=list(_fetch_timeout_cases.keys()),
)
def test_fetch_list_fetch_timeout(timeout: int | None, expected_timeout: int) -> None:
    """Test that _fetch_list passes the configured or default fetch_timeout.

    Args:
        timeout: fetch_timeout to set in client settings; None to use the default.
        expected_timeout: Expected timeout kwarg in the API request.
    """
    client = _build_client(timeout)
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, 'get', return_value=mock_resp) as mock_get:
        client._fetch_list('/api/v3/tag')

    assert mock_get.call_args_list[0].kwargs['timeout'] == expected_timeout


@pytest.mark.parametrize(
    'timeout, expected_timeout',
    [(case['timeout'], case['expected_timeout']) for case in _fetch_timeout_cases.values()],
    ids=list(_fetch_timeout_cases.keys()),
)
def test_fetch_unlimited_fetch_timeout(timeout: int | None, expected_timeout: int) -> None:
    """Test that _fetch_unlimited passes the configured or default fetch_timeout.

    Args:
        timeout: fetch_timeout to set in client settings; None to use the default.
        expected_timeout: Expected timeout kwarg in the API request.
    """
    client = _build_client(timeout)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {'records': []}
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, 'get', return_value=mock_resp) as mock_get:
        client._fetch_unlimited('/api/v3/wanted/missing')

    assert mock_get.call_args_list[0].kwargs['timeout'] == expected_timeout


def test_resolve_tag_ids_uses_fixed_request_timeout() -> None:
    """Test that startup tag resolution uses the fixed REQUEST_TIMEOUT, not fetch_timeout."""
    builder = ClientBuilder(RadarrClient).with_settings(fetch_timeout=120).with_include_tags('keep')

    with patch.object(requests.Session, 'get', return_value=mock_tag_api([{'id': 1, 'label': 'keep'}])) as mock_get:
        builder.build()

    assert mock_get.call_args_list[0].kwargs['timeout'] == ArrClient.REQUEST_TIMEOUT


def test_sonarr_season_search_uses_fixed_request_timeout() -> None:
    """Test that the Sonarr SeasonSearch POST uses the fixed REQUEST_TIMEOUT, not fetch_timeout."""
    client = ClientBuilder(SonarrClient).with_settings(fetch_timeout=120).build()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, 'post', return_value=mock_resp) as mock_post:
        client._trigger_single('season:5:2', 'missing', 'Example Series', 1, 1)

    assert mock_post.call_args_list[0].kwargs['timeout'] == ArrClient.REQUEST_TIMEOUT


def test_trigger_single_uses_fixed_request_timeout() -> None:
    """Test that search command POSTs use the fixed REQUEST_TIMEOUT, not fetch_timeout."""
    client = _build_client(120)
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None

    with patch.object(client.session, 'post', return_value=mock_resp) as mock_post:
        client._trigger_single(1, 'missing', 'Example Movie', 1, 1)

    assert mock_post.call_args_list[0].kwargs['timeout'] == ArrClient.REQUEST_TIMEOUT

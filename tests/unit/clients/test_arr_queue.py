"""Tests for ArrClient.get_active_queue_depth."""

import logging
from collections.abc import Callable
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from tests.builders import ClientBuilder
from tests.builders import QueueRecordBuilder

_get_active_queue_depth_cases = {
    'counts_active_only': {
        'statuses': ['downloading', 'queued', 'paused', 'delay', 'importPending', 'completed', 'failed', 'warning'],
        'expected_depth': 4,
    },
    'mixed_case_status': {
        'statuses': ['Downloading', 'QUEUED', 'completed'],
        'expected_depth': 2,
    },
    'empty_queue': {
        'statuses': [],
        'expected_depth': 0,
    },
}


def _paged_queue_responses(records: list[dict]) -> Callable[..., MagicMock]:
    """Return a session.get side effect that paginates queue records."""

    def side_effect(*_args: object, **kwargs: object) -> MagicMock:
        params = kwargs.get('params', {})
        page = params.get('page', 1)
        page_size = params['pageSize']
        start = (page - 1) * page_size
        chunk = records[start : start + page_size]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'records': chunk}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    return side_effect


@pytest.mark.parametrize(
    'statuses, expected_depth',
    [(case['statuses'], case['expected_depth']) for case in _get_active_queue_depth_cases.values()],
    ids=list(_get_active_queue_depth_cases.keys()),
)
def test_get_active_queue_depth(statuses: list[str], expected_depth: int) -> None:
    """Test that get_active_queue_depth counts only active-status records, case-insensitively."""
    records = [QueueRecordBuilder().with_id(idx).with_status(status).build() for idx, status in enumerate(statuses)]
    client = ClientBuilder().radarr().with_settings(max_queue_size=10).build()
    with patch.object(client.session, 'get', side_effect=_paged_queue_responses(records)):
        assert client.get_active_queue_depth() == expected_depth


def test_get_active_queue_depth_paginates() -> None:
    """Test that get_active_queue_depth sums active records across multiple pages."""
    records = [QueueRecordBuilder().with_id(idx).with_status('downloading').build() for idx in range(2500)]
    client = ClientBuilder().radarr().with_settings(max_queue_size=10, fetch_page_size=1000).build()
    with patch.object(client.session, 'get', side_effect=_paged_queue_responses(records)) as mock_get:
        assert client.get_active_queue_depth() == 2500
    assert len(mock_get.call_args_list) == 3


def test_get_active_queue_depth_returns_none_on_error(caplog: pytest.LogCaptureFixture) -> None:
    """Test that a request failure yields None (the fail-closed signal) and logs the error."""
    client = ClientBuilder().radarr().with_settings(max_queue_size=10).build()
    with patch.object(client.session, 'get', side_effect=requests.ConnectionError('boom')):
        with caplog.at_level(logging.ERROR):
            assert client.get_active_queue_depth() is None
    assert 'Failed to fetch queue' in caplog.text


def test_get_active_queue_depth_uses_v1_endpoint_for_lidarr() -> None:
    """Test that Lidarr queries the /api/v1/queue endpoint."""
    client = ClientBuilder().lidarr().with_settings(max_queue_size=10).build()
    with patch.object(client.session, 'get', side_effect=_paged_queue_responses([])) as mock_get:
        client.get_active_queue_depth()
    assert mock_get.call_args_list[0].args[0].endswith('/api/v1/queue')

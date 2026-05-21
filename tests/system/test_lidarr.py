"""System tests for LidarrClient end-to-end flow using realistic HTTP fixtures."""

import logging
from unittest.mock import patch

import pytest
import requests

from rangarr.main import _run_search_cycle
from rangarr.main import build_arr_clients
from tests.helpers import load_fixture
from tests.system.helpers import _make_lidarr_router


def test_full_search_cycle_with_lidarr(caplog: pytest.LogCaptureFixture) -> None:
    """Test a full search cycle with a real LidarrClient and fixture HTTP responses."""
    config = {
        'instances': {
            'lidarr': [
                {
                    'name': 'test-lidarr',
                    'url': 'http://localhost:8686',
                    'api_key': 'testkey',
                    'enabled': True,
                    'weight': 1.0,
                }
            ]
        },
        'global_settings': {
            'missing_batch_size': 5,
            'upgrade_batch_size': 0,
            'stagger_interval_seconds': 0,
            'retry_interval_days': 0,
            'search_order': 'last_searched_ascending',
            'dry_run': False,
        },
    }

    router = _make_lidarr_router(
        load_fixture('lidarr', 'api_v1_tag.json'),
        load_fixture('lidarr', 'api_v1_wanted_missing.json'),
        load_fixture('lidarr', 'api_v1_wanted_cutoff.json'),
    )

    with patch.object(requests.Session, 'request', side_effect=router):
        clients = build_arr_clients(config['instances'], config['global_settings'])
        with caplog.at_level(logging.INFO):
            _run_search_cycle(clients, config['global_settings'])

    assert len(clients) == 1
    assert '--- Starting search cycle ---' in caplog.text
    assert 'Searching' in caplog.text

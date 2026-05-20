"""System tests for multi-instance search cycles using realistic HTTP fixtures."""

import logging
from typing import Any
from unittest.mock import patch

import pytest
import requests

from rangarr.main import _run_search_cycle
from rangarr.main import build_arr_clients
from tests.helpers import load_fixture
from tests.system.helpers import _make_lidarr_router
from tests.system.helpers import _make_radarr_router
from tests.system.helpers import _make_sonarr_router


def _three_instance_config(interleave: bool, interleave_types: bool = True) -> dict:
    """Return a config dict for Radarr + Sonarr + Lidarr with upgrade disabled."""
    return {
        'instances': {
            'radarr': [
                {
                    'name': 'test-radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'testkey',
                    'enabled': True,
                    'weight': 1.0,
                }
            ],
            'sonarr': [
                {
                    'name': 'test-sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'testkey',
                    'enabled': True,
                    'weight': 1.0,
                }
            ],
            'lidarr': [
                {
                    'name': 'test-lidarr',
                    'url': 'http://localhost:8686',
                    'api_key': 'testkey',
                    'enabled': True,
                    'weight': 1.0,
                }
            ],
        },
        'global_settings': {
            'dry_run': False,
            'interleave_instances': interleave,
            'interleave_types': interleave_types,
            'missing_batch_size': 9,
            'retry_interval_days': 0,
            'search_order': 'last_searched_ascending',
            'stagger_interval_seconds': 0,
            'upgrade_batch_size': 0,
        },
    }


def test_full_search_cycle_three_instances_grouped(caplog: pytest.LogCaptureFixture) -> None:
    """Test search cycle groups all items per instance when interleave_instances is False."""
    config = _three_instance_config(interleave=False)

    radarr_router = _make_radarr_router(
        load_fixture('radarr', 'api_v3_tag.json'),
        load_fixture('radarr', 'api_v3_qualityprofile.json'),
        load_fixture('radarr', 'api_v3_wanted_missing.json'),
        load_fixture('radarr', 'api_v3_wanted_cutoff.json'),
    )
    sonarr_router = _make_sonarr_router(
        load_fixture('sonarr', 'api_v3_tag.json'),
        load_fixture('sonarr', 'api_v3_wanted_missing.json'),
        load_fixture('sonarr', 'api_v3_wanted_cutoff.json'),
    )
    lidarr_router = _make_lidarr_router(
        load_fixture('lidarr', 'api_v1_tag.json'),
        load_fixture('lidarr', 'api_v1_wanted_missing.json'),
        load_fixture('lidarr', 'api_v1_wanted_cutoff.json'),
    )

    def combined_router(method: str, url: str, **kwargs: Any) -> Any:
        """Route requests to the appropriate instance router by URL."""
        router = radarr_router if '7878' in url else sonarr_router if '8989' in url else lidarr_router
        return router(method, url, **kwargs)

    with patch.object(requests.Session, 'request', side_effect=combined_router):
        clients = build_arr_clients(config['instances'], config['global_settings'])
        with caplog.at_level(logging.INFO):
            _run_search_cycle(clients, config['global_settings'])

    assert len(clients) == 3
    assert '--- Starting search cycle ---' in caplog.text
    assert 'Total search batch: 9 item(s)' in caplog.text


def test_full_search_cycle_three_instances_interleaved(caplog: pytest.LogCaptureFixture) -> None:
    """Test search cycle interleaves items across instances when interleave_instances is True."""
    config = _three_instance_config(interleave=True)

    radarr_router = _make_radarr_router(
        load_fixture('radarr', 'api_v3_tag.json'),
        load_fixture('radarr', 'api_v3_qualityprofile.json'),
        load_fixture('radarr', 'api_v3_wanted_missing.json'),
        load_fixture('radarr', 'api_v3_wanted_cutoff.json'),
    )
    sonarr_router = _make_sonarr_router(
        load_fixture('sonarr', 'api_v3_tag.json'),
        load_fixture('sonarr', 'api_v3_wanted_missing.json'),
        load_fixture('sonarr', 'api_v3_wanted_cutoff.json'),
    )
    lidarr_router = _make_lidarr_router(
        load_fixture('lidarr', 'api_v1_tag.json'),
        load_fixture('lidarr', 'api_v1_wanted_missing.json'),
        load_fixture('lidarr', 'api_v1_wanted_cutoff.json'),
    )

    def combined_router(method: str, url: str, **kwargs: Any) -> Any:
        """Route requests to the appropriate instance router by URL."""
        router = radarr_router if '7878' in url else sonarr_router if '8989' in url else lidarr_router
        return router(method, url, **kwargs)

    with patch.object(requests.Session, 'request', side_effect=combined_router):
        clients = build_arr_clients(config['instances'], config['global_settings'])
        with caplog.at_level(logging.INFO):
            _run_search_cycle(clients, config['global_settings'])

    assert len(clients) == 3
    assert '--- Starting search cycle ---' in caplog.text
    assert 'Total search batch: 9 item(s)' in caplog.text

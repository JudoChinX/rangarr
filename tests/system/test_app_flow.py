"""System tests for end-to-end app flow using realistic HTTP fixtures."""

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests

from rangarr.main import _run_search_cycle
from rangarr.main import build_arr_clients

_FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures'


def _load_fixture(subdir: str, filename: str) -> dict | list:
    """Load a JSON fixture file from the tests/fixtures directory."""
    fixture_path = _FIXTURES_DIR / subdir / filename
    with fixture_path.open() as fobj:
        return json.load(fobj)


def _make_radarr_router(
    tag_data: list,
    quality_data: list,
    missing_data: dict,
    cutoff_data: dict,
) -> Any:
    """Return a request router that serves Radarr fixture data by URL."""

    def route(method: str, url: str, **_kwargs: Any) -> Any:
        """Route a request to the appropriate fixture response."""
        response = MagicMock()
        response.raise_for_status.return_value = None

        if '/api/v3/tag' in url:
            response.json.return_value = tag_data
        elif '/api/v3/qualityprofile' in url:
            response.json.return_value = quality_data
        elif '/api/v3/wanted/missing' in url:
            response.json.return_value = missing_data
        elif '/api/v3/wanted/cutoff' in url:
            response.json.return_value = cutoff_data
        elif '/api/v3/movie' in url and method.upper() == 'GET':
            response.json.return_value = []
        elif '/api/v3/command' in url and method.upper() == 'POST':
            response.json.return_value = {'id': 1}
        else:
            raise ValueError(f'Unexpected URL: {url}')

        return response

    return route


def test_full_search_cycle_with_radarr(caplog: pytest.LogCaptureFixture) -> None:
    """Test a full search cycle with a real RadarrClient and fixture HTTP responses."""
    tag_data = _load_fixture('radarr', 'api_v3_tag.json')
    quality_data = _load_fixture('radarr', 'api_v3_qualityprofile.json')
    missing_data = _load_fixture('radarr', 'api_v3_wanted_missing.json')
    cutoff_data = _load_fixture('radarr', 'api_v3_wanted_cutoff.json')

    config = {
        'instances': {
            'radarr': [
                {
                    'name': 'test-radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'testkey',
                    'enabled': True,
                    'weight': 1.0,
                }
            ]
        },
        'global_settings': {
            'missing_batch_size': 5,
            'upgrade_batch_size': 5,
            'stagger_interval_seconds': 0,
            'retry_interval_days': 0,
            'search_order': 'last_searched_ascending',
            'dry_run': False,
        },
    }

    router = _make_radarr_router(tag_data, quality_data, missing_data, cutoff_data)

    with patch.object(requests.Session, 'request', side_effect=router):
        clients = build_arr_clients(config['instances'], config['global_settings'])
        with caplog.at_level(logging.INFO):
            _run_search_cycle(clients, config['global_settings'])

    assert len(clients) == 1
    assert '--- Starting search cycle ---' in caplog.text
    assert 'Triggering search' in caplog.text

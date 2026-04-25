"""Script to generate sanitized test fixtures from live *arr API instances."""

import json
import os
from pathlib import Path

import requests
import yaml

_CONFIG_PATH = '/mnt/docker/rangarr/config.yaml'
_FIXTURE_DIR = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures'
_SENSITIVE_KEYS = ('apiKey', 'api_key', 'host', 'label', 'url')
_SUPPORTED_TYPES = {'radarr', 'sonarr', 'lidarr'}
_TIMEOUT = 10


def _fetch_and_save(name: str, host: str, api_key: str, endpoint: str, target_dir: Path) -> None:
    """Fetch one endpoint from a live instance and save sanitized JSON to fixtures."""
    print(f'Fetching {endpoint} from {name}...')
    headers = {'X-Api-Key': api_key}
    try:
        resp = requests.get(f'{host}{endpoint}', headers=headers, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = _sanitize(resp.json())
        filename = endpoint.strip('/').replace('/', '_') + '.json'
        filepath = target_dir / filename
        with open(filepath, 'w', encoding='utf-8') as fle:
            json.dump(data, fle, indent=2)
        print(f'  Saved to {filepath}')
    except requests.RequestException as err:
        print(f'  Failed: {err}')


def _sanitize(data: object) -> object:
    """Recursively remove sensitive fields from API response data."""
    if isinstance(data, list):
        result: object = [_sanitize(item) for item in data]
    elif isinstance(data, dict):
        result = {key: ('REDACTED' if key in _SENSITIVE_KEYS else _sanitize(val)) for key, val in data.items()}
    else:
        result = data
    return result


def main() -> None:
    """Fetch real-world API responses and save sanitized fixtures to tests/fixtures/.

    Reads instance configuration from the live config file, iterates over all
    supported *arr instances, and writes sanitized JSON responses for each
    relevant endpoint into the appropriate fixture subdirectory.
    """
    if not os.path.exists(_CONFIG_PATH):
        print(f'Config not found at {_CONFIG_PATH}')
        return

    with open(_CONFIG_PATH, encoding='utf-8') as fle:
        config = yaml.safe_load(fle)

    for name, inst in config.get('instances', {}).items():
        itype = inst.get('type')
        if itype not in _SUPPORTED_TYPES:
            continue

        target_dir = _FIXTURE_DIR / itype
        target_dir.mkdir(parents=True, exist_ok=True)

        api_version = 'v1' if itype == 'lidarr' else 'v3'
        endpoints = [
            f'/api/{api_version}/wanted/missing',
            f'/api/{api_version}/wanted/cutoff',
            f'/api/{api_version}/qualityprofile',
            f'/api/{api_version}/tag',
        ]

        for endpoint in endpoints:
            _fetch_and_save(name, inst['host'], inst['api_key'], endpoint, target_dir)


if __name__ == '__main__':
    main()

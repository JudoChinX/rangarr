"""E2E system tests using real Docker instances of Sonarr, Radarr, Lidarr, and Whisparr."""

import os
import socket
import sqlite3
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Generator
from typing import Any

import pytest
import requests

from rangarr.main import _run_search_cycle
from rangarr.main import build_arr_clients

_COMPOSE_NETWORK: str = 'rangarr-test-net'
_API_VERSIONS: dict[str, str] = {
    'lidarr': 'v1',
    'radarr': 'v3',
    'sonarr': 'v3',
    'whisparr': 'v3',
}
_COMMAND_CHECKED_APPS: tuple[str, ...] = ('lidarr', 'radarr', 'sonarr')
_COMMAND_POLL_INTERVAL: int = 1
_COMMAND_POLL_TIMEOUT: int = 30
_COMPOSE_PATH: str = os.path.join(os.path.dirname(__file__), 'compose.yaml')
_CONTAINER_NAMES: dict[str, str] = {
    'lidarr': 'rangarr-test-lidarr',
    'radarr': 'rangarr-test-radarr',
    'sonarr': 'rangarr-test-sonarr',
    'whisparr': 'rangarr-test-whisparr',
}
_DB_PATHS: dict[str, str] = {
    'lidarr': '/config/lidarr.db',
    'radarr': '/config/radarr.db',
    'sonarr': '/config/sonarr.db',
    'whisparr': '/config/whisparr3.db',
}
_HTTP_TIMEOUT: int = 10
_SERVICES: dict[str, int] = {
    'lidarr': 8686,
    'radarr': 7878,
    'sonarr': 8989,
    'whisparr': 6969,
}


def _container_url(container_name: str, port: int) -> str:
    """Return a base URL for a container using its Docker network IP."""
    res = subprocess.run(
        ['docker', 'inspect', '-f', '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}', container_name],
        capture_output=True,
        text=True,
        check=True,
    )
    return f'http://{res.stdout.strip()}:{port}'


def _extract_api_key(container_name: str) -> str:
    """Extract the API key from an Arr container's config.xml."""
    result = subprocess.run(
        ['docker', 'exec', container_name, 'cat', '/config/config.xml'],
        capture_output=True,
        text=True,
        check=True,
    )
    tree = ET.fromstring(result.stdout)
    api_key = tree.findtext('ApiKey')
    assert api_key, f'No ApiKey found in {container_name} config.xml'
    return api_key


def _poll_command(url: str, api_key: str, command_id: int, api_version: str = 'v3') -> dict[str, Any]:
    """Poll an Arr command endpoint until it reaches a terminal state."""
    for _ in range(_COMMAND_POLL_TIMEOUT):
        resp = requests.get(
            f'{url}/api/{api_version}/command/{command_id}',
            headers={'X-Api-Key': api_key},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if data['status'] in ('completed', 'failed'):
            return data
        time.sleep(_COMMAND_POLL_INTERVAL)
    raise TimeoutError(f'Command {command_id} did not reach a terminal state in {_COMMAND_POLL_TIMEOUT}s')


def _wait_for_ping(url: str, timeout: int = 120) -> None:
    """Poll /ping until the service responds, raising TimeoutError on failure."""
    for _ in range(timeout):
        try:
            resp = requests.get(f'{url}/ping', timeout=5)
            if resp.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise TimeoutError(f'Service at {url} did not become healthy within {timeout}s')


@pytest.fixture(scope='session')
def api_keys(docker_env: dict[str, str]) -> dict[str, str]:
    """Extract API keys from all running Arr containers."""
    return {service: _extract_api_key(_CONTAINER_NAMES[service]) for service in docker_env}


@pytest.fixture(scope='session')
def docker_env() -> Generator[dict[str, str], None, None]:
    """Start Docker Arr containers and yield a mapping of service name to base URL."""
    subprocess.run(
        ['docker', 'compose', '-f', _COMPOSE_PATH, 'up', '-d', '--wait'],
        check=True,
    )
    # Connect this runner to the compose network so container IPs are reachable.
    # On containerized CI runners the hostname is the short container ID; on bare
    # metal this fails silently and the bridge is already routable.
    subprocess.run(
        ['docker', 'network', 'connect', _COMPOSE_NETWORK, socket.gethostname()],
        capture_output=True,
        check=False,
    )

    urls: dict[str, str] = {
        service: _container_url(_CONTAINER_NAMES[service], port) for service, port in _SERVICES.items()
    }

    yield urls

    subprocess.run(
        ['docker', 'network', 'disconnect', _COMPOSE_NETWORK, socket.gethostname()],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ['docker', 'compose', '-f', _COMPOSE_PATH, 'down'],
        check=True,
    )


@pytest.fixture(scope='session')
def seeded_env(docker_env: dict[str, str]) -> None:
    """Seed each app's SQLite database with test records, then restart to reload."""
    fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
    for service in docker_env:
        container = _CONTAINER_NAMES[service]
        db_path = _DB_PATHS[service]
        sql_path = os.path.join(fixtures_dir, service, 'seed.sql')
        # Stop before touching the DB to prevent live writes during copy.
        subprocess.run(['docker', 'stop', container], check=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            host_db = os.path.join(tmpdir, 'app.db')
            subprocess.run(['docker', 'cp', f'{container}:{db_path}', host_db], check=True)
            for ext in ('-wal', '-shm'):
                subprocess.run(
                    ['docker', 'cp', f'{container}:{db_path}{ext}', f'{host_db}{ext}'],
                    capture_output=True,
                    check=False,
                )
            conn = sqlite3.connect(host_db)
            try:
                with open(sql_path, encoding='utf-8') as sql_file:
                    conn.executescript(sql_file.read())
                conn.commit()
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                conn.commit()
            finally:
                conn.close()
            subprocess.run(['docker', 'cp', host_db, f'{container}:{db_path}'], check=True)
            for ext in ('-wal', '-shm'):
                wal_path = f'{host_db}{ext}'
                if os.path.exists(wal_path):
                    subprocess.run(
                        ['docker', 'cp', wal_path, f'{container}:{db_path}{ext}'],
                        check=True,
                    )
        subprocess.run(['docker', 'start', container], check=True)
        new_url = _container_url(container, _SERVICES[service])
        docker_env[service] = new_url
        _wait_for_ping(new_url)
        subprocess.run(['docker', 'exec', container, 'mkdir', '-p', '/tmp/media'], check=True)


def test_api_connectivity(docker_env: dict[str, str], api_keys: dict[str, str]) -> None:
    """Verify API key extraction and connectivity to each app's system/status endpoint."""
    for service, url in docker_env.items():
        ver = _API_VERSIONS[service]
        resp = requests.get(
            f'{url}/api/{ver}/system/status',
            headers={'X-Api-Key': api_keys[service]},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        assert 'version' in resp.json()


def test_containers_healthy(docker_env: dict[str, str]) -> None:
    """Verify all Arr containers are running and their /ping endpoints respond."""
    for service, url in docker_env.items():
        res = subprocess.run(
            ['curl', '-fs', f'{url}/ping'],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res.returncode == 0, f'{service} ping failed: {res.stderr}'
        assert 'OK' in res.stdout or 'pong' in res.stdout.lower() or res.stdout.strip() == ''


def test_search_cycle_runs(
    docker_env: dict[str, str],
    api_keys: dict[str, str],
    seeded_env: None,  # pylint: disable=unused-argument
) -> None:
    """_run_search_cycle dispatches and completes commands against seeded Sonarr, Radarr, Lidarr."""
    instances_config = {
        app: [{'name': f'docker-{app}', 'url': url, 'api_key': api_keys[app], 'enabled': True, 'weight': 1.0}]
        for app, url in docker_env.items()
    }
    global_settings = {
        'dry_run': False,
        'missing_batch_size': 3,
        'retry_interval_days': 0,
        'search_order': 'last_searched_ascending',
        'stagger_interval_seconds': 0,
        'upgrade_batch_size': 0,
    }
    clients = build_arr_clients(instances_config, global_settings)
    _run_search_cycle(clients, global_settings)

    for app in _COMMAND_CHECKED_APPS:
        url = docker_env[app]
        ver = _API_VERSIONS[app]
        api_key = api_keys[app]
        resp = requests.get(
            f'{url}/api/{ver}/command',
            headers={'X-Api-Key': api_key},
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        command_ids = [cmd['id'] for cmd in resp.json()]
        assert len(command_ids) > 0, f'No commands triggered for {app}'
        for cmd_id in command_ids:
            result = _poll_command(url, api_key, cmd_id, ver)
            assert result['status'] == 'completed', f'{app} command {cmd_id} ended with status {result["status"]}'

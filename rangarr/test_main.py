"""Tests for main.py entry point and search logic."""
# pylint: disable=redefined-outer-name

import datetime
import logging
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from rangarr.config_parser import get_setting_default
from rangarr.main import build_arr_clients
from rangarr.main import verify_arr_clients


@pytest.fixture
def mock_client() -> Mock:
    """Create a mock ArrClient for testing."""
    client = Mock()
    client.name = 'test-instance'
    client.weight = 1.0
    client.get_media_to_search = Mock(return_value=[])
    client.trigger_search = Mock()
    return client


def _make_run_config(
    missing_batch_size: Any = None,
    upgrade_batch_size: Any = None,
    active_hours: str = '',
    dry_run: bool = False,
) -> Any:
    """Build a minimal valid run config dict with optional batch size overrides."""
    return {
        'global_settings': {
            'run_interval_minutes': 60,
            'missing_batch_size': missing_batch_size
            if missing_batch_size is not None
            else get_setting_default('missing_batch_size'),
            'upgrade_batch_size': upgrade_batch_size
            if upgrade_batch_size is not None
            else get_setting_default('upgrade_batch_size'),
            'stagger_interval_seconds': 5,
            'retry_interval_days': 0,
            'search_order': 'alphabetical_ascending',
            'active_hours': active_hours,
            'dry_run': dry_run,
        },
        'instances': {},
    }


_build_clients_cases = {
    'empty': {
        'instances_config': {},
        'settings': {},
        'expected_count': 0,
    },
    'single_radarr': {
        'instances_config': {
            'radarr': [
                {
                    'name': 'Test Radarr',
                    'url': 'http://test',
                    'api_key': 'abc123',
                    'enabled': True,
                }
            ]
        },
        'settings': {},
        'expected_count': 1,
        'expected_name': 'Test Radarr',
        'expected_weight': 1.0,
    },
    'multiple_with_weights': {
        'instances_config': {
            'radarr': [
                {
                    'name': 'Radarr One',
                    'url': 'http://test',
                    'api_key': 'key1',
                    'weight': 2.0,
                    'enabled': True,
                }
            ],
            'sonarr': [
                {
                    'name': 'Sonarr One',
                    'url': 'http://test',
                    'api_key': 'key2',
                    'weight': 1.5,
                    'enabled': True,
                }
            ],
        },
        'settings': {},
        'expected_count': 2,
        'expected_weights': [2.0, 1.5],
    },
    'with_two_instances': {
        'instances_config': {
            'radarr': [
                {
                    'name': 'Active Radarr',
                    'url': 'http://test',
                    'api_key': 'key1',
                    'enabled': True,
                },
                {
                    'name': 'Second Radarr',
                    'url': 'http://localhost:7879',
                    'api_key': 'key2',
                    'enabled': True,
                },
            ]
        },
        'settings': {},
        'expected_count': 2,
    },
}

_run_cases = {
    'loads_volume_config_first': {
        'config_file_exists': 'config/config.yaml',
        'has_clients': True,
        'expected_config_path': 'config/config.yaml',
    },
    'falls_back_to_local_config': {
        'config_file_exists': 'config.yaml',
        'has_clients': True,
        'expected_config_path': 'config.yaml',
    },
    'exits_when_no_config_found': {
        'config_file_exists': None,
        'has_clients': False,
        'expected_exit_code': 1,
    },
    'exits_when_no_clients': {
        'config_file_exists': 'config.yaml',
        'has_clients': False,
        'expected_exit_code': 1,
    },
    'exits_when_config_is_invalid': {
        'config_file_exists': 'config.yaml',
        'has_clients': False,
        'load_config_raises': True,
        'expected_exit_code': 1,
    },
    'continues_on_file_not_found': {
        'config_file_exists': 'config/config.yaml',
        'has_clients': False,
        'load_config_raises': 'FileNotFoundError',
        'expected_exit_code': 1,
    },
    'triggers_search_when_items_found': {
        'config_file_exists': 'config.yaml',
        'has_clients': True,
        'media_to_return': [(1, 'missing', 'Movie A')],
        'expected_trigger_called': True,
    },
}


@pytest.mark.parametrize(
    'instances_config, settings, expected_count, expected_name, expected_weights',
    [
        (
            case['instances_config'],
            case['settings'],
            case['expected_count'],
            case.get('expected_name'),
            case.get('expected_weights'),
        )
        for case in _build_clients_cases.values()
    ],
    ids=list(_build_clients_cases.keys()),
)
def test_build_arr_clients(
    instances_config: Any,
    settings: Any,
    expected_count: Any,
    expected_name: Any,
    expected_weights: Any,
) -> None:
    """Test build_arr_clients instantiates clients correctly."""
    clients = build_arr_clients(instances_config, settings)
    assert len(clients) == expected_count

    if expected_count > 0:
        if expected_name:
            assert clients[0].name == expected_name
        if expected_weights:
            for index, weight in enumerate(expected_weights):
                assert clients[index].weight == weight


def test_build_arr_clients_instance_settings_override_global() -> None:
    """Test that instance-level settings override global settings for that client only."""
    instances_config = {
        'sonarr': [
            {
                'name': 'Sonarr SP',
                'url': 'http://test',
                'api_key': 'key1',
                'season_packs': True,
            }
        ]
    }
    global_settings = {'season_packs': False}
    clients = build_arr_clients(instances_config, global_settings)
    assert len(clients) == 1
    assert clients[0].season_packs is True
    assert global_settings['season_packs'] is False


@pytest.mark.parametrize(
    'config_file_exists, has_clients, expected_config_path, expected_exit_code, '
    'load_config_raises, media_to_return, expected_trigger_called',
    [
        (
            case.get('config_file_exists'),
            case.get('has_clients'),
            case.get('expected_config_path'),
            case.get('expected_exit_code'),
            case.get('load_config_raises', False),
            case.get('media_to_return'),
            case.get('expected_trigger_called', False),
        )
        for case in _run_cases.values()
    ],
    ids=list(_run_cases.keys()),
)
def test_run(
    config_file_exists: Any,
    has_clients: Any,
    expected_config_path: Any,
    expected_exit_code: Any,
    load_config_raises: Any,
    media_to_return: Any,
    expected_trigger_called: Any,
) -> None:
    """Test run function loads config and executes searches."""

    def is_file_mock(path_obj: Any) -> Any:
        return str(path_obj) == config_file_exists if config_file_exists else False

    run_client = MagicMock()
    run_client.name = 'Test'
    run_client.weight = 1.0
    run_client.get_media_to_search.return_value = media_to_return or []

    with (
        patch('pathlib.Path.is_file', new=is_file_mock),
        patch('rangarr.main.load_config') as mock_load,
        patch('rangarr.main.build_arr_clients') as mock_build,
        patch('rangarr.main.verify_arr_clients', side_effect=lambda clients: clients),
    ):
        if load_config_raises == 'FileNotFoundError':
            mock_load.side_effect = FileNotFoundError()
        elif load_config_raises:
            mock_load.side_effect = ValueError('bad config')
        elif config_file_exists is not None:
            mock_load.return_value = _make_run_config()

        mock_build.return_value = [run_client] if has_clients else []

        from rangarr.main import run

        if expected_exit_code:
            with pytest.raises(SystemExit) as exc_info:
                run()
            assert exc_info.value.code == expected_exit_code
        else:
            with (
                patch('rangarr.main.time.sleep', side_effect=KeyboardInterrupt),
                pytest.raises(KeyboardInterrupt),
            ):
                run()
            if expected_config_path:
                mock_load.assert_called_once_with(expected_config_path)
            if expected_trigger_called:
                run_client.trigger_search.assert_called_once_with(media_to_return)


_is_within_active_hours_cases = {
    'normal_window_inside': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(12, 0),
        'expected': True,
    },
    'normal_window_outside': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(21, 0),
        'expected': False,
    },
    'normal_window_at_start': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(8, 0),
        'expected': True,
    },
    'normal_window_at_end': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(20, 0),
        'expected': False,
    },
    'cross_midnight_inside_after_start': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(23, 0),
        'expected': True,
    },
    'cross_midnight_inside_before_end': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(3, 0),
        'expected': True,
    },
    'cross_midnight_outside_gap': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(12, 0),
        'expected': False,
    },
    'cross_midnight_at_start': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(22, 0),
        'expected': True,
    },
    'cross_midnight_at_end': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(6, 0),
        'expected': False,
    },
}


@pytest.mark.parametrize(
    'start, end, now, expected',
    [(case['start'], case['end'], case['now'], case['expected']) for case in _is_within_active_hours_cases.values()],
    ids=list(_is_within_active_hours_cases.keys()),
)
def test_is_within_active_hours(start: datetime.time, end: datetime.time, now: datetime.time, expected: bool) -> None:
    """Test _is_within_active_hours handles normal and cross-midnight windows."""
    from rangarr.main import _is_within_active_hours

    assert _is_within_active_hours(start, end, now) == expected


_parse_active_hours_cases = {
    'normal_window': {
        'active_hours': '08:00-20:00',
        'expected_start': datetime.time(8, 0),
        'expected_end': datetime.time(20, 0),
    },
    'cross_midnight_window': {
        'active_hours': '22:00-06:00',
        'expected_start': datetime.time(22, 0),
        'expected_end': datetime.time(6, 0),
    },
}


@pytest.mark.parametrize(
    'active_hours, expected_start, expected_end',
    [
        (case['active_hours'], case['expected_start'], case['expected_end'])
        for case in _parse_active_hours_cases.values()
    ],
    ids=list(_parse_active_hours_cases.keys()),
)
def test_parse_active_hours(active_hours: str, expected_start: datetime.time, expected_end: datetime.time) -> None:
    """Test parse_active_hours parses HH:MM-HH:MM strings into datetime.time pairs."""
    from rangarr.config_parser import parse_active_hours

    start, end = parse_active_hours(active_hours)
    assert start == expected_start
    assert end == expected_end


_fixed_today = datetime.date(2026, 1, 1)

_seconds_until_window_open_cases = {
    'window_opens_later_today': {
        'start': datetime.time(22, 0),
        'now': datetime.time(21, 0),
        'expected_seconds': 3600,
    },
    'window_opens_tomorrow': {
        'start': datetime.time(22, 0),
        'now': datetime.time(23, 0),
        'expected_seconds': 82800,
    },
    'sub_second_before_window_rounds_up_to_one': {
        'start': datetime.time(6, 0, 0),
        'now': datetime.time(5, 59, 59, 999999),
        'expected_seconds': 1,
    },
}


@pytest.mark.parametrize(
    'start, now, expected_seconds',
    [(case['start'], case['now'], case['expected_seconds']) for case in _seconds_until_window_open_cases.values()],
    ids=list(_seconds_until_window_open_cases.keys()),
)
def test_seconds_until_window_open(start: datetime.time, now: datetime.time, expected_seconds: int) -> None:
    """Test _seconds_until_window_open returns correct seconds until window start."""
    from rangarr.main import _seconds_until_window_open

    assert _seconds_until_window_open(start, now, today=_fixed_today) == expected_seconds


def test_run_skips_cycle_outside_active_hours() -> None:
    """Test run skips the search cycle and sleeps when outside the active hours window."""
    run_client = MagicMock()
    run_client.name = 'Test'
    run_client.weight = 1.0
    run_client.get_media_to_search.return_value = []

    settings = _make_run_config(active_hours='22:00-06:00')

    fixed_outside_time = datetime.time(12, 0)

    sleep_calls = []

    def fake_sleep(secs: float) -> None:
        sleep_calls.append(secs)
        raise KeyboardInterrupt

    with (
        patch('pathlib.Path.is_file', return_value=True),
        patch('rangarr.main.load_config', return_value=settings),
        patch('rangarr.main.build_arr_clients', return_value=[run_client]),
        patch('rangarr.main.datetime') as mock_dt,
        patch('rangarr.main.time.sleep', side_effect=fake_sleep),
        pytest.raises(KeyboardInterrupt),
    ):
        mock_dt.datetime.now.return_value.time.return_value = fixed_outside_time
        mock_dt.date.today.return_value = datetime.date(2026, 4, 13)
        mock_dt.datetime.combine = datetime.datetime.combine
        mock_dt.timedelta = datetime.timedelta
        mock_dt.time = datetime.time

        from rangarr.main import run

        run()

    run_client.get_media_to_search.assert_not_called()
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 36000


def test_run_executes_cycle_inside_active_hours() -> None:
    """Test run executes the search cycle normally when inside the active hours window."""
    run_client = MagicMock()
    run_client.name = 'Test'
    run_client.weight = 1.0
    run_client.get_media_to_search.return_value = []

    settings = _make_run_config(active_hours='22:00-06:00')

    fixed_inside_time = datetime.time(23, 0)

    with (
        patch('pathlib.Path.is_file', return_value=True),
        patch('rangarr.main.load_config', return_value=settings),
        patch('rangarr.main.build_arr_clients', return_value=[run_client]),
        patch('rangarr.main.datetime') as mock_dt,
        patch('rangarr.main.time.sleep', side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        mock_dt.datetime.now.return_value.time.return_value = fixed_inside_time
        mock_dt.time = datetime.time

        from rangarr.main import run

        run()

    run_client.get_media_to_search.assert_called_once()


def test_run_no_active_hours_always_executes() -> None:
    """Test run executes the search cycle at any time when active_hours is empty."""
    run_client = MagicMock()
    run_client.name = 'Test'
    run_client.weight = 1.0
    run_client.get_media_to_search.return_value = []

    settings = _make_run_config()

    with (
        patch('pathlib.Path.is_file', return_value=True),
        patch('rangarr.main.load_config', return_value=settings),
        patch('rangarr.main.build_arr_clients', return_value=[run_client]),
        patch('rangarr.main.time.sleep', side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        from rangarr.main import run

        run()

    run_client.get_media_to_search.assert_called_once()


def test_run_search_cycle_both_disabled(mock_client: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that search cycle reports no media when both batch types are disabled."""
    from rangarr.main import _run_search_cycle

    settings = {
        'interleave_instances': False,
        'missing_batch_size': 0,
        'stagger_interval_seconds': 30,
        'upgrade_batch_size': 0,
    }

    with caplog.at_level(logging.INFO):
        _run_search_cycle([mock_client], settings)

    assert 'No media to search this cycle across all instances.' in caplog.text
    mock_client.get_media_to_search.assert_called_once_with(0, 0)
    mock_client.trigger_search.assert_not_called()


def test_run_search_cycle_missing_disabled(mock_client: Mock) -> None:
    """Test that search cycle still processes upgrade items when missing is disabled."""
    from rangarr.main import _run_search_cycle

    upgrade_item = (1, 'upgrade', 'Movie 1')
    mock_client.get_media_to_search = Mock(return_value=[upgrade_item])

    settings = {
        'interleave_instances': False,
        'missing_batch_size': 0,
        'stagger_interval_seconds': 30,
        'upgrade_batch_size': 10,
    }

    _run_search_cycle([mock_client], settings)

    mock_client.get_media_to_search.assert_called_once_with(0, 10)
    mock_client.trigger_search.assert_called_once_with([upgrade_item])


def test_run_search_cycle_unlimited(mock_client: Mock) -> None:
    """Test that search cycle passes -1 for unlimited batch size."""
    from rangarr.main import _run_search_cycle

    mock_client.get_media_to_search = Mock(
        return_value=[
            (1, 'missing', 'Movie 1'),
            (2, 'missing', 'Movie 2'),
        ]
    )

    settings = {
        'interleave_instances': False,
        'missing_batch_size': -1,
        'stagger_interval_seconds': 0,
        'upgrade_batch_size': 10,
    }

    _run_search_cycle([mock_client], settings)

    mock_client.get_media_to_search.assert_called_once_with(-1, 10)


_log_rangarr_start_cases = {
    'disabled': {
        'missing_batch_size': 0,
        'upgrade_batch_size': 20,
        'interleave_instances': False,
        'expected_missing': 'Missing Batch: Disabled',
        'expected_upgrade': 'Upgrade Batch: 20',
        'expected_interleave': 'Interleave Instances: No',
    },
    'unlimited': {
        'missing_batch_size': -1,
        'upgrade_batch_size': -1,
        'interleave_instances': False,
        'expected_missing': 'Missing Batch: Unlimited',
        'expected_upgrade': 'Upgrade Batch: Unlimited',
        'expected_interleave': 'Interleave Instances: No',
    },
    'limited': {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'interleave_instances': False,
        'expected_missing': 'Missing Batch: 20',
        'expected_upgrade': 'Upgrade Batch: 10',
        'expected_interleave': 'Interleave Instances: No',
    },
    'active_hours_set': {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'active_hours': '22:00-06:00',
        'interleave_instances': False,
        'expected_missing': 'Missing Batch: 20',
        'expected_upgrade': 'Upgrade Batch: 10',
        'expected_active_hours': 'Active Hours: 22:00-06:00',
        'expected_interleave': 'Interleave Instances: No',
    },
    'active_hours_all': {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'active_hours': '',
        'interleave_instances': False,
        'expected_missing': 'Missing Batch: 20',
        'expected_upgrade': 'Upgrade Batch: 10',
        'expected_active_hours': 'Active Hours: All hours',
        'expected_interleave': 'Interleave Instances: No',
    },
    'interleave_enabled': {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'interleave_instances': True,
        'expected_missing': 'Missing Batch: 20',
        'expected_upgrade': 'Upgrade Batch: 10',
        'expected_interleave': 'Interleave Instances: Yes',
    },
}


@pytest.mark.parametrize(
    'missing_batch_size, upgrade_batch_size, active_hours, interleave_instances, '
    'expected_missing, expected_upgrade, expected_active_hours, expected_interleave',
    [
        (
            case['missing_batch_size'],
            case['upgrade_batch_size'],
            case.get('active_hours', ''),
            case['interleave_instances'],
            case['expected_missing'],
            case['expected_upgrade'],
            case.get('expected_active_hours', 'Active Hours: All hours'),
            case['expected_interleave'],
        )
        for case in _log_rangarr_start_cases.values()
    ],
    ids=list(_log_rangarr_start_cases.keys()),
)
def test_log_rangarr_start(
    mock_client: Mock,
    caplog: pytest.LogCaptureFixture,
    missing_batch_size: int,
    upgrade_batch_size: int,
    active_hours: str,
    interleave_instances: bool,
    expected_missing: str,
    expected_upgrade: str,
    expected_active_hours: str,
    expected_interleave: str,
) -> None:
    """Test startup log displays correct batch size labels and active hours."""
    from rangarr.main import _log_rangarr_start

    settings = {
        'missing_batch_size': missing_batch_size,
        'upgrade_batch_size': upgrade_batch_size,
        'retry_interval_days': 30,
        'run_interval_minutes': 60,
        'stagger_interval_seconds': 30,
        'search_order': 'last_searched_ascending',
        'dry_run': False,
        'active_hours': active_hours,
        'interleave_instances': interleave_instances,
    }

    with caplog.at_level(logging.INFO):
        _log_rangarr_start([mock_client], settings)

    assert expected_missing in caplog.text
    assert expected_upgrade in caplog.text
    assert expected_active_hours in caplog.text
    assert expected_interleave in caplog.text


_log_rangarr_start_retry_cases = {
    'base_only': {
        'retry_interval_days': 30,
        'retry_interval_days_missing': None,
        'retry_interval_days_upgrade': None,
        'expected_retry': 'Retry Interval: 30 Days',
    },
    'base_disabled': {
        'retry_interval_days': 0,
        'retry_interval_days_missing': None,
        'retry_interval_days_upgrade': None,
        'expected_retry': 'Retry Interval: Disabled',
    },
    'missing_override_only': {
        'retry_interval_days': 30,
        'retry_interval_days_missing': 7,
        'retry_interval_days_upgrade': None,
        'expected_retry': 'Retry Interval: Global: 30 Days, Missing: 7 Days, Upgrade: 30 Days',
    },
    'upgrade_override_only': {
        'retry_interval_days': 30,
        'retry_interval_days_missing': None,
        'retry_interval_days_upgrade': 60,
        'expected_retry': 'Retry Interval: Global: 30 Days, Missing: 30 Days, Upgrade: 60 Days',
    },
    'both_overrides': {
        'retry_interval_days': 30,
        'retry_interval_days_missing': 7,
        'retry_interval_days_upgrade': 14,
        'expected_retry': 'Retry Interval: Global: 30 Days, Missing: 7 Days, Upgrade: 14 Days',
    },
    'base_disabled_with_missing_override': {
        'retry_interval_days': 0,
        'retry_interval_days_missing': 7,
        'retry_interval_days_upgrade': None,
        'expected_retry': 'Retry Interval: Global: Disabled, Missing: 7 Days, Upgrade: Disabled',
    },
}


@pytest.mark.parametrize(
    'retry_interval_days, retry_interval_days_missing, retry_interval_days_upgrade, expected_retry',
    [
        (
            case['retry_interval_days'],
            case['retry_interval_days_missing'],
            case['retry_interval_days_upgrade'],
            case['expected_retry'],
        )
        for case in _log_rangarr_start_retry_cases.values()
    ],
    ids=list(_log_rangarr_start_retry_cases.keys()),
)
def test_log_rangarr_start_retry_interval(
    mock_client: Mock,
    caplog: pytest.LogCaptureFixture,
    retry_interval_days: int,
    retry_interval_days_missing: int | None,
    retry_interval_days_upgrade: int | None,
    expected_retry: str,
) -> None:
    """Test startup log displays correct retry interval string with optional overrides."""
    from rangarr.main import _log_rangarr_start

    settings = {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'retry_interval_days': retry_interval_days,
        'retry_interval_days_missing': retry_interval_days_missing,
        'retry_interval_days_upgrade': retry_interval_days_upgrade,
        'run_interval_minutes': 60,
        'stagger_interval_seconds': 30,
        'search_order': 'last_searched_ascending',
        'dry_run': False,
        'active_hours': '',
        'interleave_instances': False,
    }

    with caplog.at_level(logging.INFO):
        _log_rangarr_start([mock_client], settings)

    assert expected_retry in caplog.text


_verify_arr_clients_cases = {
    'all_succeed_first_attempt': {
        'connection_results': [[True], [True]],
        'expected_count': 2,
        'expected_sleep_count': 0,
        'expected_log_fragments': [],
    },
    'one_fails_all_attempts': {
        'connection_results': [[True], [False, False, False]],
        'expected_count': 1,
        'expected_sleep_count': 2,
        'expected_log_fragments': [
            'Connection attempt 1/3 failed',
            'Connection attempt 2/3 failed',
            'Could not connect after 3 attempts',
        ],
    },
    'one_succeeds_on_second_attempt': {
        'connection_results': [[False, True]],
        'expected_count': 1,
        'expected_sleep_count': 1,
        'expected_log_fragments': [
            'Connection attempt 1/3 failed',
            'Connected on attempt 2/3',
        ],
    },
    'all_fail': {
        'connection_results': [[False, False, False]],
        'expected_count': 0,
        'expected_sleep_count': 2,
        'expected_log_fragments': [
            'Connection attempt 1/3 failed',
            'Connection attempt 2/3 failed',
            'Could not connect after 3 attempts',
        ],
    },
    'no_clients': {
        'connection_results': [],
        'expected_count': 0,
        'expected_sleep_count': 0,
        'expected_log_fragments': [],
    },
    'succeeds_on_third_attempt': {
        'connection_results': [[False, False, True]],
        'expected_count': 1,
        'expected_sleep_count': 2,
        'expected_log_fragments': [
            'Connection attempt 1/3 failed',
            'Connection attempt 2/3 failed',
            'Connected on attempt 3/3',
        ],
    },
}


@pytest.mark.parametrize(
    'connection_results, expected_count, expected_sleep_count, expected_log_fragments',
    [
        (
            case['connection_results'],
            case['expected_count'],
            case['expected_sleep_count'],
            case['expected_log_fragments'],
        )
        for case in _verify_arr_clients_cases.values()
    ],
    ids=list(_verify_arr_clients_cases.keys()),
)
def test_verify_arr_clients(
    connection_results: list[list[bool]],
    expected_count: int,
    expected_sleep_count: int,
    expected_log_fragments: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test verify_arr_clients retries and filters clients based on connection results."""
    clients = []
    for results in connection_results:
        client = Mock()
        client.name = 'test-instance'
        client.check_connection = Mock(side_effect=results)
        clients.append(client)

    with caplog.at_level(logging.INFO):
        with patch('rangarr.main.time.sleep') as mock_sleep:
            verified = verify_arr_clients(clients)

    assert len(verified) == expected_count
    assert mock_sleep.call_count == expected_sleep_count
    if expected_sleep_count > 0:
        mock_sleep.assert_called_with(10)
    for fragment in expected_log_fragments:
        assert fragment in caplog.text


def test_run_exits_when_all_clients_fail_connection() -> None:
    """Test run exits when all clients fail connection verification."""
    run_client = MagicMock()
    run_client.name = 'Test'
    run_client.weight = 1.0

    with (
        patch('pathlib.Path.is_file', return_value=True),
        patch('rangarr.main.load_config', return_value=_make_run_config()),
        patch('rangarr.main.build_arr_clients', return_value=[run_client]),
        patch('rangarr.main.verify_arr_clients', return_value=[]),
        pytest.raises(SystemExit) as exc_info,
    ):
        from rangarr.main import run

        run()

    assert exc_info.value.code == 1

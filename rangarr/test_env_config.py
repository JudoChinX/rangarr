"""Tests for loading configuration from environment variables."""

import os
import re
from typing import Any
from unittest import mock

import pytest

from rangarr.config_parser import load_config_from_env
from rangarr.main import run
from tests.helpers import assert_config_result

_BASE_INSTANCE = {
    'RANGARR_INSTANCE_0_NAME': 'movies',
    'RANGARR_INSTANCE_0_TYPE': 'radarr',
    'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
    'RANGARR_INSTANCE_0_API_KEY': 'abc123',
}

_load_config_from_env_cases = {
    'no_instances': {
        'env': {},
        'expected_error': 'No instances defined',
    },
    'global_interval_converted_to_minutes': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_INTERVAL': '1800',
        },
        'expected_result': {
            'global_settings': {'run_interval_minutes': 30},
        },
    },
    'global_dry_run_parsed_as_bool': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_DRY_RUN': 'true',
        },
        'expected_result': {
            'global_settings': {'dry_run': True},
        },
    },
    'string_setting_remains_string': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_SEARCH_ORDER': 'random',
        },
        'expected_result': {
            'global_settings': {'search_order': 'random'},
        },
    },
    'integer_setting_parsed_as_int': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_RETRY_INTERVAL_DAYS': '5',
        },
        'expected_result': {
            'global_settings': {'retry_interval_days': 5},
        },
    },
    'non_numeric_string_rejected_for_int_setting': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_RETRY_INTERVAL_DAYS': '--123',
        },
        'expected_error': "'global.retry_interval_days' must be of type int",
    },
    'multiple_instances_parsed_by_type': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': 'movies',
            'RANGARR_INSTANCE_0_TYPE': 'radarr',
            'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_0_API_KEY': 'key1',
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_INSTANCE_1_NAME': 'tv',
            'RANGARR_INSTANCE_1_TYPE': 'sonarr',
            'RANGARR_INSTANCE_1_URL': 'http://localhost:8989',
            'RANGARR_INSTANCE_1_API_KEY': 'key2',
            'RANGARR_INSTANCE_1_ENABLED': 'true',
        },
        'expected_result': {
            'instances': {
                'radarr': [{'name': 'movies'}],
                'sonarr': [{'name': 'tv'}],
            },
        },
    },
    'negative_int_rejected_for_non_negative_setting': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_RETRY_INTERVAL_DAYS': '-5',
        },
        'expected_error': "'global.retry_interval_days' must be a non-negative integer",
    },
    'float_weight_parsed': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_INSTANCE_0_WEIGHT': '1.5',
        },
        'expected_result': {
            'instances': {'radarr': [{'name': 'movies', 'weight': 1.5}]},
        },
    },
    'host_key_aliased_to_url': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': 'tv',
            'RANGARR_INSTANCE_0_TYPE': 'sonarr',
            'RANGARR_INSTANCE_0_HOST': 'http://localhost:8989',
            'RANGARR_INSTANCE_0_API_KEY': 'key1',
            'RANGARR_INSTANCE_0_ENABLED': 'true',
        },
        'expected_result': {
            'instances': {'sonarr': [{'url': 'http://localhost:8989'}]},
        },
    },
    'enabled_defaults_to_true_when_absent': {
        'env': {**_BASE_INSTANCE},
        'expected_result': {
            'instances': {'radarr': [{'name': 'movies'}]},
        },
    },
    'mixed_case_type_accepted': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': 'movies',
            'RANGARR_INSTANCE_0_TYPE': 'Radarr',
            'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_0_API_KEY': 'abc123',
            'RANGARR_INSTANCE_0_ENABLED': 'true',
        },
        'expected_result': {
            'instances': {'radarr': [{'name': 'movies'}]},
        },
    },
    'missing_name_skips_slot': {
        'env': {
            'RANGARR_INSTANCE_0_TYPE': 'radarr',
            'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_0_API_KEY': 'key1',
        },
        'expected_error': 'No instances defined',
    },
    'empty_name_skips_slot': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': '',
            'RANGARR_INSTANCE_0_TYPE': 'radarr',
            'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_0_API_KEY': 'key1',
            'RANGARR_INSTANCE_1_NAME': 'movies',
            'RANGARR_INSTANCE_1_TYPE': 'radarr',
            'RANGARR_INSTANCE_1_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_1_API_KEY': 'key1',
        },
        'expected_result': {
            'instances': {'radarr': [{'name': 'movies'}]},
        },
    },
    'all_slots_empty_name_raises_no_instances': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': '',
        },
        'expected_error': 'No instances defined',
    },
    'two_instances_same_type': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': 'movies-hd',
            'RANGARR_INSTANCE_0_TYPE': 'radarr',
            'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_0_API_KEY': 'key1',
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_INSTANCE_1_NAME': 'movies-4k',
            'RANGARR_INSTANCE_1_TYPE': 'radarr',
            'RANGARR_INSTANCE_1_URL': 'http://localhost:7879',
            'RANGARR_INSTANCE_1_API_KEY': 'key2',
            'RANGARR_INSTANCE_1_ENABLED': 'true',
        },
        'expected_result': {
            'instances': {
                'radarr': [{'name': 'movies-hd'}, {'name': 'movies-4k'}],
            },
        },
    },
    'duplicate_instance_names_raises_error': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': 'movies',
            'RANGARR_INSTANCE_0_TYPE': 'radarr',
            'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_0_API_KEY': 'key1',
            'RANGARR_INSTANCE_1_NAME': 'movies',
            'RANGARR_INSTANCE_1_TYPE': 'radarr',
            'RANGARR_INSTANCE_1_URL': 'http://localhost:7879',
            'RANGARR_INSTANCE_1_API_KEY': 'key2',
        },
        'expected_error': "Duplicate instance name 'movies' found at index 1",
    },
    'non_sequential_indexes_supported': {
        'env': {
            'RANGARR_INSTANCE_0_NAME': 'movies',
            'RANGARR_INSTANCE_0_TYPE': 'radarr',
            'RANGARR_INSTANCE_0_URL': 'http://localhost:7878',
            'RANGARR_INSTANCE_0_API_KEY': 'key1',
            'RANGARR_INSTANCE_2_NAME': 'tv',
            'RANGARR_INSTANCE_2_TYPE': 'sonarr',
            'RANGARR_INSTANCE_2_URL': 'http://localhost:8989',
            'RANGARR_INSTANCE_2_API_KEY': 'key2',
        },
        'expected_result': {
            'instances': {
                'radarr': [{'name': 'movies'}],
                'sonarr': [{'name': 'tv'}],
            },
        },
    },
    'include_tags_parsed_from_comma_separated_env_var': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_INCLUDE_TAGS': 'alpha, beta',
        },
        'expected_result': {
            'global_settings': {'include_tags': ['alpha', 'beta']},
        },
    },
    'retry_interval_days_missing_parsed_as_int': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_RETRY_INTERVAL_DAYS_MISSING': '14',
        },
        'expected_result': {
            'global_settings': {'retry_interval_days_missing': 14},
        },
    },
    'retry_interval_days_upgrade_parsed_as_int': {
        'env': {
            **_BASE_INSTANCE,
            'RANGARR_INSTANCE_0_ENABLED': 'true',
            'RANGARR_GLOBAL_RETRY_INTERVAL_DAYS_UPGRADE': '60',
        },
        'expected_result': {
            'global_settings': {'retry_interval_days_upgrade': 60},
        },
    },
}


@pytest.mark.parametrize(
    'env, expected_error, expected_result',
    [
        (
            case['env'],
            case.get('expected_error'),
            case.get('expected_result'),
        )
        for case in _load_config_from_env_cases.values()
    ],
    ids=list(_load_config_from_env_cases.keys()),
)
def test_load_config_from_env(env: Any, expected_error: Any, expected_result: Any) -> None:
    """Test load_config_from_env parses environment variables into a validated config dict.

    Args:
        env: Environment variable dict to patch into os.environ.
        expected_error: If set, asserts ValueError is raised matching this string.
        expected_result: If set, asserts result contains these keys and values.
    """
    with mock.patch.dict(os.environ, env, clear=True):
        if expected_error:
            with pytest.raises(ValueError, match=re.escape(expected_error)):
                load_config_from_env()
        else:
            assert_config_result(load_config_from_env(), expected_result)


def test_load_config_from_env_is_idempotent() -> None:
    """Test load_config_from_env returns consistent results across multiple calls."""
    env = {**_BASE_INSTANCE}
    with mock.patch.dict(os.environ, env, clear=True):
        first_call = load_config_from_env()
        second_call = load_config_from_env()
    assert first_call == second_call


def test_main_run_exits_on_invalid_env_config() -> None:
    """Test run() exits with code 1 when env config contains a validation error."""
    env = {'RANGARR_CONFIG_SOURCE': 'env'}
    with mock.patch.dict(os.environ, env, clear=True):
        with pytest.raises(SystemExit) as exc_info:
            run()
    assert exc_info.value.code == 1


def test_main_run_warns_on_unrecognized_config_source(caplog: pytest.LogCaptureFixture) -> None:
    """Test run() logs a warning and falls back to file mode for unrecognized RANGARR_CONFIG_SOURCE."""
    env = {'RANGARR_CONFIG_SOURCE': 'bogus'}
    with mock.patch.dict(os.environ, env, clear=True):
        with mock.patch('rangarr.main._load_config_from_paths', return_value=None):
            with pytest.raises(SystemExit):
                run()
    assert any('bogus' in record.message for record in caplog.records)


def test_main_run_with_env_config() -> None:
    """Test run() loads environment-based configuration and enters the search loop."""
    env = {
        'RANGARR_CONFIG_SOURCE': 'env',
        **_BASE_INSTANCE,
    }
    with mock.patch.dict(os.environ, env, clear=True):
        with mock.patch('rangarr.main._run_search_cycle') as mock_cycle:
            with mock.patch('rangarr.main.verify_arr_clients', side_effect=lambda clients: clients):
                with mock.patch('time.sleep', side_effect=InterruptedError):
                    with pytest.raises(InterruptedError):
                        run()
            mock_cycle.assert_called_once()


def test_load_config_from_env_warns_on_skipped_slot(caplog: pytest.LogCaptureFixture) -> None:
    """Test load_config_from_env logs a warning when an instance slot has an empty name."""
    with mock.patch.dict(os.environ, _load_config_from_env_cases['empty_name_skips_slot']['env'], clear=True):
        with caplog.at_level('WARNING', logger='rangarr.config_parser'):
            load_config_from_env()
    assert any(
        'Skipping unconfigured instance slot at index 0' in record.message and record.levelname == 'WARNING'
        for record in caplog.records
    )

"""Tests for the fetch_timeout setting in config_parser.py."""

import re
from typing import Any

import pytest

from rangarr.config_parser import parse_config
from tests.helpers import assert_config_result

_BASE_INSTANCE = {
    'type': 'radarr',
    'host': 'http://test',
    'api_key': 'testkey',
    'enabled': True,
}

_instance_fetch_timeout_rejects_invalid_values_cases = {
    'zero': {
        'bad_value': 0,
        'expected_error': "'instances.slow-instance.fetch_timeout' must be at least 1.",
    },
    'negative': {
        'bad_value': -5,
        'expected_error': "'instances.slow-instance.fetch_timeout' must be at least 1.",
    },
    'string': {
        'bad_value': '120',
        'expected_error': "'instances.slow-instance.fetch_timeout' must be of type int.",
    },
    'boolean': {
        'bad_value': True,
        'expected_error': "'instances.slow-instance.fetch_timeout' must be of type int.",
    },
}

_parse_config_fetch_timeout_cases = {
    'fetch_timeout_default': {
        'config_data': {
            'instances': {'test-instance': _BASE_INSTANCE},
            'global': {},
        },
        'expected_result': {
            'global_settings': {
                'fetch_timeout': 30,
            },
        },
    },
    'fetch_timeout_custom': {
        'config_data': {
            'instances': {'test-instance': _BASE_INSTANCE},
            'global': {
                'fetch_timeout': 120,
            },
        },
        'expected_result': {
            'global_settings': {
                'fetch_timeout': 120,
            },
        },
    },
    'fetch_timeout_minimum_valid': {
        'config_data': {
            'instances': {'test-instance': _BASE_INSTANCE},
            'global': {
                'fetch_timeout': 1,
            },
        },
        'expected_result': {
            'global_settings': {
                'fetch_timeout': 1,
            },
        },
    },
    'fetch_timeout_rejects_zero': {
        'config_data': {
            'instances': {'test-instance': _BASE_INSTANCE},
            'global': {
                'fetch_timeout': 0,
            },
        },
        'expected_error': "'global.fetch_timeout' must be at least 1.",
    },
    'fetch_timeout_rejects_negative': {
        'config_data': {
            'instances': {'test-instance': _BASE_INSTANCE},
            'global': {
                'fetch_timeout': -1,
            },
        },
        'expected_error': "'global.fetch_timeout' must be at least 1.",
    },
    'fetch_timeout_rejects_wrong_type': {
        'config_data': {
            'instances': {'test-instance': _BASE_INSTANCE},
            'global': {
                'fetch_timeout': '120',
            },
        },
        'expected_error': "'global.fetch_timeout' must be of type int.",
    },
    'fetch_timeout_rejects_boolean': {
        'config_data': {
            'instances': {'test-instance': _BASE_INSTANCE},
            'global': {
                'fetch_timeout': True,
            },
        },
        'expected_error': "'global.fetch_timeout' must be of type int.",
    },
}


def test_instance_fetch_timeout_override_is_accepted() -> None:
    """Test that a valid per-instance fetch_timeout override survives parsing."""
    config_data = {
        'instances': {'slow-instance': {**_BASE_INSTANCE, 'fetch_timeout': 120}},
        'global': {'fetch_timeout': 30},
    }
    parsed = parse_config(config_data)
    assert parsed['instances']['radarr'][0]['fetch_timeout'] == 120
    assert parsed['global_settings']['fetch_timeout'] == 30


@pytest.mark.parametrize(
    'bad_value, expected_error',
    [
        (case['bad_value'], case['expected_error'])
        for case in _instance_fetch_timeout_rejects_invalid_values_cases.values()
    ],
    ids=list(_instance_fetch_timeout_rejects_invalid_values_cases.keys()),
)
def test_instance_fetch_timeout_rejects_invalid_values(bad_value: Any, expected_error: str) -> None:
    """Test that invalid per-instance fetch_timeout values fail parsing instead of reaching requests.

    Args:
        bad_value: The invalid override to place on the instance.
        expected_error: The validation message expected from parse_config.
    """
    config_data = {
        'instances': {'slow-instance': {**_BASE_INSTANCE, 'fetch_timeout': bad_value}},
        'global': {},
    }
    with pytest.raises(ValueError, match=re.escape(expected_error)):
        parse_config(config_data)


def test_instance_parsing_does_not_inject_schema_defaults() -> None:
    """Test that parsing leaves unset schema keys absent from an instance so globals still apply."""
    config_data = {
        'instances': {'slow-instance': {**_BASE_INSTANCE, 'fetch_timeout': 120}},
        'global': {'missing_batch_size': 7},
    }
    parsed = parse_config(config_data)
    instance = parsed['instances']['radarr'][0]
    assert 'missing_batch_size' not in instance
    assert 'max_queue_size' not in instance
    assert 'fetch_page_size' not in instance


@pytest.mark.parametrize(
    'config_data, expected_error, expected_result',
    [
        (
            case['config_data'],
            case.get('expected_error'),
            case.get('expected_result'),
        )
        for case in _parse_config_fetch_timeout_cases.values()
    ],
    ids=list(_parse_config_fetch_timeout_cases.keys()),
)
def test_parse_config_fetch_timeout(config_data: Any, expected_error: Any, expected_result: Any) -> None:
    """Test parse_config validates the fetch_timeout setting.

    Args:
        config_data: The raw configuration dictionary to validate.
        expected_error: Expected validation error message, if any.
        expected_result: Expected values in the parsed configuration, if valid.
    """
    if expected_error:
        with pytest.raises(ValueError, match=re.escape(expected_error)):
            parse_config(config_data)
    else:
        assert_config_result(parse_config(config_data), expected_result)

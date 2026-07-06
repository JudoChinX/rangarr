"""Tests for the max_queue_size global setting in config_parser.py."""

import re
from typing import Any

import pytest

from rangarr.config_parser import parse_config

_VALID_INSTANCE = {'type': 'radarr', 'host': 'http://test', 'api_key': 'testkey', 'enabled': True}

_max_queue_size_cases = {
    'default_disabled': {
        'config_data': {'instances': {'test-instance': dict(_VALID_INSTANCE)}, 'global': {}},
        'expected': 0,
    },
    'explicit_value': {
        'config_data': {'instances': {'test-instance': dict(_VALID_INSTANCE)}, 'global': {'max_queue_size': 25}},
        'expected': 25,
    },
}


@pytest.mark.parametrize(
    'config_data, expected',
    [(case['config_data'], case['expected']) for case in _max_queue_size_cases.values()],
    ids=list(_max_queue_size_cases.keys()),
)
def test_max_queue_size(config_data: dict[str, Any], expected: int) -> None:
    """Test that max_queue_size defaults to 0 and accepts an explicit value."""
    parsed = parse_config(config_data)
    assert parsed['global_settings']['max_queue_size'] == expected


def test_max_queue_size_rejects_negative() -> None:
    """Test that a negative max_queue_size raises a validation error."""
    config_data = {
        'instances': {'test-instance': dict(_VALID_INSTANCE)},
        'global': {'max_queue_size': -1},
    }
    with pytest.raises(ValueError, match=re.escape("'global.max_queue_size' must be at least 0.")):
        parse_config(config_data)


def test_max_queue_size_rejects_non_integer() -> None:
    """Test that a non-integer max_queue_size raises a validation error."""
    config_data = {
        'instances': {'test-instance': dict(_VALID_INSTANCE)},
        'global': {'max_queue_size': 'lots'},
    }
    with pytest.raises(ValueError, match=re.escape("'global.max_queue_size' must be of type int.")):
        parse_config(config_data)

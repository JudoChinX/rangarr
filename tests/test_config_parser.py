"""Tests for config_parser.py configuration loading and validation."""

import re
from pathlib import Path
from typing import Any

import pytest

from rangarr.config_parser import SETTINGS_SCHEMA
from rangarr.config_parser import get_setting_default
from rangarr.config_parser import load_config
from rangarr.config_parser import parse_config

_load_config_cases = {
    'file_not_found': {
        'file_exists': False,
        'expected_error': FileNotFoundError,
    },
    'reads_valid_file': {
        'file_exists': True,
        'file_path': 'test_config.yaml',
        'expected_result': 'not_none',
    },
}

_parse_config_cases = {
    'not_a_dict_string': {
        'config_data': 'not a dict\nanother string',
        'expected_error': 'Configuration file must be a YAML mapping at the top level.',
    },
    'list_instead_of_dict': {
        'config_data': ['list', 'instead', 'of', 'dict'],
        'expected_error': 'Configuration file must be a YAML mapping at the top level.',
    },
    'missing_instances_key': {
        'config_data': {},
        'expected_error': "Missing required top-level key: 'instances'",
    },
    'invalid_run_interval_type': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'run_interval_minutes': 'not int'},
        },
        'expected_error': "'global.run_interval_minutes' must be of type int.",
    },
    'global_not_a_dict': {
        'config_data': {'instances': {}, 'global': 'not a dict'},
        'expected_error': "'global' must be a YAML mapping.",
    },
    'invalid_interval_type': {
        'config_data': {'instances': {}, 'global': {'interval': '3600'}},
        'expected_error': "'global.interval' must be an integer.",
    },
    'negative_run_interval': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'run_interval_minutes': -1},
        },
        'expected_error': "'global.run_interval_minutes' must be a non-negative integer.",
    },
    'negative_missing_batch_size': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'missing_batch_size': -5},
        },
        'expected_error': "'global.missing_batch_size' must be 0 (disabled), -1 (unlimited), or a positive integer.",
    },
    'instances_not_a_dict': {
        'config_data': {'instances': 'not a dict'},
        'expected_error': "'instances' must be a YAML mapping.",
    },
    'instance_not_a_dict': {
        'config_data': {'instances': {'radarr-main': 'not a dict'}},
        'expected_error': "Instance 'radarr-main' must be a YAML mapping.",
    },
    'missing_type_field': {
        'config_data': {
            'instances': {
                'my-instance': {
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                }
            }
        },
        'expected_error': "Missing 'type' field for instance 'my-instance'.",
    },
    'radarr_missing_url': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'api_key': 'radarr_api_key',
                }
            }
        },
        'expected_error': "Missing or empty 'url' for instance 'radarr-main'.",
    },
    'sonarr_missing_api_key': {
        'config_data': {
            'instances': {
                'sonarr-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                }
            }
        },
        'expected_error': "Missing or empty 'api_key' for instance 'sonarr-tv'.",
    },
    'sonarr_empty_api_key': {
        'config_data': {
            'instances': {
                'sonarr-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': '',
                }
            }
        },
        'expected_error': "Missing or empty 'api_key' for instance 'sonarr-tv'.",
    },
    'radarr_negative_weight': {
        'config_data': {
            'instances': {
                'radarr-4k': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'weight': -1,
                    'enabled': True,
                }
            }
        },
        'expected_error': "'weight' for instance 'radarr-4k' must be a positive number.",
    },
    'radarr_invalid_weight_type': {
        'config_data': {
            'instances': {
                'radarr-4k': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'weight': 'heavy',
                    'enabled': True,
                }
            }
        },
        'expected_error': "'weight' for instance 'radarr-4k' must be a positive number.",
    },
    'invalid_search_order': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                    'enabled': True,
                }
            },
            'global': {'search_order': 'sideways'},
        },
        'expected_error': "'global.search_order' must be one of: 'alphabetical_ascending', 'alphabetical_descending', 'last_added_ascending', 'last_added_descending', 'last_searched_ascending', 'last_searched_descending', 'random', 'release_date_ascending', 'release_date_descending'.",
    },
    'invalid_instance_type': {
        'config_data': {
            'instances': {
                'readarr': {
                    'type': 'readarr',
                    'url': 'http://localhost:8787',
                    'api_key': 'readarr_api_key',
                }
            }
        },
        'expected_error': "Invalid type 'readarr' for instance 'readarr'. Must be either 'Radarr', 'Sonarr', or 'Lidarr'.",
    },
    'empty_instances_dict': {
        'config_data': {'instances': {}},
        'expected_error': "No instances defined under 'instances'. Add at least one Radarr, Sonarr, or Lidarr instance.",
    },
    'missing_batch_size_unlimited': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'missing_batch_size': -1,
            },
        },
        'expected_result': {
            'global_settings': {
                'missing_batch_size': -1,
            },
        },
    },
    'upgrade_batch_size_unlimited': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'upgrade_batch_size': -1,
            },
        },
        'expected_result': {
            'global_settings': {
                'upgrade_batch_size': -1,
            },
        },
    },
    'missing_batch_size_disabled': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'missing_batch_size': 0,
            },
        },
        'expected_result': {
            'global_settings': {
                'missing_batch_size': 0,
            },
        },
    },
    'upgrade_batch_size_disabled': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'upgrade_batch_size': 0,
            },
        },
        'expected_result': {
            'global_settings': {
                'upgrade_batch_size': 0,
            },
        },
    },
    'missing_batch_size_invalid_negative_two': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'missing_batch_size': -2,
            },
        },
        'expected_error': "'global.missing_batch_size' must be 0 (disabled), -1 (unlimited), or a positive integer.",
    },
    'upgrade_batch_size_invalid_negative_two': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'upgrade_batch_size': -2,
            },
        },
        'expected_error': "'global.upgrade_batch_size' must be 0 (disabled), -1 (unlimited), or a positive integer.",
    },
    'retry_interval_days_rejects_negative': {
        'config_data': {
            'instances': {
                'test-instance': {
                    'type': 'radarr',
                    'host': 'http://test',
                    'api_key': 'test_key',
                    'enabled': True,
                }
            },
            'global': {
                'retry_interval_days': -1,
            },
        },
        'expected_error': 'must be a non-negative integer',
    },
    'all_instances_implicit_disabled': {
        'config_data': {
            'instances': {
                'radarr-main': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'radarr_api_key',
                },
                'sonarr-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'sonarr_api_key',
                },
            }
        },
        'expected_error': "No instances defined under 'instances'. Add at least one Radarr, Sonarr, or Lidarr instance.",
    },
    'yaml_style_mapping': {
        'config_data': {
            'global': {'interval': 3600},
            'instances': {
                'sonarr-main': {
                    'type': 'sonarr',
                    'host': 'http://sonarr:8989',
                    'api_key': 'abc',
                    'enabled': True,
                },
                'my-radarr': {
                    'type': 'radarr',
                    'url': 'http://radarr:7878',
                    'api_key': 'def',
                    'enabled': False,
                },
            },
        },
        'expected_result': {
            'global_settings': {
                'run_interval_minutes': 60,
                'dry_run': False,
            },
            'instances': {
                'sonarr': [
                    {
                        'name': 'sonarr-main',
                        'url': 'http://sonarr:8989',
                        'api_key': 'abc',
                    }
                ],
                'radarr': [],
            },
        },
    },
    'valid_basic': {
        'config_data': {
            'instances': {
                'my-movies': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'somekey',
                    'enabled': True,
                },
                'my-tv': {
                    'type': 'sonarr',
                    'url': 'http://localhost:8989',
                    'api_key': 'anotherkey',
                    'enabled': True,
                },
                'my-music': {
                    'type': 'lidarr',
                    'url': 'http://localhost:8686',
                    'api_key': 'lidarrkey',
                    'enabled': True,
                },
            }
        },
        'expected_result': {
            'global_settings': {
                'run_interval_minutes': 60,
                'stagger_interval_seconds': 30,
                'retry_interval_days': 30,
                'search_order': 'last_searched_ascending',
                'dry_run': False,
            },
            'instances': {
                'radarr': [
                    {
                        'name': 'my-movies',
                        'weight': 1,
                    }
                ],
                'sonarr': [
                    {
                        'name': 'my-tv',
                        'weight': 1,
                    }
                ],
                'lidarr': [
                    {
                        'name': 'my-music',
                        'url': 'http://localhost:8686',
                        'api_key': 'lidarrkey',
                        'enabled': True,
                        'weight': 0.1,
                    }
                ],
            },
        },
    },
    'valid_overrides': {
        'config_data': {
            'global': {'run_interval_minutes': 30, 'missing_batch_size': 100},
            'instances': {
                'ultra-hd-movies': {
                    'type': 'radarr',
                    'url': 'http://localhost:7878',
                    'api_key': 'x',
                    'enabled': True,
                    'weight': 2.5,
                }
            },
        },
        'expected_result': {
            'global_settings': {
                'run_interval_minutes': 30,
                'missing_batch_size': 100,
                'stagger_interval_seconds': 30,
                'retry_interval_days': 30,
                'search_order': 'last_searched_ascending',
                'dry_run': False,
            },
            'instances': {
                'radarr': [{'name': 'ultra-hd-movies', 'weight': 2.5}],
            },
        },
    },
}


def _assert_parse_config_result(result: Any, expected_result: Any) -> None:
    """Assert that the parsed config result matches all expected keys and values."""
    for key, value in expected_result.items():
        if key == 'global_settings':
            for setting_key, setting_value in value.items():
                assert result['global_settings'][setting_key] == setting_value
        elif key == 'instances':
            for arr_type, instances_list in value.items():
                assert len(result['instances'][arr_type]) >= len(instances_list)
                for index, expected_instance in enumerate(instances_list):
                    for instance_key, instance_value in expected_instance.items():
                        assert result['instances'][arr_type][index][instance_key] == instance_value


@pytest.mark.parametrize(
    'file_exists, file_path, expected_error',
    [
        (
            case['file_exists'],
            case.get('file_path'),
            case.get('expected_error'),
        )
        for case in _load_config_cases.values()
    ],
    ids=list(_load_config_cases.keys()),
)
def test_load_config(tmp_path: Any, file_exists: Any, file_path: Any, expected_error: Any) -> None:
    """Test load_config reads and validates YAML files."""
    if not file_exists:
        with pytest.raises(expected_error):
            load_config(str(tmp_path / 'does_not_exist.yaml'))
    else:
        assert load_config(str(Path(__file__).parent / file_path)) is not None


def test_load_config_empty_yaml_treats_as_empty_dict(tmp_path: Any) -> None:
    """Test load_config treats an empty YAML file as an empty config dict."""
    empty_file = tmp_path / 'empty.yaml'
    empty_file.write_text('')
    with pytest.raises(ValueError, match='Missing required top-level key'):
        load_config(str(empty_file))


@pytest.mark.parametrize(
    'config_data, expected_error, expected_result',
    [
        (
            case['config_data'],
            case.get('expected_error'),
            case.get('expected_result'),
        )
        for case in _parse_config_cases.values()
    ],
    ids=list(_parse_config_cases.keys()),
)
def test_parse_config(config_data: Any, expected_error: Any, expected_result: Any) -> None:
    """Test parse_config validates configuration structure and values."""
    if expected_error:
        with pytest.raises(ValueError, match=re.escape(expected_error)):
            parse_config(config_data)
    else:
        _assert_parse_config_result(parse_config(config_data), expected_result)


def test_get_setting_default_returns_schema_values() -> None:
    """Test get_setting_default returns values consistent with SETTINGS_SCHEMA."""
    for setting, definition in SETTINGS_SCHEMA.items():
        assert get_setting_default(setting) == definition['default']


def test_get_setting_default_raises_on_invalid_setting() -> None:
    """Test get_setting_default raises KeyError for undefined settings."""
    with pytest.raises(KeyError):
        get_setting_default('nonexistent_setting')


def test_load_config_expands_env_vars_in_yaml(tmp_path: Any, monkeypatch: Any) -> None:
    """Test load_config substitutes ${VAR} placeholders with environment variable values."""
    monkeypatch.setenv('RADARR_URL', 'http://radarr:7878')
    monkeypatch.setenv('RADARR_API_KEY', 'test-api-key')
    config_file = tmp_path / 'config.yaml'
    config_file.write_text(
        'instances:\n'
        '  my-radarr:\n'
        '    type: radarr\n'
        '    url: ${RADARR_URL}\n'
        '    api_key: ${RADARR_API_KEY}\n'
        '    enabled: true\n'
    )
    result = load_config(str(config_file))
    instance = result['instances']['radarr'][0]
    assert instance['url'] == 'http://radarr:7878'
    assert instance['api_key'] == 'test-api-key'


def test_load_config_raises_on_missing_env_var(tmp_path: Any, monkeypatch: Any) -> None:
    """Test load_config raises ValueError when a referenced env var is not set."""
    monkeypatch.delenv('RADARR_API_KEY', raising=False)
    config_file = tmp_path / 'config.yaml'
    config_file.write_text(
        'instances:\n'
        '  my-radarr:\n'
        '    type: radarr\n'
        '    url: http://radarr:7878\n'
        '    api_key: ${RADARR_API_KEY}\n'
        '    enabled: true\n'
    )
    with pytest.raises(ValueError, match='RADARR_API_KEY'):
        load_config(str(config_file))


def test_load_config_expands_multiple_placeholders_in_single_value(monkeypatch: Any) -> None:
    """Test load_config expands multiple ${VAR} placeholders within a single string value."""
    monkeypatch.setenv('APP_HOST', 'radarr')
    monkeypatch.setenv('APP_PORT', '7878')
    result = load_config(str(Path(__file__).parent / 'test_config_env_vars.yaml'))
    instance = result['instances']['radarr'][0]
    assert instance['url'] == 'http://radarr:7878'


def test_load_config_leaves_plain_string_values_unchanged() -> None:
    """Test load_config does not alter string values that contain no ${VAR} placeholders."""
    result = load_config(str(Path(__file__).parent / 'test_config.yaml'))
    instance = result['instances']['radarr'][0]
    assert instance['url'] == 'http://localhost:7878'
    assert instance['api_key'] == 'somekey'

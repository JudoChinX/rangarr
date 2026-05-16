"""Tests for config_parser.py file loading and environment variable expansion."""

from pathlib import Path
from typing import Any

import pytest

from rangarr.config_parser import load_config
from tests.helpers import assert_config_result

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

_load_config_expand_env_var_type_cases = {
    'numeric_converts_to_int': {
        'env_vars': {'RUN_INTERVAL': '3600'},
        'yaml_content': (
            'global:\n'
            '  interval: ${RUN_INTERVAL}\n'
            'instances:\n'
            '  my-radarr:\n'
            '    type: radarr\n'
            '    url: http://radarr:7878\n'
            '    api_key: test-key\n'
            '    enabled: true\n'
        ),
        'expected_result': {'global_settings': {'run_interval_minutes': 60}},
    },
    'boolean_true_converts_to_bool': {
        'env_vars': {'DRY_RUN': 'true'},
        'yaml_content': (
            'global:\n'
            '  dry_run: ${DRY_RUN}\n'
            'instances:\n'
            '  my-radarr:\n'
            '    type: radarr\n'
            '    url: http://radarr:7878\n'
            '    api_key: test-key\n'
            '    enabled: true\n'
        ),
        'expected_result': {'global_settings': {'dry_run': True}},
    },
    'boolean_false_converts_to_bool': {
        'env_vars': {'DRY_RUN': 'false'},
        'yaml_content': (
            'global:\n'
            '  dry_run: ${DRY_RUN}\n'
            'instances:\n'
            '  my-radarr:\n'
            '    type: radarr\n'
            '    url: http://radarr:7878\n'
            '    api_key: test-key\n'
            '    enabled: true\n'
        ),
        'expected_result': {'global_settings': {'dry_run': False}},
    },
    'partial_substitution_stays_string': {
        'env_vars': {'APP_PORT': '7878'},
        'yaml_content': (
            'instances:\n'
            '  my-radarr:\n'
            '    type: radarr\n'
            '    url: http://radarr:${APP_PORT}\n'
            '    api_key: test-key\n'
            '    enabled: true\n'
        ),
        'expected_result': {'instances': {'radarr': [{'url': 'http://radarr:7878'}]}},
    },
}


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
        assert load_config(str(Path(__file__).parent.parent.parent / 'tests' / file_path)) is not None


def test_load_config_empty_yaml_treats_as_empty_dict(tmp_path: Any) -> None:
    """Test load_config treats an empty YAML file as an empty config dict."""
    empty_file = tmp_path / 'empty.yaml'
    empty_file.write_text('')
    with pytest.raises(ValueError, match='Missing required top-level key'):
        load_config(str(empty_file))


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


def test_load_config_expands_list_values(tmp_path: Any, monkeypatch: Any) -> None:
    """Test load_config expands ${VAR} placeholders inside YAML list values."""
    monkeypatch.setenv('TAG_A', 'alpha')
    monkeypatch.setenv('TAG_B', 'beta')
    config_file = tmp_path / 'config.yaml'
    config_file.write_text(
        'instances:\n'
        '  my-radarr:\n'
        '    type: radarr\n'
        '    url: http://localhost:7878\n'
        '    api_key: testkey\n'
        '    enabled: true\n'
        'global:\n'
        '  include_tags:\n'
        '    - ${TAG_A}\n'
        '    - ${TAG_B}\n'
    )
    result = load_config(str(config_file))
    assert result['global_settings']['include_tags'] == ['alpha', 'beta']


def test_load_config_expands_multiple_placeholders_in_single_value(monkeypatch: Any) -> None:
    """Test load_config expands multiple ${VAR} placeholders within a single string value."""
    monkeypatch.setenv('APP_HOST', 'radarr')
    monkeypatch.setenv('APP_PORT', '7878')
    result = load_config(str(Path(__file__).parent.parent.parent / 'tests' / 'test_config_env_vars.yaml'))
    instance = result['instances']['radarr'][0]
    assert instance['url'] == 'http://radarr:7878'


def test_load_config_leaves_plain_string_values_unchanged() -> None:
    """Test load_config does not alter string values that contain no ${VAR} placeholders."""
    result = load_config(str(Path(__file__).parent.parent.parent / 'tests' / 'test_config.yaml'))
    instance = result['instances']['radarr'][0]
    assert instance['url'] == 'http://localhost:7878'
    assert instance['api_key'] == 'somekey'


@pytest.mark.parametrize(
    'env_vars, yaml_content, expected_result',
    [
        (case['env_vars'], case['yaml_content'], case['expected_result'])
        for case in _load_config_expand_env_var_type_cases.values()
    ],
    ids=list(_load_config_expand_env_var_type_cases.keys()),
)
def test_load_config_expand_env_var_type(
    tmp_path: Any, monkeypatch: Any, env_vars: Any, yaml_content: Any, expected_result: Any
) -> None:
    """Test load_config correctly type-converts ${VAR} expansions in YAML to their Python equivalent."""
    for var, val in env_vars.items():
        monkeypatch.setenv(var, val)
    config_file = tmp_path / 'config.yaml'
    config_file.write_text(yaml_content)
    assert_config_result(load_config(str(config_file)), expected_result)

"""Shared test helpers for rangarr test suite."""

import json
from pathlib import Path
from typing import Any

_FIXTURES_DIR = Path(__file__).parent / 'fixtures'


def assert_config_result(result: Any, expected: Any) -> None:
    """Assert that a parsed config result matches all expected keys and values.

    Args:
        result: The parsed configuration dictionary returned by a config loader.
        expected: A partial dictionary of expected keys and values to assert against.

    Raises:
        AssertionError: If any expected key or value does not match the result.
    """
    for key, value in expected.items():
        if key == 'global_settings':
            for setting_key, setting_value in value.items():
                assert result['global_settings'][setting_key] == setting_value
        elif key == 'instances':
            for arr_type, instances_list in value.items():
                assert len(result['instances'][arr_type]) >= len(instances_list)
                for index, expected_instance in enumerate(instances_list):
                    for instance_key, instance_value in expected_instance.items():
                        assert result['instances'][arr_type][index][instance_key] == instance_value
        else:
            raise AssertionError(f"Unknown expected key: '{key}'")


def load_fixture(subdir: str, filename: str) -> Any:
    """Load a JSON fixture file from the tests/fixtures directory.

    Args:
        subdir: Subdirectory under tests/fixtures (e.g. 'radarr').
        filename: JSON filename (e.g. 'api_v3_wanted_missing.json').

    Returns:
        Parsed JSON content as a dict or list.
    """
    fixture_path = _FIXTURES_DIR / subdir / filename
    with fixture_path.open() as fobj:
        return json.load(fobj)

"""Configuration loader and validator for Rangarr."""

import datetime
import logging
import os
import re
from collections.abc import Callable
from typing import Any

import yaml

from rangarr.validators import _parse_hhmm
from rangarr.validators import _validate_active_hours
from rangarr.validators import _validate_season_packs

logger = logging.getLogger(__name__)

REQUIRED_TOP_LEVEL = ('instances',)
VALID_ARR_TYPES = ('radarr', 'sonarr', 'lidarr')


SETTINGS_SCHEMA = {
    'missing_batch_size': {
        'default': 20,
        'type': int,
        'allow_special_values': True,
    },
    'retry_interval_days': {
        'default': 30,
        'type': int,
    },
    'retry_interval_days_missing': {
        'default': None,
        'type': int,
    },
    'retry_interval_days_upgrade': {
        'default': None,
        'type': int,
    },
    'run_interval_minutes': {
        'default': 60,
        'type': int,
    },
    'dry_run': {
        'default': False,
        'type': bool,
    },
    'interleave_instances': {
        'default': False,
        'type': bool,
    },
    'search_order': {
        'default': 'last_searched_ascending',
        'type': str,
        'choices': (
            'alphabetical_ascending',
            'alphabetical_descending',
            'last_added_ascending',
            'last_added_descending',
            'last_searched_ascending',
            'last_searched_descending',
            'random',
            'release_date_ascending',
            'release_date_descending',
        ),
    },
    'stagger_interval_seconds': {
        'default': 30,
        'type': int,
        'min_value': 1,
    },
    'upgrade_batch_size': {
        'default': 10,
        'type': int,
        'allow_special_values': True,
    },
    'season_packs': {
        'default': False,
        'custom_validator': _validate_season_packs,
    },
    'include_tags': {
        'default': [],
        'type': list,
        'element_type': str,
    },
    'exclude_tags': {
        'default': [],
        'type': list,
        'element_type': str,
    },
    'active_hours': {
        'default': '',
        'type': str,
        'validator': _validate_active_hours,
    },
}


def _expand_env_var(match: re.Match) -> str:
    """Resolve a regex match group to its environment variable value."""
    name = match.group(1)
    val = os.environ.get(name)
    if val is None:
        raise ValueError(f"Environment variable '{name}' referenced in config is not set.")
    return val


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand ${VAR} placeholders in string values using environment variables."""
    if isinstance(obj, dict):
        result = {key: _expand_env_vars(val) for key, val in obj.items()}
    elif isinstance(obj, list):
        result = [_expand_env_vars(item) for item in obj]
    elif isinstance(obj, str):
        expanded = re.sub(r'\$\{([^}]+)\}', _expand_env_var, obj)
        result = _parse_env_value(expanded) if expanded != obj else expanded
    else:
        result = obj
    return result


def _parse_env_value(value: str) -> Any:
    """Convert an environment string value to a boolean, integer, float, or string."""
    val_lower = value.lower()
    result = value

    if val_lower == 'true':
        result = True
    elif val_lower == 'false':
        result = False
    elif re.match(r'^-?\d+$', value):
        result = int(value)
    elif re.match(r'^-?\d+\.\d+$', value):
        result = float(value)

    return result


def _parse_instance(name: str, config: dict) -> tuple[str, dict] | None:
    """Parse and validate a single instance configuration."""
    instance = config.copy()
    if 'host' in instance:
        instance['url'] = instance.pop('host')
    inst_type = str(instance.pop('type', None) or '').lower()
    if not inst_type:
        raise ValueError(f"Missing 'type' field for instance '{name}'. Must be one of: {', '.join(VALID_ARR_TYPES)}.")
    if inst_type not in VALID_ARR_TYPES:
        raise ValueError(
            f"Invalid type '{inst_type}' for instance '{name}'. Must be one of: {', '.join(VALID_ARR_TYPES)}."
        )
    instance['name'] = name
    for field in ('url', 'api_key'):
        if not instance.get(field):
            raise ValueError(f"Missing or empty '{field}' for instance '{name}'.")
    instance.setdefault('weight', 1)
    if not isinstance(instance['weight'], (int, float)) or instance['weight'] <= 0:
        raise ValueError(f"'weight' for instance '{name}' must be a positive number.")
    result = None
    if instance.get('enabled', False):
        result = (inst_type, instance)
    return result


def _validate_global_settings(settings: dict, schema: dict) -> None:
    """Validate all global settings against their schema."""
    for setting, definition in schema.items():
        default = definition['default']
        settings.setdefault(setting, list(default) if isinstance(default, list) else default)
        if definition['default'] is None and settings[setting] is None:
            continue
        if 'custom_validator' in definition:
            definition['custom_validator'](setting, settings[setting])
            continue
        _validate_setting(
            setting,
            settings[setting],
            definition['type'],
            definition.get('choices'),
            allow_special_values=definition.get('allow_special_values', False),
            min_value=definition.get('min_value'),
            element_type=definition.get('element_type'),
            validator=definition.get('validator'),
            prefix='global',
        )


def _validate_setting(
    setting: str,
    value: Any,
    expected_type: type,
    choices: tuple | None = None,
    allow_special_values: bool = False,
    min_value: int | None = None,
    prefix: str = 'global',
    element_type: type | None = None,
    validator: Callable[[str], None] | None = None,
) -> None:
    """Validate a setting value based on its expected type."""
    if not isinstance(value, expected_type):
        raise ValueError(f"'{prefix}.{setting}' must be of type {expected_type.__name__}.")

    if expected_type is int:
        if min_value is not None and value < min_value:
            raise ValueError(f"'{prefix}.{setting}' must be at least {min_value}.")
        if min_value is None:
            limit = -1 if allow_special_values else 0
            if value < limit:
                msg = (
                    f"'{prefix}.{setting}' must be 0 (disabled), -1 (unlimited), or a positive integer."
                    if allow_special_values
                    else f"'{prefix}.{setting}' must be a non-negative integer."
                )
                raise ValueError(msg)

    if expected_type is list and element_type is not None:
        for element in value:
            if not isinstance(element, element_type):
                raise ValueError(f"'{prefix}.{setting}' must be a list of {element_type.__name__} values.")
            if element_type is str and not element:
                raise ValueError(f"'{prefix}.{setting}' entries must not be empty strings.")

    if choices is not None and value not in choices:
        valid_choices = ', '.join(repr(choice) for choice in choices)
        raise ValueError(f"'{prefix}.{setting}' must be one of: {valid_choices}.")

    if validator is not None:
        validator(value)


def get_setting_default(setting: str) -> Any:
    """Get the default value for a setting from the schema.

    Args:
        setting: The setting name.

    Returns:
        The default value for the setting.

    Raises:
        KeyError: If the setting is not defined in the schema.
    """
    return SETTINGS_SCHEMA[setting]['default']


def load_config(path: str) -> dict:
    """Load and validate the YAML configuration file.

    Args:
        path: Filesystem path to config.yaml.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If required keys are missing, values are invalid, or a referenced environment variable is not set.
    """
    with open(path, encoding='utf-8') as file:
        config = yaml.safe_load(file)

    if config is None:
        config = {}

    config = _expand_env_vars(config)
    return parse_config(config)


def load_config_from_env() -> dict:
    """Load configuration from environment variables.

    Scans for RANGARR_GLOBAL_* and RANGARR_INSTANCE_{index}_* variables to
    build a configuration dictionary compatible with parse_config. Instance
    slots with an absent or empty name are skipped with a warning log.

    Returns:
        Validated and normalized configuration dictionary.

    Raises:
        ValueError: If required keys are missing or values are invalid.
    """
    config = {'global': {}, 'instances': {}}
    instance_data = {}

    for key, value in os.environ.items():
        if key.startswith('RANGARR_GLOBAL_'):
            setting_name = key.removeprefix('RANGARR_GLOBAL_').lower()
            schema_entry = SETTINGS_SCHEMA.get(setting_name)
            if schema_entry and schema_entry.get('type') is list:
                config['global'][setting_name] = [item.strip() for item in value.split(',') if item.strip()]
            else:
                config['global'][setting_name] = _parse_env_value(value)
        elif key.startswith('RANGARR_INSTANCE_'):
            remainder = key.removeprefix('RANGARR_INSTANCE_')
            match = re.match(r'(?P<index>\d+)_(?P<field>.+)', remainder)
            if match:
                index = int(match.group('index'))
                field = match.group('field').lower()
                instance_data.setdefault(index, {})[field] = _parse_env_value(value)

    for index in sorted(instance_data.keys()):
        data = instance_data[index].copy()
        name = data.pop('name', '')
        if name:
            if name in config['instances']:
                raise ValueError(f"Duplicate instance name '{name}' found at index {index}.")
            data.setdefault('enabled', True)
            config['instances'][name] = data
        else:
            logger.warning(f'Skipping unconfigured instance slot at index {index} (name is empty).')

    return parse_config(config)


def parse_active_hours(value: str) -> tuple[datetime.time, datetime.time]:
    """Parse a validated HH:MM-HH:MM string into a start and end time pair.

    Args:
        value: A validated time window string in HH:MM-HH:MM format.

    Returns:
        A tuple of (start, end) as datetime.time objects.
    """
    start_str, end_str = value.split('-')
    return _parse_hhmm(start_str), _parse_hhmm(end_str)


def parse_config(config: Any) -> dict:
    """Validate a loaded YAML configuration dictionary.

    Args:
        config: The parsed configuration object.

    Returns:
        Validated and normalized configuration dictionary.

    Raises:
        ValueError: If required keys are missing or values are invalid.
    """
    if not isinstance(config, dict):
        raise ValueError('Configuration file must be a YAML mapping at the top level.')

    for key in REQUIRED_TOP_LEVEL:
        if key not in config:
            raise ValueError(f"Missing required top-level key: '{key}'")

    settings = config.get('global', {})
    if not isinstance(settings, dict):
        raise ValueError("'global' must be a YAML mapping.")

    # Convert interval (seconds) to run_interval_minutes.
    if 'interval' in settings:
        if not isinstance(settings['interval'], int):
            raise ValueError("'global.interval' must be an integer.")
        settings['run_interval_minutes'] = settings['interval'] // 60

    _validate_global_settings(settings, SETTINGS_SCHEMA)
    config['global_settings'] = settings

    raw_instances = config.get('instances', {})
    if not isinstance(raw_instances, dict):
        raise ValueError("'instances' must be a YAML mapping.")

    final_instances = {'radarr': [], 'sonarr': [], 'lidarr': []}
    all_empty = True

    for instance_name, instance_config in raw_instances.items():
        if not isinstance(instance_config, dict):
            raise ValueError(f"Instance '{instance_name}' must be a YAML mapping.")

        parsed = _parse_instance(instance_name, instance_config)
        if parsed is not None:
            inst_type, inst = parsed
            all_empty = False
            final_instances[inst_type].append(inst)

    if all_empty:
        raise ValueError("No instances defined under 'instances'. Add at least one Radarr, Sonarr, or Lidarr instance.")

    config['instances'] = final_instances
    return config

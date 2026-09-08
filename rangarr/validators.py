"""Setting validators for Rangarr configuration."""

import datetime
import re
from typing import Any


def _parse_hhmm(token: str) -> datetime.time:
    """Parse an HH:MM token into a datetime.time object."""
    return datetime.time.fromisoformat(token)


def _validate_active_hours(value: str, prefix: str = 'global') -> None:
    """Validate the active_hours setting format and component ranges."""
    if not value:
        return
    if not re.match(r'^\d{2}:\d{2}-\d{2}:\d{2}$', value):
        raise ValueError(f"'{prefix}.active_hours' must be in HH:MM-HH:MM format (e.g. '22:00-06:00'), got '{value}'.")
    start_str, end_str = value.split('-')
    for part, label in ((start_str, 'start'), (end_str, 'end')):
        try:
            _parse_hhmm(part)
        except ValueError as exc:
            raise ValueError(f"'{prefix}.active_hours' {label} time '{part}' is not a valid 24-hour time.") from exc
    if start_str == end_str:
        raise ValueError(f"'{prefix}.active_hours' start and end times must differ.")


def _validate_season_packs(setting: str, value: Any, prefix: str = 'global') -> None:
    """Validate season_packs accepts bool, int >= 1, or float strictly between 0.0 and 1.0."""
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        if value < 1:
            raise ValueError(f"'{prefix}.{setting}' integer must be >= 1.")
    elif isinstance(value, float):
        if not 0.0 < value < 1.0:
            raise ValueError(f"'{prefix}.{setting}' float must be between 0.0 and 1.0 (exclusive).")
    else:
        raise ValueError(f"'{prefix}.{setting}' must be a bool, integer >= 1, or float between 0.0 and 1.0.")

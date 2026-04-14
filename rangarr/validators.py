"""Setting validators for Rangarr configuration."""

import datetime
import re


def _parse_hhmm(token: str) -> datetime.time:
    """Parse an HH:MM token into a datetime.time object."""
    return datetime.time.fromisoformat(token)


def _validate_active_hours(value: str) -> None:
    """Validate the active_hours setting format and component ranges."""
    if not value:
        return
    if not re.match(r'^\d{2}:\d{2}-\d{2}:\d{2}$', value):
        raise ValueError(f"'global.active_hours' must be in HH:MM-HH:MM format (e.g. '22:00-06:00'), got '{value}'.")
    start_str, end_str = value.split('-')
    for part, label in ((start_str, 'start'), (end_str, 'end')):
        try:
            _parse_hhmm(part)
        except ValueError as exc:
            raise ValueError(f"'global.active_hours' {label} time '{part}' is not a valid 24-hour time.") from exc
    if start_str == end_str:
        raise ValueError("'global.active_hours' start and end times must differ.")

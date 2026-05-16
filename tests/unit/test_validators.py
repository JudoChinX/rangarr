"""Tests for rangarr.validators module."""

import pytest

from rangarr.validators import _validate_active_hours

_validate_active_hours_cases = {
    'accepts_empty_string': {
        'value': '',
        'expected_error': None,
    },
    'accepts_normal_window': {
        'value': '08:00-20:00',
        'expected_error': None,
    },
    'accepts_cross_midnight_window': {
        'value': '22:00-06:00',
        'expected_error': None,
    },
    'rejects_invalid_end_hour': {
        'value': '22:00-25:00',
        'expected_error': "end time '25:00' is not a valid 24-hour time",
    },
    'rejects_invalid_end_minute': {
        'value': '22:00-06:60',
        'expected_error': "end time '06:60' is not a valid 24-hour time",
    },
    'rejects_invalid_start_hour': {
        'value': '25:00-06:00',
        'expected_error': "start time '25:00' is not a valid 24-hour time",
    },
    'rejects_invalid_start_minute': {
        'value': '22:60-06:00',
        'expected_error': "start time '22:60' is not a valid 24-hour time",
    },
    'rejects_missing_end': {
        'value': '22:00',
        'expected_error': 'must be in HH:MM-HH:MM format',
    },
    'rejects_non_time_string': {
        'value': 'not-a-time',
        'expected_error': 'must be in HH:MM-HH:MM format',
    },
    'rejects_start_equals_end': {
        'value': '12:00-12:00',
        'expected_error': "'global.active_hours' start and end times must differ.",
    },
}


@pytest.mark.parametrize(
    'value, expected_error',
    [(case['value'], case['expected_error']) for case in _validate_active_hours_cases.values()],
    ids=list(_validate_active_hours_cases.keys()),
)
def test_validate_active_hours(value: str, expected_error: str | None) -> None:
    """Test _validate_active_hours accepts valid formats and rejects invalid ones."""
    if expected_error is not None:
        with pytest.raises(ValueError, match=expected_error):
            _validate_active_hours(value)
    else:
        _validate_active_hours(value)

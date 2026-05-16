"""Tests for parse_active_hours and active-hours time-window functions."""

import datetime

import pytest

from rangarr.config_parser import parse_active_hours
from rangarr.main import _is_within_active_hours
from rangarr.main import _seconds_until_window_open

_is_within_active_hours_cases = {
    'normal_window_inside': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(12, 0),
        'expected': True,
    },
    'normal_window_outside': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(21, 0),
        'expected': False,
    },
    'normal_window_at_start': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(8, 0),
        'expected': True,
    },
    'normal_window_at_end': {
        'start': datetime.time(8, 0),
        'end': datetime.time(20, 0),
        'now': datetime.time(20, 0),
        'expected': False,
    },
    'cross_midnight_inside_after_start': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(23, 0),
        'expected': True,
    },
    'cross_midnight_inside_before_end': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(3, 0),
        'expected': True,
    },
    'cross_midnight_outside_gap': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(12, 0),
        'expected': False,
    },
    'cross_midnight_at_start': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(22, 0),
        'expected': True,
    },
    'cross_midnight_at_end': {
        'start': datetime.time(22, 0),
        'end': datetime.time(6, 0),
        'now': datetime.time(6, 0),
        'expected': False,
    },
}


@pytest.mark.parametrize(
    'start, end, now, expected',
    [(case['start'], case['end'], case['now'], case['expected']) for case in _is_within_active_hours_cases.values()],
    ids=list(_is_within_active_hours_cases.keys()),
)
def test_is_within_active_hours(start: datetime.time, end: datetime.time, now: datetime.time, expected: bool) -> None:
    """Test _is_within_active_hours handles normal and cross-midnight windows."""
    assert _is_within_active_hours(start, end, now) == expected


_parse_active_hours_cases = {
    'normal_window': {
        'active_hours': '08:00-20:00',
        'expected_start': datetime.time(8, 0),
        'expected_end': datetime.time(20, 0),
    },
    'cross_midnight_window': {
        'active_hours': '22:00-06:00',
        'expected_start': datetime.time(22, 0),
        'expected_end': datetime.time(6, 0),
    },
}


@pytest.mark.parametrize(
    'active_hours, expected_start, expected_end',
    [
        (case['active_hours'], case['expected_start'], case['expected_end'])
        for case in _parse_active_hours_cases.values()
    ],
    ids=list(_parse_active_hours_cases.keys()),
)
def test_parse_active_hours(active_hours: str, expected_start: datetime.time, expected_end: datetime.time) -> None:
    """Test parse_active_hours parses HH:MM-HH:MM strings into datetime.time pairs."""
    start, end = parse_active_hours(active_hours)
    assert start == expected_start
    assert end == expected_end


_fixed_today = datetime.date(2026, 1, 1)

_seconds_until_window_open_cases = {
    'window_opens_later_today': {
        'start': datetime.time(22, 0),
        'now': datetime.time(21, 0),
        'expected_seconds': 3600,
    },
    'window_opens_tomorrow': {
        'start': datetime.time(22, 0),
        'now': datetime.time(23, 0),
        'expected_seconds': 82800,
    },
    'sub_second_before_window_rounds_up_to_one': {
        'start': datetime.time(6, 0, 0),
        'now': datetime.time(5, 59, 59, 999999),
        'expected_seconds': 1,
    },
}


@pytest.mark.parametrize(
    'start, now, expected_seconds',
    [(case['start'], case['now'], case['expected_seconds']) for case in _seconds_until_window_open_cases.values()],
    ids=list(_seconds_until_window_open_cases.keys()),
)
def test_seconds_until_window_open(start: datetime.time, now: datetime.time, expected_seconds: int) -> None:
    """Test _seconds_until_window_open returns correct seconds until window start."""
    assert _seconds_until_window_open(start, now, today=_fixed_today) == expected_seconds

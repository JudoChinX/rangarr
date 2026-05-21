"""Tests for main.py formatting helper functions."""

from unittest.mock import Mock

import pytest


def _make_allocation_pairs(pairs: list[tuple[str, str]]) -> list[tuple[Mock, str]]:
    """Convert (name, item) string pairs into (Mock client, item) allocation pairs."""
    clients: dict[str, Mock] = {}
    result: list[tuple[Mock, str]] = []
    for name, item in pairs:
        if name not in clients:
            client = Mock()
            client.name = name
            clients[name] = client
        result.append((clients[name], item))
    return result


_calculate_eta_cases = {
    'stagger_disabled': {
        'item_count': 10,
        'stagger_seconds': 0,
        'expected': '',
    },
    'single_item': {
        'item_count': 1,
        'stagger_seconds': 1800,
        'expected': '',
    },
    'multiple_items': {
        'item_count': 441,
        'stagger_seconds': 1800,
        'expected': ' (1 every 1800 seconds, ETA: 9 days, 4:00:00)',
    },
    'two_items': {
        'item_count': 2,
        'stagger_seconds': 60,
        'expected': ' (1 every 60 seconds, ETA: 0:01:00)',
    },
}


@pytest.mark.parametrize(
    'item_count, stagger_seconds, expected',
    [(case['item_count'], case['stagger_seconds'], case['expected']) for case in _calculate_eta_cases.values()],
    ids=list(_calculate_eta_cases.keys()),
)
def test_calculate_eta(item_count: int, stagger_seconds: int, expected: str) -> None:
    """Test _calculate_eta returns correct ETA string or empty string when stagger is disabled."""
    from rangarr.main import _calculate_eta

    result = _calculate_eta(item_count, stagger_seconds)

    assert result == expected


_format_cycle_complete_log_cases = {
    'both_ran': {
        'ran_missing': True,
        'ran_upgrade': True,
        'next_missing_secs': 3600.0,
        'next_upgrade_secs': 21600.0,
        'expected': '--- Cycle complete (missing, upgrade). Next: missing in 60m, upgrade in 360m. ---',
    },
    'only_missing_ran': {
        'ran_missing': True,
        'ran_upgrade': False,
        'next_missing_secs': 3600.0,
        'next_upgrade_secs': 17999.0,
        'expected': '--- Cycle complete (missing). Next: missing in 60m, upgrade in 300m. ---',
    },
    'only_upgrade_ran': {
        'ran_missing': False,
        'ran_upgrade': True,
        'next_missing_secs': 1800.0,
        'next_upgrade_secs': 21600.0,
        'expected': '--- Cycle complete (upgrade). Next: missing in 30m, upgrade in 360m. ---',
    },
    'rounds_up_partial_minutes': {
        'ran_missing': True,
        'ran_upgrade': True,
        'next_missing_secs': 3599.5,
        'next_upgrade_secs': 61.0,
        'expected': '--- Cycle complete (missing, upgrade). Next: missing in 60m, upgrade in 2m. ---',
    },
    'cycle_exceeded_interval_clamps_to_zero': {
        'ran_missing': True,
        'ran_upgrade': True,
        'next_missing_secs': -65.0,
        'next_upgrade_secs': -5.0,
        'expected': '--- Cycle complete (missing, upgrade). Next: missing in 0m, upgrade in 0m. ---',
    },
    'neither_type_ran': {
        'ran_missing': False,
        'ran_upgrade': False,
        'next_missing_secs': 1800.0,
        'next_upgrade_secs': 3600.0,
        'expected': '--- Cycle complete (). Next: missing in 30m, upgrade in 60m. ---',
    },
}


@pytest.mark.parametrize(
    'ran_missing, ran_upgrade, next_missing_secs, next_upgrade_secs, expected',
    [
        (
            case['ran_missing'],
            case['ran_upgrade'],
            case['next_missing_secs'],
            case['next_upgrade_secs'],
            case['expected'],
        )
        for case in _format_cycle_complete_log_cases.values()
    ],
    ids=list(_format_cycle_complete_log_cases.keys()),
)
def test_format_cycle_complete_log(
    ran_missing: bool,
    ran_upgrade: bool,
    next_missing_secs: float,
    next_upgrade_secs: float,
    expected: str,
) -> None:
    """Test _format_cycle_complete_log produces correct message for all type combinations."""
    from rangarr.main import _format_cycle_complete_log

    result = _format_cycle_complete_log(ran_missing, ran_upgrade, next_missing_secs, next_upgrade_secs)

    assert result == expected


_format_instance_breakdown_cases = {
    'missing_only_single_instance': {
        'allocated_missing': [('Alpha', 'item1'), ('Alpha', 'item2'), ('Alpha', 'item3')],
        'allocated_upgrade': [],
        'expected': 'Alpha: 3 missing',
    },
    'upgrade_only_single_instance': {
        'allocated_missing': [],
        'allocated_upgrade': [('Beta', 'item1')],
        'expected': 'Beta: 1 upgrade',
    },
    'mixed_single_instance': {
        'allocated_missing': [('Alpha', 'item1'), ('Alpha', 'item2')],
        'allocated_upgrade': [('Alpha', 'item3')],
        'expected': 'Alpha: 2 missing, 1 upgrade',
    },
    'multiple_instances': {
        'allocated_missing': [('Alpha', 'item1'), ('Alpha', 'item2'), ('Beta', 'item3')],
        'allocated_upgrade': [('Beta', 'item4'), ('Gamma', 'item5')],
        'expected': 'Alpha: 2 missing, Beta: 1 missing, 1 upgrade, Gamma: 1 upgrade',
    },
    'preserves_allocation_order': {
        'allocated_missing': [('Beta', 'item1')],
        'allocated_upgrade': [('Alpha', 'item2')],
        'expected': 'Beta: 1 missing, Alpha: 1 upgrade',
    },
    'both_empty': {
        'allocated_missing': [],
        'allocated_upgrade': [],
        'expected': '',
    },
}


@pytest.mark.parametrize(
    'allocated_missing, allocated_upgrade, expected',
    [
        (case['allocated_missing'], case['allocated_upgrade'], case['expected'])
        for case in _format_instance_breakdown_cases.values()
    ],
    ids=list(_format_instance_breakdown_cases.keys()),
)
def test_format_instance_breakdown(
    allocated_missing: list[tuple[str, str]],
    allocated_upgrade: list[tuple[str, str]],
    expected: str,
) -> None:
    """Test _format_instance_breakdown returns correct per-instance item count string."""
    from rangarr.main import _format_instance_breakdown

    all_pairs = _make_allocation_pairs(allocated_missing + allocated_upgrade)
    result = _format_instance_breakdown(all_pairs[: len(allocated_missing)], all_pairs[len(allocated_missing) :])

    assert result == expected


_format_retry_interval_str_cases = {
    'no_overrides': {
        'retry_days': 30,
        'retry_missing': None,
        'retry_upgrade': None,
        'expected': 'Missing: 30d, Upgrade: 30d',
    },
    'disabled': {
        'retry_days': 0,
        'retry_missing': None,
        'retry_upgrade': None,
        'expected': 'Missing: Disabled, Upgrade: Disabled',
    },
    'missing_override_only': {
        'retry_days': 30,
        'retry_missing': 14,
        'retry_upgrade': None,
        'expected': 'Missing: 14d, Upgrade: 30d',
    },
    'upgrade_override_only': {
        'retry_days': 30,
        'retry_missing': None,
        'retry_upgrade': 60,
        'expected': 'Missing: 30d, Upgrade: 60d',
    },
    'both_overrides': {
        'retry_days': 30,
        'retry_missing': 14,
        'retry_upgrade': 60,
        'expected': 'Missing: 14d, Upgrade: 60d',
    },
    'base_disabled_with_missing_override': {
        'retry_days': 0,
        'retry_missing': 7,
        'retry_upgrade': None,
        'expected': 'Missing: 7d, Upgrade: Disabled',
    },
    'missing_override_equals_global': {
        'retry_days': 30,
        'retry_missing': 30,
        'retry_upgrade': 60,
        'expected': 'Missing: 30d, Upgrade: 60d',
    },
}


@pytest.mark.parametrize(
    'retry_days, retry_missing, retry_upgrade, expected',
    [
        (
            case['retry_days'],
            case['retry_missing'],
            case['retry_upgrade'],
            case['expected'],
        )
        for case in _format_retry_interval_str_cases.values()
    ],
    ids=list(_format_retry_interval_str_cases.keys()),
)
def test_format_retry_interval_str(
    retry_days: int,
    retry_missing: int | None,
    retry_upgrade: int | None,
    expected: str,
) -> None:
    """Test _format_retry_interval_str returns correct display string."""
    from rangarr.main import _format_retry_interval_str

    result = _format_retry_interval_str(retry_days, retry_missing, retry_upgrade)

    assert result == expected


_format_run_interval_str_cases = {
    'no_overrides': {
        'run_interval_m': 60,
        'run_interval_missing_m': None,
        'run_interval_upgrade_m': None,
        'expected': 'Missing: 60m, Upgrade: 60m',
    },
    'missing_override_only': {
        'run_interval_m': 60,
        'run_interval_missing_m': 30,
        'run_interval_upgrade_m': None,
        'expected': 'Missing: 30m, Upgrade: 60m',
    },
    'upgrade_override_only': {
        'run_interval_m': 60,
        'run_interval_missing_m': None,
        'run_interval_upgrade_m': 360,
        'expected': 'Missing: 60m, Upgrade: 360m',
    },
    'both_overrides': {
        'run_interval_m': 60,
        'run_interval_missing_m': 30,
        'run_interval_upgrade_m': 360,
        'expected': 'Missing: 30m, Upgrade: 360m',
    },
    'missing_override_equals_global': {
        'run_interval_m': 60,
        'run_interval_missing_m': 60,
        'run_interval_upgrade_m': 360,
        'expected': 'Missing: 60m, Upgrade: 360m',
    },
}


@pytest.mark.parametrize(
    'run_interval_m, run_interval_missing_m, run_interval_upgrade_m, expected',
    [
        (
            case['run_interval_m'],
            case['run_interval_missing_m'],
            case['run_interval_upgrade_m'],
            case['expected'],
        )
        for case in _format_run_interval_str_cases.values()
    ],
    ids=list(_format_run_interval_str_cases.keys()),
)
def test_format_run_interval_str(
    run_interval_m: int,
    run_interval_missing_m: int | None,
    run_interval_upgrade_m: int | None,
    expected: str,
) -> None:
    """Test _format_run_interval_str returns correct display string."""
    from rangarr.main import _format_run_interval_str

    result = _format_run_interval_str(run_interval_m, run_interval_missing_m, run_interval_upgrade_m)

    assert result == expected


_resolve_interval_secs_cases = {
    'specific_key_overrides_global': {
        'settings': {'run_interval_minutes': 60, 'run_interval_minutes_missing': 30},
        'specific_key': 'run_interval_minutes_missing',
        'expected': 1800.0,
    },
    'falls_back_to_global_when_specific_absent': {
        'settings': {'run_interval_minutes': 120},
        'specific_key': 'run_interval_minutes_missing',
        'expected': 7200.0,
    },
}


@pytest.mark.parametrize(
    'settings, specific_key, expected',
    [
        (
            case['settings'],
            case['specific_key'],
            case['expected'],
        )
        for case in _resolve_interval_secs_cases.values()
    ],
    ids=list(_resolve_interval_secs_cases.keys()),
)
def test_resolve_interval_secs(settings: dict, specific_key: str, expected: float) -> None:
    """Test _resolve_interval_secs returns per-type interval in seconds with correct fallback."""
    from rangarr.main import _resolve_interval_secs

    result = _resolve_interval_secs(settings, specific_key)

    assert result == expected

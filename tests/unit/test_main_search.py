"""Tests for main.py search orchestration: _run_search_cycle and _build_final_queue."""

import logging
from unittest.mock import Mock
from unittest.mock import call

import pytest

from rangarr.main import _apply_queue_headroom
from rangarr.main import _build_final_queue
from rangarr.main import _run_search_cycle

_build_final_queue_cases = {
    'instances_true_types_true': {
        'interleave_instances': True,
        'interleave_types': True,
        'expected_titles': ['AM1', 'AU1', 'BM1', 'BU1', 'AM2', 'AU2', 'BM2', 'BU2'],
    },
    'instances_false_types_true': {
        'interleave_instances': False,
        'interleave_types': True,
        'expected_titles': ['AM1', 'AU1', 'AM2', 'AU2', 'BM1', 'BU1', 'BM2', 'BU2'],
    },
    'instances_true_types_false': {
        'interleave_instances': True,
        'interleave_types': False,
        'expected_titles': ['AM1', 'BM1', 'AM2', 'BM2', 'AU1', 'BU1', 'AU2', 'BU2'],
    },
    'instances_false_types_false': {
        'interleave_instances': False,
        'interleave_types': False,
        'expected_titles': ['AM1', 'AM2', 'AU1', 'AU2', 'BM1', 'BM2', 'BU1', 'BU2'],
    },
}


@pytest.mark.parametrize(
    'interleave_instances, interleave_types, expected_titles',
    [
        (case['interleave_instances'], case['interleave_types'], case['expected_titles'])
        for case in _build_final_queue_cases.values()
    ],
    ids=list(_build_final_queue_cases.keys()),
)
def test_build_final_queue(
    interleave_instances: bool,
    interleave_types: bool,
    expected_titles: list[str],
) -> None:
    """Test _build_final_queue produces the correct execution order for all flag combinations."""
    client_a = Mock()
    client_b = Mock()
    am1 = (1, 'missing', 'AM1')
    am2 = (2, 'missing', 'AM2')
    au1 = (3, 'upgrade', 'AU1')
    au2 = (4, 'upgrade', 'AU2')
    bm1 = (5, 'missing', 'BM1')
    bm2 = (6, 'missing', 'BM2')
    bu1 = (7, 'upgrade', 'BU1')
    bu2 = (8, 'upgrade', 'BU2')

    allocated_missing = [(client_a, am1), (client_b, bm1), (client_a, am2), (client_b, bm2)]
    allocated_upgrade = [(client_a, au1), (client_b, bu1), (client_a, au2), (client_b, bu2)]

    queue = _build_final_queue(allocated_missing, allocated_upgrade, interleave_instances, interleave_types)

    assert [item[2] for _, item in queue] == expected_titles


def test_run_search_cycle_both_disabled(mock_client: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that search cycle reports no media when both batch types are disabled."""
    settings = {
        'interleave_instances': False,
        'missing_batch_size': 0,
        'stagger_interval_seconds': 30,
        'upgrade_batch_size': 0,
    }

    with caplog.at_level(logging.INFO):
        _run_search_cycle([mock_client], settings)

    assert 'No media to search this cycle across all instances.' in caplog.text
    mock_client.get_media_to_search.assert_called_once_with(0, 0)
    mock_client.trigger_search.assert_not_called()


def test_run_search_cycle_counter_increments(mock_client: Mock) -> None:
    """Test that trigger_search receives incrementing index and correct total across a multi-item queue."""
    item_a = (1, 'missing', 'Item One')
    item_b = (2, 'missing', 'Item Two')
    item_c = (3, 'missing', 'Item Three')
    mock_client.get_media_to_search = Mock(return_value=[item_a, item_b, item_c])

    settings = {
        'interleave_instances': False,
        'missing_batch_size': 3,
        'stagger_interval_seconds': 0,
        'upgrade_batch_size': 0,
    }

    _run_search_cycle([mock_client], settings)

    assert mock_client.trigger_search.call_args_list == [
        call([item_a], index=1, total=3),
        call([item_b], index=2, total=3),
        call([item_c], index=3, total=3),
    ]


def test_run_search_cycle_missing_disabled(mock_client: Mock) -> None:
    """Test that search cycle still processes upgrade items when missing is disabled."""
    upgrade_item = (1, 'upgrade', 'Movie 1')
    mock_client.get_media_to_search = Mock(return_value=[upgrade_item])

    settings = {
        'interleave_instances': False,
        'missing_batch_size': 0,
        'stagger_interval_seconds': 30,
        'upgrade_batch_size': 10,
    }

    _run_search_cycle([mock_client], settings)

    mock_client.get_media_to_search.assert_called_once_with(0, 10)
    mock_client.trigger_search.assert_called_once_with([upgrade_item], index=1, total=1)


def test_run_search_cycle_run_missing_false_skips_missing_fetch(mock_client: Mock) -> None:
    """Test that run_missing=False passes missing_batch_size=0 to get_media_to_search."""
    upgrade_item = (1, 'upgrade', 'Movie 1')
    mock_client.get_media_to_search = Mock(return_value=[upgrade_item])

    settings = {
        'interleave_instances': False,
        'missing_batch_size': 20,
        'stagger_interval_seconds': 0,
        'upgrade_batch_size': 10,
    }

    _run_search_cycle([mock_client], settings, run_missing=False)

    mock_client.get_media_to_search.assert_called_once_with(0, 10)
    mock_client.trigger_search.assert_called_once_with([upgrade_item], index=1, total=1)


def test_run_search_cycle_run_upgrade_false_skips_upgrade_fetch(mock_client: Mock) -> None:
    """Test that run_upgrade=False passes upgrade_batch_size=0 to get_media_to_search."""
    missing_item = (1, 'missing', 'Movie 1')
    mock_client.get_media_to_search = Mock(return_value=[missing_item])

    settings = {
        'interleave_instances': False,
        'missing_batch_size': 20,
        'stagger_interval_seconds': 0,
        'upgrade_batch_size': 10,
    }

    _run_search_cycle([mock_client], settings, run_upgrade=False)

    mock_client.get_media_to_search.assert_called_once_with(20, 0)
    mock_client.trigger_search.assert_called_once_with([missing_item], index=1, total=1)


def test_run_search_cycle_unlimited(mock_client: Mock) -> None:
    """Test that search cycle passes -1 for unlimited batch size."""
    mock_client.get_media_to_search = Mock(
        return_value=[
            (1, 'missing', 'Movie 1'),
            (2, 'missing', 'Movie 2'),
        ]
    )

    settings = {
        'interleave_instances': False,
        'missing_batch_size': -1,
        'stagger_interval_seconds': 0,
        'upgrade_batch_size': 10,
    }

    _run_search_cycle([mock_client], settings)

    mock_client.get_media_to_search.assert_called_once_with(-1, 10)


def test_run_search_cycle_logs_instance_breakdown(mock_client: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that the batch log line includes count and per-instance breakdown."""
    mock_client.get_media_to_search = Mock(return_value=[(1, 'missing', 'Item 1'), (2, 'missing', 'Item 2')])

    settings = {
        'interleave_instances': False,
        'missing_batch_size': 2,
        'stagger_interval_seconds': 0,
        'upgrade_batch_size': 0,
    }

    with caplog.at_level(logging.INFO):
        _run_search_cycle([mock_client], settings)

    assert f'Total search batch: 2 item(s) | {mock_client.name}: 2 missing' in caplog.text


_apply_queue_headroom_cases = {
    'proportional_split': {
        'missing_count': 10,
        'upgrade_count': 10,
        'headroom': 3,
        'global_missing': 20,
        'global_upgrade': 10,
        'expected_missing': 2,
        'expected_upgrade': 1,
    },
    'spill_to_missing_when_no_upgrades': {
        'missing_count': 10,
        'upgrade_count': 0,
        'headroom': 3,
        'global_missing': 20,
        'global_upgrade': 10,
        'expected_missing': 3,
        'expected_upgrade': 0,
    },
    'spill_to_upgrade_when_no_missing': {
        'missing_count': 0,
        'upgrade_count': 10,
        'headroom': 3,
        'global_missing': 20,
        'global_upgrade': 10,
        'expected_missing': 0,
        'expected_upgrade': 3,
    },
    'all_missing_when_upgrades_disabled': {
        'missing_count': 10,
        'upgrade_count': 0,
        'headroom': 4,
        'global_missing': 20,
        'global_upgrade': 0,
        'expected_missing': 4,
        'expected_upgrade': 0,
    },
    'fewer_candidates_than_headroom': {
        'missing_count': 2,
        'upgrade_count': 1,
        'headroom': 10,
        'global_missing': 20,
        'global_upgrade': 10,
        'expected_missing': 2,
        'expected_upgrade': 1,
    },
    'banker_rounding_favors_upgrade': {
        'missing_count': 10,
        'upgrade_count': 10,
        'headroom': 5,
        'global_missing': 10,
        'global_upgrade': 10,
        'expected_missing': 2,
        'expected_upgrade': 3,
    },
    'unlimited_missing_caps_to_headroom': {
        'missing_count': 100,
        'upgrade_count': 100,
        'headroom': 10,
        'global_missing': -1,
        'global_upgrade': 20,
        'expected_missing': 3,
        'expected_upgrade': 7,
    },
    'both_unlimited_splits_evenly': {
        'missing_count': 100,
        'upgrade_count': 100,
        'headroom': 10,
        'global_missing': -1,
        'global_upgrade': -1,
        'expected_missing': 5,
        'expected_upgrade': 5,
    },
    'zero_headroom_caps_to_nothing': {
        'missing_count': 10,
        'upgrade_count': 10,
        'headroom': 0,
        'global_missing': 20,
        'global_upgrade': 10,
        'expected_missing': 0,
        'expected_upgrade': 0,
    },
}


@pytest.mark.parametrize(
    'missing_count, upgrade_count, headroom, global_missing, global_upgrade, expected_missing, expected_upgrade',
    [
        (
            case['missing_count'],
            case['upgrade_count'],
            case['headroom'],
            case['global_missing'],
            case['global_upgrade'],
            case['expected_missing'],
            case['expected_upgrade'],
        )
        for case in _apply_queue_headroom_cases.values()
    ],
    ids=list(_apply_queue_headroom_cases.keys()),
)
def test_apply_queue_headroom(
    missing_count: int,
    upgrade_count: int,
    headroom: int,
    global_missing: int,
    global_upgrade: int,
    expected_missing: int,
    expected_upgrade: int,
) -> None:
    """Test that _apply_queue_headroom caps candidates to the shared headroom with proportional split and spillover."""
    missing_items = [(idx, 'missing', f'M{idx}') for idx in range(missing_count)]
    upgrade_items = [(idx, 'upgrade', f'U{idx}') for idx in range(upgrade_count)]

    capped_missing, capped_upgrade = _apply_queue_headroom(
        missing_items, upgrade_items, headroom, global_missing, global_upgrade
    )

    assert len(capped_missing) == expected_missing
    assert len(capped_upgrade) == expected_upgrade
    assert len(capped_missing) + len(capped_upgrade) <= headroom


def test_run_search_cycle_queue_disabled_skips_check(mock_client: Mock) -> None:
    """Test that max_queue_size=0 means the queue endpoint is never consulted."""
    mock_client.max_queue_size = 0
    mock_client.get_media_to_search = Mock(return_value=[(1, 'missing', 'Item 1')])
    settings = {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'stagger_interval_seconds': 0,
        'interleave_instances': False,
        'interleave_types': True,
    }

    _run_search_cycle([mock_client], settings)

    mock_client.get_active_queue_depth.assert_not_called()
    mock_client.trigger_search.assert_called_once()


def test_run_search_cycle_queue_full_skips_instance(mock_client: Mock, caplog: pytest.LogCaptureFixture) -> None:
    """Test that an instance whose queue is at/above the threshold is skipped without searching."""
    mock_client.max_queue_size = 20
    mock_client.get_active_queue_depth = Mock(return_value=22)
    settings = {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'stagger_interval_seconds': 0,
        'interleave_instances': False,
        'interleave_types': True,
    }

    with caplog.at_level(logging.INFO):
        _run_search_cycle([mock_client], settings)

    mock_client.get_media_to_search.assert_not_called()
    mock_client.trigger_search.assert_not_called()
    assert 'queue depth 22' in caplog.text


def test_run_search_cycle_queue_headroom_caps_batch(mock_client: Mock) -> None:
    """Test that an instance with limited headroom only searches up to that headroom."""
    mock_client.max_queue_size = 20
    mock_client.get_active_queue_depth = Mock(return_value=18)
    mock_client.get_media_to_search = Mock(return_value=[(idx, 'missing', f'Item {idx}') for idx in range(10)])
    settings = {
        'missing_batch_size': 20,
        'upgrade_batch_size': 0,
        'stagger_interval_seconds': 0,
        'interleave_instances': False,
        'interleave_types': True,
    }

    _run_search_cycle([mock_client], settings)

    # headroom = 20 - 18 = 2, so exactly 2 items are searched
    assert mock_client.trigger_search.call_count == 2


def test_run_search_cycle_queue_headroom_splits_missing_and_upgrade(mock_client: Mock) -> None:
    """Test headroom capping flows through the full cycle with both missing and upgrade candidates."""
    mock_client.max_queue_size = 20
    mock_client.get_active_queue_depth = Mock(return_value=17)  # headroom = 3
    mock_client.get_media_to_search = Mock(
        return_value=[(idx, 'missing', f'M{idx}') for idx in range(10)]
        + [(idx, 'upgrade', f'U{idx}') for idx in range(10)]
    )
    settings = {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'stagger_interval_seconds': 0,
        'interleave_instances': False,
        'interleave_types': True,
    }

    _run_search_cycle([mock_client], settings)

    # headroom=3, ratio 20:10 -> missing_share=round(3*20/30)=2, upgrade_share=1 -> 3 searches total
    assert mock_client.trigger_search.call_count == 3


def test_run_search_cycle_queue_check_failure_skips_instance(
    mock_client: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that a None queue depth (fetch failure) skips the instance for the cycle (fail-closed)."""
    mock_client.max_queue_size = 20
    mock_client.get_active_queue_depth = Mock(return_value=None)
    mock_client.get_media_to_search = Mock(return_value=[(1, 'missing', 'Item 1')])
    settings = {
        'missing_batch_size': 20,
        'upgrade_batch_size': 10,
        'stagger_interval_seconds': 0,
        'interleave_instances': False,
        'interleave_types': True,
    }

    with caplog.at_level(logging.WARNING):
        _run_search_cycle([mock_client], settings)

    mock_client.get_media_to_search.assert_not_called()
    mock_client.trigger_search.assert_not_called()
    assert 'Queue check failed' in caplog.text


def test_run_search_cycle_unlimited_batch_respects_headroom(mock_client: Mock) -> None:
    """Test that an unlimited (-1) batch size still caps searches to the queue headroom."""
    mock_client.max_queue_size = 20
    mock_client.get_active_queue_depth = Mock(return_value=10)  # headroom = 10
    mock_client.get_media_to_search = Mock(
        return_value=[(idx, 'missing', f'M{idx}') for idx in range(100)]
        + [(idx, 'upgrade', f'U{idx}') for idx in range(100)]
    )
    settings = {
        'missing_batch_size': -1,
        'upgrade_batch_size': 20,
        'stagger_interval_seconds': 0,
        'interleave_instances': False,
        'interleave_types': True,
    }

    _run_search_cycle([mock_client], settings)

    assert mock_client.trigger_search.call_count == 10

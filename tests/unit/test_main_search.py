"""Tests for main.py search orchestration: _run_search_cycle and _build_final_queue."""

import logging
from unittest.mock import Mock
from unittest.mock import call

import pytest

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

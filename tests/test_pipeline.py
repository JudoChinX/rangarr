"""Integration tests for the 3-stage search pipeline in _run_search_cycle."""

import logging
from collections.abc import Callable
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from rangarr.main import _run_search_cycle


def _make_mock_client(name: str, weight: float, media: list[tuple[int, str, str]]) -> Mock:
    """Create a mock client with the given name, weight, and media items."""
    client = Mock()
    client.name = name
    client.weight = weight
    client.get_media_to_search = Mock(return_value=media)
    client.trigger_search = Mock()
    return client


def _make_settings(
    missing: int,
    upgrade: int,
    stagger: int = 0,
    interleave_instances: bool = False,
    interleave_types: bool = True,
) -> dict:
    """Create a minimal settings dict for pipeline tests."""
    return {
        'interleave_instances': interleave_instances,
        'interleave_types': interleave_types,
        'missing_batch_size': missing,
        'stagger_interval_seconds': stagger,
        'upgrade_batch_size': upgrade,
    }


def _make_trigger_side_effect(accumulator: list) -> Callable[..., None]:
    """Return a trigger_search side effect that appends dispatched items to accumulator."""
    return lambda items, **kwargs: accumulator.extend(items)


def test_pipeline_distributes_across_two_clients() -> None:
    """Test global allocation distributes slots across two equal-weight clients."""
    client_a = _make_mock_client('ClientA', 1.0, [(1, 'missing', 'A1'), (2, 'missing', 'A2')])
    client_b = _make_mock_client('ClientB', 1.0, [(3, 'missing', 'B1'), (4, 'missing', 'B2')])
    settings = _make_settings(missing=3, upgrade=0)

    _run_search_cycle([client_a, client_b], settings)

    total_calls = client_a.trigger_search.call_count + client_b.trigger_search.call_count
    assert total_calls == 3
    assert client_a.trigger_search.call_count >= 1
    assert client_b.trigger_search.call_count >= 1


def test_pipeline_groups_by_instance_when_not_interleaved() -> None:
    """Test all of client A's items execute before client B's when interleave_instances is False."""
    client_a = _make_mock_client('ClientA', 1.0, [(1, 'missing', 'A1'), (2, 'missing', 'A2')])
    client_b = _make_mock_client('ClientB', 1.0, [(3, 'missing', 'B1'), (4, 'missing', 'B2')])
    settings = _make_settings(missing=4, upgrade=0, interleave_instances=False)

    triggered_items: list = []
    client_a.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))
    client_b.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))

    _run_search_cycle([client_a, client_b], settings)

    titles = [item[2] for item in triggered_items]
    assert titles == ['A1', 'A2', 'B1', 'B2']


def test_pipeline_interleaves_across_clients_when_enabled() -> None:
    """Test items from multiple clients alternate when interleave_instances is True."""
    client_a = _make_mock_client('ClientA', 1.0, [(1, 'missing', 'A1'), (2, 'missing', 'A2')])
    client_b = _make_mock_client('ClientB', 1.0, [(3, 'missing', 'B1'), (4, 'missing', 'B2')])
    settings = _make_settings(missing=4, upgrade=0, interleave_instances=True)

    triggered_items: list = []
    client_a.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))
    client_b.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))

    _run_search_cycle([client_a, client_b], settings)

    titles = [item[2] for item in triggered_items]
    assert titles == ['A1', 'B1', 'A2', 'B2']


def test_pipeline_interleaves_missing_and_upgrade() -> None:
    """Test missing and upgrade items are interleaved in the final queue."""
    client = _make_mock_client(
        'Client',
        1.0,
        [
            (1, 'missing', 'M1'),
            (2, 'missing', 'M2'),
            (3, 'upgrade', 'U1'),
            (4, 'upgrade', 'U2'),
        ],
    )
    settings = _make_settings(missing=2, upgrade=2)

    triggered_items: list = []
    client.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))

    _run_search_cycle([client], settings)

    assert len(triggered_items) == 4
    titles = [item[2] for item in triggered_items]
    assert titles == ['M1', 'U1', 'M2', 'U2']


def test_pipeline_logs_no_media_when_empty(caplog: pytest.LogCaptureFixture) -> None:
    """Test correct message is logged when no items are available across all clients."""
    client = _make_mock_client('Client', 1.0, [])
    settings = _make_settings(missing=5, upgrade=5)

    with caplog.at_level(logging.INFO):
        _run_search_cycle([client], settings)

    assert 'No media to search this cycle across all instances.' in caplog.text


def test_pipeline_redistributes_when_client_has_no_items() -> None:
    """Test that slots redistribute to client B when client A has no items."""
    client_a = _make_mock_client('ClientA', 1.0, [])
    client_b = _make_mock_client(
        'ClientB',
        1.0,
        [(1, 'missing', 'B1'), (2, 'missing', 'B2'), (3, 'missing', 'B3')],
    )
    settings = _make_settings(missing=3, upgrade=0)

    _run_search_cycle([client_a, client_b], settings)

    client_a.trigger_search.assert_not_called()
    assert client_b.trigger_search.call_count == 3


def test_pipeline_staggers_between_items() -> None:
    """Test time.sleep is called between items but not after the last one."""
    client = _make_mock_client(
        'Client',
        1.0,
        [(1, 'missing', 'M1'), (2, 'missing', 'M2')],
    )
    settings = _make_settings(missing=2, upgrade=0, stagger=5)

    with patch('rangarr.main.time.sleep') as mock_sleep:
        _run_search_cycle([client], settings)

    mock_sleep.assert_called_once_with(5)


def test_pipeline_missing_before_upgrades_with_instance_interleave() -> None:
    """Test all missing items execute before upgrades when interleave_types is False and instances are interleaved."""
    client_a = _make_mock_client(
        'ClientA',
        1.0,
        [
            (1, 'missing', 'AM1'),
            (2, 'missing', 'AM2'),
            (3, 'upgrade', 'AU1'),
            (4, 'upgrade', 'AU2'),
        ],
    )
    client_b = _make_mock_client(
        'ClientB',
        1.0,
        [
            (5, 'missing', 'BM1'),
            (6, 'missing', 'BM2'),
            (7, 'upgrade', 'BU1'),
            (8, 'upgrade', 'BU2'),
        ],
    )
    settings = _make_settings(missing=4, upgrade=4, interleave_instances=True, interleave_types=False)

    triggered_items: list = []
    client_a.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))
    client_b.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))

    _run_search_cycle([client_a, client_b], settings)

    titles = [item[2] for item in triggered_items]
    missing_indices = [idx for idx, title in enumerate(titles) if title.startswith(('AM', 'BM'))]
    upgrade_indices = [idx for idx, title in enumerate(titles) if title.startswith(('AU', 'BU'))]
    assert max(missing_indices) < min(upgrade_indices)


def test_pipeline_missing_before_upgrades_per_instance() -> None:
    """Test per-instance grouping with missing before upgrades when interleave_types is False."""
    client_a = _make_mock_client(
        'ClientA',
        1.0,
        [
            (1, 'missing', 'AM1'),
            (2, 'missing', 'AM2'),
            (3, 'upgrade', 'AU1'),
            (4, 'upgrade', 'AU2'),
        ],
    )
    client_b = _make_mock_client(
        'ClientB',
        1.0,
        [
            (5, 'missing', 'BM1'),
            (6, 'missing', 'BM2'),
            (7, 'upgrade', 'BU1'),
            (8, 'upgrade', 'BU2'),
        ],
    )
    settings = _make_settings(missing=4, upgrade=4, interleave_instances=False, interleave_types=False)

    triggered_items: list = []
    client_a.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))
    client_b.trigger_search = Mock(side_effect=_make_trigger_side_effect(triggered_items))

    _run_search_cycle([client_a, client_b], settings)

    titles = [item[2] for item in triggered_items]
    assert titles == ['AM1', 'AM2', 'AU1', 'AU2', 'BM1', 'BM2', 'BU1', 'BU2']

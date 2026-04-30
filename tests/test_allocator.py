"""Tests for _allocate_slots weighted round-robin slot distribution."""

from unittest.mock import Mock

import pytest

from rangarr.main import _allocate_slots

_allocate_slots_cases = {
    'fair_distribution': {
        'limit': 3,
        'clients': [
            {'name': 'ClientA', 'weight': 1.0, 'items': [(1, 'missing', 'A1'), (2, 'missing', 'A2')]},
            {'name': 'ClientB', 'weight': 1.0, 'items': [(3, 'missing', 'B1'), (4, 'missing', 'B2')]},
        ],
        'expected_titles': ['A1', 'B1', 'A2'],
    },
    'redistribution': {
        'limit': 3,
        'clients': [
            {'name': 'ClientA', 'weight': 1.0, 'items': []},
            {
                'name': 'ClientB',
                'weight': 1.0,
                'items': [(1, 'missing', 'B1'), (2, 'missing', 'B2'), (3, 'missing', 'B3')],
            },
        ],
        'expected_titles': ['B1', 'B2', 'B3'],
    },
    'weighted_distribution': {
        'limit': 5,
        'clients': [
            {
                'name': 'ClientA',
                'weight': 2.0,
                'items': [(1, 'missing', 'A1'), (2, 'missing', 'A2'), (3, 'missing', 'A3')],
            },
            {'name': 'ClientB', 'weight': 1.0, 'items': [(4, 'missing', 'B1'), (5, 'missing', 'B2')]},
        ],
        'expected_titles': ['A1', 'A2', 'B1', 'A3', 'B2'],
    },
    'limit_larger_than_items': {
        'limit': 10,
        'clients': [
            {'name': 'ClientA', 'weight': 1.0, 'items': [(1, 'missing', 'A1')]},
            {'name': 'ClientB', 'weight': 1.0, 'items': [(2, 'missing', 'B1')]},
        ],
        'expected_titles': ['A1', 'B1'],
    },
    'limit_reached_mid_turn_weighted_client': {
        'limit': 1,
        'clients': [
            {'name': 'ClientA', 'weight': 2.0, 'items': [(1, 'missing', 'A1'), (2, 'missing', 'A2')]},
        ],
        'expected_titles': ['A1'],
    },
    'zero_limit_returns_empty': {
        'limit': 0,
        'clients': [
            {'name': 'ClientA', 'weight': 1.0, 'items': [(1, 'missing', 'A1')]},
        ],
        'expected_titles': [],
    },
    'empty_backlogs_returns_empty': {
        'limit': 3,
        'clients': [],
        'expected_titles': [],
    },
    'unlimited_returns_all_items': {
        'limit': -1,
        'clients': [
            {'name': 'ClientA', 'weight': 1.0, 'items': [(1, 'missing', 'A1'), (2, 'missing', 'A2')]},
            {'name': 'ClientB', 'weight': 1.0, 'items': [(3, 'missing', 'B1')]},
        ],
        'expected_titles': ['A1', 'B1', 'A2'],
    },
}


@pytest.mark.parametrize(
    'limit, clients, expected_titles',
    [(case['limit'], case['clients'], case['expected_titles']) for case in _allocate_slots_cases.values()],
    ids=list(_allocate_slots_cases.keys()),
)
def test_allocate_slots(limit: int, clients: list[dict], expected_titles: list[str]) -> None:
    """Test _allocate_slots distributes slots using weighted round-robin."""
    backlogs: dict[Mock, list] = {}
    for spec in clients:
        client = Mock()
        client.name = spec['name']
        client.weight = spec['weight']
        backlogs[client] = spec['items']

    winners = _allocate_slots(limit, backlogs)

    assert [item[2] for _, item in winners] == expected_titles

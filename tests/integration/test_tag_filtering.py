"""Tests for tag resolution and tag-based filtering in ArrClient."""

import logging
from typing import Any
from unittest.mock import patch

import pytest
import requests

from tests.builders import ClientBuilder
from tests.builders import RadarrRecordBuilder
from tests.builders import mock_tag_api

_process_record_tag_filter_cases = {
    'no_filtering_when_tag_sets_empty': {
        'tag_data': [],
        'include_tags': [],
        'exclude_tags': [],
        'record_tags': [99],
        'expected_match': True,
    },
    'keeps_item_matching_include_tag': {
        'tag_data': [{'id': 1, 'label': 'keep'}],
        'include_tags': ['keep'],
        'exclude_tags': [],
        'record_tags': [1],
        'expected_match': True,
    },
    'skips_item_not_matching_include_tag': {
        'tag_data': [{'id': 1, 'label': 'keep'}],
        'include_tags': ['keep'],
        'exclude_tags': [],
        'record_tags': [99],
        'expected_match': False,
    },
    'skips_item_with_excluded_tag': {
        'tag_data': [{'id': 5, 'label': 'skip'}],
        'include_tags': [],
        'exclude_tags': ['skip'],
        'record_tags': [5],
        'expected_match': False,
    },
    'exclude_wins_over_include': {
        'tag_data': [{'id': 1, 'label': 'keep'}, {'id': 2, 'label': 'skip'}],
        'include_tags': ['keep'],
        'exclude_tags': ['skip'],
        'record_tags': [1, 2],
        'expected_match': False,
    },
}


@pytest.mark.parametrize(
    'tag_data, include_tags, exclude_tags, record_tags, expected_match',
    [
        (
            case['tag_data'],
            case['include_tags'],
            case['exclude_tags'],
            case['record_tags'],
            case['expected_match'],
        )
        for case in _process_record_tag_filter_cases.values()
    ],
    ids=list(_process_record_tag_filter_cases.keys()),
)
def test_process_record_tag_filtering(
    tag_data: Any,
    include_tags: Any,
    exclude_tags: Any,
    record_tags: Any,
    expected_match: Any,
) -> None:
    """Test that _process_record applies include/exclude tag filtering correctly."""
    builder = ClientBuilder()
    if include_tags:
        builder = builder.with_include_tags(*include_tags)
    if exclude_tags:
        builder = builder.with_exclude_tags(*exclude_tags)
    with patch.object(requests.Session, 'get', return_value=mock_tag_api(tag_data)):
        client = builder.build()
    record = RadarrRecordBuilder().with_tags(record_tags).build()
    result = client._process_record(record, 'missing', set())
    if expected_match:
        assert result is not None
    else:
        assert result is None


def test_resolve_tag_ids_falls_back_to_empty_sets_on_api_error(caplog: pytest.LogCaptureFixture) -> None:
    """Test that tag filtering is disabled when the tag API call fails."""
    with patch.object(requests.Session, 'get', side_effect=requests.RequestException('timeout')):
        with caplog.at_level(logging.ERROR):
            client = ClientBuilder().with_include_tags('action').build()
    assert client._include_tag_ids == set()
    assert client._exclude_tag_ids == set()
    assert 'tag filtering disabled' in caplog.text


def test_resolve_tag_ids_resolves_names_case_insensitively() -> None:
    """Test that tag names are matched case-insensitively when resolving IDs."""
    tag_data = [{'id': 1, 'label': 'action'}, {'id': 2, 'label': 'drama'}]
    with patch.object(requests.Session, 'get', return_value=mock_tag_api(tag_data)):
        client = ClientBuilder().with_include_tags('Action').with_exclude_tags('DRAMA').build()
    assert client._include_tag_ids == {1}
    assert client._exclude_tag_ids == {2}


def test_resolve_tag_ids_skips_api_call_when_no_tags_configured() -> None:
    """Test that no HTTP request is made when include_tags and exclude_tags are both empty."""
    with patch.object(requests.Session, 'get') as mock_get:
        ClientBuilder().build()
    mock_get.assert_not_called()


def test_resolve_tag_ids_warns_on_unknown_tag(caplog: pytest.LogCaptureFixture) -> None:
    """Test that a warning is logged and the tag is skipped when a name is not found."""
    tag_data = [{'id': 1, 'label': 'action'}]
    with patch.object(requests.Session, 'get', return_value=mock_tag_api(tag_data)):
        with caplog.at_level(logging.WARNING):
            client = ClientBuilder().with_include_tags('missing-tag').build()
    assert client._include_tag_ids == set()
    assert 'missing-tag' in caplog.text

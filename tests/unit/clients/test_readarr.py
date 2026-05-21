"""Tests specific to the ReadarrClient implementation."""

from unittest.mock import MagicMock

import pytest

from tests.builders import ClientBuilder
from tests.builders import ReadarrRecordBuilder


def test_readarr_command_name() -> None:
    """Test ReadarrClient._command_name returns 'BookSearch'."""
    client = ClientBuilder().readarr().build()
    assert client._command_name == 'BookSearch'  # pylint: disable=protected-access


def test_readarr_fetch_quality_profile_cutoffs_returns_empty() -> None:
    """Test ReadarrClient._fetch_quality_profile_cutoffs always returns {} without HTTP calls."""
    client = ClientBuilder().readarr().build()
    client.session.get = MagicMock()
    result = client._fetch_quality_profile_cutoffs()  # pylint: disable=protected-access
    assert result == {}
    client.session.get.assert_not_called()


def test_readarr_get_record_tags() -> None:
    """Test ReadarrClient._get_record_tags returns tags list from record."""
    client = ClientBuilder().readarr().build()
    assert client._get_record_tags({'tags': [1, 2]}) == [1, 2]  # pylint: disable=protected-access
    assert client._get_record_tags({}) == []  # pylint: disable=protected-access


def test_readarr_get_record_title() -> None:
    """Test ReadarrClient._get_record_title formats Author - Book correctly."""
    client = ClientBuilder().readarr().build()
    record = ReadarrRecordBuilder().with_author('Test Author').with_title('Test Book').build()
    assert client._get_record_title(record) == 'Test Author - Test Book'  # pylint: disable=protected-access


def test_readarr_get_record_title_unknown() -> None:
    """Test ReadarrClient._get_record_title handles missing author or book title."""
    client = ClientBuilder().readarr().build()
    assert client._get_record_title({}) == 'Unknown Author - Unknown Book'  # pylint: disable=protected-access


def test_readarr_get_release_date() -> None:
    """Test ReadarrClient._get_release_date returns releaseDate field."""
    client = ClientBuilder().readarr().build()
    record = {'releaseDate': '2023-10-27T00:00:00Z'}
    assert client._get_release_date(record) == '2023-10-27T00:00:00Z'  # pylint: disable=protected-access


def test_readarr_id_field() -> None:
    """Test ReadarrClient._id_field returns 'bookIds'."""
    client = ClientBuilder().readarr().build()
    assert client._id_field == 'bookIds'  # pylint: disable=protected-access


_is_available_cases = {
    'future_release_date': {
        'release_date': '2030-01-01T00:00:00Z',
        'expected': False,
    },
    'missing_release_date': {
        'release_date': None,
        'expected': False,
    },
    'past_release_date': {
        'release_date': '2020-01-01T00:00:00Z',
        'expected': True,
    },
}


@pytest.mark.parametrize(
    'release_date, expected',
    [(case['release_date'], case['expected']) for case in _is_available_cases.values()],
    ids=list(_is_available_cases.keys()),
)
def test_readarr_is_available(release_date: str | None, expected: bool) -> None:
    """Test ReadarrClient._is_available based on releaseDate."""
    client = ClientBuilder().readarr().build()
    record = {'releaseDate': release_date}
    assert client._is_available(record) == expected  # pylint: disable=protected-access

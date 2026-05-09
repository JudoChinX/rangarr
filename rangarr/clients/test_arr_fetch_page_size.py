"""Tests for the fetch_page_size setting in ArrClient._fetch_unlimited."""

from collections.abc import Callable
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from rangarr.clients.arr import RadarrClient
from tests.builders import ClientBuilder

_fetch_unlimited_page_size_cases = {
    'default_page_size': {
        'page_size': None,
        'record_count': 100,
        'expected_page_size': 2000,
        'expected_record_count': 100,
        'expected_call_count': 1,
    },
    'custom_page_size_500': {
        'page_size': 500,
        'record_count': 3500,
        'expected_page_size': 500,
        'expected_record_count': 3500,
        'expected_call_count': 8,
    },
    'custom_page_size_5000': {
        'page_size': 5000,
        'record_count': 100,
        'expected_page_size': 5000,
        'expected_record_count': 100,
        'expected_call_count': 1,
    },
}


def _paged_responses(records: list[dict]) -> Callable[..., MagicMock]:
    """Return a side-effect function that simulates paginated API responses."""

    def side_effect(*_args: object, **kwargs: object) -> MagicMock:
        params = kwargs.get('params', {})
        page = params.get('page', 1)
        page_size = params['pageSize']
        start = (page - 1) * page_size
        chunk = records[start : start + page_size]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'records': chunk}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    return side_effect


@pytest.mark.parametrize(
    'page_size, record_count, expected_page_size, expected_record_count, expected_call_count',
    [
        (
            case['page_size'],
            case['record_count'],
            case['expected_page_size'],
            case['expected_record_count'],
            case['expected_call_count'],
        )
        for case in _fetch_unlimited_page_size_cases.values()
    ],
    ids=list(_fetch_unlimited_page_size_cases.keys()),
)
def test_fetch_unlimited_page_size(
    page_size: int | None,
    record_count: int,
    expected_page_size: int,
    expected_record_count: int,
    expected_call_count: int,
) -> None:
    """Test that _fetch_unlimited uses the configured or default fetch_page_size.

    Args:
        page_size: fetch_page_size to set in client settings; None to use the default.
        record_count: Total number of records the mock API will return.
        expected_page_size: Expected pageSize in the first API request.
        expected_record_count: Expected total records returned by _fetch_unlimited.
        expected_call_count: Expected number of API calls made during the fetch.
    """
    records = [{'id': i} for i in range(record_count)]
    builder = ClientBuilder(RadarrClient)
    if page_size is not None:
        builder = builder.with_settings(fetch_page_size=page_size)
    client = builder.build()

    with patch.object(client.session, 'get', side_effect=_paged_responses(records)) as mock_get:
        result = client._fetch_unlimited('/api/v3/wanted/missing')  # pylint: disable=protected-access

    assert mock_get.call_args_list[0].kwargs['params']['pageSize'] == expected_page_size
    assert len(result) == expected_record_count
    assert len(mock_get.call_args_list) == expected_call_count

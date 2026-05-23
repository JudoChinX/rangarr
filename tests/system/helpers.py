"""Shared HTTP request router factories for system test fixtures."""

from typing import Any
from unittest.mock import MagicMock


def _make_lidarr_router(
    tag_data: list,
    missing_data: dict,
    cutoff_data: dict,
) -> Any:
    """Return a request router that serves Lidarr fixture data by URL."""

    def route(method: str, url: str, **_kwargs: Any) -> Any:
        """Route a request to the appropriate fixture response."""
        response = MagicMock()
        response.raise_for_status.return_value = None

        if '/api/v1/tag' in url:
            response.json.return_value = tag_data
        elif '/api/v1/wanted/missing' in url:
            response.json.return_value = missing_data
        elif '/api/v1/wanted/cutoff' in url:
            response.json.return_value = cutoff_data
        elif '/api/v1/command' in url and method.upper() == 'POST':
            response.json.return_value = {'id': 1}
        else:
            raise ValueError(f'Unexpected URL: {url}')

        return response

    return route


def _make_radarr_router(
    tag_data: list,
    quality_data: list,
    missing_data: dict,
    cutoff_data: dict,
) -> Any:
    """Return a request router that serves Radarr fixture data by URL."""

    def route(method: str, url: str, **_kwargs: Any) -> Any:
        """Route a request to the appropriate fixture response."""
        response = MagicMock()
        response.raise_for_status.return_value = None

        if '/api/v3/tag' in url:
            response.json.return_value = tag_data
        elif '/api/v3/qualityprofile' in url:
            response.json.return_value = quality_data
        elif '/api/v3/wanted/missing' in url:
            response.json.return_value = missing_data
        elif '/api/v3/wanted/cutoff' in url:
            response.json.return_value = cutoff_data
        elif '/api/v3/movie' in url and method.upper() == 'GET':
            response.json.return_value = []
        elif '/api/v3/command' in url and method.upper() == 'POST':
            response.json.return_value = {'id': 1}
        else:
            raise ValueError(f'Unexpected URL: {url}')

        return response

    return route


def _make_readarr_router(
    tag_data: list,
    missing_data: dict,
    cutoff_data: dict,
) -> Any:
    """Return a request router that serves Readarr fixture data by URL."""

    def route(method: str, url: str, **_kwargs: Any) -> Any:
        """Route a request to the appropriate fixture response."""
        response = MagicMock()
        response.raise_for_status.return_value = None

        if '/api/v1/tag' in url:
            response.json.return_value = tag_data
        elif '/api/v1/wanted/missing' in url:
            response.json.return_value = missing_data
        elif '/api/v1/wanted/cutoff' in url:
            response.json.return_value = cutoff_data
        elif '/api/v1/command' in url and method.upper() == 'POST':
            response.json.return_value = {'id': 1}
        else:
            raise ValueError(f'Unexpected URL: {url}')

        return response

    return route


def _make_sonarr_router(
    tag_data: list,
    missing_data: dict,
    cutoff_data: dict,
) -> Any:
    """Return a request router that serves Sonarr fixture data by URL."""

    def route(method: str, url: str, **_kwargs: Any) -> Any:
        """Route a request to the appropriate fixture response."""
        response = MagicMock()
        response.raise_for_status.return_value = None

        if '/api/v3/tag' in url:
            response.json.return_value = tag_data
        elif '/api/v3/wanted/missing' in url:
            response.json.return_value = missing_data
        elif '/api/v3/wanted/cutoff' in url:
            response.json.return_value = cutoff_data
        elif '/api/v3/command' in url and method.upper() == 'POST':
            response.json.return_value = {'id': 1}
        else:
            raise ValueError(f'Unexpected URL: {url}')

        return response

    return route


def _make_whisparr_router(
    tag_data: list,
    missing_data: dict,
    cutoff_data: dict,
) -> Any:
    """Return a request router that serves Whisparr fixture data by URL."""

    def route(method: str, url: str, **_kwargs: Any) -> Any:
        """Route a request to the appropriate fixture response."""
        response = MagicMock()
        response.raise_for_status.return_value = None

        if '/api/v3/tag' in url:
            response.json.return_value = tag_data
        elif '/api/v3/wanted/missing' in url:
            response.json.return_value = missing_data
        elif '/api/v3/wanted/cutoff' in url:
            response.json.return_value = cutoff_data
        elif '/api/v3/command' in url and method.upper() == 'POST':
            response.json.return_value = {'id': 1}
        else:
            raise ValueError(f'Unexpected URL: {url}')

        return response

    return route

"""Global test fixtures enforcing isolation and determinism."""

import datetime
import time

import pytest
import requests

FIXED_NOW = datetime.datetime(2026, 4, 23, 12, 0, 0, tzinfo=datetime.UTC)


class UnmockedNetworkError(Exception):
    """Raised when a test attempts an unmocked network call."""


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raise UnmockedNetworkError for any unmocked requests.Session.request call."""

    def mocked_request(*args: object, **kwargs: object) -> None:
        raise UnmockedNetworkError(
            f'Unmocked network call attempted: {args} {kwargs}. Use a mock or builder to define expected behavior.'
        )

    monkeypatch.setattr(requests.Session, 'request', mocked_request)


@pytest.fixture(autouse=True)
def pin_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin datetime.datetime.now() to FIXED_NOW and make time.sleep a no-op."""

    class MockDatetime(datetime.datetime):
        """datetime.datetime subclass that always returns FIXED_NOW as the current time."""

        @classmethod
        def now(cls, tz: datetime.tzinfo | None = None) -> 'MockDatetime':
            if tz is None:
                return FIXED_NOW  # type: ignore[return-value]
            return FIXED_NOW.astimezone(tz)  # type: ignore[return-value]

    monkeypatch.setattr(datetime, 'datetime', MockDatetime)
    monkeypatch.setattr(time, 'sleep', lambda secs: None)

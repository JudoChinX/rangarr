"""System-tier conftest that overrides block_network and pin_time to no-ops."""

import pytest


@pytest.fixture(autouse=True)
def block_network() -> None:
    """No-op: system tests manage their own network isolation."""


@pytest.fixture(autouse=True)
def pin_time() -> None:
    """No-op: fixture-based tests use retry_interval_days=0; Docker tests need real time."""

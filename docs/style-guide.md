# Rangarr Style Guide

This guide codifies all code and test conventions for Rangarr. Primary audience is AI agents
writing or reviewing code; secondary audience is human contributors.

For contribution workflow (branching, PRs, commit messages), see
[CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Table of Contents

- [General Conventions](#general-conventions)
- [Naming](#naming)
- [Module Structure](#module-structure)
- [Docstrings](#docstrings)
- [Type Hints](#type-hints)
- [Error Handling](#error-handling)
- [Testing](#testing)
- [Tooling Reference](#tooling-reference)

---

## General Conventions

### Single Quotes

All strings use single quotes. Ruff enforces this via `quote-style = "single"`.

```python
# Do
message = f'Client {name} registered.'
label = 'Disabled'

# Don't
message = f'Client {name} registered.'
label = 'Disabled'
```

### f-strings

Prefer f-strings over `.format()` or `%`-style interpolation.

```python
# Do
logger.info(f'Loaded configuration from: {config_path}')

# Don't
logger.info('Loaded configuration from: {}'.format(config_path))
logger.info('Loaded configuration from: %s' % config_path)
```

### Early Returns

No more than 2 early returns per function.

```python
# Do — two returns maximum (from main.py)
def _calculate_batch(global_batch: int, weight_share: float) -> int:
    """Calculate batch size from global setting and instance weight share."""
    if global_batch in (0, -1):
        return global_batch
    return max(1, int(round(global_batch * weight_share)))


# Don't — three or more returns
def _process(value: int) -> int:
    """Process a value."""
    if value < 0:
        return -1
    if value == 0:
        return 0
    if value > 100:
        return 100
    return value
```

### Variable Names

Variable names must be at least 3 characters.

```python
# Do
ids = client.get_media_to_search(client_missing, client_upgrade)
eta = datetime.timedelta(seconds=item_count * stagger_seconds)

# Don't
id = record['id']
x = datetime.timedelta(seconds=n * s)
```

### Constants — No Magic Numbers or Strings

Bare numeric and string literals used as meaningful values must be assigned a named constant.
Place class-level constants in alphabetical order.

```python
# Do (from arr.py)
class RadarrClient(ArrClient):
    ENDPOINT_MOVIE = '/api/v3/movie'
    ENDPOINT_MOVIE_FILE = '/api/v3/moviefile'
    MOVIE_FILE_BATCH_SIZE = 100

    def _fetch_movie_file_scores(self, file_ids: list[int]) -> dict[int, int]:
        for batch_start in range(0, len(file_ids), self.MOVIE_FILE_BATCH_SIZE):
            batch = file_ids[batch_start : batch_start + self.MOVIE_FILE_BATCH_SIZE]
            ...


# Don't — bare literal obscures intent and creates a maintenance hazard
def _fetch_movie_file_scores(self, file_ids: list[int]) -> dict[int, int]:
    for idx in range(0, len(file_ids), 100):
        batch = file_ids[idx : idx + 100]
        ...
```

### Comments

Write comments only when the WHY is non-obvious — a hidden constraint, a workaround, a subtle
invariant. Never describe what the code does.

```python
# Do — explains a non-obvious environment requirement
if 'TZ' not in os.environ:
    os.environ['TZ'] = 'UTC'
    if hasattr(time, 'tzset'):
        time.tzset()

# Don't — describes what the code does
# Check if TZ is not set, then set it to UTC
if 'TZ' not in os.environ:
    os.environ['TZ'] = 'UTC'
```

### Function Ordering

Functions are sorted alphabetically within a module. Private functions (`_name`) come before
public ones.

```python
# Do (excerpt from main.py — all private functions precede all public ones)
def _allocate_slots(...): ...       # private, 'a'
def _day_str(...): ...              # private, 'd'
def _format_batch_info(...): ...    # private, 'f'
# ... additional private functions in alphabetical order ...
def build_arr_clients(...): ...     # public, 'b'
def run(...): ...                   # public, 'r'

# Don't — unsorted or public before private
def run(...): ...
def _calculate_batch(...): ...
def build_arr_clients(...): ...
```

---

## Naming

| Entity | Convention | Example |
|---|---|---|
| Private function | `_snake_case` | `_calculate_batch`, `_format_batch_info` |
| Public function | `snake_case` | `build_arr_clients`, `get_media_to_search` |
| Public module constant | `UPPER_CASE` | `ENDPOINT_WANTED_MISSING`, `ENDPOINT_COMMAND` |
| Private module constant | `_UPPER_CASE` | `_CLIENT_MAP`, `_SEARCH_ORDER_LABELS` |
| Class | `PascalCase` | `ArrClient`, `RadarrClient`, `ClientBuilder` |
| Type alias | `type Name = ...` | `type MediaItem = tuple[int, str, str]` |
| Test case dict | `_snake_case_cases` | `_calculate_batch_cases`, `_run_cases` |
| Builder class | `<Subject>Builder` | `ClientBuilder`, `RadarrRecordBuilder` |

---

## Module Structure

Every file follows this top-to-bottom ordering:

1. Module docstring
2. Standard library imports (one per line, sorted)
3. Third-party imports (one per line, sorted)
4. Local imports (one per line, sorted)
5. Module-level type aliases and constants
6. Private functions (alphabetical)
7. Public functions and classes (interleaved alphabetically by name)
8. `if __name__ == '__main__':` guard (when present)

The isort configuration enforces `force-single-line = true` — each import is on its own line.

```python
# Do — canonical module structure (illustrative excerpt drawing from main.py and arr.py)
"""Rangarr entry point.

Orchestrates automated media searches across multiple *arr instances by fetching
missing and upgrade-eligible items, dispatching search commands with configurable
delays, and repeating at scheduled intervals.
"""

import datetime
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from rangarr.clients.arr import ArrClient
from rangarr.clients.arr import RadarrClient
from rangarr.config_parser import load_config
# ... additional local imports follow the same pattern

_CLIENT_MAP: dict[str, type[ArrClient]] = {
    'radarr': RadarrClient,
}

type MediaItem = tuple[int, str, str]


def _calculate_batch(global_batch: int, weight_share: float) -> int:
    """Calculate batch size from global setting and instance weight share."""
    ...


def build_arr_clients(instances_config: dict, settings: dict) -> list[ArrClient]:
    """Instantiate all *arr clients declared in the config."""
    ...
```

---

## Docstrings

### Module Docstrings

Every module starts with a docstring. A one-sentence summary is sufficient for simple modules;
add a paragraph for complex ones.

```python
# Do — single sentence (from arr.py)
"""*arr API clients: base class with pagination, and app-specific subclasses."""

# Do — multi-sentence (from main.py)
"""Rangarr entry point.

Orchestrates automated media searches across multiple *arr instances by fetching
missing and upgrade-eligible items, dispatching search commands with configurable
delays, and repeating at scheduled intervals.
"""
```

### Private Functions

Private functions get a **single-line docstring only**. No `Args:` or `Returns:` block.

```python
# Do (from main.py)
def _calculate_batch(global_batch: int, weight_share: float) -> int:
    """Calculate batch size from global setting and instance weight share."""
    ...


# Don't — Args block on a private function
def _calculate_batch(global_batch: int, weight_share: float) -> int:
    """Calculate batch size.

    Args:
        global_batch: The global batch size.
        weight_share: The weight share.

    Returns:
        The calculated batch size.
    """
    ...
```

### Public Functions and Methods

Public functions use Google style: a summary line, then `Args:`, `Returns:`, and `Raises:` as
applicable. Omit sections that don't apply.

```python
# Do (from main.py)
def build_arr_clients(
    instances_config: dict,
    settings: dict,
    client_registry: dict[str, type[ArrClient]] | None = None,
) -> list[ArrClient]:
    """Instantiate all *arr clients declared in the config.

    Args:
        instances_config: The ``instances`` section of the config dict.
        settings: The ``settings`` section of the config dict.
        client_registry: Optional client type registry (defaults to _CLIENT_MAP).

    Returns:
        Flat list of instantiated *arr client objects.
    """
    ...
```

### @override Methods

`@override` methods get **no docstring**. The base class docstring is sufficient.

```python
# Do (from arr.py subclasses)
@override
def _get_record_title(self, record: dict) -> str:
    return record['title']


# Don't — docstring duplicates the base
@override
def _get_record_title(self, record: dict) -> str:
    """Get the record title."""
    return record['title']
```

### Docstring Rules

- All docstrings end with punctuation.
- Never restate the function name (don't write `"Returns the name."` for `get_name`).
- Use double-backtick quoting for inline code references in docstrings: `` ``instances`` ``.

---

## Type Hints

### All Signatures Must Be Typed

Mypy enforces `disallow_untyped_defs`. Every parameter and return type must be annotated.

```python
# Do
def _day_str(days: int) -> str:
    """Format a day count as a display string."""
    ...


# Don't
def _day_str(days): ...
```

### Type Aliases

Use the `type` keyword (Python 3.12+ PEP 695 syntax) for module-level type aliases.

```python
# Do (from arr.py)
type MediaItem = tuple[int, str, str]

# Don't
MediaItem = tuple[int, str, str]
```

### Self for Fluent Builders

Use `Self` from `typing` for all builder return types — both in class hierarchies and in
standalone concrete builders. Forward-reference strings (`-> 'ClassName'`) are not acceptable;
they break under subclassing and are harder to refactor.

```python
# Do (from builders.py) — Self works for both base classes and standalone builders
from typing import Self


def with_id(self, record_id: int) -> Self:
    """Set the record ID."""
    self._data['id'] = record_id
    return self


# Don't — string annotation loses the concrete subclass type and is fragile on rename
def with_id(self, record_id: int) -> 'RadarrMovieFileRecordBuilder': ...
```

### @override

The `@override` decorator from `typing` is required when overriding a base class method.

```python
# Do (from arr.py)
from typing import override


@override
def _get_record_title(self, record: dict) -> str:
    return record['title']


# Don't — missing decorator
def _get_record_title(self, record: dict) -> str:
    return record['title']
```

### Any

Use `Any` only at true system boundaries: test helpers and external API response shapes where
the type genuinely cannot be known.

```python
# Do — external API response (from builders.py)
def mock_http_response(data: Any) -> Any:
    """Create mock HTTP response object."""
    ...


# Don't — internal code with known types
def _process_record(record: Any, reason: Any) -> Any: ...
```

---

## Error Handling

### Validate at Boundaries Only

Validate user input and external data at entry points (config loading, API responses). Trust
internal code — do not add defensive guards for states that cannot occur.

```python
# Do — validate at the config loading boundary (from main.py)
try:
    config = load_config(config_path)
except ValueError as error:
    error_message = f'Configuration error in {config_path}: {error}'


# Don't — defensive guard inside pure internal logic
def _calculate_batch(global_batch: int, weight_share: float) -> int:
    """Calculate batch size from global setting and instance weight share."""
    if not isinstance(global_batch, int):  # impossible in internal use
        raise TypeError('global_batch must be int')
    ...
```

### Catch Specific Exceptions

Never use bare `except:`. Catch the specific exception type you expect.

```python
# Do (from main.py)
try:
    config = load_config(config_path)
except ValueError as error:
    error_message = f'Configuration error in {config_path}: {error}'
except FileNotFoundError:
    continue

# Don't
try:
    config = load_config(config_path)
except:
    pass
```

### Logging

Log errors and warnings with f-string context. Never log API keys, tokens, or other secrets.

```python
# Do
logger.error(f'Configuration error in {config_path}: {error}')
logger.warning(f"Client '{name}' is using a non-HTTPS URL ({self.url}).")
```

Double quotes are used in the second example because the string contains embedded single quotes; Ruff permits this to avoid escaping.

```python
# Don't — leaks authentication headers
logger.debug(f'Request headers: {self.session.headers}')
```

### Startup Failures

Use `sys.exit(1)` for unrecoverable startup failures — not exceptions.

```python
# Do (from main.py)
if not config:
    sys.exit(1)

if not active_clients:
    logger.warning("No *arr instances are configured. Add at least one entry under 'instances' to begin.")
    sys.exit(1)
```

---

## Testing

### Core Principles

#### 1. Absolute Isolation
Tests must be isolated from the environment. The root `tests/conftest.py` enforces this via `autouse` fixtures:
- **Network:** Real network calls are blocked. Unmocked calls raise `UnmockedNetworkError`.
- **Time:** System time is pinned to a constant (`FIXED_NOW`), and `time.sleep` is a no-op.

#### 2. Determinism
Tests must produce the same result regardless of the machine or time. Normalize all volatile outputs (UUIDs, paths, timestamps) before assertion.

#### 3. Tiered Structure
Separate fast logic tests from broader integration flows:
- `tests/unit/`: Unit tests (e.g., `tests/unit/test_config_parser.py`, `tests/unit/clients/test_radarr.py`). Fast, isolated tests for individual modules.
- `tests/integration/`: Cross-module tests verifying interactions between components.
- `tests/system/`: End-to-end tests using realistic API fixtures.

### Standards & Strictness

- **Warnings as Errors:** All Python warnings are treated as hard failures (`filterwarnings = error` in `pyproject.toml`).
- **Coverage:** A 95% coverage floor is enforced. Every branch must be tested.
- **No Side Effects:** Tests must not modify the local filesystem (outside of `tmp_path`) or environment variables.

### Patterns

#### Case Dict + Parametrize Pattern
Test data lives in a module-level dict named `_<function>_cases`. Dict keys become the
parametrize `ids`. Test functions receive unpacked values, not the dict itself.

```python
# Do (from test_main.py)
_calculate_batch_cases = {
    'full_share': {
        'global_batch': 20,
        'weight_share': 1.0,
        'expected': 20,
    },
    'zero_weight_share': {
        'global_batch': 20,
        'weight_share': 0.0,
        'expected': 1,
    },
}


@pytest.mark.parametrize(
    'global_batch, weight_share, expected',
    [(case['global_batch'], case['weight_share'], case['expected']) for case in _calculate_batch_cases.values()],
    ids=list(_calculate_batch_cases.keys()),
)
def test_calculate_batch(global_batch: int, weight_share: float, expected: int) -> None:
    """Test _calculate_batch distributes appropriately and bounds to minimum 1 when global > 0."""
    assert _calculate_batch(global_batch, weight_share) == expected
```

#### Builder Pattern
Use builders from `tests/builders.py` to construct test objects. Extend `tests/builders.py`
when you need a new builder — do not inline raw dicts in tests.

```python
# Do (from test_arr_client.py)
from tests.builders import ClientBuilder
from tests.builders import RadarrRecordBuilder

client = ClientBuilder().radarr().with_settings(search_order='alphabetical_ascending').build()
record = RadarrRecordBuilder().with_id(42).with_title('Test Movie').available().build()
```

### Conventions

#### Naming
- **Files:** `test_<module>.py` inside `tests/unit/` for unit tests (e.g., `tests/unit/test_config_parser.py`, `tests/unit/clients/test_radarr.py`), or inside `tests/integration/` or `tests/system/` for broader tests.
- **Standalone test:** `test_<function>_<scenario>`.
- **Parametrized test:** `test_<function>` (the case dict key serves as the scenario id).

#### Fixtures
Declare fixtures with `@pytest.fixture` at the top of the test file. Use `tests/conftest.py` for shared or global safety fixtures.

#### Log Assertions
Assert log output via `caplog` with an explicit log level.

```python
# Do (from test_main.py)
with caplog.at_level(logging.INFO):
    _run_search_cycle([mock_client], settings)
assert 'Missing and upgrade items disabled, skipping' in caplog.text
```

#### Generic Data
No identifying information in test data. Use generic placeholders: `name = 'test'`, `url = 'http://test'`, `api_key = 'testkey'`.

---

## Tooling Reference

All tools run automatically via `utils/pre-push.sh`. Every task must pass the pre-push hook
before being considered complete.

| Tool | Purpose | Command |
|---|---|---|
| Ruff | Lint + format | `ruff check . && ruff format .` |
| Pylint | Code quality | `pylint rangarr/ tests/` |
| Mypy | Type checking | `mypy rangarr/ tests/` |
| Bandit | Security (high severity only) | `bandit -r rangarr/ -lll` |
| Pytest | Tests + 95% coverage | `pytest` |

To auto-fix linting issues:

```bash
ruff check --fix .
```

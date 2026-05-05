# Technical Audit

Architecture, security model, and design philosophy for Rangarr. Intended for security reviewers, contributors, and anyone who wants to verify the software's claims.

---

## Table of Contents

- [Why This Project Exists](#why-this-project-exists)
- [What Rangarr Does NOT Do](#what-rangarr-does-not-do)
- [Architecture Overview](#architecture-overview)
- [Module Breakdown](#module-breakdown)
- [API Interactions](#api-interactions)
- [Security-Critical Code Paths](#security-critical-code-paths)
- [Design Principles](#design-principles)
- [Technical Decisions](#technical-decisions)
- [Testing Strategy](#testing-strategy)
- [Dependencies](#dependencies)
- [File Sizes](#file-sizes)
- [Verification](#verification)

---

## Why This Project Exists

Following a security incident affecting similar tools in the ecosystem, the *arr community needed a transparent, auditable automation tool. Rangarr was built from scratch with security and simplicity as first principles.

---

## What Rangarr Does NOT Do

To be absolutely clear, Rangarr does not and will never:

- Access media files on disk
- Connect to external services (indexers, trackers, notification services, etc.)
- Collect usage statistics or telemetry
- Phone home or check for updates
- Access download client APIs or credentials
- Modify *arr configuration settings
- Access user authentication data beyond API keys
- Add or remove media from your library
- Modify library settings or quality profiles

---

## Architecture Overview

Rangarr is a ~1,461-line Python service with three core modules:

```
rangarr/
├── main.py           # Orchestration loop
├── config_parser.py  # Configuration validation
└── clients/
    └── arr.py        # *arr API client implementations
```

**Data Flow:**
```
config.yaml → config_parser.py → main.py → ArrClient instances → *arr APIs
```

---

## Module Breakdown

### main.py — Orchestration Loop

**Purpose:** Coordinates search cycles across configured *arr instances.

**Key Functions:**
- `run()`: Loads configuration and starts the infinite orchestration loop.
- `_run_search_cycle()`: Executes one search cycle across all enabled instances using a 3-stage pipeline (Collect, Allocate, Execute).
- `build_arr_clients()`: Instantiates all *arr clients from configuration.
- `_allocate_slots()`: Centralized allocator that distributes global search slots across instances using weighted round-robin.
- `_build_final_queue()`: Constructs the ordered execution list, optionally interleaving items between instances.

**No Network Activity:** Only calls client methods; does not make HTTP requests directly.

### config_parser.py — Configuration Validation

**Purpose:** Loads and validates YAML configuration.

**Key Functions:**
- `load_config()`: Reads config.yaml from disk and delegates to `parse_config()`.
- `parse_config()`: Validates and normalises the loaded configuration dictionary.
- `_parse_instance()`: Validates each instance entry, renames `host` to `url` for internal use, and enforces required fields (type, host, api_key).

**No Network Activity:** Pure configuration parsing; never makes HTTP requests.

**Security Note:** Extracts API keys from config and passes to client instances. Keys are never logged.

### clients/arr.py — API Client

**Purpose:** Implements *arr API interactions.

**Classes:**
- `ArrClient`: Abstract base class with shared fetch, client-side sorting, and filtering logic.
- `RadarrClient`: Radarr-specific implementation.
- `SonarrClient`: Sonarr-specific implementation.
- `LidarrClient`: Lidarr-specific implementation (uses `/api/v1/` endpoints).

**Key Methods:**
- `get_media_to_search()`: Fetches, sorts, and filters missing/upgrade items from wanted endpoints. Returns the full backlog for global allocation.
- `_get_target_media()`: Fetches all records via `_fetch_unlimited()`, sorts them client-side, and applies retry-window and availability filtering.
- `_interleave_items()`: Proportionally interleaves missing and upgrade items within a single instance's results.
- `_get_custom_format_score_unmet_records()`: Orchestrates the supplemental upgrade pass — fetches quality profiles, then delegates to `_get_custom_format_upgrade_records()`.
- `_get_custom_format_upgrade_records()`: Per-client override that finds items where `customFormatScore` is below the profile's `cutoffFormatScore`. Monitored status is enforced for all records (movies, series, and episodes) before scoring. No-op in base class and `LidarrClient`.
- `_fetch_movie_file_scores()`: Radarr — fetches custom format scores for a list of movie file IDs, batched at 100 IDs per request.
- `_fetch_episode_file_scores()`: Sonarr — fetches episode file IDs for a series where the score is below the cutoff.
- `trigger_search()`: Dispatches search commands via POST to `/api/v3/command` (Radarr/Sonarr) or `/api/v1/command` (Lidarr), staggered by `stagger_interval_seconds`.
- `_fetch_unlimited()`: Low-level paged HTTP fetcher that collects all records across pages (uses requests.Session).
- `_fetch_list()`: Low-level single-page HTTP fetcher for non-paginated list endpoints.
- `_sort_records_client_side()`: Sorts fetched records in-place according to `search_order`.
- `_is_within_retry_window()`: Filters out items searched within `retry_interval_days`.

**Security Note:** This is the ONLY module that makes network requests. All API calls use the session configured in `__init__` with `X-Api-Key` header.

---

## API Interactions

| Endpoint | Method | Purpose | Frequency | Read/Write |
|----------|--------|---------|-----------|------------|
| `/api/v3/wanted/missing` (Radarr/Sonarr), `/api/v1/wanted/missing` (Lidarr) | GET | Fetch missing items (`monitored=true`) | Per cycle per instance | Read-only |
| `/api/v3/wanted/cutoff` (Radarr/Sonarr), `/api/v1/wanted/cutoff` (Lidarr) | GET | Fetch upgrade candidates (`monitored=true`) | Per cycle per instance | Read-only |
| `/api/v3/qualityprofile` (Radarr/Sonarr) | GET | Fetch quality profiles to identify cutoff format score thresholds | Per cycle per instance | Read-only |
| `/api/v3/movie` (Radarr) | GET | Fetch movies to find upgrade candidates (skips unmonitored) | Per cycle when profiles have non-zero cutoff format scores | Read-only |
| `/api/v3/moviefile` (Radarr) | GET | Fetch movie file scores to compare against profile cutoff | Per cycle when movie candidates exist, batched at 100 IDs | Read-only |
| `/api/v3/series` (Sonarr) | GET | Fetch series — find upgrade candidates (skips unmonitored); determine air status | Per cycle per Sonarr instance when either condition applies | Read-only |
| `/api/v3/episodefile` (Sonarr) | GET | Fetch episode file scores to compare against profile cutoff | Per series with a tracked profile, per cycle | Read-only |
| `/api/v3/episode` (Sonarr) | GET | Fetch episodes with files (skips unmonitored) | Per series with low-scoring files, per cycle | Read-only |
| `/api/v3/command` (Radarr/Sonarr), `/api/v1/command` (Lidarr) | POST | Trigger search command | Per item | **Write** |

**Search Commands Sent:**
- Radarr: `{"name": "MoviesSearch", "movieIds": [...]}`
- Sonarr: `{"name": "EpisodeSearch", "episodeIds": [...]}` (or `{"name": "SeasonSearch", "seriesId": ..., "seasonNumber": ...}` when `season_packs` is `true`, an integer count threshold is met, or a float ratio threshold is met; airing seasons and seasons that don't meet the configured threshold always use `EpisodeSearch`)
- Lidarr: `{"name": "AlbumSearch", "albumIds": [...]}`

**Data Accessed:**
- Media metadata only: titles, IDs, air dates, search timestamps, quality profile IDs, custom format scores
- No media files, no user data, no download client information

---

## Security-Critical Code Paths

### API Key Usage

**Location:** `clients/arr.py` — `ArrClient.__init__`

API keys are set once during client initialization:
```python
self.session.headers.update({'X-Api-Key': api_key, 'Content-Type': 'application/json'})
```

This is the ONLY place API keys are used. They are:
- Never logged
- Never transmitted except in `X-Api-Key` header
- Never stored to disk
- Only held in memory during service runtime

API keys are stored in `config.yaml` and read once at startup. The configuration file should be protected with appropriate filesystem permissions (recommend `chmod 600 config.yaml`).

Rangarr does not encrypt credentials or API keys in transit. It is designed for use on a trusted local network and should **not** be exposed to the public internet.

### Write Operations

**Location:** `clients/arr.py` — `ArrClient._trigger_single()` (base) and `SonarrClient.trigger_search()` (season pack override)

Search commands are POST requests that trigger media searches on *arr instances. These are the ONLY write operations Rangarr performs — the same commands you would trigger manually through the *arr web interfaces.

When `dry_run: true` is set in config, search commands are logged but not executed.

### Retry Window Logic

**Location:** `clients/arr.py` — `_is_within_retry_window()`

Uses `lastSearchTime` field from *arr API responses to skip recently-searched items. This timestamp comes from the *arr instance; Rangarr does not store or log search history.

### Network Activity

Rangarr operates entirely within your local network (or wherever you host your *arr instances):
- Only communicates with URLs explicitly configured in `config.yaml`
- No telemetry, analytics, or external API calls
- No automatic updates or version checks
- All HTTP requests use the session configured at startup; no request data is logged externally

---

## Design Principles

### 1. Security Through Simplicity

**Decision:** ~1,461 lines of core Python code, zero external dependencies beyond requests and PyYAML.

**Why:** Small codebases are auditable. Every line of code is a potential attack surface. By keeping the codebase minimal, security reviewers can read and understand the entire project in under an hour.

**Trade-off:** Some convenience features are intentionally omitted to maintain this simplicity.

### 2. Explicit Over Implicit

**Decision:** No magic, no auto-discovery, no background services you didn't configure.

**Why:** Security incidents often stem from software doing things users don't expect. Every API call Rangarr makes is explicitly listed in this document. Every configuration option must be set by the user.

**Examples:**
- No automatic *arr instance discovery on the network.
- No phone-home, analytics, or update checks.
- No default API endpoints beyond what's documented.

### 3. Read-Heavy, Write-Light

**Decision:** Only one write operation exists: triggering searches via `/api/v3/command`.

**Why:** Write operations are where damage happens. Rangarr cannot modify your library, change settings, or access download clients. The single write operation matches what you'd do manually in the *arr UI.

**Architecture:** The `ArrClient` base class makes this constraint visible — the only write method is `trigger_search()`.

### 4. Test Coverage as Documentation

**Decision:** 300 tests covering all code paths, including error conditions.

**Why:** Tests serve three purposes:
1. Prevent regressions.
2. Document expected behavior.
3. Prove security-relevant code works as claimed.

**Example:** The trailing slash test exists not because it's complex, but because URL handling is security-relevant. The test proves the code does what documentation claims.

### 5. No Secrets in Code

**Decision:** All secrets live in `config.yaml` (gitignored). API keys never appear in logs.

**Why:** Credentials in code or logs are the most common source of credential leaks.

**Implementation:**
- `config.yaml` is gitignored by default.
- API keys are only used in HTTP headers, never logged.
- Test data uses placeholder values like `testkey` and `localhost`.

---

## Technical Decisions

### Distroless Container Image

**Choice:** `gcr.io/distroless/python3-debian13` as the runtime base image, built via a multi-stage Dockerfile.

**Why:** The runtime image contains only the Python interpreter, CA certificates, and the application itself. There is no shell, no package manager, no build tooling. This limits what an attacker can do with a compromised container — they cannot execute shell commands, install tools, or escalate privileges through the package manager.

**How it works:** A `python:3.13-slim` builder stage installs dependencies into an isolated prefix (`/install`) using `pip install --prefix`. The distroless runtime stage copies only that prefix and the application source. pip, build headers, and the OS package manager never exist in the final image.

**Trade-off:** Debugging a running container is harder — there is no shell to exec into. Use `LOG_LEVEL=DEBUG` and structured logs for diagnostics.

### Python Over Other Languages

**Choice:** Python 3.13+ with type hints.

**Why:**
- Widely understood in the homelab community.
- Type hints provide static analysis benefits.
- No compilation step means source code is what runs.

**Trade-off:** Slightly slower than compiled languages, but performance isn't relevant for this use case (running every hour, processing <100 items).

### Minimal Dependencies

**Choice:** Only `requests` and `PyYAML`.

**Why:** Every dependency is a trust decision. Both libraries are industry standard and well-maintained with public security disclosure policies.

**Trade-off:** Some convenience (like async HTTP) requires more code, but the security benefit outweighs the development cost.

### Configuration in YAML

**Choice:** YAML over JSON, TOML, or environment variables.

**Why:**
- Readable by non-developers.
- Supports comments for documentation.
- No executable code (unlike some config formats).

**Trade-off:** YAML parsing has edge cases, but PyYAML (with `safe_load`) mitigates this.

### Stateless Operation

**Choice:** No database, no persistent state beyond `config.yaml`. All sorting and filtering is done in-memory per cycle with no carry-over state.

**Why:**
- Nothing to corrupt.
- Easy to backup (copy one file).
- Transparent behavior (state is visible in *arr instances, not hidden in Rangarr).

**Trade-off:** Every cycle fetches all records and re-sorts client-side. This is acceptable — the wanted endpoints are read-only and the full fetch ensures correct ordering regardless of service restarts.

### AI-Assisted Development

AI-assisted development tools were used to accelerate implementation, but not as a replacement for expertise:

**What AI helped with:** Boilerplate code generation, test case expansion, documentation consistency.

**What required human judgment:** Architecture decisions, security trade-offs, API design, test strategy.

Every line of AI-generated code was reviewed, tested, and validated against requirements.

---

## Testing Strategy

**Test Coverage:** See `rangarr/` and `tests/` directories.

Unit tests (co-located with source):
- `test_config_parser.py`: Configuration validation without network calls.
- `test_env_config.py`: Environment variable configuration loading.
- `test_validators.py`: Input validation logic.
- `test_main.py`: Orchestration loop with mocked clients.
- `clients/test_arr_base.py`: Shared ArrClient base class behaviour.
- `clients/test_arr_client_sort.py`: Client-side sorting for all search orders across all client types.
- `clients/test_radarr.py`, `clients/test_sonarr.py`, `clients/test_lidarr.py`: Client-specific logic with mocked HTTP responses.
- `clients/test_sonarr_sort.py`: Sorting and interleaving correctness for Sonarr season pack results.

Integration / system tests (`tests/`):
- `integration/test_search_cycle.py`: Full search cycle with mocked *arr API responses.
- `integration/test_sonarr_season_packs.py`: Season pack search logic end-to-end.
- `integration/test_tag_filtering.py`: Tag-based include/exclude filtering.
- `system/test_app_flow.py`: Full application flow smoke test.

**Testing Without Production Instances:**

1. **Dry Run Mode:** Set `dry_run: true` in config.yaml
2. **Debug Logging:** Set `LOG_LEVEL=DEBUG` environment variable
3. **Review Logs:** All API calls are logged with endpoints and parameters

---

## Dependencies

Minimal third-party libraries (see `requirements.txt`):
- `requests`: HTTP client for *arr API calls.
- `PyYAML`: Configuration file parsing.

Both are widely-used, well-maintained libraries with public security disclosure policies.

---

## File Sizes

- `main.py`: ~383 lines
- `config_parser.py`: ~366 lines
- `clients/arr.py`: ~712 lines
- **Total:** ~1,461 lines of Python (excluding tests/comments)

The small codebase size makes comprehensive security auditing feasible.

---

## Verification

Don't trust documentation — verify the claims:

1. **Run the tests:** `pytest` — See that security-relevant code is tested.
2. **Read the code:** Start with `rangarr/main.py` — a manageable entry point.
3. **Check the API calls:** Enable `LOG_LEVEL=DEBUG` — Every HTTP request is logged.
4. **Review dependencies:** `cat requirements.txt` — Two libraries, both standard.

If anything in this document contradicts the code, the code is correct and this document needs updating. File an issue.

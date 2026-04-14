# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-04-14

### Added

- `include_tags` and `exclude_tags` global settings to filter searches by *arr tags.
- `active_hours` global setting to restrict searches to a configured time window, sleeping until the window opens when a cycle falls outside it.

### Fixed

- Season packs: `missing_batch_size` and `upgrade_batch_size` are now enforced when `season_packs: true` is set on a Sonarr instance. Previously these limits were ignored and all eligible seasons were collected unconditionally.

## [0.4.0] - 2026-04-12

### Added

- Support for season packs in Sonarr (#15)
- Project roadmap at `ROADMAP.md` (#14)
- "Ranger the Pig" to `README.md`
- Enforce yaml style with `yamllint` (#19)

### Changed

- Warn if clients connect using HTTP rather than HTTPS (#18)
- Ensure `stagger_interval_seconds` is at least 1 (#16)

### Fixed

- Improve date comparison logic in `_is_date_past` (#20)
- Avoid `time.tzset()` when unavailable (#17)
- Harden CI workflow with pinned actions and least-privilege permissions (#12)

## [0.3.0] - 2026-03-31

### Added

- Support for providing configuration values through environment variables (e.g. `RANGARR_INSTANCE_0_NAME=radarr`)
- Set default weight for Lidarr to 1 (from 0.1).

## [0.2.2] - 2026-03-28

### Fixed

- Sonarr API calls no longer incorrectly pass `includeSeries` (a Radarr-only parameter)

### Changed

- Documentation updated to include `docker run` usage and a `docker compose` example

## [0.2.1] - 2026-03-27

### Added

- Support for environment variable expansion in config file (e.g. `${MY_VAR}`)

## [0.2.0] - 2026-03-26

### Breaking Changes

- **Batch size semantics changed:** `0` now means "disabled" instead of "unlimited"
  - `0` = disabled (skip this batch type entirely — no API calls made)
  - `-1` = unlimited (search all available items, weights ignored)
  - `N > 0` = limited (search up to N items, distributed by weight)
  - Migration: Change `missing_batch_size: 0` to `missing_batch_size: -1` for unlimited behavior
  - If you previously used `missing_batch_size: 0` for unlimited, update to `missing_batch_size: -1`

### Added

- Support for disabled batch types (`missing_batch_size: 0` or `upgrade_batch_size: 0`)
- Support for unlimited batch types (`missing_batch_size: -1` or `upgrade_batch_size: -1`)
- Per-batch-type disabled logging: separate log messages when only one batch type is disabled
- Startup log now displays "Disabled" or "Unlimited" for batch sizes (instead of `0` or `-1`)

### Changed

- Docker image now uses a distroless base (`gcr.io/distroless/python3-debian13`), removing the shell, package manager, and build tooling from the runtime image
- Python runtime version updated to 3.13 (distroless does not provide a Python 3.12 image)
- Container runs as `nonroot` (UID 65532) via the distroless built-in user
- Config validation now accepts `-1` for `missing_batch_size` and `upgrade_batch_size`
- Config validation rejects values below `-1` for batch size settings (e.g. `-2` is invalid)
- When set to unlimited, batch size weights are not applied (each instance gets all items)
- `retry_interval_days` still applies in unlimited mode

## [0.1.0] - 2026-03-24

Initial beta release of Rangarr. Configuration format and behaviour may change before 1.0.

### Added
- Initial beta release of Rangarr

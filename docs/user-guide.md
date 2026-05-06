# User Guide

Complete guide to installing, configuring, and operating Rangarr.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (Docker)](#quick-start-docker)
- [Configuration Sources](#configuration-sources)
- [Configuration Reference](#configuration-reference)
  - [Environment Variable Expansion](#environment-variable-expansion)
  - [Environment Variable-Only Configuration](#environment-variable-only-configuration)
- [Docker](#docker)
  - [Docker Compose](#docker-compose)
  - [Docker Run](#docker-run)
  - [Docker Networking](#docker-networking)
- [Indexer Safety & Limits](#indexer-safety--limits)
- [Operational Best Practices](#operational-best-practices)
- [Troubleshooting](#troubleshooting)
- [Development Setup](#development-setup)

---

## Prerequisites

- **Docker** with Compose plugin (Docker Desktop or Docker Engine + Compose)

---

## Quick Start (Docker)

The fastest way to get Rangarr running:

1. Download the example files:
   ```bash
   curl -O https://raw.githubusercontent.com/JudoChinX/rangarr/main/config.example.yaml
   curl -O https://raw.githubusercontent.com/JudoChinX/rangarr/main/compose.example.yaml
   mv config.example.yaml config.yaml
   mv compose.example.yaml compose.yaml
   chmod 644 config.yaml
   ```
   The `chmod 644` is required. The container runs as UID 65532 (`nonroot`), not your host user, so the file must be world-readable.

2. Edit `config.yaml` with your *arr instance details.

3. Start the service with dry run enabled to verify your configuration before triggering real searches:
   ```yaml
   global:
     dry_run: true
   ```
   ```bash
   docker compose up -d && docker compose logs -f
   ```
   Confirm the log output looks correct, then set `dry_run: false` and restart.

4. Start normally:
   ```bash
   docker compose up -d
   ```

5. View logs:
   ```bash
   docker compose logs -f
   ```

---

## Configuration Sources

Rangarr supports two primary configuration methods:
1. **YAML File (Default):** Configured via `config/config.yaml`.
2. **Environment Variables:** Configured via `RANGARR_GLOBAL_*` and `RANGARR_INSTANCE_*` variables.

To switch to environment-only configuration, set:
```bash
RANGARR_CONFIG_SOURCE=env
```

---

## Configuration Reference

Rangarr is configured via a single `config.yaml` file.

### Configuration Structure

```yaml
global:
  # Global settings

instances:
  Instance-Name:
    # Instance-specific settings
```

### Environment Variable Expansion

Any string value in `config.yaml` may contain `${VAR_NAME}` placeholders. Rangarr replaces them with the matching environment variable at startup. Expansion applies to all string fields — not just `api_key`. A single value may contain multiple placeholders.

Set secrets as environment variables and reference them in `config.yaml`:

```yaml
# config.yaml
instances:
  Radarr:
    type: radarr
    host: "http://radarr:7878"
    api_key: ${RADARR_API_KEY}
    enabled: true
```

Pass the value via `compose.yaml`:

```yaml
environment:
  RADARR_API_KEY: your_api_key_here
```

If a referenced variable is not set, Rangarr logs an error and exits:

```
Configuration error in <path>: Environment variable 'RADARR_API_KEY' referenced in config is not set.
```

Check startup logs to identify which variable is missing. Integer and boolean fields are not subject to expansion.

### Global Settings

Settings that apply to all instances.

#### `interval`

**Type:** Integer | **Default:** `3600`

Seconds to wait between orchestration cycles.

```yaml
global:
  interval: 1800  # Run every 30 minutes
```

#### `dry_run`

**Type:** Boolean | **Default:** `false`

When `true`, search commands are logged but not executed. Useful for testing configuration changes.

```yaml
global:
  dry_run: true  # Test mode - no actual searches triggered
```

#### `missing_batch_size`

**Type:** Integer | **Default:** `20`

Target number of missing items to search globally per cycle.

- Set to `0` to disable missing item searches entirely.
- Set to `-1` for unlimited (search all available missing items).
- Set to a positive integer to limit the total global batch size.

Search slots are distributed across instances using weighted round-robin; unused slots from instances with empty backlogs are automatically redistributed to ensure the full budget is used.

Rangarr will fetch multiple pages if necessary to reach the target after filtering.

```yaml
global:
  missing_batch_size: 50   # Limited to 50 items
  # missing_batch_size: -1  # Unlimited - search all
  # missing_batch_size: 0   # Disabled - skip missing items
```

#### `upgrade_batch_size`

**Type:** Integer | **Default:** `10`

Target number of upgrade items to search globally per cycle.

- Set to `0` to disable upgrade searches entirely.
- Set to `-1` for unlimited (search all available upgrades).
- Set to a positive integer to limit the total global batch size.

Search slots are distributed across instances using weighted round-robin; unused slots from instances with empty backlogs are automatically redistributed to ensure the full budget is used.

Upgrade candidates come from two sources each cycle:

1. **Cutoff Unmet** — items reported by *arr's Cutoff Unmet endpoint (quality level below the profile cutoff).
2. **Custom format score pass** (Radarr and Sonarr only) — items where `customFormatScore` is below the profile's `cutoffFormatScore`. *arr's Cutoff Unmet endpoint silently omits these even though they are eligible for a better release.

In both passes, only items marked as **monitored** in *arr are considered.

Both sources share the same `upgrade_batch_size` budget. Tag filters and `retry_interval_days` apply to both. Lidarr uses only the Cutoff Unmet source.

```yaml
global:
  upgrade_batch_size: 10   # Limited to 10 items
  # upgrade_batch_size: -1  # Unlimited - search all
  # upgrade_batch_size: 0   # Disabled - skip upgrades
```

#### `stagger_interval_seconds`

**Type:** Integer | **Default:** `30` | **Minimum:** `1`

Seconds to wait between individual search commands. Prevents overwhelming *arr instances with simultaneous requests. When greater than zero, Rangarr logs an ETA alongside the total batch count at the start of each cycle (e.g. `Total search batch: 120 item(s) (1 every 30 seconds, ETA: 1:00:00)`).

#### `interleave_instances`

**Type:** Boolean | **Default:** `false`

Controls the execution order of the search queue.

- `false` (default): Executes all allocated items for one instance before moving to the next.
- `true`: Alternates between instances in round-robin order for the duration of the cycle.

Interleaving is recommended when multiple instances share indexers. Global weighted slot allocation applies in both modes.

#### `retry_interval_days`

**Type:** Integer | **Default:** `30`

Skip items that were searched within this many days. Set to `0` to disable (search all items every cycle).

Uses `lastSearchTime` from the *arr API; Rangarr does not store search history.

```yaml
global:
  retry_interval_days: 14  # Only re-search items after 14 days
```

#### `retry_interval_days_missing`

**Type:** Integer | **Default:** `null` (inherits `retry_interval_days`)

Override `retry_interval_days` for **missing** item searches only. When set, missing items use this interval instead of the base value. Set to `0` to disable the retry window for missing searches (re-search every cycle).

```yaml
global:
  retry_interval_days: 30         # Base interval for all searches
  retry_interval_days_missing: 7  # Re-search missing items after only 7 days
```

#### `retry_interval_days_upgrade`

**Type:** Integer | **Default:** `null` (inherits `retry_interval_days`)

Override `retry_interval_days` for **upgrade** searches only. When set, upgrade-eligible items use this interval instead of the base value. Set to `0` to disable the retry window for upgrade searches (re-search every cycle).

```yaml
global:
  retry_interval_days: 30          # Base interval for all searches
  retry_interval_days_upgrade: 60  # Re-search upgrade candidates only after 60 days
```

#### `search_order`

**Type:** String | **Default:** `last_searched_ascending`

**Options:**
- `alphabetical_ascending`: Alphabetical by title (A-Z).
- `alphabetical_descending`: Reverse alphabetical (Z-A).
- `last_added_ascending`: Oldest added to *arr first.
- `last_added_descending`: Most recently added to *arr first.
- `last_searched_ascending`: Oldest last-searched first (items never searched come first).
- `last_searched_descending`: Most recently searched first.
- `random`: Randomized order.
- `release_date_ascending`: Oldest release date first.
- `release_date_descending`: Newest release date first.

#### `season_packs`

**Type:** `Boolean | Integer (≥ 1) | Float (0.0 < x < 1.0)` | **Default:** `false` | **Applies to:** Sonarr instances only

Controls whether Sonarr searches are grouped into season packs, and optionally gated behind a threshold. Instead of sending one `EpisodeSearch` per episode, Rangarr sends one `SeasonSearch` per `(series, season)` pair — more efficient when many episodes of the same season are affected.

| Value | Behaviour |
|---|---|
| `false` | Always use individual episode searches (default). |
| `true` | Always use season pack searches for completed seasons. |
| Integer `N` (≥ 1) | Use a season pack only if at least `N` episodes in that season are missing or upgrade-eligible; otherwise fall back to individual episode searches. |
| Float `x` (0.0 < x < 1.0) | Use a season pack only if the ratio of affected episodes to total monitored episodes meets or exceeds `x`; otherwise fall back to individual episode searches. |

For seasons that have not yet finished airing, Rangarr always falls back to individual episode searches regardless of the `season_packs` value.

`missing_batch_size` and `upgrade_batch_size` apply as normal — they limit the number of seasons (or individual episodes, after fallback) searched per cycle.

```yaml
global:
  season_packs: true      # always use season packs
  # season_packs: 3       # season pack only when 3+ episodes are affected
  # season_packs: 0.5     # season pack only when ≥50% of monitored episodes are affected
```

#### `include_tags`

**Type:** List of strings | **Default:** `[]`

When non-empty, only search items that have **any** of the listed tags. Tags are matched case-insensitively. Leave empty (or omit) to search all items regardless of tags.

```yaml
global:
  include_tags: ["active"]  # Only search items tagged "active"
```

#### `exclude_tags`

**Type:** List of strings | **Default:** `[]`

Skip items that have **any** of the listed tags. Tags are matched case-insensitively. When both `include_tags` and `exclude_tags` are set, exclude takes precedence — an item with an excluded tag is always skipped.

```yaml
global:
  exclude_tags: ["on-hold"]  # Never search items tagged "on-hold"
```

#### `active_hours`

**Type:** String | **Default:** `""` (all hours)

Restrict searches to a specific time window. Format: `"HH:MM-HH:MM"` (24-hour clock). Times are interpreted in the container's local time — set the `TZ` environment variable in your `compose.yaml` to control this.

Cross-midnight windows are supported: `"22:00-06:00"` means active from 22:00 through 06:00 the following morning. Outside the window, Rangarr skips the cycle and sleeps until the window opens rather than waiting the normal `interval`.

Leave unset or set to `""` to search at any hour.

```yaml
global:
  active_hours: "22:00-06:00"  # Only search overnight
```

### Instance Settings

Settings for individual *arr instances.

#### `type` (required)

**Options:** `radarr`, `sonarr`, `lidarr`

Prowlarr is not supported — it is an indexer aggregator, not a media manager, and does not expose the missing/cutoff wanted endpoints that Rangarr uses.

```yaml
instances:
  Movies:
    type: radarr
```

#### `host` (required)

Base URL of the *arr instance.

**Docker deployments:** Use `http://` with the container hostname (e.g., `http://radarr:7878`). Traffic stays on the internal Docker network, so HTTPS is not needed and not typically configured.

**HTTPS:** Only works when routing through a reverse proxy with a publicly trusted certificate (e.g., Let's Encrypt). Self-signed certificates are not supported — there is no option to disable certificate verification.

```yaml
instances:
  Movies:
    host: "http://radarr:7878"  # Docker: container hostname
    # host: "http://localhost:7878"  # Non-Docker: localhost
```

#### `api_key` (required)

API key for authentication. Found in *arr settings under Settings → General → Security. Never commit `config.yaml` to version control — it is gitignored by default. To avoid storing secrets in `config.yaml`, use environment variable expansion — see [Environment Variable Expansion](#environment-variable-expansion).

#### `enabled`

**Type:** Boolean | **Default:** `false`

Instances are disabled by default as a safety measure. You must explicitly set this to `true` for an instance to be actively searched.

#### `weight`

**Type:** Number | **Default:** `1`

Relative priority for batch distribution. Higher weight = more items.

```yaml
instances:
  Movies-Main:
    weight: 2  # Gets 2x items compared to weight: 1
  Movies-4K:
    weight: 1
```

With `missing_batch_size: 30`, Movies-Main gets ~20 items, Movies-4K gets ~10.

### Common Scenarios

#### Single Instance

```yaml
global:
  interval: 3600
  missing_batch_size: 20
  upgrade_batch_size: 10

instances:
  Radarr:
    type: radarr
    host: "http://radarr:7878"  # Docker: use container hostname
    api_key: "your_api_key"
    enabled: true
```

#### Multiple Instances with Priority

```yaml
global:
  interval: 1800
  missing_batch_size: 50

instances:
  Radarr-Main:
    type: radarr
    host: "http://radarr:7878"
    api_key: "key1"
    enabled: true
    weight: 3

  Radarr-4K:
    type: radarr
    host: "http://radarr-4k:7879"
    api_key: "key2"
    enabled: true
    weight: 1

  Lidarr-Music:
    type: lidarr
    host: "http://lidarr:8686"
    api_key: "key3"
    enabled: true
```

With these three instances (weights 3, 1, and 1), Radarr-Main gets ~60% of the batch, Radarr-4K gets ~20%, and Lidarr-Music gets ~20%.

#### Dry Run Testing

```yaml
global:
  dry_run: true  # Log searches without executing
  interval: 60   # Run frequently for testing
  missing_batch_size: 5

instances:
  Radarr:
    type: radarr
    host: "http://radarr:7878"
    api_key: "your_api_key"
    enabled: true
```

Check logs with `docker compose logs -f` to verify behavior.

#### Focus on Missing Items

```yaml
global:
  missing_batch_size: 50
  upgrade_batch_size: 5  # Small allocation for upgrades
```

#### Disable Upgrades, Unlimited Missing

```yaml
global:
  missing_batch_size: -1  # Search all missing items
  upgrade_batch_size: 0   # Skip upgrade searches entirely
```

#### Tag Filtering

```yaml
global:
  include_tags: ["active"]   # Only search items with this tag
  exclude_tags: ["on-hold"]  # Skip items with this tag; takes precedence over include_tags
```

Tags are resolved at startup from each *arr instance. If a tag name is not found on a specific instance, a warning is logged and that name is ignored for that instance — other configured tags still apply. Adding or removing tags in *arr requires restarting Rangarr to take effect.

#### Off-Peak Searching

Restrict searches to overnight hours to avoid hitting indexers during peak usage. Set the `TZ` environment variable to your local timezone so `active_hours` uses your clock, not UTC.

In `compose.yaml`:
```yaml
environment:
  TZ: America/New_York
```

In `config.yaml`:
```yaml
global:
  active_hours: "22:00-06:00"  # Search from 10 PM to 6 AM local time
```

Outside the window, Rangarr logs a message and sleeps until the window opens. It does not drift — when the window opens it runs the next cycle immediately.

### Environment Variable-Only Configuration

Set `RANGARR_CONFIG_SOURCE=env` to have Rangarr ignore `config.yaml` entirely and read all configuration from environment variables. This is useful for container deployments where injecting a config file is inconvenient.

#### Global Settings

The following global settings are supported, each prefixed with `RANGARR_GLOBAL_`. All values are type-coerced automatically — `"true"`/`"false"` become booleans and numeric strings become integers or floats.

| Variable | Default | Description |
|---|---|---|
| `RANGARR_GLOBAL_INTERVAL` | `3600` | Run interval in seconds (converted to minutes internally). |
| `RANGARR_GLOBAL_RUN_INTERVAL_MINUTES` | `60` | Run interval in minutes. Ignored if `INTERVAL` is also set. |
| `RANGARR_GLOBAL_MISSING_BATCH_SIZE` | `20` | Items to search per instance per cycle. `0` disables, `-1` is unlimited. |
| `RANGARR_GLOBAL_UPGRADE_BATCH_SIZE` | `10` | Upgrade-eligible items to search per cycle. `0` disables, `-1` is unlimited. |
| `RANGARR_GLOBAL_STAGGER_INTERVAL_SECONDS` | `30` | Delay between individual search triggers. |
| `RANGARR_GLOBAL_RETRY_INTERVAL_DAYS` | `30` | Days before a previously searched item is eligible again. `0` disables. |
| `RANGARR_GLOBAL_RETRY_INTERVAL_DAYS_MISSING` | `(none)` | Override `retry_interval_days` for missing searches only. |
| `RANGARR_GLOBAL_RETRY_INTERVAL_DAYS_UPGRADE` | `(none)` | Override `retry_interval_days` for upgrade searches only. |
| `RANGARR_GLOBAL_SEARCH_ORDER` | `last_searched_ascending` | One of: `alphabetical_ascending`, `alphabetical_descending`, `last_added_ascending`, `last_added_descending`, `last_searched_ascending`, `last_searched_descending`, `random`, `release_date_ascending`, `release_date_descending`. |
| `RANGARR_GLOBAL_DRY_RUN` | `false` | Log searches without triggering them. |
| `RANGARR_GLOBAL_INTERLEAVE_INSTANCES` | `false` | `false` = run all items for one instance before moving to the next. `true` = alternate across instances in round-robin order. |
| `RANGARR_GLOBAL_SEASON_PACKS` | `false` | Season pack mode for Sonarr. `false` = individual episode searches. `true` = always use season packs. Integer `N` = season pack only when N or more episodes are affected. Float `x` = season pack only when the ratio of affected to monitored episodes meets or exceeds x. Airing seasons always fall back to individual searches. Sonarr only; ignored by other instance types. |
| `RANGARR_GLOBAL_INCLUDE_TAGS` | `(none)` | Comma-separated tag names. Only search items that have any of these tags. |
| `RANGARR_GLOBAL_EXCLUDE_TAGS` | `(none)` | Comma-separated tag names. Skip items that have any of these tags. |
| `RANGARR_GLOBAL_ACTIVE_HOURS` | `""` | Time window for searches, e.g. `22:00-06:00`. Leave empty to search at any hour. |

#### Instance Settings

Each instance is identified by a numeric index. Prefix instance fields with `RANGARR_INSTANCE_<INDEX>_` where `<INDEX>` is any non-negative integer. Indices do not need to be sequential — you can define instances at index `0` and `2` without `1`.

| Variable | Required | Description |
|---|---|---|
| `RANGARR_INSTANCE_<n>_NAME` | Yes | Unique name for this instance. |
| `RANGARR_INSTANCE_<n>_TYPE` | Yes | `radarr`, `sonarr`, or `lidarr` (case-insensitive). |
| `RANGARR_INSTANCE_<n>_URL` | Yes | Base URL of the instance (e.g. `http://radarr:7878`). `HOST` is accepted as an alias. |
| `RANGARR_INSTANCE_<n>_API_KEY` | Yes | API key from the instance's settings page. |
| `RANGARR_INSTANCE_<n>_ENABLED` | No | Defaults to `true`. Set to `false` to disable without removing the variable. |
| `RANGARR_INSTANCE_<n>_WEIGHT` | No | Relative search weight. Defaults to `1`. |

#### Example

```bash
RANGARR_CONFIG_SOURCE=env
RANGARR_GLOBAL_INTERVAL=1800
RANGARR_GLOBAL_DRY_RUN=false

RANGARR_INSTANCE_0_NAME=Movies
RANGARR_INSTANCE_0_TYPE=radarr
RANGARR_INSTANCE_0_URL=http://radarr:7878
RANGARR_INSTANCE_0_API_KEY=your-api-key
RANGARR_INSTANCE_0_WEIGHT=2

RANGARR_INSTANCE_1_NAME=TV
RANGARR_INSTANCE_1_TYPE=sonarr
RANGARR_INSTANCE_1_URL=http://sonarr:8989
RANGARR_INSTANCE_1_API_KEY=your-api-key
```

---

## Docker

### Docker Compose

A minimal `compose.yaml`:

```yaml
services:
  rangarr:
    image: judochinx/rangarr:latest
    container_name: rangarr
    hostname: rangarr
    restart: unless-stopped
    environment:
      TZ: UTC          # Set your timezone for log timestamps (e.g. America/New_York). Full list: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
      LOG_LEVEL: INFO  # Use DEBUG for verbose logging
    volumes:
      - ./config.yaml:/app/config/config.yaml:ro
    networks:
      - arr

networks:
  arr:
    external: true
```

The `networks` block is optional but recommended — it keeps traffic between Rangarr and your *arr containers internal rather than routing through the host. If you omit it, use `http://localhost:<port>` hostnames in `config.yaml` instead. If you include it, the `arr` network must exist before starting — see [Docker Networking](#docker-networking). The [Quick Start](#quick-start-docker) section covers the full setup flow.

**View logs:**
```bash
docker compose logs -f
```

**Update to a new release:**
```bash
docker compose pull
docker compose up -d
```

This downloads the new image and recreates the container. Your `config.yaml` is unchanged.

### Docker Run

If you prefer not to use Compose, you can run Rangarr with a single `docker run` command. First, prepare your config file:

```bash
curl -O https://raw.githubusercontent.com/JudoChinX/rangarr/main/config.example.yaml
mv config.example.yaml config.yaml
chmod 644 config.yaml  # Required: container runs as UID 65532 (nonroot)
# Edit config.yaml with your *arr API keys and hostnames
```

Then start the container:

```bash
docker run -d \
  --name rangarr \
  --hostname rangarr \
  --restart unless-stopped \
  --network arr \
  -e TZ=UTC \
  -e LOG_LEVEL=INFO \
  -v ./config.yaml:/app/config/config.yaml:ro \
  judochinx/rangarr:latest
```

Replace `TZ=UTC` with your local timezone (e.g. `America/New_York`). The `--network arr` flag is optional but recommended — it keeps traffic between Rangarr and your *arr containers on an internal network rather than routing through the host. If you omit it, use `http://localhost:<port>` hostnames in `config.yaml` instead. See [Docker Networking](#docker-networking).

**View logs:**
```bash
docker logs -f rangarr
```

**Update to a new release:**
```bash
docker pull judochinx/rangarr:latest
docker stop rangarr && docker rm rangarr
# Re-run the docker run command above
```

### Docker Networking

Rangarr and all *arr containers (Radarr, Sonarr, Lidarr, Prowlarr) should share a single, dedicated Docker network. This keeps traffic between containers internal and off the host network stack.

Create the network once:
```bash
docker network create arr
```

In `config.yaml`, use container hostnames instead of `localhost`:
```yaml
instances:
  Radarr:
    type: radarr
    host: "http://radarr:7878"  # Container hostname, not localhost
    api_key: "your_api_key"
    enabled: true
```

---

## Indexer Safety & Limits

Rangarr staggers searches to reduce indexer load, but it does not enforce indexer-level download or search limits. To prevent hitting indexer rate limits or being banned, **configure search and download limits per-indexer** in your *arr apps.

### Preferred: Configure limits in Prowlarr

If you use Prowlarr as your indexer proxy, set limits there rather than in individual *arr apps. Prowlarr enforces limits globally — a single cap applies regardless of which *arr app triggers the search. This is the most reliable way to stay within indexer quotas.

In Prowlarr: *Indexers → (select indexer) → Query Limit / Grab Limit*

### Alternative: Configure limits per *arr app

If you manage indexers directly in Radarr, Sonarr, or Lidarr (without Prowlarr), set limits on each indexer within each app. Be aware that limits are enforced independently per app, so the effective total across all apps can exceed any single app's cap.

In each *arr app: *Settings → Indexers → (select indexer) → Query Limit / Grab Limit*

---

## Operational Best Practices

### Search Strategies

Choosing the right search order depends on your library size and goals:

- **Small Libraries (<500 items):** Use `last_added_descending`. This prioritizes getting your newest additions indexed and downloaded quickly.
- **Large Backlogs (5,000+ items):** Use `random` or `last_searched_ascending`. This ensures the entire backlog is eventually touched and prevents the same items from being "stuck" at the front of the queue if they are difficult to find.
- **The Audit Phase:** When first setting up Rangarr with a massive existing library, set `dry_run: true` and `interval: 60` for one or two cycles. Review the logs to see what *would* be searched before committing to actual API commands.

---

## Troubleshooting

### Connection Errors

#### "Connection refused" or "Failed to connect"

**Symptoms:** Logs show connection errors when trying to reach *arr instances.

**Causes:**
1. Wrong URL in config.yaml.
2. *arr instance is down.
3. Network connectivity issues.
4. Firewall blocking access.

**Solutions:**

1. **Verify URL format:**
   ```yaml
   host: "http://localhost:7878"  # Correct
   host: "localhost:7878"         # Missing http://
   host: "http://radarr:7878/"    # Also valid (trailing slash is stripped)
   ```

2. **Test connectivity manually:**
   ```bash
   curl http://localhost:7878/api/v3/system/status?apikey=YOUR_API_KEY
   ```

3. **Check *arr instance is running:**
   - Access web UI directly in browser.
   - Check *arr service logs.

4. **Docker networking:** If running in Docker, Rangarr and all *arr containers should be on the same named Docker network (e.g., `arr`). Use container hostnames instead of `localhost` in `config.yaml`:
   ```yaml
   host: "http://radarr:7878"   # Container hostname — correct
   host: "http://localhost:7878" # Will not resolve inside Docker — incorrect
   ```
   If containers are on different networks, they cannot reach each other.

#### "401 Unauthorized" or "403 Forbidden"

**Symptoms:** Authentication errors in logs.

**Cause:** Invalid or missing API key.

**Solutions:**

1. Go to Settings → General → Security in the *arr UI and copy the API Key exactly (no extra spaces).
2. Update `config.yaml` with the correct key.
3. Check for typos — API keys are case-sensitive and typically 32 characters.

### No Items Found

#### "No items to search" despite missing media

**Possible Causes:**

1. **Retry window:** Items were recently searched and are within the `retry_interval_days` window.
2. **Availability filtering:** Items may not meet availability criteria yet. Rangarr skips items that are not considered available: for Sonarr, episodes whose `airDateUtc` is in the future or missing; for Lidarr, albums whose `releaseDate` is in the future or missing. Radarr uses the `isAvailable` flag returned by the API.
3. **Items not monitored or already available:** Check the *arr web UI to confirm items are monitored and actually missing/wanted.
4. **Tag filtering:** `include_tags` or `exclude_tags` is configured and items do not match. Enable debug logging to see `Skipping ... item (tag filter):` messages.

**Solutions:**

1. **Check retry window:** Enable debug logging and look for "within retry window" messages. If items are being skipped due to the retry window and you want to re-search them sooner, reduce the window:
   ```yaml
   global:
     retry_interval_days: 7  # Re-search items after 7 days instead of 30
   ```

2. **Enable debug logging:**
   ```yaml
   environment:
     LOG_LEVEL: DEBUG
   ```

3. **Verify in *arr UI:** Go to Wanted → Missing/Cutoff Unmet to see what *arr reports. Note that items eligible only via the custom format score pass will not appear there — they are found by Rangarr separately.

#### Items found but not being searched

**Cause:** Likely `dry_run: true` in config.

**Solution:**
```yaml
global:
  dry_run: false  # Ensure this is false for actual searches
```

#### Lidarr: albums silently skipped

**Cause:** Albums without a `releaseDate` in Lidarr's API response are skipped by Rangarr's availability check. This can happen with releases that have not been given a release date in MusicBrainz.

**Solution:** Enable `LOG_LEVEL=DEBUG` to see which albums are being skipped and why. If the missing date is the issue, update the release information in MusicBrainz or set the release date manually in Lidarr.

### Performance Issues

#### Searches triggering too frequently

**Solutions:**

1. Reduce batch sizes:
   ```yaml
   global:
     missing_batch_size: 10
     upgrade_batch_size: 5
   ```

2. Increase stagger interval:
   ```yaml
   global:
     stagger_interval_seconds: 60
   ```

3. Increase run interval:
   ```yaml
   global:
     interval: 7200  # Run every 2 hours instead of 1
   ```

#### Searches taking too long

**Cause:** Large batch sizes with stagger interval creates long cycles.

**Example:** 100 items × 10 second stagger = 16+ minutes per cycle

**Solutions:**

1. Reduce batch sizes:
   ```yaml
   global:
     missing_batch_size: 10
     upgrade_batch_size: 5
   ```
2. Reduce stagger interval (if *arr instances can handle it):
   ```yaml
   global:
     stagger_interval_seconds: 10
   ```

### Configuration Issues

#### "No instances defined" on startup

**Cause:** All instances have `enabled: false` (the default). Rangarr requires at least one enabled instance to start.

**Solution:** Set `enabled: true` on each instance you want Rangarr to search:

```yaml
instances:
  Radarr:
    type: radarr
    host: "http://radarr:7878"
    api_key: "your_api_key"
    enabled: true  # Required — instances are disabled by default
```

#### "Invalid configuration" errors

1. Check required fields: each instance needs `type`, `host`, and `api_key`.
2. Validate YAML syntax using an online YAML validator (e.g. yamllint.com) or any local YAML linting tool.
3. Check indentation — YAML is whitespace-sensitive. Use spaces, not tabs.

#### Changes to config.yaml not taking effect

The service must be restarted to load new configuration.

```bash
docker compose restart
```

### Debug Logging

Enable detailed logging to diagnose issues:

```yaml
environment:
  LOG_LEVEL: DEBUG
```

Debug logs show: unlimited fetch triggers, items skipped due to availability filtering, and per-item stagger delays.

### Reporting Bugs

If you encounter issues not covered here:

1. Enable DEBUG logging and capture logs.
2. Redact sensitive information (API keys, IPs, hostnames).
3. Check existing issues: https://github.com/JudoChinX/rangarr/issues
4. Create a new issue with: Rangarr version, Docker image tag, configuration (redacted), and logs showing the error.

**Security Issues:** Report privately via [SECURITY.md](../SECURITY.md), not public issues.

---

## Development Setup

If you plan to contribute or modify the code:

1. **Clone the repository:**
   ```bash
   git clone https://github.com/JudoChinX/rangarr.git
   cd rangarr
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Create `config.yaml`:**
   ```bash
   cp config.example.yaml config.yaml
   ```
   Edit with your *arr instance details.

5. **Build and run locally:**
   ```bash
   docker build -t rangarr .
   docker compose up
   ```
   Or run directly with Python:
   ```bash
   python -m rangarr.main
   ```

6. **Install git hooks:**
   ```bash
   ./utils/setup.sh
   ```
   This installs a pre-push hook that runs `ruff check`, `ruff format`, `pylint`, `mypy`, `bandit`, and `pytest` before every push. Pushes are blocked if any check fails.

7. **Run tests:**
   ```bash
   pytest
   ```

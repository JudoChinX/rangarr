# Rangarr

[![Tests & Quality](https://github.com/JudoChinX/rangarr/actions/workflows/ci.yml/badge.svg)](https://github.com/JudoChinX/rangarr/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/JudoChinX/rangarr)](https://github.com/JudoChinX/rangarr/releases)
[![Docker Pulls](https://img.shields.io/docker/pulls/judochinx/rangarr)](https://hub.docker.com/r/judochinx/rangarr)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pylint](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/pylint-dev/pylint)
[![mypy](https://img.shields.io/badge/type%20checked-mypy-blue)](https://mypy-lang.org)
[![yamllint](https://img.shields.io/badge/yamllint-enabled-blue)](https://github.com/adrienverge/yamllint)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![pytest](https://img.shields.io/badge/tested%20with-pytest-0a9edc)](https://pytest.org)
[![Docker Scout](https://img.shields.io/badge/docker%20scout-enabled-blue)](https://hub.docker.com/r/judochinx/rangarr)
[![Architectures](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-blue)](https://hub.docker.com/r/judochinx/rangarr/tags)
[![Sponsor](https://img.shields.io/badge/Sponsor-JudoChinX-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/JudoChinX)
[![Pairs with Killarr](https://img.shields.io/badge/pairs%20with-Killarr-blue)](https://github.com/JudoChinX/killarr)

<p align="center">
  <img src="https://github.com/JudoChinX/unraid-templates/raw/main/assets/rangarr-logo.png" alt="Rangarr Logo">
</p>

**Rangarr** is a lightweight orchestration service that automates and staggers media searches across multiple *arr instances ([Radarr](https://github.com/Radarr/Radarr), [Sonarr](https://github.com/Sonarr/Sonarr), [Lidarr](https://github.com/Lidarr/Lidarr)). It helps keep your library complete without overwhelming your indexers or API limits.

## Key Features

- **Multi-Instance Support:** Manage Radarr, Sonarr, and Lidarr from a single service.
- **Global Slot Allocation:** Efficiently distributes search slots across all instances, ensuring no search capacity is wasted.
- **Instance Interleaving:** Spreads search pressure evenly across multiple *arr instances and shared indexers throughout the cycle.
- **Smart Staggering:** Prevents "thundering herd" issues by spacing out search requests.
- **Proportional Interleaving:** Balanced searching between missing items and upgrades within each instance.
- **Weighted Distribution:** Prioritize specific instances (e.g., prioritize Movies over Music).
- **Season Pack Support:** Group Sonarr searches by season, with configurable count or ratio thresholds and automatic fallback to individual episode searches for seasons that are still airing.
- **Retry Logic:** Configurable skip windows for recently searched items, with independent intervals for missing and upgrade searches, plus automatic startup connection retries (3 attempts, 10-second delay) to handle Docker Compose race conditions.
- **Custom Format Score Awareness:** Finds Radarr and Sonarr items below their custom format score target — candidates *arr's Cutoff Unmet endpoint silently omits.
- **Tag Filtering:** Restrict searches to items with specific *arr tags, or exclude tagged items entirely.
- **Active Hours:** Restrict searches to a configured time window (e.g., overnight only) to avoid peak indexer load.
- **Flexible Configuration:** Configure via `config.yaml` with `${ENV_VAR}` expansion for secrets, or skip the file entirely and use environment variables only.
- **No External Connections:** Only communicates with the *arr instances you configure. No telemetry, no phone-home, no external services.

## Why Rangarr?

Some tools in this space have done things their users didn't know about — phoning home, collecting data, making connections that were never disclosed. Rangarr exists as a direct response to that. It talks to the *arr instances you configure. It talks to nothing else.

The codebase is intentionally small. There is no database, no persistence layer. If you want to verify what it does, [SECURITY.md](SECURITY.md) documents the exact threat model, and the source itself is three files you can read in an afternoon.

## Quick Start

The fastest way to get started is with Docker Compose.

```bash
# 1. Get the configuration
curl -O https://raw.githubusercontent.com/JudoChinX/rangarr/main/config.example.yaml
curl -O https://raw.githubusercontent.com/JudoChinX/rangarr/main/compose.example.yaml
mv config.example.yaml config.yaml
mv compose.example.yaml compose.yaml
chmod 644 config.yaml  # Required: container runs as UID 65532 (nonroot), not your user

# 2. Edit config.yaml with your *arr API keys and hostnames
nano config.yaml

# 3. Start with dry_run: true to verify config before triggering real searches
#    Set dry_run: false in config.yaml once logs look correct, then restart
docker compose up -d
```

**Without Compose**, use `docker run` directly:

```bash
docker run -d \
  --name rangarr \
  --restart unless-stopped \
  -v ./config.yaml:/app/config/config.yaml:ro \
  judochinx/rangarr:latest
```

See the [User Guide](docs/user-guide.md#docker-run) for full details including Docker networking.

A minimal `config.yaml` to get you running:

```yaml
global:
  interval: 3600             # Run every hour
  stagger_interval_seconds: 30 # Wait 30s between searches
  missing_batch_size: 20      # Search 20 missing items per cycle (0=disabled, -1=unlimited)
  upgrade_batch_size: 10      # Search 10 upgrade-eligible items per cycle (0=disabled, -1=unlimited)
  interleave_instances: true  # Alternate between instances during search
  search_order: last_searched_ascending  # Prioritize items not searched recently

instances:
  Radarr:
    type: radarr
    host: "http://radarr:7878"
    api_key: "YOUR_API_KEY"
    enabled: true
```

## Quick Start (Environment Variables Only)

If you prefer not to use a `config.yaml` file, you can configure Rangarr entirely through environment variables.

```bash
docker run -d \
  --name rangarr \
  --restart unless-stopped \
  -e RANGARR_CONFIG_SOURCE=env \
  -e RANGARR_GLOBAL_INTERVAL=3600 \
  -e RANGARR_INSTANCE_0_NAME=MyRadarr \
  -e RANGARR_INSTANCE_0_TYPE=radarr \
  -e RANGARR_INSTANCE_0_URL=http://radarr:7878 \
  -e RANGARR_INSTANCE_0_API_KEY=YOUR_API_KEY \
  judochinx/rangarr:latest
```

## Documentation

- **[User Guide](docs/user-guide.md)** — Setup, configuration, Docker networking, and troubleshooting.
- **[Technical Audit](docs/technical-audit.md)** — Architecture, security model, and design philosophy.
- **[Security & Trust](SECURITY.md)** — What Rangarr does and doesn't do, how to verify it, and how to report vulnerabilities.
- **[Contributing](CONTRIBUTING.md)** — How to help improve Rangarr.
- **[Roadmap](ROADMAP.md)** — Planned and in-progress features.

## Related Projects

- **[Killarr](https://github.com/JudoChinX/killarr)** — Detects and removes stalled downloads from Radarr, Sonarr, and Lidarr queues. Shares the same `config.yaml` format as Rangarr — both tools can run side-by-side from a single config file.

## Development Transparency

AI tooling was used to assist with development tasks in this project. The architecture — no database, no persistence layer, three files, two dependencies — was designed by the author. All code is human-reviewed before inclusion.

## License

MIT License — see [LICENSE](LICENSE) for details.

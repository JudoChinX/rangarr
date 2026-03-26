# Rangarr

[![Tests & Quality](https://github.com/JudoChinX/rangarr/actions/workflows/ci.yml/badge.svg)](https://github.com/JudoChinX/rangarr/actions/workflows/ci.yml)
[![GitHub Release](https://img.shields.io/github/v/release/JudoChinX/rangarr)](https://github.com/JudoChinX/rangarr/releases)
[![Docker Pulls](https://img.shields.io/docker/pulls/judochinx/rangarr)](https://hub.docker.com/r/judochinx/rangarr)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![Docker Scout](https://img.shields.io/badge/docker%20scout-enabled-blue)](https://hub.docker.com/r/judochinx/rangarr)
[![Architectures](https://img.shields.io/badge/arch-amd64%20%7C%20arm64-blue)](https://hub.docker.com/r/judochinx/rangarr/tags)

**Rangarr** is a lightweight orchestration service that automates and staggers media searches across multiple *arr instances ([Radarr](https://github.com/Radarr/Radarr), [Sonarr](https://github.com/Sonarr/Sonarr), [Lidarr](https://github.com/Lidarr/Lidarr)). It helps keep your library complete without overwhelming your indexers or API limits.

## Key Features

- **Multi-Instance Support:** Manage Radarr, Sonarr, and Lidarr from a single service.
- **Smart Staggering:** Prevents "thundering herd" issues by spacing out search requests.
- **Proportional Interleaving:** Balanced searching between missing items and upgrades.
- **Weighted Distribution:** Prioritize specific instances (e.g., prioritize Movies over Music).
- **Retry Logic:** Intelligent skip windows for items recently searched.
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

A minimal `config.yaml` to get you running:

```yaml
global:
  interval: 3600             # Run every hour
  stagger_interval_seconds: 30 # Wait 30s between searches
  missing_batch_size: 20      # Search 20 missing items per cycle (0=disabled, -1=unlimited)
  upgrade_batch_size: 10      # Search 10 upgrade-eligible items per cycle (0=disabled, -1=unlimited)
  search_order: last_searched_ascending  # Prioritize items not searched recently

instances:
  Radarr:
    type: radarr
    host: "http://radarr:7878"
    api_key: "YOUR_API_KEY"
    enabled: true
```

## Documentation

- **[User Guide](docs/user-guide.md)** — Setup, configuration, Docker networking, and troubleshooting.
- **[Technical Audit](docs/technical-audit.md)** — Architecture, security model, and design philosophy.
- **[Security & Trust](SECURITY.md)** — What Rangarr does and doesn't do, how to verify it, and how to report vulnerabilities.
- **[Contributing](CONTRIBUTING.md)** — How to help improve Rangarr.

## Development Transparency

AI tooling was used to assist with development tasks in this project. The architecture — no database, no persistence layer, three files, two dependencies — was designed by the author. All code is human-reviewed before inclusion.

## License

MIT License — see [LICENSE](LICENSE) for details.

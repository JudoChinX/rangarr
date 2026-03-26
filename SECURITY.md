# Security Policy

## What Rangarr Does

Understanding what the software accesses and why is important for trust, especially in light of security incidents affecting similar tools in the ecosystem.

Rangarr talks to the *arr instances you configure. It talks to nothing else.

To be absolutely clear, Rangarr does not and will never:
- Access media files on disk
- Connect to external services (indexers, trackers, notification services, etc.)
- Collect usage statistics or telemetry
- Phone home or check for updates
- Access download client APIs or credentials
- Modify *arr configuration settings
- Access user authentication data beyond API keys

## Verify It Yourself

The entire application is three source files. The links below track the `main` branch — once a stable release tag exists, they will be updated to point to it:

- [`rangarr/main.py`](https://github.com/JudoChinX/rangarr/blob/main/rangarr/main.py) — orchestration loop
- [`rangarr/config_parser.py`](https://github.com/JudoChinX/rangarr/blob/main/rangarr/config_parser.py) — configuration loading and validation
- [`rangarr/clients/arr.py`](https://github.com/JudoChinX/rangarr/blob/main/rangarr/clients/arr.py) — *arr API client

The only direct dependencies are [`requests`](https://github.com/psf/requests) and [`PyYAML`](https://github.com/yaml/pyyaml), both widely used and well-maintained with public security disclosure policies. `requests` pulls in four transitive dependencies ([`certifi`](https://github.com/certifi/python-certifi), [`charset-normalizer`](https://github.com/Ousret/charset_normalizer), [`idna`](https://github.com/kjd/idna), [`urllib3`](https://github.com/urllib3/urllib3)); `PyYAML` has none.

## What Rangarr Accesses

Rangarr interacts exclusively with your configured Radarr, Sonarr, and Lidarr instances through their official APIs. Specifically:

**API Endpoints Called:**
- `GET /api/v3/wanted/missing` (or `/api/v1/wanted/missing` for Lidarr) - Retrieves lists of missing media items (not yet downloaded)
- `GET /api/v3/wanted/cutoff` (or `/api/v1/wanted/cutoff` for Lidarr) - Retrieves lists of items eligible for quality upgrades
- `POST /api/v3/command` (or `/api/v1/command` for Lidarr) - Sends search commands (`MoviesSearch` for Radarr, `EpisodeSearch` for Sonarr, `AlbumSearch` for Lidarr)

**Data Accessed:**
- Media metadata only: titles, IDs, air dates, search timestamps
- No media files, no user data, no download client information
- No access to authentication credentials beyond the API keys provided in `config.yaml`

**Search Commands Sent:**
The only write operations Rangarr performs are triggering search commands on your *arr instances. These are the same commands you would trigger manually through the *arr web interfaces. Rangarr does not:
- Modify library settings or quality profiles
- Add or remove media from your library
- Access or modify download clients
- Interact with indexers directly
- Send data to external services

## Network Activity

Rangarr operates entirely within your local network (or wherever you host your *arr instances):
- Only communicates with URLs explicitly configured in `config.yaml`
- No telemetry, analytics, or external API calls
- No automatic updates or version checks
- All HTTP requests use the session configured at startup; no request data is logged externally

**Important:** Rangarr does not encrypt credentials or API keys in transit. It is designed for use on a trusted local network and should **not** be exposed to the public internet. For Docker deployments, keep all *arr containers on an isolated internal Docker network (see README for details).

## API Key Handling

API keys are stored in `config.yaml` and used exclusively for authentication headers:
- Keys are read once at startup and stored in memory
- Keys are added to HTTP request headers as `X-Api-Key` (standard *arr authentication)
- No API keys are logged, transmitted externally, or written to disk beyond your configuration file
- The configuration file should be protected with appropriate filesystem permissions (recommend `chmod 600 config.yaml`)

## Container Security

The official Docker image is built on `gcr.io/distroless/python3-debian13` — Google's distroless Python base image. Distroless images contain only the application runtime and its dependencies; they do not include a shell, package manager, or any OS userland beyond what is strictly required.

**Properties of the runtime image:**
- No shell (`/bin/sh`, `/bin/bash`) — interactive access to a running container is not possible
- No package manager (`apt`, `pip`) — no packages can be installed at runtime
- No build tooling, compilers, or utilities
- Runs as a non-root user (`nonroot`, UID 65532) by default
- CA certificates included — outbound HTTPS connections work without modification

This limits the blast radius of a compromised container: an attacker cannot execute arbitrary shell commands, install additional tooling, or escalate to root via the package manager.

To verify the runtime image contains no shell:
```bash
docker run --rm --entrypoint /bin/sh judochinx/rangarr
# Expected: "exec: /bin/sh: stat /bin/sh: no such file or directory"
```

## Reporting a Vulnerability

If you discover a security vulnerability in Rangarr, please report it responsibly. Do not create a public GitHub issue for security vulnerabilities.

**Primary contact:** GitHub Security Advisories (https://github.com/JudoChinX/rangarr/security)

**Email contact for non-GitHub users:** rangarr@judochinx.com

**Response Timeline:**
- **Acknowledgment:** You will receive an acknowledgment of your report within 48 hours.
- **Coordinated Disclosure:** We follow a 90-day coordinated disclosure timeline. Security fixes will be released before public disclosure whenever possible.

We appreciate responsible disclosure and will credit security researchers in release notes unless you prefer to remain anonymous.

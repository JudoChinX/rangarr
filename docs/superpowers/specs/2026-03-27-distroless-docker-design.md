# Distroless Docker Migration Design

**Date:** 2026-03-27
**Status:** Approved

## Overview

Migrate the Rangarr `Dockerfile` from a single-stage `python:3.12-slim` build to a multi-stage build using `gcr.io/distroless/python3-debian12` as the runtime image. This removes the shell, package manager, and other unnecessary tooling from the final image, reducing the attack surface.

## Architecture

### Build Stage (`builder`)

- Base image: `python:3.12-slim`
- Installs Python dependencies from `requirements.txt` into `/install` using `pip install --prefix=/install`
- No application code changes; pip and build tooling stay in this stage only

### Runtime Stage

- Base image: `gcr.io/distroless/python3-debian12`
- Copies `/install` from builder into `/install` (site-packages live at `/install/lib/python3.12/site-packages`)
- Copies application source from builder's `/app` into `/app`
- Sets `PYTHONPATH=/install/lib/python3.12/site-packages` so the runtime Python finds installed packages
- Retains all existing env vars: `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`
- Drops `PIP_NO_CACHE_DIR` and `PIP_DISABLE_PIP_VERSION_CHECK` — pip is not present in the runtime image
- Uses distroless built-in `nonroot` user (UID 65532) instead of a manually created `rangarr` user
- `WORKDIR /app`

### CMD

```
CMD ["/usr/bin/python3", "-m", "rangarr.main"]
```

Distroless does not symlink `python` or `python3` onto `PATH`; the interpreter must be referenced by absolute path.

## What Changes

| Current | New |
|---|---|
| Single stage | Two stages (builder + runtime) |
| `python:3.12-slim` runtime | `gcr.io/distroless/python3-debian12` runtime |
| Manual `adduser`/`addgroup` (UID 1000) | Distroless built-in `nonroot` (UID 65532) |
| `chown -R rangarr:rangarr /app` | Not needed; `USER nonroot` set directly |
| `CMD ["python", "-m", "rangarr.main"]` | `CMD ["/usr/bin/python3", "-m", "rangarr.main"]` |

## What Does Not Change

- Multi-arch build (`linux/amd64`, `linux/arm64`) — distroless Python supports both
- CI workflow (`ci.yml`) — no changes required
- Application source code
- CA certificates — included in `gcr.io/distroless/python3-debian12` by default, so outbound HTTPS calls to *arr instances continue to work

## Security Properties of Final Image

- No shell (`/bin/sh`, `/bin/bash`)
- No package manager (`apt`, `pip`)
- No build tooling or compilers
- Minimal OS userland (libc, CA certs, tzdata only)
- Non-root by default

# Runbook: Cutting a Release

Step-by-step process for tagging and publishing a new Rangarr release.

---

## Overview

Pushing a `v*` tag to `main` triggers the CI/CD pipeline, which:

1. Runs the full test and quality suite
2. Builds and pushes a multi-arch Docker image (`linux/amd64`, `linux/arm64`) to Docker Hub as both `judochinx/rangarr:<version>` and `judochinx/rangarr:latest`
3. Creates a GitHub Release with release notes extracted from `CHANGELOG.md`

---

## Pre-flight Checks

Before cutting a release, confirm:

- [ ] All intended changes are merged to `main`
- [ ] `CHANGELOG.md` `[Unreleased]` section is empty — all notable changes moved into the versioned section
- [ ] User-facing docs are accurate (`docs/user-guide.md`, `docs/technical-audit.md`, `config.example.yaml`)
- [ ] The version follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

---

## Steps

### 1. Run the release script

The `utils/release.sh` script handles branch creation, version bump, changelog validation, commit, and push:

```bash
./utils/release.sh
```

**What the script does:**
1. Validates the version format (`MAJOR.MINOR.PATCH`) and pre-flight checks
2. Creates a `release-vX.Y.Z` branch from `main`
3. Bumps the version in `pyproject.toml`
4. Pauses for manual steps (see below)
5. Validates `CHANGELOG.md` — versioned entry exists and `[Unreleased]` is empty
6. Commits `CHANGELOG.md` + `pyproject.toml` and pushes the release branch

### 2. Manual steps (while the script is paused)

Before confirming in the script:

- **Update `CHANGELOG.md`** — move all `[Unreleased]` entries into a `[X.Y.Z] - YYYY-MM-DD` section and leave `[Unreleased]` empty:

  ```diff
   ## [Unreleased]
  +
  +## [X.Y.Z] - YYYY-MM-DD
  +
  +### Added
  +- ...
  +
  +### Fixed
  +- ...
  ```

- **Review user-facing docs** — check `docs/user-guide.md`, `docs/technical-audit.md`, and `config.example.yaml` for accuracy (defaults, feature descriptions, line counts).

### 3. Open and merge the PR

The script prints the `gh pr create` command on completion. Merge once reviewed.

### 4. Tag main after the PR merges

```bash
git fetch origin
git tag vX.Y.Z origin/main
git push origin vX.Y.Z
```

The tag push triggers the CI release pipeline.

---

## What Happens Next (Automated)

| Step | Action |
|------|--------|
| CI runs tests | Full lint, type-check, security scan, and pytest suite |
| Docker build | Multi-arch image built for `linux/amd64` and `linux/arm64` |
| Docker push | Image pushed to `judochinx/rangarr:X.Y.Z` and `judochinx/rangarr:latest` |
| GitHub Release | Created automatically with body pulled from the `[X.Y.Z]` section in `CHANGELOG.md` |

---

## Verifying the Release

Once CI completes:

1. **GitHub Release** — check the Releases page; confirm the release notes look correct
2. **Docker Hub** — confirm the new tag and `latest` are present at `hub.docker.com/r/judochinx/rangarr`

---

## Rollback / Recovery

**If you tagged the wrong commit:**

```bash
# Delete the tag locally and remotely, then re-tag the correct commit
git tag -d vX.Y.Z
git push origin :refs/tags/vX.Y.Z
git tag vX.Y.Z <correct-commit-sha>
git push origin vX.Y.Z
```

> Note: This will re-trigger the CI release pipeline on the new tag.

**If the commit pushed but the tag did not:**

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

**If CI fails after tagging:**

1. Fix the issue on `main` and push the fix
2. Delete and re-push the tag (see above) to re-trigger the pipeline

---

## Versioning Guidelines

| Change type | Version bump |
|-------------|-------------|
| Breaking changes to config or behavior | `MAJOR` (once >= 1.0.0) or `MINOR` (pre-1.0) |
| New features, backward-compatible | `MINOR` |
| Bug fixes, documentation, internal changes | `PATCH` |

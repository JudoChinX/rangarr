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

- [ ] `main` branch is clean (`git status` shows no uncommitted changes)
- [ ] All intended changes are merged to `main`
- [ ] `CHANGELOG.md` has a dated entry for the new version (move from `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`)
- [ ] The version follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

---

## Steps

### 1. Update CHANGELOG.md

Move the unreleased changes into a versioned section:

```diff
-## [Unreleased]
+## [Unreleased]
+
+## [X.Y.Z] - YYYY-MM-DD
```

Add the release date and ensure all notable changes are documented.

### 2. Run the Release Script

The `utils/release.sh` script handles the version bump, commit, push, and tagging in one step:

```bash
./utils/release.sh
```

It will prompt for the version, validate pre-flight checks, show a diff of the `pyproject.toml` change, and ask for confirmation before proceeding.

**What the script does:**
1. Validates the version format (`MAJOR.MINOR.PATCH`)
2. Confirms you are on `main` with a clean working tree
3. Confirms the version is new and not already tagged
4. Confirms a `CHANGELOG.md` entry exists for the version
5. Bumps the version in `pyproject.toml`
6. Commits and pushes to `main`
7. Creates and pushes the `v*` tag

The tag push triggers the CI release pipeline.

> **Note:** If you prefer to run steps manually:
> ```bash
> git add CHANGELOG.md pyproject.toml
> git commit -m "new: Rangarr vX.Y.Z release."
> git push origin main
> git tag vX.Y.Z
> git push origin vX.Y.Z
> ```

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

---
title: Release Script Design
date: 2026-03-26
status: approved
---

# Release Script Design

## Overview

A bash script at `utils/release.sh` that automates the Rangarr release process. It prompts interactively for a version, runs pre-flight checks, updates `pyproject.toml`, commits, tags, and pushes — aborting with a clear error at any failure point.

## Behavior

### Invocation

```bash
./utils/release.sh
```

No arguments. The script prompts for the version interactively.

### Shebang

```bash
#!/usr/bin/env bash
set -euo pipefail
```

`-u` ensures unbound variables abort rather than silently expanding to empty strings. `-o pipefail` ensures failures in piped commands are not swallowed.

### Step-by-Step Flow

1. **Prompt for version** — asks `Release version (e.g. 0.3.0):` and validates input matches `MAJOR.MINOR.PATCH` (digits only, no `v` prefix)
2. **Pre-flight checks** — run in order; abort with a descriptive error message on first failure:
   - `origin` remote exists (`git remote get-url origin`)
   - Current branch is `main`
   - Working tree is clean (`git status --porcelain` is empty)
   - Entered version differs from the current version in `pyproject.toml`
   - Tag `vX.Y.Z` does not already exist locally (`git tag`) or remotely (`git ls-remote --tags origin`)
   - `CHANGELOG.md` contains a line starting with `## [X.Y.Z]` (grep anchored to start of line: `^## \[X\.Y\.Z\]`)
3. **Update `pyproject.toml`** — replace the `version = "..."` field using `sed`, replacing only the first occurrence to avoid touching unrelated version-like fields in tool sections. The sed interpolation is safe because `$VERSION` has already been validated to match `^[0-9]+\.[0-9]+\.[0-9]+$` in Step 1:
   ```bash
   sed -i '0,/^version = ".*"$/s//version = "'"$VERSION"'"/' pyproject.toml
   ```
4. **Show diff** — print `git diff pyproject.toml` so the user can confirm the change
5. **Confirm** — prompt `Proceed with commit, tag, and push? [y/N]`; exit cleanly (code 0) on anything other than `y`
6. **Commit** — `git add pyproject.toml` then `git commit -m "new: Rangarr vX.Y.Z release."`
7. **Push commit** — `git push origin main`
8. **Tag** — `git tag vX.Y.Z`
9. **Push tag** — `git push origin vX.Y.Z`
10. **Done** — print: `Released: vX.Y.Z`

### Error Handling

- Any failed command exits immediately (`set -euo pipefail`)
- Pre-flight failures print a descriptive message explaining what to fix before re-running
- Failures in Steps 7–9 (after the commit has been pushed) print a message directing the user to `docs/runbook-release.md`, since re-running the script will be blocked by the "version differs from current" pre-flight check
- User declining the confirmation prompt exits with code 0 (not an error)

## Files

| Path | Purpose |
|------|---------|
| `utils/release.sh` | The new release script |
| `utils/setup.sh` | Moved from root |
| `utils/pre-push.sh` | Moved from root |

Existing references to `setup.sh` and `pre-push.sh` must be updated:

- `utils/setup.sh` line 3: update path from `pre-push.sh` to `utils/pre-push.sh`
- `CONTRIBUTING.md`: update link from `pre-push.sh` to `utils/pre-push.sh`
- `docs/user-guide.md`: update invocation from `./setup.sh` to `./utils/setup.sh`

## Out of Scope

- Updating `CHANGELOG.md` — done manually before running the script
- Dry-run mode
- Rollback of partially completed steps — see `docs/runbook-release.md`

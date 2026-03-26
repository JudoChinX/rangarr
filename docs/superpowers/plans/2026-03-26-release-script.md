# Release Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move existing shell scripts to `utils/`, update all references, and write `utils/release.sh` that automates the Rangarr release process.

**Architecture:** Two independent tasks — (1) reorganise existing scripts into `utils/` and patch references, (2) write the new release script. The release script runs top-to-bottom with pre-flight checks, a `pyproject.toml` bump, a confirmation prompt, then commit/tag/push.

**Tech Stack:** Bash (`#!/usr/bin/env bash`, `set -euo pipefail`), git, sed

---

## File Map

| Action | Path | Change |
|--------|------|--------|
| Move | `pre-push.sh` → `utils/pre-push.sh` | No content change |
| Move | `setup.sh` → `utils/setup.sh` | Update path on line 3 |
| Create | `utils/release.sh` | New release script |
| Modify | `CONTRIBUTING.md:40` | Update link to `utils/pre-push.sh` |
| Modify | `docs/user-guide.md:620` | Update invocation to `./utils/setup.sh` |

---

## Task 1: Move existing scripts to utils/ and update references

**Files:**
- Create: `utils/pre-push.sh` (moved from `pre-push.sh`)
- Create: `utils/setup.sh` (moved from `setup.sh`)
- Modify: `CONTRIBUTING.md`
- Modify: `docs/user-guide.md`

- [ ] **Step 1: Create utils/ and move the scripts**

```bash
mkdir utils
git mv pre-push.sh utils/pre-push.sh
git mv setup.sh utils/setup.sh
```

- [ ] **Step 2: Update the path in utils/setup.sh**

Change line 3 from `cp pre-push.sh .git/hooks/pre-push` to `cp utils/pre-push.sh .git/hooks/pre-push`.

`utils/setup.sh` should read:

```bash
#!/bin/bash

cp utils/pre-push.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push
echo "pre-push hook installed successfully!"
```

- [ ] **Step 3: Update CONTRIBUTING.md**

On line 40, change:
```
All pushes automatically run pre-push hooks (see [pre-push.sh](pre-push.sh)) that enforce:
```
to:
```
All pushes automatically run pre-push hooks (see [pre-push.sh](utils/pre-push.sh)) that enforce:
```

- [ ] **Step 4: Update docs/user-guide.md**

On line 620, change:
```
   ./setup.sh
```
to:
```
   ./utils/setup.sh
```

- [ ] **Step 5: Verify syntax of both moved scripts**

```bash
bash -n utils/pre-push.sh && echo "pre-push.sh: OK"
bash -n utils/setup.sh && echo "setup.sh: OK"
```

Expected: both print `OK` with no errors.

- [ ] **Step 6: Commit**

```bash
git add utils/pre-push.sh utils/setup.sh CONTRIBUTING.md docs/user-guide.md
git commit -m "refactor: move shell scripts to utils/"
```

---

## Task 2: Write utils/release.sh

**Files:**
- Create: `utils/release.sh`

- [ ] **Step 1: Write the script**

Create `utils/release.sh` with the following content:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── helpers ────────────────────────────────────────────────────────────────────
abort() { echo "ERROR: $1" >&2; exit 1; }
runbook_hint() { echo "See docs/runbook-release.md for recovery steps." >&2; }

# ── prompt for version ─────────────────────────────────────────────────────────
read -rp "Release version (e.g. 0.3.0): " VERSION

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  abort "Version must match MAJOR.MINOR.PATCH (e.g. 0.3.0). Got: $VERSION"
fi

# ── pre-flight checks ──────────────────────────────────────────────────────────
git remote get-url origin > /dev/null 2>&1 \
  || abort "'origin' remote not found."

BRANCH=$(git rev-parse --abbrev-ref HEAD)
[[ "$BRANCH" == "main" ]] \
  || abort "Must be on 'main' branch. Currently on: $BRANCH"

[[ -z "$(git status --porcelain)" ]] \
  || abort "Working tree is not clean. Commit or stash changes first."

CURRENT_VERSION=$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "//;s/"//')
[[ "$VERSION" != "$CURRENT_VERSION" ]] \
  || abort "Version $VERSION is already the current version in pyproject.toml."

if git tag | grep -q "^v${VERSION}$"; then
  abort "Tag v${VERSION} already exists locally."
fi
if git ls-remote --tags origin | grep -q "refs/tags/v${VERSION}$"; then
  abort "Tag v${VERSION} already exists on remote."
fi

grep -q "^## \[${VERSION}\]" CHANGELOG.md \
  || abort "No '## [${VERSION}]' entry found in CHANGELOG.md. Add a changelog entry before releasing."

# ── update pyproject.toml ──────────────────────────────────────────────────────
sed -i '0,/^version = ".*"$/s//version = "'"$VERSION"'"/' pyproject.toml

echo ""
echo "Changes to pyproject.toml:"
git diff pyproject.toml

# ── confirm ────────────────────────────────────────────────────────────────────
echo ""
read -rp "Proceed with commit, tag, and push? [y/N] " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  git checkout pyproject.toml
  echo "Aborted."
  exit 0
fi

# ── commit ─────────────────────────────────────────────────────────────────────
git add pyproject.toml
git commit -m "new: Rangarr v${VERSION} release."

# ── push commit ────────────────────────────────────────────────────────────────
git push origin main || { runbook_hint; exit 1; }

# ── tag and push tag ───────────────────────────────────────────────────────────
git tag "v${VERSION}"
git push origin "v${VERSION}" || { runbook_hint; exit 1; }

echo ""
echo "Released: v${VERSION}"
```

- [ ] **Step 2: Make the script executable**

```bash
chmod +x utils/release.sh
```

- [ ] **Step 3: Verify syntax**

```bash
bash -n utils/release.sh && echo "release.sh: OK"
```

Expected: prints `OK` with no errors.

- [ ] **Step 4: Commit**

```bash
git add utils/release.sh
git commit -m "feat: add utils/release.sh release automation script"
```

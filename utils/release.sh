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
sed -i "0,/^version = \".*\"$/s||version = \"${VERSION}\"|" pyproject.toml

echo ""
echo "Changes to pyproject.toml:"
git diff pyproject.toml

# ── confirm ────────────────────────────────────────────────────────────────────
echo ""
read -rp "Proceed with commit, tag, and push? [y/N] " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  git checkout pyproject.toml || echo "WARNING: Could not restore pyproject.toml; run 'git checkout pyproject.toml' manually." >&2
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
git push origin "v${VERSION}" || {
  echo "ERROR: Commit is on origin/main but tag v${VERSION} was not pushed." >&2
  runbook_hint
  exit 1
}

echo ""
echo "Released: v${VERSION}"

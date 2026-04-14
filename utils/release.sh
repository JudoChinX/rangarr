#!/usr/bin/env bash
set -euo pipefail

# ── helpers ────────────────────────────────────────────────────────────────────
abort() { echo "ERROR: $1" >&2; exit 1; }
runbook_hint() { echo "See docs/runbook-release.md for recovery steps." >&2; }

# ── prompt for version ─────────────────────────────────────────────────────────
read -rp "Release version (e.g. 0.5.0): " VERSION

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  abort "Version must match MAJOR.MINOR.PATCH (e.g. 0.5.0). Got: $VERSION"
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

# ── create release branch ──────────────────────────────────────────────────────
RELEASE_BRANCH="release-v${VERSION}"
git checkout -b "$RELEASE_BRANCH"

# ── bump version in pyproject.toml ────────────────────────────────────────────
sed -i "0,/^version = \".*\"$/s||version = \"${VERSION}\"|" pyproject.toml

echo ""
echo "Release branch '$RELEASE_BRANCH' created and version bumped to $VERSION."
echo ""
echo "Before continuing, complete these manual steps:"
echo "  1. Update CHANGELOG.md — move [Unreleased] entries into a [${VERSION}] section and leave [Unreleased] empty."
echo "  2. Review docs/user-guide.md, docs/technical-audit.md, and config.example.yaml for accuracy."
echo ""
read -rp "Press Enter when done (or Ctrl-C to abort)..."

# ── validate changelog ─────────────────────────────────────────────────────────
grep -q "^## \[${VERSION}\]" CHANGELOG.md \
  || abort "No '## [${VERSION}]' entry found in CHANGELOG.md."

UNRELEASED_CONTENT=$(awk '/^## \[Unreleased\]/{found=1; next} found && /^## \[/{exit} found{print}' CHANGELOG.md | grep -v '^[[:space:]]*$' || true)
[[ -z "$UNRELEASED_CONTENT" ]] \
  || abort "[Unreleased] section in CHANGELOG.md still has content. Move all entries into [${VERSION}] before releasing."

# ── show diff and confirm ──────────────────────────────────────────────────────
echo ""
echo "Changes to commit:"
git diff
echo ""
read -rp "Proceed with commit and push? [y/N] " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  git checkout pyproject.toml CHANGELOG.md 2>/dev/null || true
  git checkout main
  git branch -D "$RELEASE_BRANCH"
  echo "Aborted."
  exit 0
fi

# ── commit and push release branch ────────────────────────────────────────────
git add CHANGELOG.md pyproject.toml
git commit -m "new: Rangarr v${VERSION} release."
git push -u origin "$RELEASE_BRANCH" || { runbook_hint; exit 1; }

echo ""
echo "Release branch pushed. Next steps:"
echo "  1. Open a PR: gh pr create --base main --head $RELEASE_BRANCH --title 'new: Rangarr v${VERSION} release.'"
echo "  2. After the PR merges, tag main:"
echo "       git fetch origin"
echo "       git tag v${VERSION} origin/main"
echo "       git push origin v${VERSION}"

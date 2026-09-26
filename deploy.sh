#!/bin/bash
# Deploy script: merges develop → main in two commits (code + build),
# tags the build commit with a timestamp version, then pushes.
set -e

cd "$(dirname "$0")"

# ── Guards ────────────────────────────────────────────────────────────────────
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "develop" ]; then
  echo "Error: must be on develop (currently on $BRANCH)" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Error: working tree is dirty — commit or stash changes first" >&2
  git status --short
  exit 1
fi

PENDING=$(git log main..develop --oneline)
if [ -z "$PENDING" ]; then
  echo "Nothing to deploy — develop is already merged into main."
  exit 0
fi

# ── Preview ───────────────────────────────────────────────────────────────────
echo "Commits to deploy:"
echo "$PENDING"
echo ""
read -p "Deploy to main? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

# ── Step 1: Merge code changes → main ────────────────────────────────────────
echo ""
echo "==> [1/4] Merging code changes: develop → main..."
git checkout main
git merge develop --no-ff -m "$(cat <<EOF
Merge develop: code changes

$(git log main..develop --oneline)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git checkout develop

# ── Step 2: Run static build on develop ──────────────────────────────────────
echo ""
echo "==> [2/4] Building static files..."
python3 generate.py

# ── Step 3: Commit + tag the build on develop ────────────────────────────────
VERSION="build-$(date +%Y%m%d-%H%M%S)"
echo ""
echo "==> [3/4] Committing build as $VERSION..."
git add static/
git commit -m "build: $VERSION

Static site generated from current develop.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git tag "$VERSION"

# ── Step 4: Merge build commit → main, push, clean up ────────────────────────
echo ""
echo "==> [4/4] Merging build → main and pushing..."
git checkout main
git merge develop --no-ff -m "build: $VERSION

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
git push origin "$VERSION"

git checkout develop

echo ""
echo "✓ Deployed $VERSION — Cloudflare build triggered."

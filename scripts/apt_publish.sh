#!/usr/bin/env bash
# Publish the .deb to the APT repository (the gh-pages branch) with plain git.
#
#   export APT_KEY=<your signing key fingerprint>
#   bash scripts/apt_publish.sh [path/to/file.deb ...]       (default: dist/release/*.deb)
#
# Optional environment:
#   REMOTE=...          default git@github.com:iqbalsound/mailpilot.git  (SSH)
#   GPG_PASSPHRASE=...  only if your signing key has a passphrase
#   NO_PUSH=1           build and commit locally, do not push (for testing)
set -euo pipefail

# resolve any .deb arguments to absolute paths BEFORE changing directory
ARGS=()
for a in "$@"; do ARGS+=("$(cd "$(dirname "$a")" && pwd)/$(basename "$a")"); done
cd "$(dirname "$0")/.."

REMOTE="${REMOTE:-git@github.com:iqbalsound/mailpilot.git}"
BRANCH="gh-pages"
SITE="build/apt-site"
KEY="${APT_KEY:-}"
[ -n "$KEY" ] || { echo "Set APT_KEY to your signing key fingerprint (gpg --list-secret-keys --keyid-format long)."; exit 1; }

if [ "${#ARGS[@]}" -gt 0 ]; then DEBS=("${ARGS[@]}"); else DEBS=(dist/release/*.deb); fi
[ -f "${DEBS[0]}" ] || { echo "No .deb found. Build it first (python scripts/build.py; bash packaging/build_deb.sh)."; exit 1; }

rm -rf "$SITE"; mkdir -p build
if git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
  git clone --quiet --branch "$BRANCH" --single-branch "$REMOTE" "$SITE"
else
  echo "Branch $BRANCH does not exist yet: creating it."
  mkdir -p "$SITE"
  git -C "$SITE" init -q -b "$BRANCH"
  git -C "$SITE" remote add origin "$REMOTE"
fi

python3 scripts/apt_repo.py "$SITE" "${DEBS[@]}" --key "$KEY"

cd "$SITE"
git config user.name  "$(git -C .. config user.name  2>/dev/null || echo 'Mailpilot release')"
git config user.email "$(git -C .. config user.email 2>/dev/null || echo 'iqbalsound@yahoo.com')"
git add -A
if git diff --cached --quiet; then
  echo "Repository is already up to date."
else
  git commit -q -m "apt: publish $(basename "${DEBS[0]}")"
  if [ "${NO_PUSH:-0}" = "1" ]; then
    echo "NO_PUSH=1: committed locally in $SITE, not pushed."
  else
    git push -u origin "$BRANCH"
    echo "Published. Enable GitHub Pages once: Settings > Pages > Deploy from branch > gh-pages > / (root)."
  fi
fi

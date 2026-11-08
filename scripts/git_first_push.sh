#!/usr/bin/env bash
# First commit + push to GitHub over SSH. Uses plain git only (no gh).
# Usage:  bash scripts/git_first_push.sh ["commit message"]
# Safe test (no network, no push):  DRY_RUN=1 bash scripts/git_first_push.sh
set -euo pipefail
cd "$(dirname "$0")/.."

REMOTE="git@github.com:iqbalsound/mailpilot.git"
BRANCH="main"
MSG="${1:-feat: Mailpilot 1.0.0 initial release}"

command -v git >/dev/null || { echo "git is not installed."; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || git init -b "$BRANCH"

if [ -z "$(git config user.name || true)" ] || [ -z "$(git config user.email || true)" ]; then
  echo "Set your git identity first:"
  echo '  git config --global user.name  "Iqbal Uddin Khan"'
  echo '  git config --global user.email "iqbalsound@yahoo.com"'
  exit 1
fi

git add -A

# --- safety checks before anything is committed ---
bad="$(git diff --cached --name-only | grep -E '(^|/)(\.venv|dist|build|__pycache__)/|(^|/)\.env|\.pem$|\.key$|id_(rsa|ed25519)|(^|/)(accounts|settings)\.json$' || true)"
if [ -n "$bad" ]; then
  echo "Refusing to commit these files:"; echo "$bad"; exit 1
fi
if git diff --cached -U0 | grep -E '^\+.*(sk-ant-[A-Za-z0-9_-]{10,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' >/dev/null; then
  echo "Something that looks like a secret key is staged. Remove it and try again."; exit 1
fi

if git diff --cached --quiet; then
  echo "Nothing new to commit."
else
  git commit -m "$MSG"
fi

if git remote get-url origin >/dev/null 2>&1; then
  [ "$(git remote get-url origin)" = "$REMOTE" ] || echo "Note: origin is $(git remote get-url origin), not $REMOTE"
else
  git remote add origin "$REMOTE"
fi

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "[dry run] checks passed; would run: git push -u origin $BRANCH"
  exit 0
fi

echo "Testing SSH access to GitHub..."
if ! ssh -o BatchMode=yes -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo "SSH to GitHub failed. Follow the SSH key steps in docs/GUIDE.md (step 9), then run again."
  exit 1
fi
git push -u origin "$BRANCH"
echo "Pushed. Next: tag a release (see docs/GUIDE.md step 11)."

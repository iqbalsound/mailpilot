#!/usr/bin/env bash
# Mailpilot project scaffold
# Creates the folder tree and BLANK files with the right extensions.
# Safe to re-run: existing files are never overwritten or emptied.
#
# Usage:   bash scaffold.sh            -> creates ./mailpilot
#          bash scaffold.sh my-folder  -> creates ./my-folder
set -euo pipefail

ROOT="${1:-mailpilot}"

DIRS=(
  "src/mailpilot/data"
  "tests"
  "scripts"
  "packaging"
  "docs"
  ".github/workflows"
)

FILES=(
  # --- project root ---
  "README.md"
  "LICENSE"
  ".gitignore"
  "requirements.txt"
  "requirements-dev.txt"
  "pyproject.toml"
  "launcher.py"
  # --- application package ---
  "src/mailpilot/__init__.py"
  "src/mailpilot/__main__.py"
  "src/mailpilot/meta.py"
  "src/mailpilot/paths.py"
  "src/mailpilot/settings.py"
  "src/mailpilot/secrets_store.py"
  "src/mailpilot/accounts.py"
  "src/mailpilot/mailcore.py"
  "src/mailpilot/editor_html.py"
  "src/mailpilot/theme.py"
  "src/mailpilot/ai.py"
  "src/mailpilot/app.py"
  "src/mailpilot/dialogs.py"
  "src/mailpilot/data/providers.json"   # (icon.png is binary: copy it in yourself)
  # --- tests ---
  "tests/__init__.py"
  "tests/test_core.py"
  # --- scripts ---
  "scripts/setup.sh"
  "scripts/setup.ps1"
  "scripts/build.py"
  "scripts/git_first_push.sh"
  # --- packaging ---
  "packaging/build_deb.sh"
  "packaging/mailpilot.desktop"
  # --- docs ---
  "docs/GUIDE.md"
  "docs/TESTS.md"
  # --- CI / release ---
  ".github/workflows/release.yml"
)

mkdir -p "$ROOT"
cd "$ROOT"

for d in "${DIRS[@]}"; do
  mkdir -p "$d"
done

created=0; kept=0
for f in "${FILES[@]}"; do
  if [ -e "$f" ]; then
    kept=$((kept + 1))
  else
    : > "$f"                      # create an empty file
    created=$((created + 1))
  fi
done

chmod +x scripts/*.sh packaging/*.sh 2>/dev/null || true

echo "Scaffold ready in: $(pwd)"
echo "  directories ensured : ${#DIRS[@]}"
echo "  blank files created : $created"
echo "  existing files kept : $kept"

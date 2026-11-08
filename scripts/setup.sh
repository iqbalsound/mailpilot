#!/usr/bin/env bash
# Create the virtual environment, install dependencies and run the tests.
# Usage: bash scripts/setup.sh        (Linux / macOS / Git Bash)
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || { echo "Python 3.10 or newer is required."; exit 1; }
"$PY" -c 'import tkinter' 2>/dev/null || {
  echo "Tkinter is missing."
  echo "  Debian/Ubuntu: sudo apt install python3-tk"
  echo "  Fedora:        sudo dnf install python3-tkinter"
  exit 1; }

"$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -m unittest -v

echo
echo "Setup finished."
echo "  Activate : source .venv/bin/activate"
echo "  Run      : python -m mailpilot      (or: python launcher.py)"

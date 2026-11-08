"""Entry script for PyInstaller and for running from a source checkout."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from mailpilot.__main__ import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())

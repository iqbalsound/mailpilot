"""Where Mailpilot keeps its files."""
import os
import sys
from pathlib import Path

from .meta import APP_ID


def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / APP_ID
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource(name: str) -> Path:
    """Path to a file in the package's data folder (works from source and PyInstaller)."""
    return Path(__file__).resolve().parent / "data" / name

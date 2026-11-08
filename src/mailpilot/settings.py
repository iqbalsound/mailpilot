"""Non-secret user settings, stored as JSON in the user's config folder."""
import json
import os
from pathlib import Path

from .paths import config_dir

DEFAULTS = {
    "theme": "system",          # system | light | dark
    "page_size": 50,
    "ai_enabled": False,
    "ai_provider": "anthropic",  # anthropic | gemini
    "ai_model": "",              # paste the current model ID from the provider docs
    "ai_temperature": 0.3,
    "ai_signature": "",          # name used to sign AI drafts
    "last_account": "",
}


def _path() -> Path:
    return config_dir() / "settings.json"


def write_json_private(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict) -> None:
    write_json_private(_path(), s)

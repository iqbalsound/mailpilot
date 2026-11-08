"""Passwords and API keys.

They are saved in the operating system's keyring when the optional `keyring`
package and a working backend exist. Otherwise they are kept in memory for the
current session only. Secrets are never written to Mailpilot's JSON files.
"""
from .meta import APP_ID

try:
    import keyring  # type: ignore
except Exception:  # package missing or broken
    keyring = None

_mem: dict = {}


def set_secret(name: str, value: str) -> bool:
    """Store a secret. Returns True if it was saved persistently (keyring)."""
    _mem[name] = value
    if keyring is not None:
        try:
            keyring.set_password(APP_ID, name, value)
            return True
        except Exception:
            return False
    return False


def get_secret(name: str):
    if name in _mem:
        return _mem[name]
    if keyring is not None:
        try:
            v = keyring.get_password(APP_ID, name)
            if v:
                _mem[name] = v
            return v
        except Exception:
            return None
    return None


def delete_secret(name: str) -> None:
    _mem.pop(name, None)
    if keyring is not None:
        try:
            keyring.delete_password(APP_ID, name)
        except Exception:
            pass

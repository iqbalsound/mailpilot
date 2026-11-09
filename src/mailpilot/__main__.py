"""Entry point: python -m mailpilot"""
import sys


def selftest() -> int:
    """Check that everything the app needs is present (used by CI on the built executables)."""
    problems = []
    try:
        import tkinter  # noqa: F401
    except Exception as e:
        problems.append(f"tkinter missing: {e}")
    try:
        from .accounts import load_providers
        if not load_providers():
            problems.append("providers.json is empty")
    except Exception as e:
        problems.append(f"providers.json not readable: {e}")
    try:
        from .paths import resource
        if not resource("icon.png").is_file():
            problems.append("icon.png not bundled")
    except Exception as e:
        problems.append(f"icon.png: {e}")
    if not problems:
        try:
            from . import app, dialogs  # noqa: F401
        except Exception as e:
            problems.append(f"GUI modules failed to import: {e}")
    for p in problems:
        print("FAIL:", p)
    if not problems:
        print("selftest ok")
    return 1 if problems else 0


def run() -> int:
    if "--version" in sys.argv:
        from .meta import APP_NAME, APP_VERSION
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    if "--selftest" in sys.argv:
        return selftest()
    from .app import main   # imported late so --version works without Tk
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run())

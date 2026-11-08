"""Entry point: python -m mailpilot"""
import sys


def run() -> int:
    if "--version" in sys.argv:
        from .meta import APP_NAME, APP_VERSION
        print(f"{APP_NAME} {APP_VERSION}")
        return 0
    from .app import main   # imported late so --version works without Tk
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run())

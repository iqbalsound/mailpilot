"""Build the single-file app with PyInstaller (run inside the virtual environment).

    python scripts/build.py

Output:  dist/mailpilot            (Linux)   or   dist/mailpilot.exe   (Windows)
         dist/release/mailpilot-<version>-<os>-x86_64[.exe]   (the file to publish)
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from mailpilot.meta import APP_ID, APP_VERSION  # noqa: E402

is_win = sys.platform.startswith("win")
sep = os.pathsep                                   # ';' on Windows, ':' elsewhere
data = ROOT / "src" / "mailpilot" / "data"

cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", APP_ID,
    "--paths", str(ROOT / "src"),
    "--add-data", f"{data}{sep}mailpilot/data",
    "--collect-submodules", "keyring",
    "--copy-metadata", "keyring",
]
ico = ROOT / "packaging" / "mailpilot.ico"
if is_win and ico.exists():
    cmd += ["--icon", str(ico)]
cmd.append(str(ROOT / "launcher.py"))

print("Running:", " ".join(cmd))
subprocess.run(cmd, check=True, cwd=ROOT)

exe = ROOT / "dist" / (APP_ID + (".exe" if is_win else ""))
if not exe.exists():
    sys.exit(f"Build finished but {exe} was not found.")
osname = "windows" if is_win else ("macos" if sys.platform == "darwin" else "linux")
arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
rel = ROOT / "dist" / "release"
rel.mkdir(parents=True, exist_ok=True)
target = rel / f"{APP_ID}-{APP_VERSION}-{osname}-{arch}{'.exe' if is_win else ''}"
shutil.copy2(exe, target)
print(f"\nBuilt: {exe}\nRelease copy: {target}")

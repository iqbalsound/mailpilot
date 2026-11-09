#!/usr/bin/env python3
"""Build or update a signed APT repository (static files, ready for GitHub Pages).

    python scripts/apt_repo.py SITE_DIR path/to/mailpilot_1.0.0_amd64.deb [more.deb ...] --key FINGERPRINT

Needs: python3, dpkg-deb, gpg.  Optional env: GPG_PASSPHRASE (if the signing key has one).
Older .deb files already in SITE_DIR/pool are kept, so every release stays installable.

Result inside SITE_DIR:
    pool/main/m/mailpilot/*.deb
    dists/stable/main/binary-<arch>/Packages(.gz)
    dists/stable/Release  Release.gpg  InRelease
    mailpilot-archive-keyring.gpg  mailpilot-archive-keyring.asc   (public key for users)
    index.html  .nojekyll
"""
import argparse
import email.utils
import gzip
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

SUITE = "stable"
COMPONENT = "main"
POOL = Path("pool") / COMPONENT / "m" / "mailpilot"
KEY_NAME = "mailpilot-archive-keyring"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, **kw)


def control_fields(deb: Path) -> str:
    return run(["dpkg-deb", "-f", str(deb)], capture_output=True).stdout.rstrip("\n")


def field(control: str, name: str) -> str:
    for line in control.splitlines():
        if line.lower().startswith(name.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def hashes(path: Path):
    data = path.read_bytes()
    return (hashlib.md5(data).hexdigest(), hashlib.sha1(data).hexdigest(),
            hashlib.sha256(data).hexdigest(), len(data))


def vkey(version: str):
    # good enough for ordering stanzas; apt itself does the real version comparison
    return [int(p) if p.isdigit() else p for p in version.replace("-", ".").replace("~", ".").split(".")]


def build_packages(site: Path):
    by_arch = {}
    for deb in sorted((site / POOL).glob("*.deb")):
        ctl = control_fields(deb)
        md5, sha1, sha256, size = hashes(deb)
        stanza = (f"{ctl}\nFilename: {deb.relative_to(site).as_posix()}\nSize: {size}\n"
                  f"MD5sum: {md5}\nSHA1: {sha1}\nSHA256: {sha256}\n")
        by_arch.setdefault(field(ctl, "Architecture"), []).append(
            (field(ctl, "Package"), vkey(field(ctl, "Version")), stanza))
    files = []
    for arch, items in by_arch.items():
        items.sort(key=lambda t: (t[0], t[1]))
        d = site / "dists" / SUITE / COMPONENT / f"binary-{arch}"
        d.mkdir(parents=True, exist_ok=True)
        text = "\n".join(s for _, _, s in items)
        (d / "Packages").write_text(text, encoding="utf-8")
        with gzip.GzipFile(d / "Packages.gz", "wb", mtime=0) as gz:
            gz.write(text.encode("utf-8"))
        files += [d / "Packages", d / "Packages.gz"]
    return sorted(by_arch), files


def write_release(site: Path, archs, files):
    base = site / "dists" / SUITE
    lines = ["Origin: Mailpilot", "Label: Mailpilot", f"Suite: {SUITE}", f"Codename: {SUITE}",
             f"Date: {email.utils.formatdate(usegmt=True)}",
             f"Architectures: {' '.join(archs)}", f"Components: {COMPONENT}",
             "Description: Mailpilot APT repository"]
    for label, idx in (("MD5Sum", 0), ("SHA1", 1), ("SHA256", 2)):
        lines.append(f"{label}:")
        for f in files:
            h = hashes(f)
            lines.append(f" {h[idx]} {h[3]:>16} {f.relative_to(base).as_posix()}")
    (base / "Release").write_text("\n".join(lines) + "\n", encoding="utf-8")


def gpg_base(key: str):
    cmd = ["gpg", "--batch", "--yes", "--default-key", key]
    if os.environ.get("GPG_PASSPHRASE"):
        cmd += ["--pinentry-mode", "loopback", "--passphrase-fd", "0"]
    return cmd


def sign(site: Path, key: str):
    base = site / "dists" / SUITE
    rel = base / "Release"
    stdin = (os.environ.get("GPG_PASSPHRASE") or "") + "\n" if os.environ.get("GPG_PASSPHRASE") else None
    for out in ("InRelease", "Release.gpg"):
        p = base / out
        if p.exists():
            p.unlink()
    run(gpg_base(key) + ["--clearsign", "-o", str(base / "InRelease"), str(rel)], input=stdin)
    run(gpg_base(key) + ["--armor", "--detach-sign", "-o", str(base / "Release.gpg"), str(rel)], input=stdin)


def export_keys(site: Path, key: str):
    (site / f"{KEY_NAME}.gpg").write_bytes(
        subprocess.run(["gpg", "--export", key], check=True, capture_output=True).stdout)
    (site / f"{KEY_NAME}.asc").write_text(
        run(["gpg", "--armor", "--export", key], capture_output=True).stdout)


INDEX = """<!doctype html><meta charset="utf-8"><title>Mailpilot APT repository</title>
<body style="font-family:sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem">
<h1>Mailpilot APT repository</h1>
<p>Debian / Ubuntu (amd64). Install:</p>
<pre>sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL {url}/{key}.gpg | sudo tee /etc/apt/keyrings/mailpilot.gpg &gt;/dev/null
echo "deb [signed-by=/etc/apt/keyrings/mailpilot.gpg] {url} stable main" | sudo tee /etc/apt/sources.list.d/mailpilot.list
sudo apt update &amp;&amp; sudo apt install mailpilot</pre>
<p>Source: <a href="https://github.com/iqbalsound/mailpilot">github.com/iqbalsound/mailpilot</a></p>
</body>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("debs", nargs="*")
    ap.add_argument("--key", required=True, help="GPG key fingerprint or e-mail used to sign")
    ap.add_argument("--url", default="https://iqbalsound.github.io/mailpilot")
    a = ap.parse_args()
    site = Path(a.site).resolve()
    (site / POOL).mkdir(parents=True, exist_ok=True)
    for d in a.debs:
        src = Path(d)
        if src.suffix != ".deb" or not src.is_file():
            sys.exit(f"Not a .deb file: {d}")
        shutil.copy2(src, site / POOL / src.name)
    if not list((site / POOL).glob("*.deb")):
        sys.exit("No .deb files in the pool: nothing to publish.")
    archs, files = build_packages(site)
    write_release(site, archs, files)
    sign(site, a.key)
    export_keys(site, a.key)
    (site / "index.html").write_text(INDEX.format(url=a.url, key=KEY_NAME), encoding="utf-8")
    (site / ".nojekyll").write_text("")
    print(f"Repository updated in {site}  (architectures: {', '.join(archs)})")


if __name__ == "__main__":
    main()

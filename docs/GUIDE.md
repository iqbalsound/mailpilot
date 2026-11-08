# Mailpilot: build, test, publish and release (Git over SSH, no `gh`)

Everything below is typed in a terminal. Linux/macOS use bash; Windows users use **Git Bash**
for Git steps and PowerShell for Python steps (or Git Bash for both).

Project facts live in one file, `src/mailpilot/meta.py` (name, version, author, GitHub URLs, copyright).
Change the version there only.

---
## 1. Prerequisites

| Need | Check | Install |
|------|-------|---------|
| Python 3.10+ | `python3 --version` | python.org / `sudo apt install python3 python3-venv` |
| Tkinter | `python3 -c "import tkinter"` | Debian/Ubuntu `sudo apt install python3-tk` · Fedora `sudo dnf install python3-tkinter` · Windows: tick "tcl/tk and IDLE" in the Python installer |
| Git | `git --version` | `sudo apt install git` / git-scm.com |
| `dpkg-deb` (only to build the .deb) | `dpkg-deb --version` | present on Debian/Ubuntu |

## 2. Get the project folder

**A. From the zip (ready to run):**
```bash
unzip mailpilot.zip
cd mailpilot
```

**B. Start blank with the scaffold script** (creates the folders and empty files with the right
extensions; safe to re-run, it never overwrites):
```bash
bash scaffold.sh              # creates ./mailpilot
cd mailpilot
```
Then fill the files (or copy them from the zip). `scripts/scaffold.sh` is the same script.

## 3. Create the virtual environment

Linux / macOS:
```bash
bash scripts/setup.sh         # makes .venv, installs requirements-dev.txt, runs the tests
source .venv/bin/activate
```
Windows PowerShell:
```powershell
.\scripts\setup.ps1           # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```
Manual equivalent:
```bash
python3 -m venv .venv
source .venv/bin/activate           # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```
After the first successful build you may run `pip freeze > requirements.lock` to record exact versions.

## 4. Run

```bash
python -m mailpilot            # or: python launcher.py
python -m mailpilot --version  # prints "Mailpilot 1.0.0" without opening a window
```

## 5. Test

```bash
python -m unittest -v          # automated: parsing, search, HTML converter, AI requests, themes…
```
Then walk through `docs/TESTS.md` by hand (the window itself can only be tested by you).

## 6. Using the app

1. **Add an account** (opens on first start). Pick a provider; servers fill in. Enter the address and your
   **app password** (Yahoo, Gmail with 2-Step Verification, iCloud, Zoho, Fastmail, AOL … create one in the
   provider's account-security page). Press **Test connection**, then **Save**.
   Outlook.com / Microsoft 365 need browser OAuth, which v1.0.0 does not have, so they cannot be used yet.
2. **Read**: pick a folder, click a message. Messages are shown as plain text; scripts never run and
   remote images are never loaded.
3. **Search** (box at the top, Enter to run):
   `from:ali  subject:"fee invoice"  unread  has:attachment  since:2026-11-01  before:2026-11-08  in:all  budget`
   Words with no prefix search the whole message. `has:attachment` is an approximation. POP3 searches sender
   and subject only.
4. **Theme**: toolbar box or View menu: System / Light / Dark. Remembered.
5. **Text colour**: in the compose window select text and press **Text colour…**; with nothing selected the
   colour applies to what you type next. **Reset colour** clears it. **B** and **I** toggle bold and italic.
   Text you do not colour carries no colour when sent, so a reader's own theme stays readable.
6. **AI draft reply** (optional): Settings → enable, choose Anthropic or Gemini, paste the **current model ID**
   from the provider's documentation and your **API key**. Open a message → **AI draft reply**. The draft opens
   in an editable compose window; nothing is sent until you press Send. If facts are missing the AI lists
   questions instead of guessing. The e-mail text is sent to the provider you chose.

Where data lives: `~/.config/mailpilot/` (Windows: `%APPDATA%\mailpilot\`): `accounts.json`, `settings.json`
(no secrets). Passwords and the API key go in your OS keyring when the `keyring` package works; otherwise
they last for the session only.

## 7. Build the executable

```bash
python scripts/build.py
```
Creates `dist/mailpilot` (Linux) or `dist/mailpilot.exe` (Windows), plus a copy named for release in
`dist/release/` (for example `mailpilot-1.0.0-linux-x86_64`). Build on each OS you want to ship for:
PyInstaller does not cross-compile.

## 8. Build the .deb (Debian / Ubuntu)

```bash
python scripts/build.py
bash packaging/build_deb.sh              # → dist/release/mailpilot_1.0.0_amd64.deb
sudo apt install ./dist/release/mailpilot_1.0.0_amd64.deb
mailpilot                                 # or start it from the applications menu
sudo apt remove mailpilot
```
An .rpm is not built by this kit. If you need one, convert the .deb with `fpm` (untested here).

## 9. Set up Git and an SSH key (once per computer)

```bash
git config --global user.name  "Iqbal Uddin Khan"
git config --global user.email "iqbalsound@yahoo.com"

ssh-keygen -t ed25519 -C "iqbalsound@yahoo.com"        # press Enter for the default path
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub                               # copy the whole line
```
On github.com: **Settings → SSH and GPG keys → New SSH key**, paste, save. Then test:
```bash
ssh -T git@github.com
# expected: "Hi iqbalsound! You've successfully authenticated, but GitHub does not provide shell access."
```
(The command exits with code 1 even when it works: that is normal.)

## 10. Create the repository and push (git only)

1. On github.com choose **New repository**: owner `iqbalsound`, name **mailpilot**, Public, and
   **do not** tick README, .gitignore or licence (the project already has them). Create it empty.
2. In the project folder, either run the helper (it refuses to commit keys, `.venv`, `dist` or config files):
   ```bash
   bash scripts/git_first_push.sh
   ```
   or do it by hand:
   ```bash
   git init -b main
   git add .
   git status                       # read the list: no .venv, dist, keys or accounts.json
   git commit -m "feat: Mailpilot 1.0.0 initial release"
   git remote add origin git@github.com:iqbalsound/mailpilot.git
   git push -u origin main
   ```
3. Open https://github.com/iqbalsound/mailpilot and check the files are there.

## 11. Tag and release (automatic builds)

The workflow `.github/workflows/release.yml` builds the Linux binary + .deb and the Windows .exe on GitHub's
servers and attaches them to a Release when you push a tag. Check that **Actions** are enabled for the repo
(Settings → Actions) and that `APP_VERSION` in `meta.py` equals the tag without the "v".

```bash
git tag -a v1.0.0 -m "Mailpilot 1.0.0"
git push origin v1.0.0
```
Watch the **Actions** tab. After a few minutes **Releases** shows v1.0.0 with:
`mailpilot_1.0.0_amd64.deb`, `mailpilot-1.0.0-linux-x86_64`, `mailpilot-1.0.0-windows-x86_64.exe`, `SHA256SUMS.txt`.
The workflow was written without being run, so the first run may need a small fix: read the log of the failing step.

## 12. Release by hand (no Actions)

Build on your own machine (steps 7-8), push the tag as above, then on github.com open
**Releases → Draft a new release**, choose tag `v1.0.0`, drag the files from `dist/release/` in, and publish.

## 13. Later versions

```bash
# 1. edit APP_VERSION in src/mailpilot/meta.py  (for example "1.0.1")
python -m unittest
git add -A
git commit -m "chore: release 1.0.1"
git push
git tag -a v1.0.1 -m "Mailpilot 1.0.1"
git push origin v1.0.1
```
Wrong tag? `git tag -d v1.0.1 && git push origin :refs/tags/v1.0.1`, fix, tag again.

## 14. Installing a release

* Debian/Ubuntu: `sudo apt install ./mailpilot_1.0.0_amd64.deb`
* Linux binary: `chmod +x mailpilot-1.0.0-linux-x86_64 && ./mailpilot-1.0.0-linux-x86_64`
* Windows: run the .exe. SmartScreen warns about an unknown publisher because the file is not code-signed.
* Verify: `sha256sum -c SHA256SUMS.txt`

## 15. Troubleshooting

| Problem | Fix |
|---------|-----|
| `No module named tkinter` | Install Tk (step 1), then recreate `.venv` |
| Passwords asked again every start | No working keyring backend. Install `keyring` and a secret service (GNOME Keyring / KWallet) |
| Yahoo/Gmail "authentication failed" | Use an **app password**, not your normal password; make sure IMAP is enabled |
| Linux binary will not start on an older distro | Build on the oldest system you support (glibc is forwards-compatible only) |
| Theme "System" shows the wrong mode on Linux | Choose Light or Dark manually |
| Antivirus flags the .exe | Common false positive for PyInstaller files; code signing removes it |
| `git push` says Permission denied (publickey) | Redo step 9; run `ssh -T git@github.com` until it greets you |
| Push rejected: remote has commits | You ticked README/licence when creating the repo. Either recreate it empty or run `git pull --rebase origin main` once |

## 16. What v1.0.0 does not do (yet)

Browser sign-in (OAuth) for Gmail/Outlook, voice search, auto-reply, deleting/moving/flagging messages,
saving drafts to the server, a local mail cache, rendered HTML (messages show as text), and GUI-level
automated tests. Plan these as separate phases once v1.0.0 is working.

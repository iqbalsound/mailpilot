# Mailpilot

A simple assignment email client with AI support.
Python 3.10+ · Tkinter · standard library only (optional `keyring`).

![license](https://img.shields.io/badge/license-MIT-blue)

**Features (v1.0.0):** IMAP and POP3 receiving, SMTP sending, built-in profiles for 11 providers,
folders and paging, text search (`from:`, `subject:`, `unread`, `since:` …), a compose editor with
**changeable text colour**, **light / dark / system themes**, safe plain-text message view
(no scripts, no remote images), optional **AI draft reply** (Anthropic Claude or Google Gemini) that you
always review and send yourself.

## Quick start

```bash
bash scripts/setup.sh            # creates .venv, installs, runs tests   (Windows: scripts\setup.ps1)
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
python -m mailpilot
```

Full step-by-step guide (build, .deb, .exe, Git over SSH, release): **[docs/GUIDE.md](docs/GUIDE.md)**
Manual test list: [docs/TESTS.md](docs/TESTS.md)

## Author

Iqbal Uddin Khan · Assistant Professor | DIT-HU -- NN Site KHI · iqbalsound@yahoo.com

© 2026 Iqbal Uddin Khan. Released under the MIT License.

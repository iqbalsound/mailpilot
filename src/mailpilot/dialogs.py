"""Tk dialogs: About, Accounts, Settings and the Compose window (with text colour)."""
import tkinter as tk
import webbrowser
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter import font as tkfont

from . import meta
from .accounts import (Account, fill_from_profile, guess_provider, load_providers,
                       supports_password_login)
from .editor_html import color_tag, dump_to_html
from .mailcore import MailError, build_message, open_receive, smtp_connect
from .secrets_store import get_secret, set_secret
from .settings import save_settings
from .theme import MODES

SECURITY = ("ssl", "starttls", "none")


def _base_dialog(win, parent, app, title, modal=True):
    win.title(title)
    win.transient(parent)
    app.theme.register(win, "window")
    if modal:
        win.after(10, win.grab_set)


def open_link(url: str) -> None:
    webbrowser.open(url)


# --------------------------------------------------------------------------
class AboutDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        _base_dialog(self, parent, app, f"About {meta.APP_NAME}")
        self.resizable(False, False)
        f = ttk.Frame(self, padding=20)
        f.pack(fill="both", expand=True)
        big = tkfont.nametofont("TkDefaultFont").copy()
        big.configure(size=18, weight="bold")
        self._big = big
        ttk.Label(f, text=f"{meta.APP_NAME}  v{meta.APP_VERSION}", font=big).pack(anchor="w")
        ttk.Label(f, text=meta.APP_DESCRIPTION, justify="left").pack(anchor="w", pady=(4, 12))
        ttk.Separator(f).pack(fill="x", pady=4)
        bold = tkfont.nametofont("TkDefaultFont").copy()
        bold.configure(weight="bold")
        self._bold = bold
        ttk.Label(f, text=meta.AUTHOR_NAME, font=bold).pack(anchor="w", pady=(8, 0))
        ttk.Label(f, text=meta.AUTHOR_TITLE).pack(anchor="w")
        mail = ttk.Label(f, text=meta.AUTHOR_EMAIL, style="Link.TLabel", cursor="hand2")
        mail.pack(anchor="w")
        mail.bind("<Button-1>", lambda e: open_link("mailto:" + meta.AUTHOR_EMAIL))
        gh = ttk.Label(f, text=meta.GITHUB_URL, style="Link.TLabel", cursor="hand2")
        gh.pack(anchor="w", pady=(0, 8))
        gh.bind("<Button-1>", lambda e: open_link(meta.GITHUB_URL))
        ttk.Separator(f).pack(fill="x", pady=4)
        ttk.Label(f, text=meta.COPYRIGHT).pack(anchor="w", pady=(8, 0))
        ttk.Label(f, text="Built with the Python standard library and Tkinter.\n"
                          "Optional: keyring (secure password storage).",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(4, 12))
        ttk.Button(f, text="Close", command=self.destroy).pack(anchor="e")
        self.bind("<Escape>", lambda e: self.destroy())


# --------------------------------------------------------------------------
class AccountDialog(tk.Toplevel):
    """Add or edit one account."""

    def __init__(self, parent, app, account: Account = None):
        super().__init__(parent)
        _base_dialog(self, parent, app, "Account")
        self.app = app
        self.providers = load_providers()
        self.editing = account is not None
        a = account or Account()
        self.v = {k: tk.StringVar(value=str(getattr(a, k))) for k in
                  ("name", "email", "username", "recv_protocol", "recv_host", "recv_port",
                   "recv_security", "smtp_host", "smtp_port", "smtp_security")}
        self.v["password"] = tk.StringVar()
        names = ["Custom server"] + [p["name"] for p in self.providers]
        self.provider_var = tk.StringVar(value="Custom server")
        for p in self.providers:
            if p["id"] == a.provider:
                self.provider_var.set(p["name"])

        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        r = 0

        def row(label, widget):
            nonlocal r
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
            widget.grid(row=r, column=1, sticky="ew", pady=3)
            r += 1

        cb = ttk.Combobox(f, textvariable=self.provider_var, values=names, state="readonly")
        cb.bind("<<ComboboxSelected>>", lambda e: self._apply_profile())
        row("Provider", cb)
        self.note = ttk.Label(f, text="", style="Muted.TLabel", wraplength=420, justify="left")
        self.note.grid(row=r, column=0, columnspan=2, sticky="w"); r += 1
        row("Display name", ttk.Entry(f, textvariable=self.v["name"]))
        em = ttk.Entry(f, textvariable=self.v["email"])
        em.bind("<FocusOut>", lambda e: self._email_changed())
        row("E-mail address", em)
        row("Username (if different)", ttk.Entry(f, textvariable=self.v["username"]))
        row("Password / app password", ttk.Entry(f, textvariable=self.v["password"], show="*"))
        ttk.Separator(f).grid(row=r, column=0, columnspan=2, sticky="ew", pady=8); r += 1
        proto = ttk.Combobox(f, textvariable=self.v["recv_protocol"], values=("imap", "pop3"), state="readonly", width=8)
        proto.bind("<<ComboboxSelected>>", lambda e: self._apply_profile())
        row("Receive with", proto)
        row("Receive server", ttk.Entry(f, textvariable=self.v["recv_host"]))
        row("Receive port", ttk.Entry(f, textvariable=self.v["recv_port"], width=8))
        row("Receive security", ttk.Combobox(f, textvariable=self.v["recv_security"], values=SECURITY, state="readonly", width=10))
        row("SMTP server", ttk.Entry(f, textvariable=self.v["smtp_host"]))
        row("SMTP port", ttk.Entry(f, textvariable=self.v["smtp_port"], width=8))
        row("SMTP security", ttk.Combobox(f, textvariable=self.v["smtp_security"], values=SECURITY, state="readonly", width=10))
        self.msg = ttk.Label(f, text="", wraplength=420, justify="left")
        self.msg.grid(row=r, column=0, columnspan=2, sticky="w", pady=(8, 0)); r += 1
        btns = ttk.Frame(f)
        btns.grid(row=r, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Test connection", command=self._test).pack(side="left", padx=4)
        ttk.Button(btns, text="Save", command=self._save).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        if self.editing:
            em.state(["disabled"])
        self._show_note()

    def _profile(self):
        for p in self.providers:
            if p["name"] == self.provider_var.get():
                return p
        return None

    def _show_note(self):
        p = self._profile()
        if not p:
            self.note.configure(text="Enter the server details from your provider or IT department.")
            return
        txt = p.get("notes", "")
        if not supports_password_login(p):
            txt += ("\nThis provider needs browser sign-in (OAuth), which Mailpilot 1.0 does not "
                    "support yet, so it cannot be used here.")
        self.note.configure(text=txt.strip())

    def _apply_profile(self):
        p = self._profile()
        self._show_note()
        if not p:
            return
        tmp = Account(recv_protocol=self.v["recv_protocol"].get())
        fill_from_profile(tmp, p)
        for k in ("recv_protocol", "recv_host", "recv_port", "recv_security",
                  "smtp_host", "smtp_port", "smtp_security"):
            self.v[k].set(str(getattr(tmp, k)))

    def _email_changed(self):
        email = self.v["email"].get().strip()
        if not self.v["username"].get():
            self.v["username"].set(email)
        if self.provider_var.get() == "Custom server":
            p = guess_provider(email, self.providers)
            if p:
                self.provider_var.set(p["name"])
                self._apply_profile()

    def _collect(self):
        email = self.v["email"].get().strip()
        if "@" not in email:
            raise MailError("Enter a valid e-mail address.")
        try:
            rp, sp = int(self.v["recv_port"].get()), int(self.v["smtp_port"].get())
        except ValueError:
            raise MailError("Ports must be numbers.") from None
        if not self.v["recv_host"].get().strip() or not self.v["smtp_host"].get().strip():
            raise MailError("Enter the receive and SMTP server names.")
        p = self._profile()
        return Account(
            name=self.v["name"].get().strip(), email=email,
            username=self.v["username"].get().strip() or email,
            provider=p["id"] if p else "custom",
            recv_protocol=self.v["recv_protocol"].get(), recv_host=self.v["recv_host"].get().strip(),
            recv_port=rp, recv_security=self.v["recv_security"].get(),
            smtp_host=self.v["smtp_host"].get().strip(), smtp_port=sp,
            smtp_security=self.v["smtp_security"].get())

    def _password(self, acct):
        return self.v["password"].get() or get_secret(acct.secret_key) or ""

    def _test(self):
        try:
            acct = self._collect()
        except MailError as e:
            self.msg.configure(text=str(e)); return
        pw = self._password(acct)
        if not pw:
            self.msg.configure(text="Enter the password or app password to test."); return

        def work():
            s = open_receive(acct.recv_protocol, acct.recv_host, acct.recv_port,
                             acct.recv_security, acct.username, pw)
            s.close()
            t = smtp_connect(acct.smtp_host, acct.smtp_port, acct.smtp_security, acct.username, pw)
            t.quit()
            return True

        self.msg.configure(text="Testing…")
        self.app.run_bg(work, lambda _: self.msg.configure(text="Success: receiving and sending both work."),
                        lambda e: self.msg.configure(text=f"Failed: {e}"), busy="Testing connection…")

    def _save(self):
        try:
            acct = self._collect()
        except MailError as e:
            self.msg.configure(text=str(e)); return
        pw = self.v["password"].get()
        persisted = True
        if pw:
            persisted = set_secret(acct.secret_key, pw)
        self.app.store.upsert(acct)
        if pw and not persisted:
            messagebox.showinfo(meta.APP_NAME, "No system keyring is available, so the password is kept "
                                "for this session only. Install the 'keyring' package to remember it.", parent=self)
        self.app.on_accounts_changed(select=acct)
        self.destroy()


class AccountsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        _base_dialog(self, parent, app, "Accounts")
        self.app = app
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        self.lb = tk.Listbox(f, height=8, width=48, exportselection=False)
        app.theme.register(self.lb, "list")
        self.lb.grid(row=0, column=0, rowspan=4, sticky="nsew")
        f.columnconfigure(0, weight=1)
        ttk.Button(f, text="Add…", command=self._add).grid(row=0, column=1, padx=8, pady=2, sticky="ew")
        ttk.Button(f, text="Edit…", command=self._edit).grid(row=1, column=1, padx=8, pady=2, sticky="ew")
        ttk.Button(f, text="Remove", command=self._remove).grid(row=2, column=1, padx=8, pady=2, sticky="ew")
        ttk.Button(f, text="Close", command=self.destroy).grid(row=3, column=1, padx=8, pady=2, sticky="sew")
        self._fill()
        app.account_listeners.append(self._fill)
        self.bind("<Destroy>", lambda e: self._unlisten() if e.widget is self else None)

    def _unlisten(self):
        if self._fill in self.app.account_listeners:
            self.app.account_listeners.remove(self._fill)

    def _fill(self):
        if not self.winfo_exists():
            return
        self.lb.delete(0, "end")
        for a in self.app.store.accounts:
            self.lb.insert("end", f"{a.label}  <{a.email}>  [{a.recv_protocol.upper()}]")

    def _sel(self):
        i = self.lb.curselection()
        return self.app.store.accounts[i[0]] if i else None

    def _add(self):
        AccountDialog(self, self.app)

    def _edit(self):
        a = self._sel()
        if a:
            AccountDialog(self, self.app, a)

    def _remove(self):
        a = self._sel()
        if a and messagebox.askyesno(meta.APP_NAME, f"Remove {a.email} from Mailpilot?\n(Your mail on the server is not touched.)", parent=self):
            self.app.store.remove(a.email)
            self.app.on_accounts_changed()


# --------------------------------------------------------------------------
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        _base_dialog(self, parent, app, "Settings")
        self.app = app
        s = app.settings
        self.theme_var = tk.StringVar(value=s["theme"])
        self.page_var = tk.StringVar(value=str(s["page_size"]))
        self.ai_on = tk.BooleanVar(value=bool(s["ai_enabled"]))
        self.provider_var = tk.StringVar(value=s["ai_provider"])
        self.model_var = tk.StringVar(value=s["ai_model"])
        self.temp_var = tk.StringVar(value=str(s["ai_temperature"]))
        self.sig_var = tk.StringVar(value=s["ai_signature"])
        self.key_var = tk.StringVar()
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        r = 0

        def row(label, widget):
            nonlocal r
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
            widget.grid(row=r, column=1, sticky="ew", pady=3)
            r += 1

        row("Theme", ttk.Combobox(f, textvariable=self.theme_var, values=MODES, state="readonly"))
        row("Messages per page", ttk.Spinbox(f, from_=10, to=200, increment=10, textvariable=self.page_var, width=6))
        ttk.Separator(f).grid(row=r, column=0, columnspan=2, sticky="ew", pady=8); r += 1
        ttk.Checkbutton(f, text="Enable AI draft reply (sends the open e-mail's text to the provider)",
                        variable=self.ai_on).grid(row=r, column=0, columnspan=2, sticky="w"); r += 1
        row("AI provider", ttk.Combobox(f, textvariable=self.provider_var, values=("anthropic", "gemini"), state="readonly"))
        row("Model ID", ttk.Entry(f, textvariable=self.model_var))
        row("API key", ttk.Entry(f, textvariable=self.key_var, show="*"))
        ttk.Label(f, text="Leave the key blank to keep the saved one. Copy the current model ID from the provider's documentation.",
                  style="Muted.TLabel", wraplength=420, justify="left").grid(row=r, column=0, columnspan=2, sticky="w"); r += 1
        row("Temperature (0-1)", ttk.Entry(f, textvariable=self.temp_var, width=6))
        row("Sign drafts as", ttk.Entry(f, textvariable=self.sig_var))
        b = ttk.Frame(f)
        b.grid(row=r, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(b, text="Save", command=self._save).pack(side="left", padx=4)
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="left", padx=4)

    def _save(self):
        s = self.app.settings
        try:
            s["page_size"] = max(5, min(200, int(self.page_var.get())))
            s["ai_temperature"] = max(0.0, min(1.0, float(self.temp_var.get())))
        except ValueError:
            messagebox.showerror(meta.APP_NAME, "Page size and temperature must be numbers.", parent=self)
            return
        s["theme"] = self.theme_var.get()
        s["ai_enabled"] = bool(self.ai_on.get())
        s["ai_provider"] = self.provider_var.get()
        s["ai_model"] = self.model_var.get().strip()
        s["ai_signature"] = self.sig_var.get().strip()
        if self.key_var.get().strip():
            if not set_secret("ai-api-key", self.key_var.get().strip()):
                messagebox.showinfo(meta.APP_NAME, "No system keyring is available, so the API key is kept "
                                    "for this session only.", parent=self)
        save_settings(s)
        self.app.set_theme(s["theme"])
        self.app.refresh_after_settings()
        self.destroy()


# --------------------------------------------------------------------------
class ComposeWindow(tk.Toplevel):
    """Write a message. Select text and use 'Text colour…' to change its colour."""

    def __init__(self, parent, app, account: Account, to="", subject="", body="",
                 cc="", in_reply_to="", references=""):
        super().__init__(parent)
        _base_dialog(self, parent, app, "New message", modal=False)
        self.geometry("760x600")
        self.app, self.account = app, account
        self.in_reply_to, self.references = in_reply_to, references
        self.attachments = []
        self.typing_color = None
        self.to_v, self.cc_v, self.bcc_v = tk.StringVar(value=to), tk.StringVar(value=cc), tk.StringVar()
        self.sub_v = tk.StringVar(value=subject)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="From").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(top, text=f"{account.label} <{account.email}>").grid(row=0, column=1, sticky="w", padx=8)
        self.entries = {}
        for i, (lbl, var) in enumerate((("To", self.to_v), ("Cc", self.cc_v), ("Bcc", self.bcc_v), ("Subject", self.sub_v)), start=1):
            ttk.Label(top, text=lbl).grid(row=i, column=0, sticky="w", pady=2)
            self.entries[lbl] = ttk.Entry(top, textvariable=var)
            self.entries[lbl].grid(row=i, column=1, sticky="ew", padx=8, pady=2)

        # --- formatting toolbar ---
        tb = ttk.Frame(self, padding=(10, 0))
        tb.pack(fill="x")
        ttk.Button(tb, text="Text colour…", command=self._choose_color).pack(side="left", padx=(0, 4))
        self.swatch = tk.Label(tb, width=3, relief="solid", borderwidth=1)
        self.swatch.pack(side="left", padx=(0, 8))
        ttk.Button(tb, text="Reset colour", command=self._reset_color).pack(side="left", padx=2)
        ttk.Button(tb, text="B", width=3, command=lambda: self._toggle("bold")).pack(side="left", padx=2)
        ttk.Button(tb, text="I", width=3, command=lambda: self._toggle("italic")).pack(side="left", padx=2)
        ttk.Button(tb, text="Attach…", command=self._attach).pack(side="left", padx=(12, 2))
        self.att_lbl = ttk.Label(tb, text="", style="Muted.TLabel")
        self.att_lbl.pack(side="left", padx=6)

        # --- editor ---
        mid = ttk.Frame(self, padding=(10, 6))
        mid.pack(fill="both", expand=True)
        base = tkfont.nametofont("TkDefaultFont").copy()
        base.configure(size=11)
        self._f_base = base
        self._f_bold = base.copy(); self._f_bold.configure(weight="bold")
        self._f_ital = base.copy(); self._f_ital.configure(slant="italic")
        self.text = tk.Text(mid, wrap="word", undo=True, font=base, padx=8, pady=8)
        sb = ttk.Scrollbar(mid, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        app.theme.register(self.text, "text")
        self.text.tag_configure("bold", font=self._f_bold)
        self.text.tag_configure("italic", font=self._f_ital)
        self.text.insert("1.0", body)
        self.text.mark_set("insert", "1.0")
        self.text.edit_reset()
        self.text.edit_modified(False)
        self.text.bind("<KeyRelease>", self._on_key)
        self._update_swatch()

        bot = ttk.Frame(self, padding=(10, 6))
        bot.pack(fill="x")
        self.send_btn = ttk.Button(bot, text="Send", command=self._send)
        self.send_btn.pack(side="right", padx=4)
        ttk.Button(bot, text="Discard", command=self._close).pack(side="right", padx=4)
        self.bind("<Control-Return>", lambda e: self._send())
        self.protocol("WM_DELETE_WINDOW", self._close)
        (self.text if to else self.entries["To"]).focus_set()

    # ---- colour handling ----
    def _update_swatch(self):
        col = self.typing_color[3:] if self.typing_color else None
        self.swatch.configure(background=("#" + col) if col else self.app.theme.palette["fg"])

    def _choose_color(self):
        initial = ("#" + self.typing_color[3:]) if self.typing_color else self.app.theme.palette["fg"]
        _, hexv = colorchooser.askcolor(color=initial, parent=self, title="Text colour")
        if not hexv:
            return
        tag = color_tag(hexv)
        self.text.tag_configure(tag, foreground=hexv)
        try:
            first, last = self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:                    # no selection: colour what you type next
            self.typing_color = tag
            self._update_swatch()
            self.text.focus_set()
            return
        self._clear_fg(first, last)
        self.text.tag_add(tag, first, last)
        self.typing_color = None
        self._update_swatch()
        self.text.focus_set()

    def _clear_fg(self, first, last):
        for t in self.text.tag_names():
            if t.startswith("fg_"):
                self.text.tag_remove(t, first, last)

    def _reset_color(self):
        try:
            self._clear_fg(self.text.index("sel.first"), self.text.index("sel.last"))
        except tk.TclError:
            pass
        self.typing_color = None
        self._update_swatch()
        self.text.focus_set()

    def _on_key(self, event):
        if self.typing_color and len(event.char) == 1 and event.char.isprintable():
            self.text.tag_add(self.typing_color, "insert-1c", "insert")

    def _toggle(self, tag):
        try:
            first, last = self.text.index("sel.first"), self.text.index("sel.last")
        except tk.TclError:
            return
        if tag in self.text.tag_names("sel.first"):
            self.text.tag_remove(tag, first, last)
        else:
            self.text.tag_add(tag, first, last)

    # ---- attachments ----
    def _attach(self):
        paths = filedialog.askopenfilenames(parent=self, title="Attach files")
        self.attachments.extend(paths)
        names = [p.replace("\\", "/").rsplit("/", 1)[-1] for p in self.attachments]
        self.att_lbl.configure(text=("Attached: " + ", ".join(names)) if names else "")

    # ---- send / close ----
    def _send(self):
        text = self.text.get("1.0", "end-1c")
        html = dump_to_html(self.text.dump("1.0", "end-1c", tag=True, text=True))
        try:
            msg, rcpts = build_message(
                self.account.email, self.to_v.get().strip(), self.sub_v.get().strip() or "(no subject)",
                text, html, cc=self.cc_v.get().strip(), bcc=self.bcc_v.get().strip(),
                in_reply_to=self.in_reply_to, references=self.references,
                attachments=self.attachments, from_name=self.account.name)
        except (MailError, OSError) as e:
            messagebox.showerror(meta.APP_NAME, str(e), parent=self)
            return
        self.send_btn.state(["disabled"])
        self.app.send_async(self.account, msg, rcpts, self._sent_ok, self._sent_err)

    def _sent_ok(self, _):
        self.text.edit_modified(False)
        self.app.set_status("Message sent.")
        self.destroy()

    def _sent_err(self, e):
        self.send_btn.state(["!disabled"])
        self.app.show_error(e)

    def _close(self):
        if self.text.edit_modified() and self.text.get("1.0", "end-1c").strip():
            if not messagebox.askyesno(meta.APP_NAME, "Discard this message?", parent=self):
                return
        self.destroy()

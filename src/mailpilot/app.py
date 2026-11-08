"""Main window: accounts, folders, message list, reading pane, search, AI draft reply."""
import queue
import threading
import tkinter as tk
import webbrowser
from email.utils import parseaddr
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter import font as tkfont

from . import ai, meta
from .accounts import AccountStore
from .dialogs import AboutDialog, AccountDialog, AccountsDialog, ComposeWindow, SettingsDialog
from .mailcore import (MailError, attachment_bytes, open_receive, parse_query_text,
                       quote_text, reply_subject, send_message)
from .paths import resource
from .secrets_store import get_secret, set_secret
from .settings import load_settings, save_settings
from .theme import ThemeManager

MODE_LABELS = {"system": "System", "light": "Light", "dark": "Dark"}
LABEL_MODES = {v: k for k, v in MODE_LABELS.items()}


class MailpilotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()
        self.store = AccountStore()
        self.theme = ThemeManager(root)
        self.account_listeners = []
        self._q = queue.Queue()
        self.lock = threading.RLock()
        self.session = None
        self.session_acct = None
        self.gen = 0                 # guards against stale background results
        self.folders = []
        self.folder = None           # raw folder name
        self.page = 0
        self.total = 0
        self.rows = []               # list of (folder_raw, MsgHeader)
        self.parsed = None
        self.in_search = False
        self.ai_warned = False

        root.title(f"{meta.APP_NAME} {meta.APP_VERSION}")
        root.geometry("1220x780")
        root.minsize(900, 560)
        try:
            self._icon = tk.PhotoImage(file=str(resource("icon.png")))
            root.iconphoto(True, self._icon)
        except Exception:
            pass
        self.base_font = tkfont.nametofont("TkDefaultFont").copy()
        self.base_font.configure(size=11)
        self.bold_font = self.base_font.copy()
        self.bold_font.configure(weight="bold")
        self.title_font = self.base_font.copy()
        self.title_font.configure(size=14, weight="bold")

        self.theme.register(root, "window")
        self._build_menu()
        self._build_ui()
        self.set_theme(self.settings["theme"])
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.after(100, self._poll)
        root.after(200, self._startup)

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        m = tk.Menu(self.root)
        self.theme.register(m, "menu")
        fm = tk.Menu(m, tearoff=0); self.theme.register(fm, "menu")
        fm.add_command(label="New message", accelerator="Ctrl+N", command=self.compose_new)
        fm.add_command(label="Accounts…", command=lambda: AccountsDialog(self.root, self))
        fm.add_command(label="Settings…", command=lambda: SettingsDialog(self.root, self))
        fm.add_separator()
        fm.add_command(label="Quit", command=self.quit)
        m.add_cascade(label="File", menu=fm)
        vm = tk.Menu(m, tearoff=0); self.theme.register(vm, "menu")
        self.theme_var = tk.StringVar(value=self.settings["theme"])
        for mode, label in MODE_LABELS.items():
            vm.add_radiobutton(label=f"Theme: {label}", value=mode, variable=self.theme_var,
                               command=lambda: self.set_theme(self.theme_var.get()))
        vm.add_separator()
        vm.add_command(label="Refresh", accelerator="F5", command=self.refresh)
        m.add_cascade(label="View", menu=vm)
        hm = tk.Menu(m, tearoff=0); self.theme.register(hm, "menu")
        hm.add_command(label=f"About {meta.APP_NAME}", command=lambda: AboutDialog(self.root, self))
        hm.add_command(label="Project page on GitHub", command=lambda: webbrowser.open(meta.GITHUB_URL))
        m.add_cascade(label="Help", menu=hm)
        self.root.configure(menu=m)

    def _build_ui(self):
        r = self.root
        bar = ttk.Frame(r, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="Compose", command=self.compose_new).pack(side="left", padx=2)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left", padx=2)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(bar, textvariable=self.search_var, width=44)
        self.search_entry.pack(side="left", padx=(14, 2))
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        ttk.Button(bar, text="Search", command=self.do_search).pack(side="left", padx=2)
        ttk.Button(bar, text="Clear", command=self.clear_search).pack(side="left", padx=2)
        ttk.Button(bar, text="About", command=lambda: AboutDialog(self.root, self)).pack(side="right", padx=2)
        ttk.Button(bar, text="Settings", command=lambda: SettingsDialog(self.root, self)).pack(side="right", padx=2)
        self.theme_box = ttk.Combobox(bar, values=list(MODE_LABELS.values()), state="readonly", width=8)
        self.theme_box.pack(side="right", padx=2)
        self.theme_box.bind("<<ComboboxSelected>>", lambda e: self.set_theme(LABEL_MODES[self.theme_box.get()]))
        ttk.Label(bar, text="Theme").pack(side="right", padx=(8, 2))

        self.status = tk.StringVar(value="Ready")
        ttk.Label(r, textvariable=self.status, style="Muted.TLabel", padding=(8, 3)).pack(side="bottom", fill="x")

        pw = ttk.PanedWindow(r, orient="horizontal")
        pw.pack(fill="both", expand=True)

        # left: account + folders
        left = ttk.Frame(pw, padding=8)
        ttk.Label(left, text="Account").pack(anchor="w")
        self.acct_box = ttk.Combobox(left, state="readonly")
        self.acct_box.pack(fill="x", pady=(0, 8))
        self.acct_box.bind("<<ComboboxSelected>>", lambda e: self._account_picked())
        ttk.Label(left, text="Folders").pack(anchor="w")
        self.folder_list = tk.Listbox(left, exportselection=False, activestyle="none", font=self.base_font)
        self.theme.register(self.folder_list, "list")
        self.folder_list.pack(fill="both", expand=True)
        self.folder_list.bind("<<ListboxSelect>>", lambda e: self._folder_picked())
        pw.add(left, weight=1)

        # middle: message list
        mid = ttk.Frame(pw, padding=8)
        cols = ("from", "subject", "date", "folder")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        for c, w in (("from", 190), ("subject", 300), ("date", 130), ("folder", 90)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("unread", font=self.bold_font)
        sb = ttk.Scrollbar(mid, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        nav = ttk.Frame(mid)
        nav.pack(side="bottom", fill="x", pady=(6, 0))
        self.newer_btn = ttk.Button(nav, text="◀ Newer", command=lambda: self.goto_page(self.page - 1))
        self.newer_btn.pack(side="left")
        self.older_btn = ttk.Button(nav, text="Older ▶", command=lambda: self.goto_page(self.page + 1))
        self.older_btn.pack(side="left", padx=4)
        self.page_lbl = ttk.Label(nav, text="", style="Muted.TLabel")
        self.page_lbl.pack(side="left", padx=8)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._row_picked())
        pw.add(mid, weight=3)

        # right: reading pane
        right = ttk.Frame(pw, padding=8)
        self.subj_lbl = ttk.Label(right, text="", font=self.title_font, wraplength=520, justify="left")
        self.subj_lbl.pack(anchor="w")
        self.meta_lbl = ttk.Label(right, text="", style="Muted.TLabel", wraplength=520, justify="left")
        self.meta_lbl.pack(anchor="w", pady=(2, 6))
        act = ttk.Frame(right)
        act.pack(fill="x", pady=(0, 6))
        ttk.Button(act, text="Reply", command=self.reply).pack(side="left", padx=(0, 4))
        ttk.Button(act, text="AI draft reply", command=self.ai_reply).pack(side="left", padx=4)
        self.att_box = ttk.Combobox(act, state="readonly", width=26)
        ttk.Button(act, text="Save attachment…", command=self.save_attachment).pack(side="right")
        self.att_box.pack(side="right", padx=4)
        body_fr = ttk.Frame(right)
        body_fr.pack(fill="both", expand=True)
        self.body = tk.Text(body_fr, wrap="word", font=self.base_font, state="disabled", padx=8, pady=8)
        bsb = ttk.Scrollbar(body_fr, command=self.body.yview)
        self.body.configure(yscrollcommand=bsb.set)
        bsb.pack(side="right", fill="y")
        self.body.pack(side="left", fill="both", expand=True)
        self.theme.register(self.body, "text")
        pw.add(right, weight=4)

    def _bind_keys(self):
        r = self.root
        r.bind_all("<Control-n>", lambda e: self.compose_new())
        r.bind_all("<Control-f>", lambda e: self.search_entry.focus_set())
        r.bind_all("<F5>", lambda e: self.refresh())
        r.bind_all("<Control-r>", lambda e: self.refresh())

    # ----------------------------------------------------------- utilities
    def set_status(self, text: str):
        self.status.set(text)

    def show_error(self, e):
        self.set_status("Error")
        msg = str(e) if isinstance(e, (MailError, ai.AiError)) else f"Unexpected problem: {e}"
        messagebox.showerror(meta.APP_NAME, msg, parent=self.root)

    def run_bg(self, fn, ok=None, err=None, busy="Working…"):
        """Run fn in a thread; deliver the result to ok()/err() on the Tk thread."""
        self.set_status(busy)

        def work():
            try:
                self._q.put((ok, fn(), False))
            except Exception as e:  # shown to the user, never silently dropped
                self._q.put((err, e, True))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                cb, val, is_err = self._q.get_nowait()
                try:
                    if is_err:
                        (cb or self.show_error)(val)
                    elif cb:
                        cb(val)
                    if not is_err and self.status.get().endswith("…"):
                        self.set_status("Ready")
                except Exception as e:
                    self.show_error(e)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def set_theme(self, mode: str):
        self.settings["theme"] = mode
        save_settings(self.settings)
        self.theme.apply(mode)
        self.theme_var.set(mode)
        self.theme_box.set(MODE_LABELS.get(mode, "System"))
        self.set_status(f"Theme: {MODE_LABELS.get(mode, mode)} ({self.theme.resolved})")

    def refresh_after_settings(self):
        self.theme_var.set(self.settings["theme"])
        self.theme_box.set(MODE_LABELS.get(self.settings["theme"], "System"))
        if self.session_acct:
            self.load_headers()

    # ------------------------------------------------------------ accounts
    def _startup(self):
        self.on_accounts_changed()
        if not self.store.accounts:
            AccountDialog(self.root, self)

    def on_accounts_changed(self, select=None):
        labels = [f"{a.label} <{a.email}>" for a in self.store.accounts]
        self.acct_box.configure(values=labels)
        for cb in list(self.account_listeners):
            try:
                cb()
            except Exception:
                pass
        if not self.store.accounts:
            self._close_session()
            self.acct_box.set("")
            return
        target = select or (self.session_acct if self.session_acct and self.store.get(self.session_acct.email) else None)
        if target is None:
            target = self.store.get(self.settings.get("last_account", "")) or self.store.accounts[0]
        i = [a.email for a in self.store.accounts].index(target.email)
        self.acct_box.current(i)
        if select is not None or self.session is None:
            self.select_account(self.store.accounts[i])

    def _account_picked(self):
        i = self.acct_box.current()
        if i >= 0:
            self.select_account(self.store.accounts[i])

    def get_password(self, acct, ask=True):
        pw = get_secret(acct.secret_key)
        if not pw and ask:
            pw = simpledialog.askstring(meta.APP_NAME, f"Password or app password for {acct.email}:",
                                        show="*", parent=self.root)
            if pw:
                set_secret(acct.secret_key, pw)
        return pw

    def _close_session(self):
        self.gen += 1
        with self.lock:
            s, self.session = self.session, None
        self.session_acct = None
        if s:
            threading.Thread(target=s.close, daemon=True).start()
        self.rows, self.folders, self.folder = [], [], None
        self.folder_list.delete(0, "end")
        self.tree.delete(*self.tree.get_children())
        self._clear_reader()

    def select_account(self, acct):
        pw = self.get_password(acct)
        if not pw:
            return
        self._close_session()
        gen = self.gen
        self.session_acct = acct
        self.settings["last_account"] = acct.email
        save_settings(self.settings)

        def work():
            s = open_receive(acct.recv_protocol, acct.recv_host, acct.recv_port,
                             acct.recv_security, acct.username or acct.email, pw)
            return s, s.folders()

        def ok(res):
            s, folders = res
            if gen != self.gen:        # user switched account meanwhile
                s.close()
                return
            with self.lock:
                self.session = s
            self.folders = folders
            self.folder_list.delete(0, "end")
            for f in folders:
                self.folder_list.insert("end", f.display)
            self.folder_list.selection_set(0)
            self.folder = folders[0].name
            self.page = 0
            self.load_headers()

        self.run_bg(work, ok, busy=f"Connecting to {acct.recv_host}…")

    def _call(self, fn):
        """Wrap fn(session) so it reconnects once if the connection dropped."""
        def wrapper():
            with self.lock:
                acct = self.session_acct
                if acct is None:
                    raise MailError("No account is selected.")
                if self.session is None or not self.session.alive():
                    pw = get_secret(acct.secret_key)
                    if not pw:
                        raise MailError("Password needed. Select the account again.")
                    self.session = open_receive(acct.recv_protocol, acct.recv_host, acct.recv_port,
                                                acct.recv_security, acct.username or acct.email, pw)
                return fn(self.session)
        return wrapper

    # ------------------------------------------------------------- listing
    def _folder_picked(self):
        i = self.folder_list.curselection()
        if not i or not self.folders:
            return
        self.folder = self.folders[i[0]].name
        self.page = 0
        self.in_search = False
        self.load_headers()

    def refresh(self):
        if self.session_acct:
            self.load_headers() if not self.in_search else self.do_search()

    def goto_page(self, page: int):
        if page < 0 or self.in_search:
            return
        self.page = page
        self.load_headers()

    def load_headers(self):
        if not self.folder or not self.session_acct:
            return
        gen, folder, page, size = self.gen, self.folder, self.page, int(self.settings["page_size"])
        label = self._folder_label(folder)

        def ok(res):
            if gen != self.gen or folder != self.folder:
                return
            headers, total = res
            self.total = total
            self.in_search = False
            self._fill_tree([(folder, h) for h in headers], label)
            start = page * size + 1 if headers else 0
            self.page_lbl.configure(text=f"{start}-{page * size + len(headers)} of {total}")
            self.newer_btn.state(["!disabled"] if page > 0 else ["disabled"])
            self.older_btn.state(["!disabled"] if (page + 1) * size < total else ["disabled"])
            self.set_status(f"{label}: {total} messages")

        self.run_bg(self._call(lambda s: s.headers(folder, page, size)), ok,
                    busy=f"Loading {label}…")

    def _folder_label(self, raw):
        for f in self.folders:
            if f.name == raw:
                return f.display
        return raw

    def _fill_tree(self, rows, label_for_all=""):
        self.rows = rows
        self.tree.delete(*self.tree.get_children())
        for i, (folder, h) in enumerate(rows):
            self.tree.insert("", "end", iid=str(i), values=(h.sender, h.subject, h.date, self._folder_label(folder)),
                             tags=("unread",) if h.unread else ())

    # -------------------------------------------------------------- search
    def do_search(self):
        text = self.search_var.get().strip()
        if not text:
            return self.clear_search()
        if not self.session_acct:
            return
        q = parse_query_text(text)
        if q.is_empty():
            return self.clear_search()
        gen, size = self.gen, int(self.settings["page_size"])
        folders = [f.name for f in self.folders] if q.all_folders else [self.folder]

        def work(s):
            hits = []
            for fo in folders:
                for h in s.search(fo, q, size):
                    hits.append((fo, h))
                if len(hits) >= size:
                    break
            return hits[:size]

        def ok(hits):
            if gen != self.gen:
                return
            self.in_search = True
            self._fill_tree(hits)
            self.page_lbl.configure(text=f"{len(hits)} result(s)")
            self.newer_btn.state(["disabled"]); self.older_btn.state(["disabled"])
            self.set_status(f"Search finished: {len(hits)} result(s). Nothing was opened or sent.")

        self.run_bg(self._call(work), ok, busy="Searching…")

    def clear_search(self):
        self.search_var.set("")
        self.in_search = False
        self.page = 0
        self.load_headers()

    # ------------------------------------------------------------- reading
    def _clear_reader(self):
        self.parsed = None
        self.subj_lbl.configure(text="")
        self.meta_lbl.configure(text="")
        self.att_box.configure(values=[]); self.att_box.set("")
        self._set_body("")

    def _set_body(self, text):
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        self.body.insert("1.0", text)
        self.body.configure(state="disabled")

    def _row_picked(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.rows):
            return
        folder, h = self.rows[idx]
        gen = self.gen

        def ok(pm):
            if gen != self.gen:
                return
            self.parsed = pm
            self.subj_lbl.configure(text=pm.subject)
            self.meta_lbl.configure(text=f"From: {pm.sender}\nTo: {pm.to}\nDate: {pm.date}")
            names = [f"{a.filename} ({a.size // 1024 or 1} KB)" for a in pm.attachments]
            self.att_box.configure(values=names)
            self.att_box.set(names[0] if names else "")
            self._set_body(pm.body or "(no text content)")
            if sel[0] in self.tree.get_children():
                self.tree.item(sel[0], tags=())
            h.unread = False

        self.run_bg(self._call(lambda s: s.message(folder, h.uid)), ok, busy="Opening message…")

    def save_attachment(self):
        if not self.parsed or not self.parsed.attachments:
            return
        i = self.att_box.current()
        if i < 0:
            return
        try:
            name, data = attachment_bytes(self.parsed.raw, self.parsed.attachments[i].index)
        except MailError as e:
            return self.show_error(e)
        path = filedialog.asksaveasfilename(parent=self.root, initialfile=name)
        if path:
            with open(path, "wb") as fh:
                fh.write(data)
            self.set_status(f"Saved {path}")

    # ------------------------------------------------------------ composing
    def _compose_account(self):
        if self.session_acct:
            return self.session_acct
        if self.store.accounts:
            return self.store.accounts[0]
        AccountDialog(self.root, self)
        return None

    def compose_new(self):
        acct = self._compose_account()
        if acct:
            ComposeWindow(self.root, self, acct)

    def reply(self, draft: str = ""):
        pm, acct = self.parsed, self._compose_account()
        if not pm or not acct:
            return self.set_status("Open a message first.")
        to = parseaddr(pm.reply_to or pm.sender)[1]
        body = (draft + "\n\n" if draft else "\n\n") + quote_text(pm)
        ComposeWindow(self.root, self, acct, to=to, subject=reply_subject(pm.subject), body=body,
                      in_reply_to=pm.message_id, references=pm.references)

    def ai_reply(self):
        s = self.settings
        pm = self.parsed
        if not pm:
            return self.set_status("Open a message first.")
        if not s["ai_enabled"]:
            return messagebox.showinfo(meta.APP_NAME, "Turn on AI draft reply in Settings first.", parent=self.root)
        key = get_secret("ai-api-key")
        if not key:
            return messagebox.showinfo(meta.APP_NAME, "Add your AI API key in Settings first.", parent=self.root)
        if not self.ai_warned:
            if not messagebox.askokcancel(meta.APP_NAME, f"The text of this e-mail (sender, subject and body) will be sent "
                                          f"to the {s['ai_provider']} service to write a draft. Continue?", parent=self.root):
                return
            self.ai_warned = True

        def work():
            return ai.draft_reply(s["ai_provider"], key, s["ai_model"], pm.sender, pm.subject, pm.body,
                                  float(s["ai_temperature"]), s["ai_signature"])

        def ok(res):
            self.set_status(f"AI draft ready ({res.input_tokens} tokens in, {res.output_tokens} out). Review it, then press Send yourself.")
            if res.text.upper().startswith("QUESTIONS FOR YOU"):
                messagebox.showinfo(meta.APP_NAME, res.text, parent=self.root)
                self.reply()
            else:
                self.reply(draft=res.text)

        self.run_bg(work, ok, busy="Asking the AI for a draft…")

    def send_async(self, acct, msg, rcpts, ok, err):
        pw = self.get_password(acct)
        if not pw:
            return err(MailError("A password is needed to send."))
        self.run_bg(lambda: send_message(acct.smtp_host, acct.smtp_port, acct.smtp_security,
                                         acct.username or acct.email, pw, msg, rcpts),
                    ok, err, busy="Sending…")

    # ---------------------------------------------------------------- exit
    def quit(self):
        self._close_session()
        self.root.destroy()


def main():
    root = tk.Tk()
    MailpilotApp(root)
    root.mainloop()

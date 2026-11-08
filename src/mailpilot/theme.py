"""Light and dark themes for the Tk/ttk widgets.

The editor's text colour is stored as Text tags, so it is NOT changed when the
theme changes; only the default text colour follows the theme.
"""
import subprocess
import sys

PALETTES = {
    "light": dict(bg="#f3f4f6", panel="#e5e7eb", fg="#111827", muted="#6b7280",
                  entry_bg="#ffffff", border="#c4c9d1", accent="#2563eb",
                  select_bg="#2563eb", select_fg="#ffffff", link="#1d4ed8"),
    "dark": dict(bg="#16181d", panel="#20242b", fg="#e5e7eb", muted="#9ca3af",
                 entry_bg="#1b1e24", border="#3a4049", accent="#6ea0ff",
                 select_bg="#3b6fd8", select_fg="#ffffff", link="#8ab4ff"),
}
MODES = ("system", "light", "dark")


def detect_system_theme() -> str:
    """Best-effort OS theme detection; falls back to light."""
    try:
        if sys.platform.startswith("win"):
            import winreg  # type: ignore
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value else "dark"
        if sys.platform == "darwin":
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, timeout=2)
            return "dark" if "dark" in r.stdout.lower() else "light"
        for args in (["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                     ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"]):
            r = subprocess.run(args, capture_output=True, text=True, timeout=2)
            if "dark" in r.stdout.lower():
                return "dark"
    except Exception:
        pass
    return "light"


def resolve_mode(mode: str) -> str:
    return detect_system_theme() if mode == "system" else ("dark" if mode == "dark" else "light")


class ThemeManager:
    def __init__(self, root):
        from tkinter import ttk
        self.root = root
        self.style = ttk.Style(root)
        self.mode = "system"
        self.resolved = "light"
        self._widgets = []   # (widget, kind)

    def register(self, widget, kind: str) -> None:
        """kind: 'window' | 'text' | 'list' | 'menu'"""
        self._widgets.append((widget, kind))
        self._paint(widget, kind)

    @property
    def palette(self) -> dict:
        return PALETTES[self.resolved]

    def apply(self, mode: str) -> None:
        self.mode = mode if mode in MODES else "system"
        self.resolved = resolve_mode(self.mode)
        p = self.palette
        s = self.style
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["entry_bg"],
                    bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"],
                    troughcolor=p["panel"], focuscolor=p["accent"], insertcolor=p["fg"])
        s.configure("TFrame", background=p["bg"])
        s.configure("Panel.TFrame", background=p["panel"])
        s.configure("TLabel", background=p["bg"], foreground=p["fg"])
        s.configure("Muted.TLabel", foreground=p["muted"])
        s.configure("Link.TLabel", foreground=p["link"])
        s.configure("TButton", background=p["panel"], foreground=p["fg"], padding=(8, 4), borderwidth=1)
        s.map("TButton", background=[("active", p["accent"]), ("pressed", p["accent"])],
              foreground=[("active", p["select_fg"])])
        s.configure("TEntry", fieldbackground=p["entry_bg"], foreground=p["fg"], insertcolor=p["fg"])
        s.configure("TCombobox", fieldbackground=p["entry_bg"], foreground=p["fg"],
                    background=p["panel"], arrowcolor=p["fg"])
        s.map("TCombobox", fieldbackground=[("readonly", p["entry_bg"])],
              foreground=[("readonly", p["fg"])])
        s.configure("TSpinbox", fieldbackground=p["entry_bg"], foreground=p["fg"], arrowcolor=p["fg"])
        s.configure("TCheckbutton", background=p["bg"], foreground=p["fg"])
        s.configure("TLabelframe", background=p["bg"], bordercolor=p["border"])
        s.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"])
        s.configure("TPanedwindow", background=p["border"])
        s.configure("Treeview", background=p["entry_bg"], fieldbackground=p["entry_bg"],
                    foreground=p["fg"], rowheight=24, borderwidth=0)
        s.map("Treeview", background=[("selected", p["select_bg"])],
              foreground=[("selected", p["select_fg"])])
        s.configure("Treeview.Heading", background=p["panel"], foreground=p["fg"], relief="flat")
        s.configure("TScrollbar", background=p["panel"], arrowcolor=p["fg"], bordercolor=p["border"])
        s.configure("TSeparator", background=p["border"])
        self.root.option_add("*TCombobox*Listbox.background", p["entry_bg"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["select_bg"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["select_fg"])
        alive = []
        for w, kind in self._widgets:
            try:
                if w.winfo_exists():
                    self._paint(w, kind)
                    alive.append((w, kind))
            except Exception:
                pass
        self._widgets = alive

    def _paint(self, w, kind: str) -> None:
        p = self.palette
        try:
            if kind == "window":
                w.configure(background=p["bg"])
            elif kind == "text":
                w.configure(background=p["entry_bg"], foreground=p["fg"], insertbackground=p["fg"],
                            selectbackground=p["select_bg"], selectforeground=p["select_fg"],
                            highlightbackground=p["border"], highlightcolor=p["accent"])
            elif kind == "list":
                w.configure(background=p["entry_bg"], foreground=p["fg"],
                            selectbackground=p["select_bg"], selectforeground=p["select_fg"],
                            highlightbackground=p["border"], highlightcolor=p["accent"])
            elif kind == "menu":
                w.configure(background=p["panel"], foreground=p["fg"],
                            activebackground=p["accent"], activeforeground=p["select_fg"])
        except Exception:
            pass

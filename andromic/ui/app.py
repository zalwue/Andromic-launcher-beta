"""Main application window."""
import queue
import threading
import tkinter as tk
import traceback
from tkinter import messagebox

from .. import APP_NAME, __version__
from ..core.config import load_config, save_config
from ..core.instances import new_instance
from ..core.paths import ROOT, ensure_dirs
from ..core.reporter import Reporter
from ..core.versions import fetch_manifest, selectable_ids
from ..i18n import set_language, tr as _
from . import theme
from .pages.console import ConsolePage
from .pages.content import ContentPage
from .pages.play import PlayPage
from .pages.profiles import ProfilesPage
from .pages.servers import ServersPage
from .pages.settings import SettingsPage
from .widgets import Button, label

NAV = (("play", "Play", PlayPage), ("content", "Content", ContentPage),
       ("servers", "Servers", ServersPage), ("profiles", "Profiles", ProfilesPage), ("settings", "Settings", SettingsPage),
       ("console", "Console", ConsolePage))


class App:
    def __init__(self):
        ensure_dirs()
        self.cfg = load_config()
        set_language(self.cfg["lang"])
        theme.set_theme(self.cfg["theme"])
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1020x700")
        self.root.minsize(920, 640)
        theme.init_fonts(self.root)
        self.queue = queue.Queue()
        self.manifest = []
        self.busy = False
        self.images = {}
        self.pages, self.nav_buttons, self.current_page = {}, {}, "play"
        self.rep = Reporter(
            log=lambda m: self.ui(self.pages["console"].append, m),
            status=lambda m: self.ui(self.pages["play"].set_status, m),
            progress=lambda d, t, label_="": self.ui(self.pages["play"].set_progress, d, t, label_),
        )
        self.build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self._pump)
        threading.Thread(target=self._load_manifest, daemon=True).start()

    # ---- threading helpers ----
    def ui(self, fn, *args):
        self.queue.put((fn, args))

    def _pump(self):
        try:
            while True:
                fn, args = self.queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(50, self._pump)

    def run_async(self, job, on_done=None, on_error=None):
        def worker():
            try:
                result = job()
            except Exception as exc:
                self.rep.log(traceback.format_exc())
                self.ui(self._fail, exc, on_error)
                return
            if on_done:
                self.ui(on_done, result)
        threading.Thread(target=worker, daemon=True).start()

    def _fail(self, exc, on_error):
        self.pages["play"].set_status(str(exc))
        if on_error:
            on_error(exc)
        messagebox.showerror(APP_NAME, str(exc))

    # ---- state ----
    def current_instance(self):
        for inst in self.cfg["instances"]:
            if inst["name"] == self.cfg["instance"]:
                return inst
        return self.cfg["instances"][0] if self.cfg["instances"] else None

    def current_account(self):
        for acc in self.cfg["accounts"]:
            if acc["id"] == self.cfg["account"]:
                return acc
        return self.cfg["accounts"][0]

    def save(self):
        save_config(self.cfg)

    def close(self):
        self.save()
        self.root.destroy()

    def _load_manifest(self):
        try:
            versions = fetch_manifest()
        except Exception:
            self.ui(self.pages["play"].set_status, _("Version list is unavailable (offline)"))
            return
        self.ui(self._manifest_ready, versions)

    def _manifest_ready(self, versions):
        self.manifest = versions
        if not self.cfg["instances"]:
            latest = selectable_ids(versions)[0]
            self.cfg["instances"].append(new_instance(_("Main"), latest))
            self.cfg["instance"] = _("Main")
        self.pages["play"].set_status(_("Ready"))
        self.refresh()

    # ---- layout ----
    def build(self):
        for child in self.root.winfo_children():
            child.destroy()
        c = theme.colors
        self.root.configure(bg=c.bg)
        side = tk.Frame(self.root, bg=c.bg, width=220)
        side.pack(side="left", fill="y", padx=(18, 0), pady=18)
        side.pack_propagate(False)
        label(side, "Andromic", 22, bold=True).pack(anchor="w", padx=12, pady=(6, 0))
        label(side, "Launcher", 10, muted=True).pack(anchor="w", padx=12, pady=(0, 22))
        self.main = tk.Frame(self.root, bg=c.bg)
        self.main.pack(side="right", fill="both", expand=True, padx=18, pady=18)
        self.pages, self.nav_buttons = {}, {}
        for key, title, page_class in NAV:
            button = Button(side, _(title), lambda k=key: self.show(k), kind="nav",
                            anchor="w", height=42, size=11)
            button.pack(fill="x", pady=2)
            self.nav_buttons[key] = button
            self.pages[key] = page_class(self, self.main)
        footer = tk.Frame(side, bg=c.bg)
        footer.pack(side="bottom", fill="x")
        Button(footer, _("Data folder"), lambda: self._open_root(), kind="ghost", height=34,
               anchor="w").pack(fill="x")
        label(footer, f"v{__version__}", 9, muted=True).pack(anchor="w", padx=12, pady=(4, 0))
        self.show(self.current_page)
        if self.manifest:
            self.pages["play"].set_status(_("Ready"))

    def _open_root(self):
        from ..core.system import open_path
        open_path(ROOT)

    def show(self, key):
        self.current_page = key
        for name, page in self.pages.items():
            page.frame.pack_forget()
            self.nav_buttons[name].set_kind("nav_active" if name == key else "nav")
        self.pages[key].frame.pack(fill="both", expand=True)
        self.pages[key].refresh()

    def refresh(self):
        for page in self.pages.values():
            page.refresh()

    def rebuild(self):
        self.save()
        set_language(self.cfg["lang"])
        theme.set_theme(self.cfg["theme"])
        self.images.clear()
        self.build()

    def run(self):
        self.root.mainloop()


def main():
    App().run()

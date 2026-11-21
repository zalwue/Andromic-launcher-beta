"""Application object and main window."""
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QMainWindow,
                               QMessageBox, QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_NAME, __version__
from ..core import customization
from ..core.config import load_config, save_config
from ..core.instances import new_instance
from ..core.paths import ROOT, ensure_dirs
from ..core.reporter import Reporter
from ..core.system import open_path
from ..core import updater
from ..core.versions import fetch_manifest, selectable_ids
from ..i18n import set_language, tr as _
from . import theme
from .pages.console import ConsolePage
from .pages.content import ContentPage
from .pages.customization import CustomizationPage
from .pages.diagnostics import DiagnosticsPage
from .pages.play import PlayPage
from .pages.profiles import ProfilesPage
from .pages.rooms import RoomsPage
from .pages.servers import ServersPage
from .pages.settings import SettingsPage
from .pages.worlds import WorldsPage
from .widgets import Button, label

NAV = (("play", "Play", "play", PlayPage), ("content", "Content", "content", ContentPage),
       ("servers", "Servers", "servers", ServersPage),
       ("profiles", "Profiles", "profiles", ProfilesPage),
       ("worlds", "Worlds", "worlds", WorldsPage),
       ("rooms", "Rooms", "rooms", RoomsPage),
       ("settings", "Settings", "settings", SettingsPage),
       ("customization", "Customization", "customization", CustomizationPage),
       ("diagnostics", "Diagnostics", "diagnostics", DiagnosticsPage),
       ("console", "Console", "console", ConsolePage))


def _get_icon() -> QIcon:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    icon_file = base / "assets" / "icon.png"
    return QIcon(str(icon_file)) if icon_file.exists() else QIcon()


class Bridge(QObject):
    """Runs callables on the GUI thread; safe to trigger from worker threads."""

    call = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._dispatch)

    def _dispatch(self, fn, args):
        fn(*args)


class MainWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_get_icon())
        self.resize(1120, 760)
        self.setMinimumSize(1000, 680)
    def build(self):
        app = self.app
        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(22)

        side = QWidget()
        side.setFixedWidth(210)
        column = QVBoxLayout(side)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(4)
        column.addWidget(label("Andromic", 22, bold=True))
        column.addWidget(label("Launcher", 10, muted=True))
        column.addSpacing(18)

        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        nav_holder = QWidget()
        nav_holder.setObjectName("navHolder")
        nav_column = QVBoxLayout(nav_holder)
        nav_column.setContentsMargins(0, 0, 2, 0)
        nav_column.setSpacing(4)
        self.stack = QStackedWidget()
        app.pages, self.nav = {}, {}
        for key, title, icon, page_class in NAV:
            button = Button(_(title), "nav", 44, icon=icon, size=11)
            button.clicked.connect(lambda _c=False, k=key: app.show(k))
            nav_column.addWidget(button)
            self.nav[key] = button
            page = page_class(app)
            app.pages[key] = page
            self.stack.addWidget(page.frame)
        nav_column.addStretch()
        nav_scroll.setWidget(nav_holder)
        column.addWidget(nav_scroll, 1)
        folder = Button(_("Data folder"), "ghost", 36, anchor="left")
        folder.clicked.connect(lambda _c=False: open_path(ROOT))
        column.addWidget(folder)
        column.addWidget(label(f"v{__version__}", 9, muted=True))

        sidebar_position = app.custom.get("sidebar_position", "left")
        if sidebar_position == "right":
            layout.addWidget(self.stack, 1)
            layout.addWidget(side)
        else:
            layout.addWidget(side)
            layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

    def show_page(self, key):
        app = self.app
        page = app.pages[key]
        for name, button in self.nav.items():
            button.set_kind("nav_active" if name == key else "nav")
        self.stack.setCurrentWidget(page.frame)
        page.refresh()

    def closeEvent(self, event):
        self.app.save()
        event.accept()


class App:
    def __init__(self):
        ensure_dirs()
        self.cfg = load_config()
        set_language(self.cfg["lang"])
        self.custom = customization.from_config(self.cfg)
        theme.set_theme(self.custom["theme"], self.custom["accent_color"], self.custom)
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setApplicationName("Andromic")
        self.qt.setWindowIcon(_get_icon())
        self.qt.setFont(theme.init_fonts())
        self.qt.setStyleSheet(theme.stylesheet())
        self.bridge = Bridge()
        self.manifest, self.busy, self.pages, self.current_page = [], False, {}, "play"
        self.rep = Reporter(
            log=lambda message: self.ui(self.pages["console"].append, message),
            status=lambda message: self.ui(self.pages["play"].set_status, message),
            progress=lambda done, total, text="": self.ui(self.pages["play"].set_progress,
                                                         done, total, text))
        self.window = MainWindow(self)
        self.window.build()
        self.show(self.current_page)
        threading.Thread(target=self._load_manifest, daemon=True).start()
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    # ---- threading ----
    def ui(self, fn, *args):
        self.bridge.call.emit(fn, args)

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
        self.error(str(exc))

    # ---- message boxes ----
    def info(self, text):
        QMessageBox.information(self.window, APP_NAME, text)

    def warn(self, text):
        QMessageBox.warning(self.window, APP_NAME, text)

    def error(self, text):
        QMessageBox.critical(self.window, APP_NAME, text)

    def ask(self, text) -> bool:
        answer = QMessageBox.question(self.window, APP_NAME, text)
        return answer == QMessageBox.StandardButton.Yes

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
            available = selectable_ids(versions)
            if not available:
                self.pages["play"].set_status(
                    _("No supported Minecraft versions were found")
                )
                return
            name = _("Main")
            self.cfg["instances"].append(new_instance(name, available[0]))
            self.cfg["instance"] = name
        self.pages["play"].set_status(_("Ready"))
        self.refresh()

    def _check_updates_worker(self):
        try:
            release = updater.check_latest_release()
        except Exception as exc:
            self.rep.log(f"Update check skipped: {exc}")
            self.ui(self._update_check_failed, str(exc))
            return
        self.ui(self._updates_checked, release)

    def _update_check_failed(self, message):
        settings_page = self.pages.get("settings")
        if settings_page:
            settings_page.update_status.setText(_("Update check failed: {error}").format(error=message))

    def _updates_checked(self, release):
        settings_page = self.pages.get("settings")
        if release:
            self.update_release = release
            if settings_page:
                settings_page.set_update_release(release)
            self.info(_("Andromic {version} is available. Open Settings to download it.")
                      .format(version=release["version"]))
        elif settings_page:
            settings_page.set_up_to_date()

    # ---- navigation ----
    def show(self, key):
        self.current_page = key
        self.window.show_page(key)

    def refresh(self):
        for page in self.pages.values():
            page.refresh()

    def rebuild(self):
        self.save()
        set_language(self.cfg["lang"])
        self.custom = customization.from_config(self.cfg)
        theme.set_theme(self.custom["theme"], self.custom["accent_color"], self.custom)
        self.qt.setStyleSheet(theme.stylesheet())
        self.window.build()
        self.show(self.current_page)
        if self.manifest:
            self.pages["play"].set_status(_("Ready"))


def main():
    app = App()
    app.window.show()
    sys.exit(app.qt.exec())
          

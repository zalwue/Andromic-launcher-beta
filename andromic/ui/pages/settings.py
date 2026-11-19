from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QFileDialog, QFrame, QHBoxLayout, QScrollArea,
                               QVBoxLayout, QWidget)

from ...core.system import open_path, total_ram_mb
from ...core import updater
from ...i18n import tr as _
from ..widgets import (Button, Card, Field, Segmented, Select, SliderRow, ToggleRow, label,
                       page_title)


class SettingsPage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        cfg = app.cfg
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(page_title(_("Settings")))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("scrollInner")
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)
        columns = QHBoxLayout(inner)
        columns.setContentsMargins(0, 0, 14, 10)
        columns.setSpacing(14)
        left, right = QVBoxLayout(), QVBoxLayout()
        for column in (left, right):
            column.setSpacing(14)
            columns.addLayout(column, 1)

        def section(column, title):
            card = Card()
            card.lay.addWidget(label(title, 12, bold=True))
            column.addWidget(card)
            return card.lay

        def store(key):
            def setter(value):
                cfg[key] = value
            return setter

        def caption(layout, text):
            layout.addSpacing(4)
            layout.addWidget(label(text, 10, muted=True))

        max_ram = min(max(2048, (total_ram_mb() // 256) * 256), 65536)
        perf = section(left, _("Performance"))
        caption(perf, _("Allocated memory"))
        ram = SliderRow(1024, max_ram, 256, cfg["ram"], lambda v: f"{v} MB")
        ram.changed.connect(store("ram"))
        perf.addWidget(ram)
        caption(perf, _("Render distance"))
        dist = SliderRow(2, 32, 1, cfg["render_distance"], lambda v: _("{n} chunks").format(n=v))
        dist.changed.connect(store("render_distance"))
        perf.addWidget(dist)
        caption(perf, _("Frame rate limit"))
        fps = SliderRow(10, 260, 10, cfg["max_fps"], lambda v: "∞" if v >= 260 else f"{v} FPS")
        fps.changed.connect(store("max_fps"))
        perf.addWidget(fps)

        display = section(left, _("Display"))
        size_row = QHBoxLayout()
        width, height = Field(str(cfg["width"])), Field(str(cfg["height"]))
        width.textChanged.connect(store("width"))
        height.textChanged.connect(store("height"))
        size_row.addWidget(width)
        size_row.addWidget(label("×", 12, muted=True))
        size_row.addWidget(height)
        display.addLayout(size_row)
        caption(display, _("Graphics"))
        graphics = Select(["Fast", "Fancy", "Fabulous"], cfg["graphics"])
        graphics.picked.connect(store("graphics"))
        display.addWidget(graphics)
        for key, text in (("fullscreen", _("Fullscreen")), ("vsync", "VSync"),
                          ("apply_video", _("Apply video settings on launch"))):
            row = ToggleRow(text, cfg[key])
            row.toggled.connect(store(key))
            display.addWidget(row)

        java = section(right, "Java")
        java.addWidget(label(_("Java 8, 17, 21 or 25 is chosen automatically for each version."),
                             9, muted=True, wrap=True))
        caption(java, _("Custom Java path (optional)"))
        path_row = QHBoxLayout()
        self.java_path = Field(cfg["java_path"])
        self.java_path.textChanged.connect(store("java_path"))
        browse = Button("…", height=40)
        browse.setFixedWidth(52)
        browse.clicked.connect(lambda _c=False: self._browse_java())
        path_row.addWidget(self.java_path, 1)
        path_row.addWidget(browse)
        java.addLayout(path_row)
        caption(java, _("Extra JVM arguments"))
        jvm = Field(cfg["jvm_args"])
        jvm.textChanged.connect(store("jvm_args"))
        java.addWidget(jvm)
        flags = ToggleRow(_("Optimised JVM flags (G1GC)"), cfg["optimize_jvm"])
        flags.toggled.connect(store("optimize_jvm"))
        java.addWidget(flags)

        launcher = section(right, _("Launcher"))
        for key, text, hint in (
            ("fabric_api", _("Install Fabric API automatically"), _("For Fabric and Quilt instances")),
            ("auto_backup", _("Back up worlds before launch"), _("Keeps the last 5 archives")),
            ("hide_launcher", _("Hide launcher while playing"), ""),
        ):
            row = ToggleRow(text, cfg[key], hint)
            row.toggled.connect(store(key))
            launcher.addWidget(row)
        caption(launcher, _("Theme"))
        theme_switch = Segmented([("light", _("Light")), ("dark", _("Dark"))], cfg["theme"])
        theme_switch.changed.connect(lambda value: self._restyle("theme", value))
        launcher.addWidget(theme_switch, 0, Qt.AlignmentFlag.AlignLeft)
        caption(launcher, _("Language"))
        language = Segmented([("ru", "Русский"), ("en", "English")], cfg["lang"])
        language.changed.connect(lambda value: self._restyle("lang", value))
        launcher.addWidget(language, 0, Qt.AlignmentFlag.AlignLeft)
        caption(launcher, _("Accent colour (Mimuix / HyperOS)"))
        self.accent_button = Button(cfg.get("accent_color", "#3482FF"), "tonal", 36)
        self.accent_button.clicked.connect(lambda _c=False: self._choose_accent())
        launcher.addWidget(self.accent_button, 0, Qt.AlignmentFlag.AlignLeft)

        updates = section(right, _("Updates"))
        updates.addWidget(label(_("Check GitHub Releases when Andromic starts."),
                                9, muted=True, wrap=True))
        self.update_status = label(_("No update checked yet"), 9, muted=True, wrap=True)
        updates.addWidget(self.update_status)
        update_actions = QHBoxLayout()
        self.check_update_button = Button(_("Check now"), "tonal", 38)
        self.check_update_button.clicked.connect(lambda _c=False: self._check_updates())
        self.download_update_button = Button(_("Download update"), "primary", 38)
        self.download_update_button.setEnabled(False)
        self.download_update_button.clicked.connect(lambda _c=False: self._download_update())
        update_actions.addWidget(self.check_update_button)
        update_actions.addWidget(self.download_update_button)
        updates.addLayout(update_actions)
        self.update_release = None
        left.addStretch()
        right.addStretch()

    def _choose_accent(self):
        current = QColor(self.app.cfg.get("accent_color", "#3482FF"))
        color = QColorDialog.getColor(current, self.frame, _("Choose accent colour"))
        if color.isValid():
            self.app.cfg["accent_color"] = color.name(QColor.NameFormat.HexRgb)
            self.accent_button.set_text(self.app.cfg["accent_color"])
            self.app.rebuild()

    def set_update_release(self, release):
        self.update_release = release
        asset = release.get("asset")
        self.update_status.setText(
            _("Version {version} is available").format(version=release["version"])
            if asset else _("Version {version} is available, but no build was published for this OS")
            .format(version=release["version"]))
        self.download_update_button.setEnabled(bool(asset))

    def set_up_to_date(self):
        self.update_release = None
        self.update_status.setText(_("Andromic is up to date"))
        self.download_update_button.setEnabled(False)

    def _check_updates(self):
        self.update_status.setText(_("Checking GitHub Releases…"))
        def done(release):
            if release:
                self.set_update_release(release)
            else:
                self.update_release = None
                self.update_status.setText(_("Andromic is up to date"))
                self.download_update_button.setEnabled(False)
        self.app.run_async(updater.check_latest_release, done)

    def _download_update(self):
        if not self.update_release or not self.update_release.get("asset"):
            return
        self.download_update_button.setEnabled(False)
        self.update_status.setText(_("Downloading update…"))
        def done(path):
            self.update_status.setText(_("Downloaded: {name}").format(name=path.name))
            self.download_update_button.setEnabled(True)
            open_path(path.parent)
            self.app.info(_("The update was downloaded. Close Andromic and install or replace it manually."))
        def failed(exc):
            self.download_update_button.setEnabled(True)
            self.update_status.setText(str(exc))
        self.app.run_async(lambda: updater.download_update(self.update_release), done, failed)

    def _browse_java(self):
        path, _filter = QFileDialog.getOpenFileName(self.frame, "Java")
        if path:
            self.java_path.setText(path)

    def _restyle(self, key, value):
        self.app.cfg[key] = value
        QTimer.singleShot(120, self.app.rebuild)

    def refresh(self):
        pass

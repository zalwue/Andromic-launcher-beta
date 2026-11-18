"""Modal dialogs."""
import webbrowser

from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from ..core import optifine
from ..core.constants import LOADERS, OPTIFINE_DOWNLOADS
from ..core.instances import instance_dir, new_instance, unique_name
from ..core.loaders import loader_versions
from ..core.versions import selectable_ids
from ..i18n import tr as _
from .widgets import Button, Field, Select, ToggleRow, label


class InstanceDialog(QDialog):
    """Create or edit an instance."""

    def __init__(self, app, instance, on_saved):
        super().__init__(app.window)
        self.app, self.instance, self.on_saved = app, instance, on_saved
        self._alive = True
        self.setWindowTitle(_("Edit instance") if instance else _("New instance"))
        self.setModal(True)
        self.setFixedSize(500, 640)
        self.finished.connect(lambda _code: setattr(self, "_alive", False))

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(6)

        self.name = Field(instance["name"] if instance else _("New instance"))
        self.mc = Select()
        self.snapshots = ToggleRow(_("Show snapshots"))
        self.loader = Select(LOADERS, instance["loader"] if instance else "Vanilla")
        self.lv = Select()
        self.server = Field(instance.get("server", "") if instance else "")
        self._initial_mc = instance["mc"] if instance else ""
        self._initial_lv = instance["lv"] if instance else ""

        for caption, widget in ((_("Name"), self.name), (_("Minecraft version"), self.mc)):
            root.addWidget(label(caption, 10, muted=True))
            root.addWidget(widget)
        root.addWidget(self.snapshots)
        root.addSpacing(6)
        root.addWidget(label(_("Mod loader"), 10, muted=True))
        root.addWidget(self.loader)
        self.lv_label = label(_("Loader version"), 10, muted=True)
        root.addWidget(self.lv_label)
        root.addWidget(self.lv)

        self.optifine_row = QWidget()
        row = QHBoxLayout(self.optifine_row)
        row.setContentsMargins(0, 4, 0, 4)
        row.addWidget(self._button(_("Get OptiFine"), lambda: webbrowser.open(OPTIFINE_DOWNLOADS)))
        row.addWidget(self._button(_("Install from jar"), self._install_optifine))
        row.addStretch()
        root.addWidget(self.optifine_row)

        root.addSpacing(6)
        root.addWidget(label(_("Auto-join server (optional)"), 10, muted=True))
        root.addWidget(self.server)
        root.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self._button(_("Cancel"), self.reject, height=42))
        save = Button(_("Save"), "primary", 42)
        save.clicked.connect(self._save)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self.snapshots.toggled.connect(lambda _on: self._fill_versions())
        self.mc.picked.connect(lambda _v: self._refresh_loader())
        self.loader.picked.connect(lambda _v: self._refresh_loader())
        self._fill_versions(first=True)

    @staticmethod
    def _button(text, callback, height=34):
        button = Button(text, height=height)
        button.clicked.connect(lambda: callback())
        return button

    def _fill_versions(self, first=False):
        ids = selectable_ids(self.app.manifest, self.snapshots.isChecked())
        if first and self._initial_mc and self._initial_mc not in ids:
            ids.append(self._initial_mc)
        current = self.mc.value() or self._initial_mc
        self.mc.set_values(ids)
        if current in ids:
            self.mc.set_value(current)
        self._refresh_loader()

    def _refresh_loader(self):
        loader, mc = self.loader.value(), self.mc.value()
        self.optifine_row.setVisible(loader == "OptiFine")
        show_version = loader != "Vanilla" and bool(mc)
        self.lv.setVisible(show_version)
        self.lv_label.setVisible(show_version)
        if not show_version:
            return
        if loader == "OptiFine":
            self._set_lv(loader, mc, optifine.installed_versions(mc))
            return
        self.lv.set_values([_("Loading…")])

        def job():
            try:
                return loader_versions(loader, mc)
            except Exception:
                return []
        self.app.run_async(job, lambda versions: self._set_lv(loader, mc, versions))

    def _set_lv(self, loader, mc, versions):
        if not self._alive or (loader, mc) != (self.loader.value(), self.mc.value()):
            return
        wanted = self._initial_lv if self._initial_lv in versions else ""
        self.lv.set_values(versions or [_("None available")])
        self.lv.set_value(wanted or (versions[0] if versions else _("None available")))

    def _install_optifine(self):
        path, _filter = QFileDialog.getOpenFileName(
            self, "OptiFine", "", "OptiFine (OptiFine_*.jar);;JAR (*.jar)")
        if not path:
            return
        java_path = self.app.cfg["java_path"]
        self.app.pages["play"].set_status(_("Installing OptiFine"))

        def done(version_id):
            self.app.pages["play"].set_status(_("OptiFine installed"))
            if self._alive:
                self._initial_lv = version_id
                self._refresh_loader()
        self.app.run_async(
            lambda: optifine.install(path, self.app.manifest, java_path, self.app.rep), done)

    def _save(self):
        name = self.name.text().strip()
        loader, mc, lv = self.loader.value(), self.mc.value(), self.lv.value()
        if not name or not mc:
            return
        if loader != "Vanilla" and (not lv or lv in (_("Loading…"), _("None available"))):
            self.app.info(_("Choose a loader version"))
            return
        instances = self.app.cfg["instances"]
        others = [i["name"] for i in instances if i is not self.instance]
        if name.lower() in (n.lower() for n in others):
            name = unique_name(name, others)
        record = new_instance(name, mc, loader, lv if loader != "Vanilla" else "",
                              self.server.text().strip())
        if self.instance is None:
            instances.append(record)
        else:
            if self.instance["name"] != name:
                old_dir, new_dir = instance_dir(self.instance), instance_dir(record)
                if old_dir.exists() and not new_dir.exists():
                    old_dir.rename(new_dir)
            instances[instances.index(self.instance)] = record
        self.accept()
        self.on_saved(name)

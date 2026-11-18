import os
import shutil

from PySide6.QtWidgets import QHBoxLayout, QListWidget, QVBoxLayout, QWidget

from ...core import modrinth, options
from ...core.accounts import SKIN_PACK_NAME
from ...core.instances import instance_dir
from ...core.modpacks import install_mrpack
from ...core.net import download
from ...core.paths import DOWNLOADS
from ...core.system import open_path
from ...i18n import tr as _
from ..widgets import Button, Card, Field, Segmented, label, page_title

KINDS = (("mod", "Mods"), ("resourcepack", "Resource packs"),
         ("shader", "Shaders"), ("modpack", "Modpacks"))
TOGGLE_TEXT = {"mod": "Enable / disable", "resourcepack": "Enable / disable",
               "shader": "Apply", "modpack": "Select"}


class ContentPage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        self.kind = "mod"
        self.hits, self.entries = [], []
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(page_title(_("Content")))
        self.segmented = Segmented([(k, _(t)) for k, t in KINDS], "mod")
        self.segmented.changed.connect(self._set_kind)
        top = QHBoxLayout()
        top.addWidget(self.segmented)
        top.addStretch()
        root.addLayout(top)

        search = QHBoxLayout()
        search.setSpacing(8)
        self.query = Field(placeholder=_("Search Modrinth"))
        self.query.returnPressed.connect(self.search)
        go = Button(_("Search Modrinth"), "primary", 40)
        go.clicked.connect(lambda _c=False: self.search())
        search.addWidget(self.query, 1)
        search.addWidget(go)
        root.addLayout(search)

        columns = QHBoxLayout()
        columns.setSpacing(14)
        results = Card(margins=(14, 14, 14, 14), spacing=6)
        results.lay.addWidget(label(_("Results"), 10, muted=True))
        self.result_list = QListWidget()
        results.lay.addWidget(self.result_list, 1)
        installed = Card(margins=(14, 14, 14, 14), spacing=6)
        self.installed_title = label(_("Installed"), 10, muted=True)
        installed.lay.addWidget(self.installed_title)
        self.installed_list = QListWidget()
        installed.lay.addWidget(self.installed_list, 1)
        columns.addWidget(results, 1)
        columns.addWidget(installed, 1)
        root.addLayout(columns, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.install_button = self._button(_("Install"), self.install, "primary")
        self.preset_button = self._button(_("FPS preset"), self.fps_preset)
        self.toggle_button = self._button(_("Toggle"), self.toggle)
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.preset_button)
        buttons.addStretch()
        buttons.addWidget(self.toggle_button)
        buttons.addWidget(self._button(_("Delete"), self.delete, "danger"))
        buttons.addWidget(self._button(_("Folder"), self.open_folder))
        root.addLayout(buttons)
        self.note = label("", 10, muted=True)
        root.addWidget(self.note)

    @staticmethod
    def _button(text, callback, kind="tonal"):
        button = Button(text, kind, 38)
        button.clicked.connect(lambda _c=False: callback())
        return button

    def _say(self, text):
        self.note.setText(text)

    def _instance(self):
        inst = self.app.current_instance()
        if inst is None:
            self.app.info(_("Create an instance first"))
        return inst

    def _folder(self):
        inst = self.app.current_instance()
        if not inst or self.kind == "modpack":
            return None
        return instance_dir(inst) / modrinth.KIND_DIRS[self.kind]

    def _set_kind(self, kind):
        self.kind = kind
        self.hits = []
        self.result_list.clear()
        self.refresh()

    def refresh(self):
        self.preset_button.setVisible(self.kind == "mod")
        self.toggle_button.set_text(_(TOGGLE_TEXT[self.kind]))
        self.installed_title.setText(_("Instances") if self.kind == "modpack" else _("Installed"))
        self.entries = []
        self.installed_list.clear()
        if self.kind == "modpack":
            for inst in self.app.cfg["instances"]:
                self.entries.append(inst["name"])
                self.installed_list.addItem(inst["name"])
            return
        folder = self._folder()
        if not folder or not folder.exists():
            return
        enabled = set(options.enabled_resource_packs(folder.parent)) if self.kind == "resourcepack" else set()
        for name in sorted(os.listdir(folder)):
            if name == SKIN_PACK_NAME or name.endswith(".part"):
                continue
            self.entries.append(name)
            if self.kind == "resourcepack":
                mark = "●  " if name in enabled else "○  "
            elif self.kind == "mod":
                mark = "○  " if name.endswith(".disabled") else "●  "
            else:
                mark = "    "
            self.installed_list.addItem(mark + name)

    # ---- search and install ----
    def search(self):
        inst = self.app.current_instance()
        mc = inst["mc"] if inst else None
        loader = inst["loader"] if inst else "Vanilla"
        kind, query = self.kind, self.query.text().strip()
        self._say(_("Searching…"))

        def done(hits):
            if kind != self.kind:
                return
            self.hits = hits
            self.result_list.clear()
            for hit in hits:
                self.result_list.addItem(f"{hit['title']}  —  {hit['description'][:60]}")
            self._say(_("Found: {count}").format(count=len(hits)))
        self.app.run_async(lambda: modrinth.search(kind, query, mc, loader), done)

    def _selected_hit(self):
        row = self.result_list.currentRow()
        return self.hits[row] if 0 <= row < len(self.hits) else None

    def install(self):
        hit, inst = self._selected_hit(), self._instance()
        if not hit or not inst:
            return
        kind = self.kind
        if kind == "mod" and inst["loader"] in ("Vanilla", "OptiFine"):
            self.app.info(_("Mods need Fabric, Quilt, Forge or NeoForge"))
            return
        self._say(_("Installing…"))
        if kind == "modpack":
            self.app.run_async(lambda: self._install_modpack(hit), self._modpack_done)
            return
        dest = self._folder()
        loaders = modrinth.mod_loaders(inst["loader"]) if kind == "mod" else None
        log = lambda message: self.app.ui(self._say, message)  # noqa: E731

        def done(name):
            self._say(_("Installed: {name}").format(name=name) if name
                      else _("No compatible version found"))
            self.refresh()
        self.app.run_async(lambda: modrinth.install_project(
            hit["project_id"], dest, inst["mc"], loaders, kind == "mod", log), done)

    def _install_modpack(self, hit):
        versions = modrinth.project_versions(hit["project_id"])
        if not versions:
            raise RuntimeError(_("No versions available for this modpack"))
        file = modrinth.primary_file(versions[0])
        archive = DOWNLOADS / file["filename"]
        download(file["url"], archive, file.get("hashes", {}).get("sha1"))
        names = [i["name"] for i in self.app.cfg["instances"]]
        return install_mrpack(archive, hit["title"], names, self.app.rep)

    def _modpack_done(self, instance):
        self.app.cfg["instances"].append(instance)
        self.app.cfg["instance"] = instance["name"]
        self.app.save()
        self._say(_("Modpack installed as \"{name}\"").format(name=instance["name"]))
        self.app.refresh()

    def fps_preset(self):
        inst = self._instance()
        if not inst:
            return
        slugs = modrinth.FPS_PRESETS.get(inst["loader"])
        if not slugs:
            self.app.info(_("Mods need Fabric, Quilt, Forge or NeoForge"))
            return
        dest = instance_dir(inst) / "mods"
        loaders = modrinth.mod_loaders(inst["loader"])
        log = lambda message: self.app.ui(self._say, message)  # noqa: E731

        def job():
            seen = set()
            for slug in slugs:
                try:
                    modrinth.install_project(slug, dest, inst["mc"], loaders, True, log, seen)
                except Exception as exc:
                    log(f"{slug}: {exc}")

        def done(_result):
            self._say(_("Performance preset installed"))
            self.refresh()
        self._say(_("Installing performance mods…"))
        self.app.run_async(job, done)

    # ---- installed list ----
    def _selected_entry(self):
        row = self.installed_list.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def delete(self):
        name = self._selected_entry()
        if not name:
            return
        if self.kind == "modpack":
            self.app.pages["play"].delete_instance_by_name(name)
            return
        target = self._folder() / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
        self.refresh()

    def toggle(self):
        name = self._selected_entry()
        if not name:
            return
        if self.kind == "modpack":
            self.app.cfg["instance"] = name
            self.app.refresh()
            return
        folder = self._folder()
        if self.kind == "mod":
            target = folder / (name[:-9] if name.endswith(".disabled") else name + ".disabled")
            (folder / name).rename(target)
        elif self.kind == "resourcepack":
            options.toggle_resource_pack(folder.parent, name)
        else:
            options.set_shader_pack(folder.parent, name)
            self._say(_("Shader pack applied: {name}").format(name=name))
        self.refresh()

    def open_folder(self):
        folder = self._folder()
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
            open_path(folder)

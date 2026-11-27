"""Content page: Modrinth search + separate Installed tab.

Search shows only installable projects (never a duplicated installed list).
Installed content lives in its own "Установленные" tab.
"""
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ...core import modrinth, options
from ...core.accounts import SKIN_PACK_NAME
from ...core.instances import instance_dir
from ...core.modpacks import install_mrpack
from ...core.modrinth import search_hit_card
from ...core.net import download
from ...core.paths import DOWNLOADS
from ...core.system import open_path
from ...i18n import tr as _
from ..widgets import Button, Card, Field, Segmented, label, page_title

KINDS = (("mod", "Mods"), ("resourcepack", "Resource packs"),
         ("shader", "Shaders"), ("modpack", "Modpacks"))
TOGGLE_TEXT = {"mod": "Enable / disable", "resourcepack": "Enable / disable",
               "shader": "Apply", "modpack": "Select"}
SOURCE = "Modrinth"


class ModCard(QWidget):
    """Rich Modrinth result card: icon, title, description, source, downloads."""

    def __init__(self, hit, on_install, on_open):
        super().__init__()
        self.hit = hit
        self.on_install = on_install
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        self.icon = QLabel()
        self.icon.setFixedSize(48, 48)
        self.icon.setScaledContents(False)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setStyleSheet("background: transparent;")
        layout.addWidget(self.icon)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.title = label(hit.get("title") or "", 12, bold=True)
        title_row.addWidget(self.title, 1)
        self.source = label(SOURCE, 9, muted=True)
        title_row.addWidget(self.source, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        texts.addLayout(title_row)

        description = hit.get("description") or ""
        self.desc = label(description, 10, muted=True, wrap=True)
        self.desc.setMaximumHeight(46)
        texts.addWidget(self.desc)

        meta_parts = []
        if hit.get("downloads") is not None:
            meta_parts.append(f"{hit['downloads']} {_('downloads')}")
        if hit.get("author"):
            meta_parts.append(hit["author"])
        meta = "  ·  ".join(meta_parts) if meta_parts else _("No metadata")
        self.meta = label(meta, 9, muted=True)
        texts.addWidget(self.meta)

        self.status = label("", 9, muted=True)
        texts.addWidget(self.status)
        texts.addStretch()
        layout.addLayout(texts, 1)

        self.install_button = Button(_("Install"), "primary", 34)
        self.install_button.setFixedWidth(96)
        self.install_button.clicked.connect(lambda _c=False: self.on_install(self.hit, self))
        layout.addWidget(self.install_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self._open = on_open

    def mouseDoubleClickEvent(self, event):
        self._open(self.hit)
        super().mouseDoubleClickEvent(event)

    def set_icon(self, data: bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.icon.setPixmap(pixmap.scaled(44, 44, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))

    def set_status(self, text):
        self.status.setText(text)

    def set_installing(self, installing: bool):
        self.install_button.setEnabled(not installing)
        self.install_button.set_text(_("Installing…") if installing else _("Install"))


class ProjectDialog(QDialog):
    """Detailed project information from Modrinth (real metadata only)."""

    def __init__(self, app, hit, on_install=None):
        super().__init__(app.window)
        self.app = app
        self.hit = hit
        self._on_install = on_install
        self.setWindowTitle(hit.get("title") or _("Project"))
        self.resize(560, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(label(hit.get("title") or "", 16, bold=True))
        meta = []
        meta.append(SOURCE)
        if hit.get("author"):
            meta.append(hit["author"])
        if hit.get("downloads") is not None:
            meta.append(f"{hit['downloads']} {_('downloads')}")
        if hit.get("project_type"):
            meta.append(hit["project_type"])
        layout.addWidget(label("  ·  ".join(meta), 10, muted=True))
        desc = QLabel(hit.get("description") or "")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(desc, 1)
        self.detail = label("", 10, muted=True, wrap=True)
        layout.addWidget(self.detail)
        self.install_button = Button(_("Install"), "primary", 40)
        self.install_button.clicked.connect(lambda _c=False: self._install())
        row = QHBoxLayout()
        row.addWidget(self.install_button)
        row.addStretch()
        layout.addLayout(row)
        self._load_details()

    def _load_details(self):
        project_id = self.hit.get("project_id")
        if not project_id:
            return

        def job():
            return modrinth.project(project_id)

        def done(info):
            extra = []
            if isinstance(info.get("downloads"), int):
                extra.append(f"{info['downloads']} {_('downloads')}")
            if isinstance(info.get("followers"), int):
                extra.append(f"{info['followers']} followers")
            if info.get("license", {}).get("name") if isinstance(info.get("license"), dict) else None:
                extra.append(info["license"]["name"])
            if info.get("body"):
                self.detail.setText(str(info["body"])[:2000])
            elif info.get("description"):
                self.detail.setText(str(info["description"]))
            if extra:
                self.detail.setText((self.detail.text() + "\n\n" + "  ·  ".join(extra)).strip())

        self.app.run_async(job, done, lambda _e: None)

    def _install(self):
        self.install_button.setEnabled(False)
        if self._on_install is not None:
            self._on_install(self.hit, None)
        self.close()


class ContentPage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        self.kind = "mod"
        self.hits, self.entries = [], []
        self.installed_kind = "mod"
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(page_title(_("Content")))

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # ---- Tab 1: search ----
        search_tab = QWidget()
        search_root = QVBoxLayout(search_tab)
        search_root.setContentsMargins(0, 12, 0, 0)
        search_root.setSpacing(12)

        self.segmented = Segmented([(k, _(t)) for k, t in KINDS], "mod")
        self.segmented.changed.connect(self._set_kind)
        top = QHBoxLayout()
        top.addWidget(self.segmented)
        top.addStretch()
        search_root.addLayout(top)

        search = QHBoxLayout()
        search.setSpacing(8)
        self.query = Field(placeholder=_("Search Modrinth"))
        self.query.returnPressed.connect(self.search)
        go = Button(_("Search Modrinth"), "primary", 40)
        go.clicked.connect(lambda _c=False: self.search())
        search.addWidget(self.query, 1)
        search.addWidget(go)
        search_root.addLayout(search)

        results = Card(margins=(10, 10, 10, 10), spacing=6)
        results.lay.addWidget(label(_("Results"), 10, muted=True))
        self.result_list = QListWidget()
        self.result_list.setSpacing(4)
        self.result_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.result_list.itemDoubleClicked.connect(lambda _item: self.open_details())
        self.result_list.currentRowChanged.connect(lambda _r: None)
        results.lay.addWidget(self.result_list, 1)
        search_root.addWidget(results, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.install_button = self._button(_("Install"), self.install, "primary")
        self.preset_button = self._button(_("FPS preset"), self.fps_preset)
        self.details_button = self._button(_("Details"), self.open_details)
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.preset_button)
        buttons.addWidget(self.details_button)
        buttons.addStretch()
        search_root.addLayout(buttons)

        self.tabs.addTab(search_tab, _("Search"))

        # ---- Tab 2: installed ----
        installed_tab = QWidget()
        installed_root = QVBoxLayout(installed_tab)
        installed_root.setContentsMargins(0, 12, 0, 0)
        installed_root.setSpacing(12)

        self.installed_segmented = Segmented([(k, _(t)) for k, t in KINDS], "mod")
        self.installed_segmented.changed.connect(self._set_installed_kind)
        irow = QHBoxLayout()
        irow.addWidget(self.installed_segmented)
        irow.addStretch()
        installed_root.addLayout(irow)

        installed_card = Card(margins=(10, 10, 10, 10), spacing=6)
        self.installed_title = label(_("Installed"), 10, muted=True)
        installed_card.lay.addWidget(self.installed_title)
        self.installed_list = QListWidget()
        self.installed_list.setSpacing(2)
        installed_card.lay.addWidget(self.installed_list, 1)
        installed_root.addWidget(installed_card, 1)

        ibuttons = QHBoxLayout()
        ibuttons.setSpacing(8)
        self.toggle_button = self._button(_(TOGGLE_TEXT["mod"]), self.toggle)
        ibuttons.addWidget(self.toggle_button)
        ibuttons.addStretch()
        ibuttons.addWidget(self._button(_("Delete"), self.delete, "danger"))
        ibuttons.addWidget(self._button(_("Open mods folder"), self.open_folder))
        ibuttons.addWidget(self._button(_("Refresh"), self.refresh_installed))
        installed_root.addLayout(ibuttons)

        self.tabs.addTab(installed_tab, _("Installed"))

        self.note = label("", 10, muted=True)
        root.addWidget(self.note)

    # ---- helpers ----
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

    def _folder(self, kind=None):
        inst = self.app.current_instance()
        kind = kind or self.kind
        if not inst or kind == "modpack":
            return None
        return instance_dir(inst) / modrinth.KIND_DIRS[kind]

    def _set_kind(self, kind):
        self.kind = kind
        self.hits = []
        self.result_list.clear()
        self.preset_button.setVisible(kind == "mod")

    def _set_installed_kind(self, kind):
        self.installed_kind = kind
        self.toggle_button.set_text(_(TOGGLE_TEXT[kind]))
        self.installed_title.setText(_("Instances") if kind == "modpack" else _("Installed"))
        self.refresh_installed()

    # ---- refresh ----
    def refresh(self):
        self.preset_button.setVisible(self.kind == "mod")
        self.refresh_installed()

    def refresh_installed(self):
        self.entries = []
        self.installed_list.clear()
        kind = self.installed_kind
        if kind == "modpack":
            for inst in self.app.cfg["instances"]:
                self.entries.append(inst["name"])
                self.installed_list.addItem(inst["name"])
            return
        folder = self._folder(kind)
        if not folder or not folder.exists():
            return
        enabled = set(options.enabled_resource_packs(folder.parent)) if kind == "resourcepack" else set()
        for name in sorted(os.listdir(folder)):
            if name == SKIN_PACK_NAME or name.endswith(".part"):
                continue
            if kind == "mod" and not _is_mod_file(name):
                continue
            self.entries.append(name)
            if kind == "resourcepack":
                mark = "●  " if name in enabled else "○  "
            elif kind == "mod":
                mark = "○  " if name.endswith(".disabled") else "●  "
            else:
                mark = ""
            info = _file_info(folder / name)
            self.installed_list.addItem(f"{mark}{name}   —   {info}" if info else mark + name)

    # ---- search ----
    def search(self):
        inst = self.app.current_instance()
        mc = inst["mc"] if inst else None
        loader = inst["loader"] if inst else "Vanilla"
        kind, query = self.kind, self.query.text().strip()
        self._say(_("Searching…"))

        def done(hits):
            if kind != self.kind:
                return
            self.hits = [search_hit_card(h) for h in hits]
            self.result_list.clear()
            for index, hit in enumerate(self.hits):
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 96))
                self.result_list.addItem(item)
                card = ModCard(hit, self._install_hit, self._open_hit)
                self.result_list.setItemWidget(item, card)
                self._load_icon(card, hit.get("icon_url"))
                if self._is_installed_hit(hit):
                    card.set_status(_("Installed"))
                    card.install_button.setEnabled(False)
                    card.install_button.set_text(_("Installed"))
            self._say(_("Found: {count}").format(count=len(self.hits)))
        self.app.run_async(lambda: modrinth.search(kind, query, mc, loader), done,
                           lambda _e: self._say(_("Search failed")))

    def _load_icon(self, card, url):
        if not url:
            return

        def job():
            try:
                from ...core.net import http_get
                return http_get(url, 15)
            except Exception:
                return b""

        def done(data):
            if data:
                card.set_icon(data)
        self.app.run_async(job, done, lambda _e: None)

    def _is_installed_hit(self, hit):
        if self.kind != "mod":
            return False
        folder = self._folder("mod")
        if not folder or not folder.exists():
            return False
        title = (hit.get("title") or "").lower().replace(" ", "")
        slug = (hit.get("slug") or "").lower()
        for name in os.listdir(folder):
            base = name[:-9] if name.endswith(".disabled") else name
            stem = base.rsplit(".", 1)[0].lower()
            if slug and slug in stem:
                return True
            if title and title in stem.replace(" ", ""):
                return True
        return False

    def _selected_hit(self):
        row = self.result_list.currentRow()
        return self.hits[row] if 0 <= row < len(self.hits) else None

    def _open_hit(self, hit):
        ProjectDialog(self.app, hit, self._install_hit).exec()

    def open_details(self):
        hit = self._selected_hit()
        if hit:
            self._open_hit(hit)

    # ---- install ----
    def install(self):
        hit = self._selected_hit()
        if hit:
            self._install_hit(hit, None)

    def _install_hit(self, hit, card):
        inst = self._instance()
        if not inst:
            return
        kind = self.kind
        if kind == "mod" and inst["loader"] in ("Vanilla", "OptiFine"):
            self.app.info(_("Mods need Fabric, Quilt, Forge or NeoForge"))
            return
        self._say(_("Installing…"))
        if card is not None:
            card.set_installing(True)
        if kind == "modpack":
            self.app.run_async(lambda: self._install_modpack(hit), self._modpack_done)
            return
        dest = self._folder(kind)
        loaders = modrinth.mod_loaders(inst["loader"]) if kind == "mod" else None
        log = lambda message: self.app.ui(self._say, message)  # noqa: E731

        def done(name):
            self._say(_("Installed: {name}").format(name=name) if name
                      else _("No compatible version found"))
            if card is not None:
                card.set_installing(False)
                if name:
                    card.set_status(_("Installed"))
            self.refresh_installed()
        self.app.run_async(lambda: modrinth.install_project(
            hit["project_id"], dest, inst["mc"], loaders, kind == "mod", log), done,
            lambda _e: card.set_installing(False) if card is not None else None)

    def _install_modpack(self, hit):
        versions = modrinth.project_versions(hit["project_id"])
        if not versions:
            raise RuntimeError(_("No versions available for this modpack"))
        file = modrinth.primary_file(versions[0])
        archive = DOWNLOADS / file["filename"]
        download(file["url"], archive, file.get("hashes", {}).get("sha1"), file.get("size"))
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
            # Bounded parallelism honouring the configured download mode.
            from ...core import net
            workers = net.configured_workers()
            with ThreadPoolExecutor(max_workers=min(workers, len(slugs)),
                                    thread_name_prefix="andromic-mods") as pool:
                def one(slug):
                    try:
                        modrinth.install_project(slug, dest, inst["mc"], loaders, True, log, seen)
                    except Exception as exc:
                        log(f"{slug}: {exc}")
                list(pool.map(one, slugs))

        def done(_result):
            self._say(_("Performance preset installed"))
            self.refresh_installed()
        self._say(_("Installing performance mods…"))
        self.app.run_async(job, done)

    # ---- installed actions ----
    def _selected_entry(self):
        row = self.installed_list.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def delete(self):
        name = self._selected_entry()
        if not name:
            return
        kind = self.installed_kind
        if kind == "modpack":
            self.app.pages["play"].delete_instance_by_name(name)
            return
        target = self._folder(kind) / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
        self.refresh_installed()

    def toggle(self):
        name = self._selected_entry()
        if not name:
            return
        kind = self.installed_kind
        if kind == "modpack":
            self.app.cfg["instance"] = name
            self.app.refresh()
            return
        folder = self._folder(kind)
        if kind == "mod":
            target = folder / (name[:-9] if name.endswith(".disabled") else name + ".disabled")
            (folder / name).rename(target)
        elif kind == "resourcepack":
            options.toggle_resource_pack(folder.parent, name)
        else:
            options.set_shader_pack(folder.parent, name)
            self._say(_("Shader pack applied: {name}").format(name=name))
        self.refresh_installed()

    def open_folder(self):
        folder = self._folder(self.installed_kind)
        if folder:
            folder.mkdir(parents=True, exist_ok=True)
            open_path(folder)


def _is_mod_file(name: str) -> bool:
    base = name[:-9] if name.endswith(".disabled") else name
    return base.lower().endswith((".jar", ".zip"))


def _file_info(path) -> str:
    try:
        stat = path.stat()
    except OSError:
        return ""
    from ...core.net import format_bytes
    if path.is_dir():
        return _("folder")
    return format_bytes(stat.st_size)

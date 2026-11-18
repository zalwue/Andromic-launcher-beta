import os
import shutil
import tkinter as tk
from tkinter import messagebox

from ... import APP_NAME
from ...core import modrinth, options
from ...core.instances import instance_dir
from ...core.modpacks import install_mrpack
from ...core.net import download
from ...core.paths import DOWNLOADS
from ...core.accounts import SKIN_PACK_NAME
from ...core.system import open_path
from ...i18n import tr as _
from ..widgets import Button, Card, Field, Segmented, label, styled_listbox

KINDS = (("mod", "Mods"), ("resourcepack", "Resource packs"),
         ("shader", "Shaders"), ("modpack", "Modpacks"))


class ContentPage:
    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=parent["bg"])
        self.kind = "mod"
        self.hits, self.entries = [], []
        self.query = tk.StringVar()
        bg = parent["bg"]

        label(self.frame, _("Content"), 20, bold=True).pack(anchor="w", pady=(0, 12))
        Segmented(self.frame, [(k, _(t)) for k, t in KINDS], self._set_kind).pack(anchor="w")

        search = tk.Frame(self.frame, bg=bg)
        search.pack(fill="x", pady=14)
        search.columnconfigure(0, weight=1)
        Field(search, self.query).grid(row=0, column=0, sticky="ew")
        Button(search, _("Search Modrinth"), self.search, kind="primary", height=40).grid(
            row=0, column=1, padx=(8, 0))

        columns = tk.Frame(self.frame, bg=bg)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure((0, 1), weight=1, uniform="col")
        columns.rowconfigure(0, weight=1)

        results = Card(columns, stretch=True, pad=14)
        results.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        results.body.rowconfigure(1, weight=1)
        results.body.columnconfigure(0, weight=1)
        label(results.body, _("Results"), 10, muted=True).grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.result_list = styled_listbox(results.body)
        self.result_list.grid(row=1, column=0, sticky="nsew")

        installed = Card(columns, stretch=True, pad=14)
        installed.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        installed.body.rowconfigure(1, weight=1)
        installed.body.columnconfigure(0, weight=1)
        self.installed_title = label(installed.body, _("Installed"), 10, muted=True)
        self.installed_title.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.installed_list = styled_listbox(installed.body)
        self.installed_list.grid(row=1, column=0, sticky="nsew")

        buttons = tk.Frame(self.frame, bg=bg)
        buttons.pack(fill="x", pady=(14, 0))
        self.install_button = Button(buttons, _("Install"), self.install, kind="primary", height=38)
        self.install_button.pack(side="left", padx=(0, 8))
        self.preset_button = Button(buttons, _("FPS preset"), self.fps_preset, height=38)
        self.preset_button.pack(side="left")
        Button(buttons, _("Folder"), self.open_folder, height=38).pack(side="right")
        Button(buttons, _("Delete"), self.delete, kind="danger", height=38).pack(side="right", padx=8)
        self.toggle_button = Button(buttons, _("Toggle"), self.toggle, height=38)
        self.toggle_button.pack(side="right")
        self.note = label(self.frame, "", 10, muted=True)
        self.note.pack(anchor="w", pady=(10, 0))

    # ---- helpers ----
    def _say(self, text):
        self.note.configure(text=text)

    def _instance(self):
        inst = self.app.current_instance()
        if inst is None:
            messagebox.showinfo(APP_NAME, _("Create an instance first"))
        return inst

    def _folder(self):
        inst = self.app.current_instance()
        if not inst or self.kind == "modpack":
            return None
        return instance_dir(inst) / modrinth.KIND_DIRS[self.kind]

    def _set_kind(self, kind):
        self.kind = kind
        self.hits = []
        self.result_list.delete(0, "end")
        self.refresh()

    def refresh(self):
        is_mod = self.kind == "mod"
        self.preset_button.pack_forget()
        if is_mod:
            self.preset_button.pack(side="left")
        self.toggle_button.set_text({"mod": _("Enable / disable"), "resourcepack": _("Enable / disable"),
                                     "shader": _("Apply"), "modpack": _("Select")}[self.kind])
        self.installed_title.configure(text=_("Instances") if self.kind == "modpack" else _("Installed"))
        self.entries = []
        self.installed_list.delete(0, "end")
        if self.kind == "modpack":
            for inst in self.app.cfg["instances"]:
                self.entries.append(inst["name"])
                self.installed_list.insert("end", inst["name"])
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
            self.installed_list.insert("end", mark + name)

    # ---- search / install ----
    def search(self):
        inst = self.app.current_instance()
        mc = inst["mc"] if inst else None
        loader = inst["loader"] if inst else "Vanilla"
        kind, query = self.kind, self.query.get().strip()
        self._say(_("Searching…"))

        def done(hits):
            if kind != self.kind:
                return
            self.hits = hits
            self.result_list.delete(0, "end")
            for hit in hits:
                self.result_list.insert("end", f"{hit['title']}  —  {hit['description'][:60]}")
            self._say(_("Found: {count}").format(count=len(hits)))
        self.app.run_async(lambda: modrinth.search(kind, query, mc, loader), done)

    def _selected_hit(self):
        selection = self.result_list.curselection()
        return self.hits[selection[0]] if selection else None

    def install(self):
        hit, inst = self._selected_hit(), self._instance()
        if not hit or not inst:
            return
        kind = self.kind
        if kind == "mod" and inst["loader"] in ("Vanilla", "OptiFine"):
            messagebox.showinfo(APP_NAME, _("Mods need Fabric, Quilt, Forge or NeoForge"))
            return
        self._say(_("Installing…"))
        if kind == "modpack":
            self.app.run_async(lambda: self._install_modpack(hit), self._modpack_done)
            return
        dest = self._folder()
        loaders = modrinth.mod_loaders(inst["loader"]) if kind == "mod" else None
        log = lambda m: self.app.ui(self._say, m)  # noqa: E731
        self.app.run_async(
            lambda: modrinth.install_project(hit["project_id"], dest, inst["mc"], loaders,
                                             kind == "mod", log),
            lambda name: (self._say(_("Installed: {name}").format(name=name) if name
                                    else _("No compatible version found")), self.refresh()))

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
            messagebox.showinfo(APP_NAME, _("Mods need Fabric, Quilt, Forge or NeoForge"))
            return
        dest = instance_dir(inst) / "mods"
        loaders = modrinth.mod_loaders(inst["loader"])
        log = lambda m: self.app.ui(self._say, m)  # noqa: E731

        def job():
            seen = set()
            for slug in slugs:
                try:
                    modrinth.install_project(slug, dest, inst["mc"], loaders, True, log, seen)
                except Exception as exc:
                    log(f"{slug}: {exc}")
        self._say(_("Installing performance mods…"))
        self.app.run_async(job, lambda _r: (self._say(_("Performance preset installed")), self.refresh()))

    # ---- installed list actions ----
    def _selected_entry(self):
        selection = self.installed_list.curselection()
        return self.entries[selection[0]] if selection else None

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
            target = (folder / name[:-9]) if name.endswith(".disabled") else (folder / (name + ".disabled"))
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

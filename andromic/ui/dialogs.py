"""Modal dialogs."""
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

from .. import APP_NAME
from ..core import optifine
from ..core.constants import LOADERS, OPTIFINE_DOWNLOADS
from ..core.instances import instance_dir, new_instance, unique_name
from ..core.loaders import loader_versions
from ..core.versions import selectable_ids
from ..i18n import tr as _
from .widgets import Button, Field, Modal, Select, label, switch_row


class InstanceDialog:
    """Create or edit an instance."""

    def __init__(self, app, instance, on_saved):
        self.app, self.instance, self.on_saved = app, instance, on_saved
        self.win = Modal(app.root, _("Edit instance") if instance else _("New instance"), 480, 600)
        body = tk.Frame(self.win, bg=self.win["bg"])
        body.pack(fill="both", expand=True, padx=26, pady=22)
        body.columnconfigure(0, weight=1)

        self.name = tk.StringVar(value=instance["name"] if instance else _("New instance"))
        self.mc = tk.StringVar(value=instance["mc"] if instance else "")
        self.loader = tk.StringVar(value=instance["loader"] if instance else "Vanilla")
        self.lv = tk.StringVar(value=instance["lv"] if instance else "")
        self.server = tk.StringVar(value=instance.get("server", "") if instance else "")
        self.snapshots = tk.BooleanVar(value=False)

        row = 0
        for text, widget in (
            (_("Name"), Field(body, self.name)),
            (_("Minecraft version"), None),
        ):
            label(body, text, 10, muted=True).grid(row=row, column=0, sticky="w", pady=(10, 4))
            if widget:
                widget.grid(row=row + 1, column=0, sticky="ew")
            row += 2
        self.mc_select = Select(body, self.mc, command=lambda _v: self._refresh_loader())
        self.mc_select.grid(row=row - 1, column=0, sticky="ew")
        switch_row(body, _("Show snapshots"), self.snapshots).grid(row=row, column=0, sticky="ew", pady=(10, 0))
        self.snapshots.trace_add("write", lambda *_a: self._fill_versions())
        row += 1

        label(body, _("Mod loader"), 10, muted=True).grid(row=row, column=0, sticky="w", pady=(12, 4))
        Select(body, self.loader, LOADERS, command=lambda _v: self._refresh_loader()).grid(
            row=row + 1, column=0, sticky="ew")
        row += 2
        self.lv_label = label(body, _("Loader version"), 10, muted=True)
        self.lv_label.grid(row=row, column=0, sticky="w", pady=(12, 4))
        self.lv_select = Select(body, self.lv)
        self.lv_select.grid(row=row + 1, column=0, sticky="ew")
        row += 2

        self.optifine_row = tk.Frame(body, bg=body["bg"])
        self.optifine_row.grid(row=row, column=0, sticky="ew", pady=(10, 0))
        Button(self.optifine_row, _("Get OptiFine"), lambda: webbrowser.open(OPTIFINE_DOWNLOADS),
               height=34).pack(side="left", padx=(0, 8))
        Button(self.optifine_row, _("Install from jar"), self._install_optifine,
               height=34).pack(side="left")
        row += 1

        label(body, _("Auto-join server (optional)"), 10, muted=True).grid(
            row=row, column=0, sticky="w", pady=(12, 4))
        Field(body, self.server).grid(row=row + 1, column=0, sticky="ew")

        buttons = tk.Frame(self.win, bg=self.win["bg"])
        buttons.pack(side="bottom", fill="x", padx=26, pady=(0, 22))
        Button(buttons, _("Save"), self._save, kind="primary", height=42).pack(side="right")
        Button(buttons, _("Cancel"), self.win.destroy, height=42).pack(side="right", padx=8)

        self._fill_versions()

    def _fill_versions(self):
        ids = selectable_ids(self.app.manifest, self.snapshots.get())
        self.mc_select.set_values(ids)
        if self.mc.get() not in ids and ids:
            self.mc.set(ids[0])
        self._refresh_loader()

    def _refresh_loader(self):
        loader, mc = self.loader.get(), self.mc.get()
        if loader == "OptiFine":
            self.optifine_row.grid()
        else:
            self.optifine_row.grid_remove()
        if loader == "Vanilla" or not mc:
            self.lv.set("")
            self.lv_select.set_values([])
            self.lv_label.grid_remove()
            self.lv_select.grid_remove()
            return
        self.lv_label.grid()
        self.lv_select.grid()
        if loader == "OptiFine":
            self._set_lv(loader, mc, optifine.installed_versions(mc))
            return
        self.lv.set(_("Loading…"))

        def job():
            try:
                return loader_versions(loader, mc)
            except Exception:
                return []
        self.app.run_async(job, lambda versions: self._set_lv(loader, mc, versions))

    def _set_lv(self, loader, mc, versions):
        if not self.win.winfo_exists() or (loader, mc) != (self.loader.get(), self.mc.get()):
            return
        self.lv_select.set_values(versions)
        current = self.lv.get()
        self.lv.set(current if current in versions else (versions[0] if versions else _("None available")))

    def _install_optifine(self):
        path = filedialog.askopenfilename(
            parent=self.win, title="OptiFine", filetypes=[("OptiFine", "OptiFine_*.jar"), ("JAR", "*.jar")])
        if not path:
            return
        cfg = dict(self.app.cfg)

        def done(version_id):
            self.app.pages["play"].set_status(_("OptiFine installed"))
            self._refresh_loader()
            self.lv.set(version_id)

        self.app.pages["play"].set_status(_("Installing OptiFine"))
        self.app.run_async(
            lambda: optifine.install(path, self.app.manifest, cfg["java_path"], self.app.rep), done)

    def _save(self):
        name = self.name.get().strip()
        loader, lv = self.loader.get(), self.lv.get()
        if not name or not self.mc.get():
            return
        if loader != "Vanilla" and (not lv or lv in (_("Loading…"), _("None available"))):
            messagebox.showinfo(APP_NAME, _("Choose a loader version"), parent=self.win)
            return
        instances = self.app.cfg["instances"]
        others = [i["name"] for i in instances if i is not self.instance]
        if name.lower() in (n.lower() for n in others):
            name = unique_name(name, others)
        record = new_instance(name, self.mc.get(), loader, lv if loader != "Vanilla" else "",
                              self.server.get().strip())
        if self.instance is None:
            instances.append(record)
        else:
            if self.instance["name"] != name:
                old_dir, new_dir = instance_dir(self.instance), instance_dir(record)
                if old_dir.exists() and not new_dir.exists():
                    old_dir.rename(new_dir)
            instances[instances.index(self.instance)] = record
        self.win.destroy()
        self.on_saved(name)

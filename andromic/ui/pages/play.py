import shutil
import tkinter as tk
from tkinter import messagebox

from ... import APP_NAME
from ...core import accounts, crash
from ...core.instances import backup_worlds, instance_dir
from ...core.java import guess_major
from ...core.launcher import GameLauncher
from ...core.system import open_path
from ...i18n import tr as _
from ..avatars import head_image
from ..dialogs import InstanceDialog
from ..widgets import Button, Card, Progress, Select, label


class PlayPage:
    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=parent["bg"])
        bg = parent["bg"]

        label(self.frame, _("Play"), 20, bold=True).pack(anchor="w", pady=(0, 14))

        account = Card(self.frame)
        account.pack(fill="x", pady=(0, 14))
        body = account.body
        body.columnconfigure(1, weight=1)
        self.avatar = tk.Label(body, bg=body["bg"], bd=0)
        self.avatar.grid(row=0, column=0, rowspan=2, padx=(0, 16))
        self.nick_label = label(body, "", 16, bold=True)
        self.nick_label.grid(row=0, column=1, sticky="sw")
        label(body, _("Offline profile"), 10, muted=True).grid(row=1, column=1, sticky="nw")
        self.account_var = tk.StringVar()
        self.account_select = Select(body, self.account_var, width=190, command=self._account_picked)
        self.account_select.grid(row=0, column=2, rowspan=2, sticky="e")

        build = Card(self.frame)
        build.pack(fill="x", pady=(0, 14))
        body = build.body
        body.columnconfigure(0, weight=1)
        label(body, _("Instance"), 10, muted=True).grid(row=0, column=0, sticky="w")
        self.instance_var = tk.StringVar()
        self.instance_select = Select(body, self.instance_var, command=self._instance_picked)
        self.instance_select.grid(row=1, column=0, sticky="ew", pady=(6, 10))
        actions = tk.Frame(body, bg=body["bg"])
        actions.grid(row=1, column=1, padx=(12, 0), sticky="e")
        Button(actions, _("New"), self.new_instance, height=40).pack(side="left", padx=(0, 6))
        Button(actions, _("Edit"), self.edit_instance, height=40).pack(side="left", padx=(0, 6))
        Button(actions, _("Delete"), self.delete_instance, kind="danger", height=40).pack(side="left")
        self.info = label(body, "", 10, muted=True)
        self.info.grid(row=2, column=0, columnspan=2, sticky="w")

        self.play_button = Button(self.frame, _("Play"), self.start, kind="primary",
                                  height=56, size=14, bold=True)
        self.play_button.pack(fill="x", pady=(2, 14))
        self.progress = Progress(self.frame)
        self.progress.pack(fill="x")
        self.status = label(self.frame, "", 10, muted=True)
        self.status.pack(anchor="w", pady=(8, 0))

        tools = tk.Frame(self.frame, bg=bg)
        tools.pack(anchor="w", pady=(18, 0))
        Button(tools, _("Open folder"), self.open_folder, height=36).pack(side="left", padx=(0, 8))
        Button(tools, _("Back up worlds"), self.backup, height=36).pack(side="left")

    # ---- display ----
    def set_status(self, text):
        self.status.configure(text=text)

    def set_progress(self, done, total, text=""):
        self.progress.set(done, total)
        if text:
            self.set_status(f"{text} ({done}/{total})")

    def _account_labels(self):
        labels, seen = {}, set()
        for acc in self.app.cfg["accounts"]:
            name = acc["nick"] if acc["nick"] not in seen else f"{acc['nick']} ({acc['id'][:4]})"
            seen.add(acc["nick"])
            labels[name] = acc["id"]
        return labels

    def refresh(self):
        cfg = self.app.cfg
        acc = self.app.current_account()
        labels = self._account_labels()
        self.account_select.set_values(list(labels))
        current = next((n for n, i in labels.items() if i == acc["id"]), acc["nick"])
        self.account_var.set(current)
        self.nick_label.configure(text=acc["nick"])
        self.avatar.configure(image=head_image(accounts.skin_file(acc), 64, self.app.images))

        names = [i["name"] for i in cfg["instances"]]
        self.instance_select.set_values(names)
        inst = self.app.current_instance()
        if inst:
            cfg["instance"] = inst["name"]
            self.instance_var.set(inst["name"])
            loader = inst["loader"] if inst["loader"] == "Vanilla" else f"{inst['loader']} {inst['lv']}"
            major = guess_major(inst["mc"])
            java = _("Java {major} (auto)").format(major=major) if major else _("Java (auto)")
            self.info.configure(text=f"{inst['mc']}  ·  {loader}  ·  {java}")
        else:
            self.instance_var.set("")
            self.info.configure(text=_("Create an instance to start playing"))

    def _account_picked(self, name):
        self.app.cfg["account"] = self._account_labels()[name]
        self.refresh()

    def _instance_picked(self, name):
        self.app.cfg["instance"] = name
        self.refresh()

    # ---- instances ----
    def new_instance(self):
        InstanceDialog(self.app, None, self._saved)

    def edit_instance(self):
        inst = self.app.current_instance()
        if inst:
            InstanceDialog(self.app, inst, self._saved)

    def _saved(self, name):
        self.app.cfg["instance"] = name
        self.app.save()
        self.app.refresh()

    def delete_instance(self):
        inst = self.app.current_instance()
        if inst:
            self.delete_instance_by_name(inst["name"])

    def delete_instance_by_name(self, name):
        instances = self.app.cfg["instances"]
        inst = next((i for i in instances if i["name"] == name), None)
        if inst is None:
            return
        if len(instances) <= 1:
            messagebox.showinfo(APP_NAME, _("At least one instance must remain"))
            return
        if not messagebox.askyesno(APP_NAME, _("Delete instance \"{name}\" and all its files?")
                                   .format(name=name)):
            return
        shutil.rmtree(instance_dir(inst), ignore_errors=True)
        instances.remove(inst)
        self.app.cfg["instance"] = instances[0]["name"]
        self.app.save()
        self.app.refresh()

    def open_folder(self):
        inst = self.app.current_instance()
        if inst:
            folder = instance_dir(inst)
            folder.mkdir(parents=True, exist_ok=True)
            open_path(folder)

    def backup(self):
        inst = self.app.current_instance()
        if not inst:
            return
        self.set_status(_("Backing up worlds"))

        def done(path):
            self.set_status(_("Backup saved: {name}").format(name=path.name) if path
                            else _("No worlds to back up"))
        self.app.run_async(lambda: backup_worlds(inst), done)

    # ---- launching ----
    def start(self, server=None):
        app = self.app
        inst, acc = app.current_instance(), app.current_account()
        if inst and server:
            inst = {**inst, "server": server}
        if app.busy:
            return
        if not inst or not app.manifest:
            messagebox.showinfo(APP_NAME, _("Versions are still loading"))
            return
        app.save()
        app.busy = True
        self.play_button.set_enabled(False)
        cfg = dict(app.cfg)
        launcher = GameLauncher(app.manifest, app.rep)

        def job():
            return launcher.run(
                cfg, inst, acc,
                on_java=lambda m: app.ui(self.info.configure, text=self.info["text"].rsplit("·", 1)[0]
                                         + "·  " + _("Java {major} (auto)").format(major=m)),
                on_start=(lambda: app.ui(app.root.withdraw)) if cfg["hide_launcher"] else None)

        def finished(code):
            app.busy = False
            self.play_button.set_enabled(True)
            app.root.deiconify()
            self.set_status(_("Ready") if code == 0 else
                            _("Game exited with code {code}").format(code=code))
            if code != 0:
                hints = crash.analyze(launcher.log_tail)
                message = "\n\n".join(hints) if hints else _("The game crashed. See the console for details.")
                messagebox.showwarning(APP_NAME, message)

        def failed(_exc):
            app.busy = False
            self.play_button.set_enabled(True)
            app.root.deiconify()

        app.run_async(job, finished, failed)

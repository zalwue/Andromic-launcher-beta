import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ...core import accounts, crash
from ...core.instances import backup_worlds, instance_dir
from ...core.java import guess_major
from ...core.launcher import GameLauncher
from ...core.system import open_path
from ...i18n import tr as _
from ..avatars import head_pixmap
from ..dialogs import InstanceDialog
from ..widgets import Button, Card, Select, label, page_title


class PlayPage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(page_title(_("Play")))

        account = Card()
        row = QHBoxLayout()
        row.setSpacing(16)
        self.avatar = QLabel()
        self.avatar.setFixedSize(64, 64)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.nick_label = label("", 16, bold=True)
        texts.addStretch()
        texts.addWidget(self.nick_label)
        texts.addWidget(label(_("Offline profile"), 10, muted=True))
        texts.addStretch()
        self.account_select = Select()
        self.account_select.setMinimumWidth(210)
        self.account_select.picked.connect(self._account_picked)
        row.addWidget(self.avatar)
        row.addLayout(texts)
        row.addStretch()
        row.addWidget(self.account_select)
        account.lay.addLayout(row)
        root.addWidget(account)

        build = Card()
        build.lay.addWidget(label(_("Instance"), 10, muted=True))
        pick = QHBoxLayout()
        pick.setSpacing(8)
        self.instance_select = Select()
        self.instance_select.picked.connect(self._instance_picked)
        pick.addWidget(self.instance_select, 1)
        for text, kind, callback in ((_("New"), "tonal", self.new_instance),
                                     (_("Edit"), "tonal", self.edit_instance),
                                     (_("Delete"), "danger", self.delete_instance)):
            button = Button(text, kind, 40)
            button.clicked.connect(lambda _checked=False, cb=callback: cb())
            pick.addWidget(button)
        build.lay.addLayout(pick)
        self.info = label("", 10, muted=True)
        build.lay.addWidget(self.info)
        root.addWidget(build)

        self.play_button = Button(_("Play"), "primary", 58, icon="play", size=14, bold=True)
        self.play_button.clicked.connect(lambda _checked=False: self.start())
        root.addWidget(self.play_button)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        root.addWidget(self.progress)
        self.status = label("", 10, muted=True)
        root.addWidget(self.status)

        tools = QHBoxLayout()
        for text, callback in ((_("Open folder"), self.open_folder), (_("Back up worlds"), self.backup)):
            button = Button(text, height=36)
            button.clicked.connect(lambda _checked=False, cb=callback: cb())
            tools.addWidget(button)
        tools.addStretch()
        root.addLayout(tools)
        root.addStretch()

    # ---- display ----
    def set_status(self, text):
        self.status.setText(text)

    def set_progress(self, done, total, text=""):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
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
        self.account_select.set_value(next((n for n, i in labels.items() if i == acc["id"]), acc["nick"]))
        self.nick_label.setText(acc["nick"])
        self.avatar.setPixmap(head_pixmap(accounts.skin_file(acc), 64))

        self.instance_select.set_values([i["name"] for i in cfg["instances"]])
        inst = self.app.current_instance()
        if inst:
            cfg["instance"] = inst["name"]
            self.instance_select.set_value(inst["name"])
            loader = inst["loader"] if inst["loader"] == "Vanilla" else f"{inst['loader']} {inst['lv']}"
            major = guess_major(inst["mc"])
            self._base_info = f"{inst['mc']}  ·  {loader}"
            self.set_java(major)
        else:
            self._base_info = ""
            self.info.setText(_("Create an instance to start playing"))

    def set_java(self, major):
        java = _("Java {major} (auto)").format(major=major) if major else _("Java (auto)")
        self.info.setText(f"{self._base_info}  ·  {java}")

    def _account_picked(self, name):
        self.app.cfg["account"] = self._account_labels()[name]
        self.app.refresh()

    def _instance_picked(self, name):
        self.app.cfg["instance"] = name
        self.refresh()

    # ---- instances ----
    def new_instance(self):
        InstanceDialog(self.app, None, self._saved).exec()

    def edit_instance(self):
        inst = self.app.current_instance()
        if inst:
            InstanceDialog(self.app, inst, self._saved).exec()

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
            self.app.info(_("At least one instance must remain"))
            return
        if not self.app.ask(_("Delete instance \"{name}\" and all its files?").format(name=name)):
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
            app.info(_("Versions are still loading"))
            return
        app.save()
        app.busy = True
        self.play_button.setEnabled(False)
        cfg = dict(app.cfg)
        launcher = GameLauncher(app.manifest, app.rep)

        def job():
            return launcher.run(
                cfg, inst, acc,
                on_java=lambda major: app.ui(self.set_java, major),
                on_start=(lambda: app.ui(app.window.hide)) if cfg["hide_launcher"] else None)

        def finished(code):
            app.busy = False
            self.play_button.setEnabled(True)
            app.window.show()
            self.set_status(_("Ready") if code == 0 else
                            _("Game exited with code {code}").format(code=code))
            if code != 0:
                hints = crash.analyze(launcher.log_tail)
                app.warn("\n\n".join(hints) if hints
                         else _("The game crashed. See the console for details."))

        def failed(_exc):
            app.busy = False
            self.play_button.setEnabled(True)
            app.window.show()

        app.run_async(job, finished, failed)

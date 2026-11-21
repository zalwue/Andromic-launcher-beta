"""World manager and backup browser."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QListWidget,
                               QVBoxLayout, QWidget)

from ...core import backup, worlds
from ...core.paths import BACKUPS
from ...core.system import open_path
from ...i18n import tr as _
from ..widgets import Button, Card, Field, Select, label, page_title


def _size_text(value: int) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class WorldsPage:
    def __init__(self, app):
        self.app = app
        self.worlds, self.backups = [], []
        self.frame = QWidget()
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(page_title(_("Worlds and backups")))

        columns = QHBoxLayout()
        columns.setSpacing(12)
        root.addLayout(columns, 1)

        left = Card(margins=(14, 14, 14, 14), spacing=8)
        left.lay.addWidget(label(_("World manager"), 12, bold=True))
        self.world_list = QListWidget()
        self.world_list.currentRowChanged.connect(self._world_selected)
        self.world_list.itemDoubleClicked.connect(lambda _item: self.open_world())
        left.lay.addWidget(self.world_list, 1)
        grid_one = QHBoxLayout()
        grid_two = QHBoxLayout()
        for text, callback in ((_("Open world folder"), self.open_world),
                               (_("Rename world"), self.rename_world),
                               (_("Duplicate world"), self.duplicate_world)):
            button = Button(text, height=34)
            button.clicked.connect(lambda _c=False, cb=callback: cb())
            grid_one.addWidget(button)
        for text, callback in ((_("Export world"), self.export_world),
                               (_("Import world"), self.import_world),
                               (_("Delete world"), self.delete_world)):
            button = Button(text, "danger" if text == _("Delete world") else "tonal", 34)
            button.clicked.connect(lambda _c=False, cb=callback: cb())
            grid_two.addWidget(button)
        left.lay.addLayout(grid_one)
        left.lay.addLayout(grid_two)
        columns.addWidget(left, 1)

        right = Card(margins=(16, 14, 16, 14), spacing=7)
        right.lay.addWidget(label(_("World details"), 12, bold=True))
        self.details = {}
        for key, caption in (("name", _("Name")), ("last_played", _("Last played")),
                             ("game_type", _("Game mode")), ("difficulty", _("Difficulty")),
                             ("version", _("Version")), ("size", _("Size")),
                             ("folder", _("Folder"))):
            row = QHBoxLayout()
            row.addWidget(label(caption, 9, muted=True), 0)
            value = label("—", 10, wrap=True)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(value, 1)
            right.lay.addLayout(row)
            self.details[key] = value
        self.world_error = label("", 9, muted=True, wrap=True)
        right.lay.addWidget(self.world_error)
        right.lay.addStretch()
        columns.addWidget(right, 1)

        backups = Card(margins=(14, 12, 14, 12), spacing=7)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(label(_("Backups"), 12, bold=True))
        top.addStretch()
        self.scope = Select([_("Worlds only"), _("Full instance")])
        self.scope.setFixedWidth(170)
        top.addWidget(self.scope)
        self.note_field = Field(placeholder=_("Note (optional)"))
        self.note_field.setFixedWidth(180)
        top.addWidget(self.note_field)
        create = Button(_("Create backup"), "primary", 36)
        create.clicked.connect(lambda _c=False: self.create_backup())
        top.addWidget(create)
        backups.lay.addLayout(top)
        self.backup_list = QListWidget()
        self.backup_list.setMaximumHeight(132)
        backups.lay.addWidget(self.backup_list)
        actions = QHBoxLayout()
        for text, callback, kind in ((_("Restore backup"), self.restore_backup, "primary"),
                                     (_("Verify backup"), self.verify_backup, "tonal"),
                                     (_("Delete backup"), self.delete_backup, "danger")):
            button = Button(text, kind, 34)
            button.clicked.connect(lambda _c=False, cb=callback: cb())
            actions.addWidget(button)
        actions.addStretch()
        folder = Button(_("Open backups folder"), height=34)
        folder.clicked.connect(lambda _c=False: open_path(BACKUPS))
        actions.addWidget(folder)
        backups.lay.addLayout(actions)
        root.addWidget(backups)

        self.status = label("", 9, muted=True)
        root.addWidget(self.status)

    def _say(self, text):
        self.status.setText(text)

    def _instance(self):
        inst = self.app.current_instance()
        if inst is None:
            self.app.info(_("Create an instance first"))
        return inst

    def _selected_world(self):
        row = self.world_list.currentRow()
        return self.worlds[row] if 0 <= row < len(self.worlds) else None

    def _selected_backup(self):
        row = self.backup_list.currentRow()
        return self.backups[row] if 0 <= row < len(self.backups) else None

    def refresh(self):
        inst = self.app.current_instance()
        self.worlds = worlds.list_worlds(inst) if inst else []
        self.world_list.blockSignals(True)
        self.world_list.clear()
        for info in self.worlds:
            marker = "⚠  " if info.get("error") else "●  "
            self.world_list.addItem(marker + str(info.get("name") or info["folder"]))
        self.world_list.blockSignals(False)
        if self.worlds:
            self.world_list.setCurrentRow(0)
        else:
            self._world_selected(-1)
        self.backups = backup.list_backups(inst) if inst else []
        self.backup_list.clear()
        for info in self.backups:
            created = str(info.get("created") or "").replace("T", " ")[:19]
            note = f"  —  {info['note']}" if info.get("note") else ""
            self.backup_list.addItem(f"{created}  ·  {info['name']}{note}")

    def _world_selected(self, row):
        info = self.worlds[row] if 0 <= row < len(self.worlds) else None
        if not info:
            for value in self.details.values():
                value.setText("—")
            self.world_error.setText("")
            return
        self.details["name"].setText(str(info.get("name") or info["folder"]))
        self.details["last_played"].setText(str(info.get("last_played") or "—").replace("T", " "))
        self.details["game_type"].setText(str(info.get("game_type") or "—"))
        self.details["difficulty"].setText(str(info.get("difficulty") or "—"))
        self.details["version"].setText(str(info.get("version") or "—"))
        self.details["size"].setText(_size_text(info.get("size", 0)))
        self.details["folder"].setText(str(info.get("folder", "")))
        self.world_error.setText(_("Broken world: {error}").format(error=info["error"])
                                 if info.get("error") else "")

    def open_world(self):
        info = self._selected_world()
        if not info:
            self._say(_("Select a world first"))
            return
        open_path(info["path"])

    def rename_world(self):
        info, inst = self._selected_world(), self._instance()
        if not info or not inst:
            self._say(_("Select a world first"))
            return
        name, ok = QInputDialog.getText(self.frame, _("Rename world"), _("New world name"),
                                        text=str(info.get("name") or info["folder"]))
        if not ok or not name.strip():
            return
        try:
            worlds.rename_world(inst, info["folder"], name.strip())
            self._say(_("World renamed"))
            self.refresh()
        except (OSError, ValueError) as exc:
            self.app.error(str(exc))

    def duplicate_world(self):
        info, inst = self._selected_world(), self._instance()
        if not info or not inst:
            self._say(_("Select a world first"))
            return
        try:
            worlds.duplicate_world(inst, info["folder"])
            self._say(_("World duplicated"))
            self.refresh()
        except (OSError, ValueError) as exc:
            self.app.error(str(exc))

    def export_world(self):
        info, inst = self._selected_world(), self._instance()
        if not info or not inst:
            self._say(_("Select a world first"))
            return
        suggested = str(Path.home() / f"{info['folder']}.zip")
        path, _filter = QFileDialog.getSaveFileName(self.frame, _("Export world"), suggested,
                                                    "ZIP (*.zip)")
        if not path:
            return
        try:
            target = worlds.export_world(inst, info["folder"], path)
            self._say(_("World exported: {name}").format(name=target.name))
        except (OSError, ValueError) as exc:
            self.app.error(str(exc))

    def import_world(self):
        inst = self._instance()
        if not inst:
            return
        path, _filter = QFileDialog.getOpenFileName(self.frame, _("Import world"), "",
                                                    "ZIP (*.zip)")
        if not path:
            return
        try:
            target = worlds.import_world(inst, path)
            self._say(_("World imported: {name}").format(name=target.name))
            self.refresh()
        except (OSError, ValueError) as exc:
            self.app.error(str(exc))

    def delete_world(self):
        info, inst = self._selected_world(), self._instance()
        if not info or not inst:
            self._say(_("Select a world first"))
            return
        if not self.app.ask(_("Delete world \"{name}\" permanently?")
                            .format(name=info.get("name") or info["folder"])):
            return
        try:
            worlds.delete_world(inst, info["folder"])
            self._say(_("World deleted"))
            self.refresh()
        except OSError as exc:
            self.app.error(str(exc))

    # ---- backups ----
    def create_backup(self):
        inst = self._instance()
        if not inst:
            return
        scope = "worlds" if self.scope.currentIndex() == 0 else "instance"
        note = self.note_field.text().strip()
        self._say(_("Backing up…"))

        def done(path):
            if path is None:
                self._say(_("No worlds to back up"))
                return
            self.note_field.clear()
            self._say(_("Backup created: {name}").format(name=path.name))
            self.refresh()
        self.app.run_async(lambda: backup.create_backup(inst, scope, note), done)

    def restore_backup(self):
        info, inst = self._selected_backup(), self._instance()
        if not info or not inst:
            self._say(_("Select a backup first"))
            return
        if not self.app.ask(_("Restore backup \"{name}\" into the current instance? "
                              "Existing files will be overwritten.").format(name=info["name"])):
            return
        self._say(_("Restoring…"))

        def done(_target):
            self._say(_("Backup restored"))
            self.refresh()
        self.app.run_async(lambda: backup.restore_backup(info["path"], inst), done)

    def delete_backup(self):
        info = self._selected_backup()
        if not info:
            self._say(_("Select a backup first"))
            return
        if not self.app.ask(_("Delete backup \"{name}\"?").format(name=info["name"])):
            return
        backup.delete_backup(info["path"])
        self._say(_("Backup deleted"))
        self.refresh()

    def verify_backup(self):
        info = self._selected_backup()
        if not info:
            self._say(_("Select a backup first"))
            return

        def done(result):
            if result["valid"]:
                self.app.info(_("Backup is valid"))
            else:
                self.app.error(_("Backup is damaged: {error}").format(error=result["error"]))
        self.app.run_async(lambda: backup.verify_backup(info["path"]), done)

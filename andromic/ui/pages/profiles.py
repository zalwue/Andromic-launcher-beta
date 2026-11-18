import random

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QVBoxLayout,
                               QWidget)

from ...core import accounts
from ...i18n import tr as _
from ..avatars import head_pixmap
from ..widgets import Button, Card, Field, ToggleRow, label, page_title


class ProfilesPage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        self.edit_id = app.cfg["account"]
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(page_title(_("Profiles")))
        columns = QHBoxLayout()
        columns.setSpacing(14)
        root.addLayout(columns, 1)

        left = Card(margins=(14, 14, 14, 14))
        left.setFixedWidth(240)
        self.listbox = QListWidget()
        self.listbox.currentRowChanged.connect(self._select)
        left.lay.addWidget(self.listbox, 1)
        new = Button(_("New profile"), height=40)
        new.clicked.connect(lambda _c=False: self._new())
        left.lay.addWidget(new)
        columns.addWidget(left)

        right = Card()
        top = QHBoxLayout()
        top.setSpacing(20)
        self.avatar = QLabel()
        self.avatar.setFixedSize(112, 112)
        top.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        fields = QVBoxLayout()
        fields.setSpacing(6)
        fields.addWidget(label(_("Nickname"), 10, muted=True))
        self.nick = Field()
        fields.addWidget(self.nick)
        fields.addWidget(label(_("The skin is shown only to you unless the server supports it."),
                               9, muted=True, wrap=True))
        fields.addStretch()
        top.addLayout(fields, 1)
        right.lay.addLayout(top)

        skin_row = QHBoxLayout()
        choose = Button(_("Choose skin (PNG)"), height=40)
        remove = Button(_("Remove skin"), "danger", 40)
        choose.clicked.connect(lambda _c=False: self._choose_skin())
        remove.clicked.connect(lambda _c=False: self._remove_skin())
        skin_row.addWidget(choose)
        skin_row.addWidget(remove)
        skin_row.addStretch()
        right.lay.addSpacing(8)
        right.lay.addLayout(skin_row)

        right.lay.addSpacing(8)
        right.lay.addWidget(label(_("Copy skin by Mojang nickname"), 10, muted=True))
        fetch_row = QHBoxLayout()
        self.mojang = Field()
        fetch = Button(_("Fetch"), height=40)
        fetch.clicked.connect(lambda _c=False: self._fetch())
        fetch_row.addWidget(self.mojang, 1)
        fetch_row.addWidget(fetch)
        right.lay.addLayout(fetch_row)

        self.slim = ToggleRow(_("Slim arms (Alex model)"))
        right.lay.addSpacing(8)
        right.lay.addWidget(self.slim)
        right.lay.addStretch()

        actions = QHBoxLayout()
        actions.addStretch()
        delete = Button(_("Delete profile"), "danger", 42)
        save = Button(_("Save"), "primary", 42)
        delete.clicked.connect(lambda _c=False: self._delete())
        save.clicked.connect(lambda _c=False: self._save())
        actions.addWidget(delete)
        actions.addWidget(save)
        right.lay.addLayout(actions)
        columns.addWidget(right, 1)

    def _account(self):
        for acc in self.app.cfg["accounts"]:
            if acc["id"] == self.edit_id:
                return acc
        return self.app.cfg["accounts"][0]

    def refresh(self):
        accs = self.app.cfg["accounts"]
        if self.edit_id not in {a["id"] for a in accs}:
            self.edit_id = accs[0]["id"]
        self.listbox.blockSignals(True)
        self.listbox.clear()
        for index, acc in enumerate(accs):
            marker = "●  " if acc["id"] == self.app.cfg["account"] else "    "
            self.listbox.addItem(marker + acc["nick"])
            if acc["id"] == self.edit_id:
                self.listbox.setCurrentRow(index)
        self.listbox.blockSignals(False)
        acc = self._account()
        self.nick.setText(acc["nick"])
        self.slim.setChecked(acc.get("slim", False))
        self._update_avatar()

    def _update_avatar(self):
        self.avatar.setPixmap(head_pixmap(accounts.skin_file(self._account()), 112))

    def _select(self, row):
        if 0 <= row < len(self.app.cfg["accounts"]):
            self.edit_id = self.app.cfg["accounts"][row]["id"]
            QTimer.singleShot(0, self.refresh)

    def _new(self):
        acc = accounts.new_account("Player" + str(random.randint(10, 999)))
        self.app.cfg["accounts"].append(acc)
        self.edit_id = acc["id"]
        self.refresh()

    def _store_skin(self, data: bytes, slim=None):
        try:
            accounts.validate_skin(data)
        except ValueError as exc:
            self.app.error(str(exc))
            return
        accounts.skin_file(self._account()).write_bytes(data)
        if slim is not None:
            self.slim.setChecked(slim)
        self._update_avatar()

    def _choose_skin(self):
        path, _filter = QFileDialog.getOpenFileName(self.frame, _("Skin"), "", "PNG (*.png)")
        if path:
            with open(path, "rb") as f:
                self._store_skin(f.read())

    def _remove_skin(self):
        accounts.skin_file(self._account()).unlink(missing_ok=True)
        self._update_avatar()

    def _fetch(self):
        name = self.mojang.text().strip()
        if name:
            self.app.run_async(lambda: accounts.fetch_mojang_skin(name),
                               lambda result: self._store_skin(result[0], result[1]))

    def _save(self):
        acc = self._account()
        acc["nick"] = accounts.clean_nick(self.nick.text())
        acc["slim"] = self.slim.isChecked()
        self.app.cfg["account"] = acc["id"]
        self.app.save()
        self.app.refresh()

    def _delete(self):
        accs = self.app.cfg["accounts"]
        if len(accs) <= 1:
            self.app.info(_("At least one profile must remain"))
            return
        acc = self._account()
        accounts.skin_file(acc).unlink(missing_ok=True)
        accs.remove(acc)
        if self.app.cfg["account"] == acc["id"]:
            self.app.cfg["account"] = accs[0]["id"]
        self.edit_id = accs[0]["id"]
        self.app.save()
        self.app.refresh()

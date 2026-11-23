import random
import uuid

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QVBoxLayout,
                               QWidget, QLineEdit)

from ...core import accounts, ely
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

        right.lay.addSpacing(12)
        right.lay.addWidget(label(_("Ely.by account"), 12, bold=True))
        right.lay.addWidget(label(_("Sign in with your existing Ely.by username or e-mail. Password is not saved."),
                                  9, muted=True, wrap=True))
        self.ely_login = Field()
        self.ely_login.setPlaceholderText(_("Ely.by username or e-mail"))
        self.ely_password = Field()
        self.ely_password.setPlaceholderText(_("Ely.by password"))
        self.ely_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ely_totp = Field()
        self.ely_totp.setPlaceholderText(_("2FA code (if enabled)"))
        self.ely_totp.setEchoMode(QLineEdit.EchoMode.Password)
        right.lay.addWidget(self.ely_login)
        right.lay.addWidget(self.ely_password)
        right.lay.addWidget(self.ely_totp)
        self.ely_button = Button(_("Sign in with Ely.by"), "primary", 40)
        self.ely_button.clicked.connect(lambda _c=False: self._ely_login())
        right.lay.addWidget(self.ely_button)
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
            label_text = acc["nick"] + ("  ·  Ely.by" if acc.get("type") == "ely" else "")
            self.listbox.addItem(marker + label_text)
            if acc["id"] == self.edit_id:
                self.listbox.setCurrentRow(index)
        self.listbox.blockSignals(False)
        acc = self._account()
        self.nick.setText(acc["nick"])
        is_ely = acc.get("type") == "ely"
        self.nick.setEnabled(not is_ely)
        self.slim.setEnabled(not is_ely)
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

    def _ely_login(self):
        username = self.ely_login.text().strip()
        password = self.ely_password.text()
        totp = self.ely_totp.text().strip()
        if not username or not password:
            self.app.warn(_("Enter your Ely.by login and password."))
            return
        client_token = self.app.cfg.get("ely_client_token") or uuid.uuid4().hex
        self.ely_button.setEnabled(False)
        self.ely_button.setText(_("Signing in…"))

        def done(account):
            self.ely_password.clear()
            self.ely_totp.clear()
            signed_account = account
            existing = next((item for item in self.app.cfg["accounts"]
                             if item.get("type") == "ely" and item.get("uuid") == signed_account["uuid"]), None)
            if existing:
                existing.update(signed_account)
                signed_account = existing
            else:
                self.app.cfg["accounts"].append(signed_account)
            self.app.cfg["ely_client_token"] = client_token
            self.app.cfg["account"] = signed_account["id"]
            self.edit_id = signed_account["id"]
            self.app.save()
            self.ely_button.setEnabled(True)
            self.ely_button.setText(_("Sign in with Ely.by"))
            self.refresh()
            self.app.info(_("Signed in to Ely.by as {name}.").format(name=signed_account["nick"]))
            self.app.refresh()

        def failed(_exc):
            self.ely_password.clear()
            self.ely_button.setEnabled(True)
            self.ely_button.setText(_("Sign in with Ely.by"))

        self.app.run_async(
            lambda: ely.authenticate(username, password, client_token=client_token, totp=totp),
            done, failed)

    def _save(self):
        acc = self._account()
        if acc.get("type") != "ely":
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

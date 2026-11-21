"""Local co-op rooms with shareable invite codes and LAN discovery."""
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QInputDialog, QListWidget,
                               QVBoxLayout, QWidget)

from ...core import rooms
from ...i18n import tr as _
from ..widgets import Button, Card, Field, Select, label, page_title


class RoomsPage:
    def __init__(self, app):
        self.app = app
        self.entries = []
        self.frame = QWidget()
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(page_title(_("Rooms")))

        form = Card(margins=(16, 14, 16, 14), spacing=7)
        form.lay.addWidget(label(_("Create a room"), 12, bold=True))
        first = QHBoxLayout()
        first.setSpacing(8)
        first.addWidget(label(_("Room name"), 9, muted=True))
        first.addWidget(label(_("Host"), 9, muted=True))
        first.addWidget(label(_("Port"), 9, muted=True))
        form.lay.addLayout(first)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.name = Field(placeholder=_("Room name"))
        self.host = Field(placeholder="play.example.net")
        self.port = Field("25565")
        self.port.setFixedWidth(92)
        row.addWidget(self.name, 2)
        row.addWidget(self.host, 2)
        row.addWidget(self.port)
        form.lay.addLayout(row)
        second = QHBoxLayout()
        second.setSpacing(8)
        self.instance = Select()
        self.instance.setMinimumWidth(170)
        self.password = Field(placeholder=_("Password (optional)"))
        self.description = Field(placeholder=_("Description (optional)"))
        create = Button(_("Create room"), "primary", 38)
        create.clicked.connect(lambda _c=False: self.create())
        second.addWidget(self.instance)
        second.addWidget(self.password, 1)
        second.addWidget(self.description, 1)
        second.addWidget(create)
        form.lay.addLayout(second)
        root.addWidget(form)

        card = Card(margins=(14, 14, 14, 14), spacing=8)
        card.lay.addWidget(label(_("Rooms"), 12, bold=True))
        self.listbox = QListWidget()
        self.listbox.itemDoubleClicked.connect(lambda _item: self.join())
        card.lay.addWidget(self.listbox, 1)
        buttons = QHBoxLayout()
        for text, callback, kind in ((_("Join room"), self.join, "primary"),
                                     (_("Copy invite"), self.copy_invite, "tonal"),
                                     (_("Import invite"), self.import_invite, "tonal"),
                                     (_("Announce on LAN"), self.announce, "tonal"),
                                     (_("Scan LAN"), self.scan, "tonal"),
                                     (_("Remove room"), self.remove, "danger")):
            button = Button(text, kind, 36)
            button.clicked.connect(lambda _c=False, cb=callback: cb())
            buttons.addWidget(button)
        buttons.addStretch()
        card.lay.addLayout(buttons)
        root.addWidget(card, 1)
        self.status = label("", 9, muted=True)
        root.addWidget(self.status)

    def _say(self, text):
        self.status.setText(text)

    def _selected(self):
        row = self.listbox.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def refresh(self):
        cfg = self.app.cfg
        names = [item["name"] for item in cfg["instances"]]
        current = cfg.get("instance", "")
        self.instance.set_values(names)
        if current in names:
            self.instance.set_value(current)
        self.entries = list(cfg.get("rooms", []))
        self.listbox.clear()
        for room in self.entries:
            detail = room.get("instance") or _("Any instance")
            self.listbox.addItem(f"●   {room.get('name')}   ·   {rooms.room_address(room)}"
                                 f"   ·   {detail}")

    def create(self):
        try:
            room = rooms.new_room(self.name.text(), self.host.text(),
                                  self.port.text().strip() or 25565,
                                  self.instance.value(), self.password.text(),
                                  self.description.text())
            rooms.add_room(self.app.cfg["rooms"], room)
        except ValueError as exc:
            self.app.error(str(exc))
            return
        self.name.clear()
        self.host.clear()
        self.password.clear()
        self.description.clear()
        self.app.save()
        self._say(_("Room created"))
        self.refresh()

    def join(self):
        room = self._selected()
        if not room:
            self._say(_("Select a room first"))
            return
        if room.get("instance") in {item["name"] for item in self.app.cfg["instances"]}:
            self.app.cfg["instance"] = room["instance"]
        self.app.save()
        self._say(_("Room joined"))
        self.app.show("play")
        self.app.pages["play"].start(server=rooms.room_address(room))

    def copy_invite(self):
        room = self._selected()
        if not room:
            self._say(_("Select a room first"))
            return
        QApplication.clipboard().setText(rooms.share_text(room))
        self._say(_("Invite copied to clipboard"))

    def import_invite(self):
        text, ok = QInputDialog.getMultiLineText(self.frame, _("Import invite"),
                                                 _("Paste an invite code"))
        if not ok or not text.strip():
            return
        try:
            room = rooms.decode_invite(text)
        except ValueError as exc:
            self.app.error(_("Invalid invite code: {error}").format(error=exc))
            return
        rooms.add_room(self.app.cfg["rooms"], room)
        self.app.save()
        self._say(_("Invite imported: {name}").format(name=room["name"]))
        self.refresh()

    def remove(self):
        room = self._selected()
        if not room:
            self._say(_("Select a room first"))
            return
        if not self.app.ask(_("Remove room \"{name}\"?").format(name=room["name"])):
            return
        rooms.remove_room(self.app.cfg["rooms"], room["id"])
        self.app.save()
        self.refresh()

    def announce(self):
        room = self._selected()
        if not room:
            self._say(_("Select a room first"))
            return
        sent = rooms.announce_room(room)
        self._say(_("Room announced on LAN") if sent else _("LAN discovery is unavailable"))

    def scan(self):
        self._say(_("Scanning…"))
        self.app.run_async(lambda: rooms.discover_lan_rooms(1.5), self._scan_done)

    def _scan_done(self, found):
        for room in found:
            try:
                rooms.add_room(self.app.cfg["rooms"], room)
            except ValueError:
                continue
        if found:
            self.app.save()
        self._say(_("LAN scan finished: {count} room(s)").format(count=len(found)))
        self.refresh()

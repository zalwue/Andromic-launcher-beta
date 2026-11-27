"""Minecraft servers page: recommended + custom servers, live ping, editing."""
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QVBoxLayout, QWidget)

from ...core import servers
from ...i18n import tr as _
from ..widgets import Button, Card, Field, label, page_title


class ServersPage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        self.results = {}
        self.checking = False
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        root.addWidget(page_title(_("Servers")))

        form = Card()
        captions = QHBoxLayout()
        captions.addWidget(label(_("Server name"), 10, muted=True), 1)
        captions.addWidget(label(_("Address (host:port)"), 10, muted=True), 1)
        captions.addSpacing(130)
        form.lay.addLayout(captions)
        inputs = QHBoxLayout()
        inputs.setSpacing(8)
        self.name = Field(placeholder=_("Server name"))
        self.address = Field(placeholder=f"host:port ({_('port')} {servers.DEFAULT_PORT})")
        add = Button(_("Add server"), "primary", 40)
        add.clicked.connect(lambda _c=False: self.add())
        inputs.addWidget(self.name, 1)
        inputs.addWidget(self.address, 1)
        inputs.addWidget(add)
        form.lay.addLayout(inputs)
        self.address.returnPressed.connect(self.add)
        root.addWidget(form)

        self.section_label = label("", 10, muted=True)

        card = Card(margins=(14, 14, 14, 14))
        card.lay.addWidget(self.section_label)
        self.listbox = QListWidget()
        self.listbox.itemDoubleClicked.connect(lambda _item: self.join())
        self.listbox.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        card.lay.addWidget(self.listbox)
        root.addWidget(card, 1)

        buttons = QHBoxLayout()
        self.join_button = Button(_("Play"), "primary", 38)
        refresh = Button(_("Refresh"), height=38)
        self.edit_button = Button(_("Edit"), height=38)
        self.remove_button = Button(_("Remove"), "danger", 38)
        self.join_button.clicked.connect(lambda _c=False: self.join())
        refresh.clicked.connect(lambda _c=False: self.check())
        self.edit_button.clicked.connect(lambda _c=False: self.edit())
        self.remove_button.clicked.connect(lambda _c=False: self.remove_selected())
        buttons.addWidget(self.join_button)
        buttons.addWidget(refresh)
        buttons.addWidget(self.edit_button)
        buttons.addStretch()
        buttons.addWidget(self.remove_button)
        root.addLayout(buttons)

    # ---- data ----
    def custom_servers(self):
        return [s for s in self.app.cfg.get("servers", []) if not s.get("recommended")]

    def recommended_visible(self):
        return servers.recommended_visible(self.app.cfg.get("servers", []))

    def entries(self):
        """Currently displayed servers with their kind."""
        custom = self.custom_servers()
        if custom:
            return [("custom", s) for s in custom]
        recommended = self.app.cfg.get("recommended_servers") or servers.RECOMMENDED_SERVERS
        return [("recommended", s) for s in recommended]

    # ---- rendering ----
    def _render(self):
        self.listbox.clear()
        entries = self.entries()
        if self.recommended_visible():
            self.section_label.setText(_("Recommended servers"))
        else:
            self.section_label.setText(_("Your servers"))
        self.edit_button.setEnabled(bool(self.custom_servers()))
        self.remove_button.setEnabled(bool(self.custom_servers()))
        for kind, entry in entries:
            address = entry["address"]
            result = self.results.get(address)
            name = entry.get("name") or address
            if result is None:
                status = _("Checking…") if self.checking else _("Unknown")
                line = f"○   {name}\n    {address}   ·   {status}"
            elif not result["online"]:
                line = f"○   {name}\n    {address}   ·   {_('Offline')}"
            else:
                latency = (f"{result['latency']} ms" if result.get("latency") is not None
                           else _("latency unknown"))
                parts = [
                    f"{result.get('players', 0)}/{result.get('max', 0)}",
                    latency,
                    result.get("version") or _("version unknown"),
                ]
                line = f"●   {name}\n    {address}   ·   {'  ·  '.join(p for p in parts if p)}"
                if result.get("motd"):
                    line += f"   —   {result['motd'][:80]}"
            if kind == "recommended" and not name.startswith(_("Recommended")):
                pass
            item = QListWidgetItem(line)
            item.setData(Qt.ItemDataRole.UserRole, (kind, entry))
            item.setToolTip(address)
            self.listbox.addItem(item)

    def refresh(self):
        self._render()
        if not self.checking:
            self.check()

    # ---- pinging ----
    def check(self):
        addresses = [s["address"] for _kind, s in self.entries()]
        if not addresses or self.checking:
            return
        self.checking = True
        self._render()

        def job():
            # Bounded pool; never spawn unbounded threads.
            workers = min(8, max(1, len(addresses)))
            with ThreadPoolExecutor(workers, thread_name_prefix="andromic-ping") as pool:
                return dict(zip(addresses, pool.map(servers.ping, addresses)))

        def done(results):
            self.checking = False
            self.results.update(results)
            self._render()
        self.app.run_async(job, done, lambda _e: setattr(self, "checking", False))

    def _selected(self):
        row = self.listbox.currentRow()
        entries = self.entries()
        if 0 <= row < len(entries):
            return entries[row]
        return None, None

    def _selected_custom_index(self):
        kind, _entry = self._selected()
        if kind != "custom":
            return None
        custom = self.custom_servers()
        row = self.listbox.currentRow()
        # custom entries are rendered in order
        return row if 0 <= row < len(custom) else None

    # ---- actions ----
    def add(self):
        name = self.name.text().strip()
        raw_address = self.address.text().strip()
        if not raw_address:
            self._warn(_("Enter a server address (host or host:port)."))
            return
        try:
            address = servers.normalize_address(raw_address)
        except ValueError as exc:
            self._warn(str(exc))
            return
        entry = {"name": name or address.rsplit(":", 1)[0], "address": address}
        self.app.cfg.setdefault("servers", []).append(entry)
        self.name.clear()
        self.address.clear()
        self.app.save()
        self._render()
        self.check()

    def edit(self):
        index = self._selected_custom_index()
        if index is None:
            return
        current = self.custom_servers()[index]
        name, ok = QInputDialog.getText(self.frame, _("Edit server"), _("Server name"),
                                        text=current.get("name", ""))
        if not ok:
            return
        address, ok = QInputDialog.getText(self.frame, _("Edit server"), _("Address (host:port)"),
                                           text=current.get("address", ""))
        if not ok:
            return
        try:
            servers.edit_server(self.app.cfg["servers"], index, name.strip(), address.strip())
        except ValueError as exc:
            self._warn(str(exc))
            return
        except IndexError:
            return
        self.app.save()
        self._render()
        self.check()

    def remove_selected(self):
        index = self._selected_custom_index()
        if index is None:
            return
        servers.remove_server(self.app.cfg["servers"], index)
        self.app.save()
        self._render()
        # Recommended servers reappear automatically when no custom remain.

    # Backwards-compatible name used by older code.
    def remove(self):
        self.remove_selected()

    def join(self):
        _kind, entry = self._selected()
        if not entry:
            self.app.pages["play"].set_status(_("Choose a server first"))
            return
        self.app.show("play")
        self.app.pages["play"].start(server=entry["address"])

    def _warn(self, text):
        QMessageBox.warning(self.frame, _("Servers"), text)

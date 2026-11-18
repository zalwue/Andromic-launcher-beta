from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import QHBoxLayout, QListWidget, QVBoxLayout, QWidget

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
        self.name = Field()
        self.address = Field()
        add = Button(_("Add server"), "primary", 40)
        add.clicked.connect(lambda _c=False: self.add())
        inputs.addWidget(self.name, 1)
        inputs.addWidget(self.address, 1)
        inputs.addWidget(add)
        form.lay.addLayout(inputs)
        root.addWidget(form)

        card = Card(margins=(14, 14, 14, 14))
        self.listbox = QListWidget()
        self.listbox.itemDoubleClicked.connect(lambda _item: self.join())
        card.lay.addWidget(self.listbox)
        root.addWidget(card, 1)

        buttons = QHBoxLayout()
        join = Button(_("Join"), "primary", 38)
        refresh = Button(_("Refresh"), height=38)
        remove = Button(_("Remove"), "danger", 38)
        join.clicked.connect(lambda _c=False: self.join())
        refresh.clicked.connect(lambda _c=False: self.check())
        remove.clicked.connect(lambda _c=False: self.remove())
        buttons.addWidget(join)
        buttons.addWidget(refresh)
        buttons.addStretch()
        buttons.addWidget(remove)
        root.addLayout(buttons)

    def _render(self):
        self.listbox.clear()
        for entry in self.app.cfg["servers"]:
            result = self.results.get(entry["address"])
            if result is None:
                line = f"○   {entry['name']}   " + (_("Checking…") if self.checking else "")
            elif not result["online"]:
                line = f"○   {entry['name']}   {_('Offline')}"
            else:
                latency = f"{result['latency']} ms" if result["latency"] is not None else ""
                parts = [f"{result['players']}/{result['max']}", latency, result["version"]]
                line = f"●   {entry['name']}   {'  ·  '.join(p for p in parts if p)}"
                if result["motd"]:
                    line += f"   —   {result['motd'][:60]}"
            self.listbox.addItem(line)

    def refresh(self):
        self._render()
        if not self.checking:
            self.check()

    def check(self):
        addresses = [s["address"] for s in self.app.cfg["servers"]]
        if not addresses or self.checking:
            return
        self.checking = True
        self._render()

        def job():
            with ThreadPoolExecutor(8) as pool:
                return dict(zip(addresses, pool.map(servers.ping, addresses)))

        def done(results):
            self.checking = False
            self.results.update(results)
            self._render()
        self.app.run_async(job, done, lambda _e: setattr(self, "checking", False))

    def _selected(self):
        row = self.listbox.currentRow()
        servers_list = self.app.cfg["servers"]
        return servers_list[row] if 0 <= row < len(servers_list) else None

    def add(self):
        address = self.address.text().strip()
        if not address:
            return
        self.app.cfg["servers"].append({"name": self.name.text().strip() or address,
                                        "address": address})
        self.name.clear()
        self.address.clear()
        self.app.save()
        self.check()
        self._render()

    def remove(self):
        entry = self._selected()
        if entry:
            self.app.cfg["servers"].remove(entry)
            self.app.save()
            self._render()

    def join(self):
        entry = self._selected()
        if not entry:
            self.app.pages["play"].set_status(_("Choose a server first"))
            return
        self.app.show("play")
        self.app.pages["play"].start(server=entry["address"])

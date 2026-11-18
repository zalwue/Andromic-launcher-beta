import tkinter as tk
from concurrent.futures import ThreadPoolExecutor

from ...core import servers
from ...i18n import tr as _
from ..widgets import Button, Card, Field, label, styled_listbox


class ServersPage:
    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=parent["bg"])
        self.name = tk.StringVar()
        self.address = tk.StringVar()
        self.results = {}
        self.checking = False
        bg = parent["bg"]

        label(self.frame, _("Servers"), 20, bold=True).pack(anchor="w", pady=(0, 14))

        form = Card(self.frame)
        form.pack(fill="x", pady=(0, 14))
        body = form.body
        body.columnconfigure((0, 1), weight=1, uniform="f")
        label(body, _("Server name"), 10, muted=True).grid(row=0, column=0, sticky="w")
        label(body, _("Address (host:port)"), 10, muted=True).grid(row=0, column=1, sticky="w", padx=(8, 0))
        Field(body, self.name).grid(row=1, column=0, sticky="ew", pady=(4, 0))
        Field(body, self.address).grid(row=1, column=1, sticky="ew", pady=(4, 0), padx=(8, 0))
        Button(body, _("Add server"), self.add, kind="primary", height=40).grid(
            row=1, column=2, padx=(8, 0), pady=(4, 0))

        card = Card(self.frame, stretch=True, pad=14)
        card.pack(fill="both", expand=True)
        card.body.rowconfigure(0, weight=1)
        card.body.columnconfigure(0, weight=1)
        self.listbox = styled_listbox(card.body)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", lambda e: self.join())

        buttons = tk.Frame(self.frame, bg=bg)
        buttons.pack(fill="x", pady=(14, 0))
        Button(buttons, _("Join"), self.join, kind="primary", height=38).pack(side="left", padx=(0, 8))
        Button(buttons, _("Refresh"), self.check, height=38).pack(side="left")
        Button(buttons, _("Remove"), self.remove, kind="danger", height=38).pack(side="right")

    def _render(self):
        self.listbox.delete(0, "end")
        for entry in self.app.cfg["servers"]:
            result = self.results.get(entry["address"])
            if result is None:
                status = _("Checking…") if self.checking else ""
                line = f"○   {entry['name']}   {status}"
            elif not result["online"]:
                line = f"○   {entry['name']}   {_('Offline')}"
            else:
                latency = f"{result['latency']} ms" if result["latency"] is not None else ""
                parts = [f"{result['players']}/{result['max']}", latency, result["version"]]
                line = f"●   {entry['name']}   {'  ·  '.join(p for p in parts if p)}"
                if result["motd"]:
                    line += f"   —   {result['motd'][:60]}"
            self.listbox.insert("end", line)

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
        selection = self.listbox.curselection()
        return self.app.cfg["servers"][selection[0]] if selection else None

    def add(self):
        address = self.address.get().strip()
        if not address:
            return
        name = self.name.get().strip() or address
        self.app.cfg["servers"].append({"name": name, "address": address})
        self.name.set("")
        self.address.set("")
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

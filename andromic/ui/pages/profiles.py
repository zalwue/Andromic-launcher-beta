import random
import tkinter as tk
from tkinter import filedialog, messagebox

from ... import APP_NAME
from ...core import accounts
from ...i18n import tr as _
from ..avatars import head_image
from ..widgets import Button, Card, Field, label, styled_listbox, switch_row


class ProfilesPage:
    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=parent["bg"])
        self.edit_id = app.cfg["account"]
        self.nick = tk.StringVar()
        self.mojang = tk.StringVar()
        self.slim = tk.BooleanVar()

        label(self.frame, _("Profiles"), 20, bold=True).pack(anchor="w", pady=(0, 14))
        row = tk.Frame(self.frame, bg=parent["bg"])
        row.pack(fill="both", expand=True)
        row.columnconfigure(1, weight=1)
        row.rowconfigure(0, weight=1)

        left = Card(row, stretch=True, pad=14)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        left.configure(width=230)
        left.grid_propagate(False)
        left.body.rowconfigure(0, weight=1)
        left.body.columnconfigure(0, weight=1)
        self.listbox = styled_listbox(left.body)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self._select)
        Button(left.body, _("New profile"), self._new, kind="tonal", height=38).grid(
            row=1, column=0, sticky="ew", pady=(10, 0))

        right = Card(row, stretch=True)
        right.grid(row=0, column=1, sticky="nsew")
        body = right.body
        body.columnconfigure(1, weight=1)
        self.avatar = tk.Label(body, bg=body["bg"], bd=0)
        self.avatar.grid(row=0, column=0, rowspan=3, padx=(0, 20), sticky="n")
        label(body, _("Nickname"), 10, muted=True).grid(row=0, column=1, sticky="w")
        Field(body, self.nick).grid(row=1, column=1, sticky="ew", pady=(4, 8))
        label(body, _("The skin is shown only to you unless the server supports it."), 9,
              muted=True, wraplength=420, justify="left").grid(row=2, column=1, sticky="w")

        skin = tk.Frame(body, bg=body["bg"])
        skin.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(22, 0))
        Button(skin, _("Choose skin (PNG)"), self._choose_skin, height=38).pack(side="left", padx=(0, 8))
        Button(skin, _("Remove skin"), self._remove_skin, kind="danger", height=38).pack(side="left")

        label(body, _("Copy skin by Mojang nickname"), 10, muted=True).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(20, 4))
        fetch = tk.Frame(body, bg=body["bg"])
        fetch.grid(row=5, column=0, columnspan=2, sticky="ew")
        fetch.columnconfigure(0, weight=1)
        Field(fetch, self.mojang).grid(row=0, column=0, sticky="ew")
        Button(fetch, _("Fetch"), self._fetch, height=40).grid(row=0, column=1, padx=(8, 0))

        switch_row(body, _("Slim arms (Alex model)"), self.slim).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(20, 0))

        actions = tk.Frame(body, bg=body["bg"])
        actions.grid(row=7, column=0, columnspan=2, sticky="se", pady=(24, 0))
        body.rowconfigure(7, weight=1)
        Button(actions, _("Delete profile"), self._delete, kind="danger", height=40).pack(side="left", padx=(0, 8))
        Button(actions, _("Save"), self._save, kind="primary", height=40).pack(side="left")

    def _account(self):
        for acc in self.app.cfg["accounts"]:
            if acc["id"] == self.edit_id:
                return acc
        return self.app.cfg["accounts"][0]

    def refresh(self):
        accs = self.app.cfg["accounts"]
        if self.edit_id not in {a["id"] for a in accs}:
            self.edit_id = accs[0]["id"]
        self.listbox.delete(0, "end")
        for index, acc in enumerate(accs):
            active = "●  " if acc["id"] == self.app.cfg["account"] else "    "
            self.listbox.insert("end", active + acc["nick"])
            if acc["id"] == self.edit_id:
                self.listbox.selection_set(index)
        acc = self._account()
        self.nick.set(acc["nick"])
        self.slim.set(acc.get("slim", False))
        self._update_avatar()

    def _update_avatar(self):
        self.avatar.configure(image=head_image(accounts.skin_file(self._account()), 112, self.app.images))

    def _select(self, _event):
        selection = self.listbox.curselection()
        if selection:
            self.edit_id = self.app.cfg["accounts"][selection[0]]["id"]
            self.refresh()

    def _new(self):
        acc = accounts.new_account("Player" + str(random.randint(10, 999)))
        self.app.cfg["accounts"].append(acc)
        self.edit_id = acc["id"]
        self.refresh()

    def _store_skin(self, data: bytes, slim=None):
        try:
            accounts.validate_skin(data)
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        accounts.skin_file(self._account()).write_bytes(data)
        if slim is not None:
            self.slim.set(slim)
        self._update_avatar()

    def _choose_skin(self):
        path = filedialog.askopenfilename(title=_("Skin"), filetypes=[("PNG", "*.png")])
        if path:
            with open(path, "rb") as f:
                self._store_skin(f.read())

    def _remove_skin(self):
        accounts.skin_file(self._account()).unlink(missing_ok=True)
        self._update_avatar()

    def _fetch(self):
        name = self.mojang.get().strip()
        if not name:
            return
        self.app.run_async(lambda: accounts.fetch_mojang_skin(name),
                           lambda result: self._store_skin(result[0], result[1]))

    def _save(self):
        acc = self._account()
        acc["nick"] = accounts.clean_nick(self.nick.get())
        acc["slim"] = self.slim.get()
        self.app.cfg["account"] = acc["id"]
        self.app.save()
        self.app.refresh()

    def _delete(self):
        accs = self.app.cfg["accounts"]
        if len(accs) <= 1:
            messagebox.showinfo(APP_NAME, _("At least one profile must remain"))
            return
        acc = self._account()
        accounts.skin_file(acc).unlink(missing_ok=True)
        accs.remove(acc)
        if self.app.cfg["account"] == acc["id"]:
            self.app.cfg["account"] = accs[0]["id"]
        self.edit_id = accs[0]["id"]
        self.app.save()
        self.app.refresh()

import tkinter as tk

from ...i18n import tr as _
from .. import theme
from ..widgets import Button, Card, label


class ConsolePage:
    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=parent["bg"])
        top = tk.Frame(self.frame, bg=parent["bg"])
        top.pack(fill="x", pady=(0, 14))
        label(top, _("Console"), 20, bold=True).pack(side="left")
        Button(top, _("Clear"), self.clear, kind="tonal", height=34).pack(side="right")
        card = Card(self.frame, stretch=True, pad=14)
        card.pack(fill="both", expand=True)
        c = theme.colors
        self.text = tk.Text(card.body, bg=c.card, fg=c.text, bd=0, highlightthickness=0,
                            font=theme.mono(), wrap="none", state="disabled")
        self.text.pack(fill="both", expand=True)

    def append(self, line: str):
        self.text.configure(state="normal")
        self.text.insert("end", line + "\n")
        if int(self.text.index("end-1c").split(".")[0]) > 3000:
            self.text.delete("1.0", "500.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def refresh(self):
        pass

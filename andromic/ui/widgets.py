"""Rounded, minimal widgets drawn on canvases."""
import time
import tkinter as tk
from tkinter import font as tkfont

from . import theme


def _points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return cv.create_polygon(_points(x1, y1, x2, y2, r), smooth=True, **kw)


def label(parent, text="", size=10, muted=False, bold=False, color=None, **kw):
    c = theme.colors
    kw.setdefault("anchor", "w")
    return tk.Label(parent, text=text, bg=parent["bg"], fg=color or (c.muted if muted else c.text),
                    font=theme.font(size, bold), bd=0, **kw)


class Card(tk.Canvas):
    """Rounded container; put children into `.body`."""

    def __init__(self, parent, radius=22, pad=18, fill=None, stretch=False):
        self.fill = fill or theme.colors.card
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=1)
        self.radius, self.pad, self.stretch = radius, pad, stretch
        self.body = tk.Frame(self, bg=self.fill)
        self._win = self.create_window(pad, pad, anchor="nw", window=self.body)
        self.bind("<Configure>", self._on_resize)
        self.body.bind("<Configure>", self._on_body)

    def _on_resize(self, event):
        self.delete("bg")
        round_rect(self, 1, 1, event.width - 1, event.height - 1, self.radius,
                   fill=self.fill, outline=self.fill, tags="bg")
        self.tag_lower("bg")
        opts = {"width": max(event.width - 2 * self.pad, 1)}
        if self.stretch:
            opts["height"] = max(event.height - 2 * self.pad, 1)
        self.itemconfigure(self._win, **opts)

    def _on_body(self, _event):
        if not self.stretch:
            self.configure(height=self.body.winfo_reqheight() + 2 * self.pad)


class Button(tk.Canvas):
    KINDS = ("primary", "tonal", "ghost", "nav", "nav_active", "danger")

    def __init__(self, parent, text, command=None, kind="tonal", width=None,
                 height=38, anchor="center", size=10, bold=False):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=height,
                         cursor="hand2")
        self.text, self.command, self.kind, self.anchor = text, command, kind, anchor
        self.size, self.bold, self.hover, self.enabled = size, bold, False, True
        f = tkfont.Font(font=theme.font(size, bold))
        self.configure(width=width or f.measure(text) + 40)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)

    def _set_hover(self, value):
        self.hover = value
        self._draw()

    def _click(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if self.enabled and inside and self.command:
            self.command()

    def _colors(self):
        c = theme.colors
        if not self.enabled:
            return c.field, c.muted
        table = {
            "primary": (c.accent_hover if self.hover else c.accent, c.on_accent),
            "tonal": (c.field_hover if self.hover else c.field, c.text),
            "ghost": (c.field if self.hover else self["bg"], c.accent),
            "nav": (c.field if self.hover else self["bg"], c.muted if not self.hover else c.text),
            "nav_active": (c.accent_soft, c.accent),
            "danger": (c.field_hover if self.hover else c.field, c.danger),
        }
        return table[self.kind]

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.delete("all")
        bg, fg = self._colors()
        round_rect(self, 0, 0, w, h, h / 2 if self.kind != "nav" and self.kind != "nav_active"
                   else 16, fill=bg, outline=bg)
        if self.anchor == "w":
            self.create_text(18, h / 2, text=self.text, fill=fg, anchor="w",
                             font=theme.font(self.size, self.bold or self.kind == "nav_active"))
        else:
            self.create_text(w / 2, h / 2, text=self.text, fill=fg,
                             font=theme.font(self.size, self.bold))

    def set_text(self, text):
        self.text = text
        self._draw()

    def set_kind(self, kind):
        self.kind = kind
        self._draw()

    def set_enabled(self, value):
        self.enabled = value
        self.configure(cursor="hand2" if value else "arrow")
        self._draw()


class Switch(tk.Canvas):
    def __init__(self, parent, variable, command=None):
        super().__init__(parent, width=48, height=28, bg=parent["bg"], highlightthickness=0,
                         bd=0, cursor="hand2")
        self.var, self.command = variable, command
        self.bind("<Button-1>", self._toggle)
        variable.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _toggle(self, _event=None):
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def _draw(self):
        c = theme.colors
        on = bool(self.var.get())
        self.delete("all")
        round_rect(self, 0, 2, 48, 26, 12, fill=c.accent if on else c.track, outline="")
        x = 36 if on else 12
        self.create_oval(x - 9, 5, x + 9, 23, fill="#FFFFFF", outline="")


def switch_row(parent, text, variable, hint=""):
    row = tk.Frame(parent, bg=parent["bg"])
    row.columnconfigure(0, weight=1)
    label(row, text, 10).grid(row=0, column=0, sticky="w")
    if hint:
        label(row, hint, 9, muted=True).grid(row=1, column=0, sticky="w")
    Switch(row, variable).grid(row=0, column=1, rowspan=2 if hint else 1, sticky="e")
    return row


class Slider(tk.Canvas):
    def __init__(self, parent, variable, lo, hi, step, fmt, height=34):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=height,
                         cursor="hand2")
        self.var, self.lo, self.hi, self.step, self.fmt = variable, lo, hi, step, fmt
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._drag)
        self.bind("<B1-Motion>", self._drag)
        variable.trace_add("write", lambda *_: self._draw())

    def _track(self):
        return 6, max(self.winfo_width() - 110, 40)

    def _drag(self, event):
        x0, x1 = self._track()
        ratio = min(1, max(0, (event.x - x0) / (x1 - x0)))
        raw = self.lo + ratio * (self.hi - self.lo)
        self.var.set(int(round(raw / self.step) * self.step))

    def _draw(self):
        c = theme.colors
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.delete("all")
        x0, x1 = self._track()
        value = min(self.hi, max(self.lo, self.var.get()))
        pos = x0 + (value - self.lo) / (self.hi - self.lo) * (x1 - x0)
        round_rect(self, x0, h / 2 - 3, x1, h / 2 + 3, 3, fill=c.track, outline="")
        round_rect(self, x0, h / 2 - 3, max(pos, x0 + 6), h / 2 + 3, 3, fill=c.accent, outline="")
        self.create_oval(pos - 9, h / 2 - 9, pos + 9, h / 2 + 9, fill="#FFFFFF",
                         outline=c.accent, width=2)
        self.create_text(w - 4, h / 2, text=self.fmt(value), fill=c.text, anchor="e",
                         font=theme.font(10, True))


class Segmented(tk.Canvas):
    def __init__(self, parent, items, command=None, value=None, height=36):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=height,
                         cursor="hand2")
        self.items, self.command = list(items), command
        self.value = value if value is not None else self.items[0][0]
        f = tkfont.Font(font=theme.font(10, True))
        self.widths = [f.measure(t) + 32 for _, t in self.items]
        self.configure(width=sum(self.widths) + 8)
        self.bind("<Button-1>", self._click)
        self._draw()

    def set(self, value):
        self.value = value
        self._draw()

    def _click(self, event):
        x = 4
        for (key, _), width in zip(self.items, self.widths):
            if x <= event.x <= x + width:
                if key != self.value:
                    self.value = key
                    self._draw()
                    if self.command:
                        self.command(key)
                return
            x += width

    def _draw(self):
        c = theme.colors
        h = int(self["height"])
        self.delete("all")
        round_rect(self, 0, 0, sum(self.widths) + 8, h, h / 2, fill=c.seg_bg, outline="")
        x = 4
        for (key, text), width in zip(self.items, self.widths):
            active = key == self.value
            if active:
                round_rect(self, x, 4, x + width, h - 4, (h - 8) / 2, fill=c.seg_active, outline="")
            self.create_text(x + width / 2, h / 2, text=text, font=theme.font(10, active),
                             fill=c.text if active else c.muted)
            x += width


class Field(tk.Canvas):
    def __init__(self, parent, variable, height=40, width=None, placeholder=""):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=height)
        c = theme.colors
        if width:
            self.configure(width=width)
        self.entry = tk.Entry(self, textvariable=variable, bd=0, highlightthickness=0,
                              bg=c.field, fg=c.text, insertbackground=c.text,
                              font=theme.font(10), relief="flat")
        self._win = self.create_window(14, height / 2, anchor="w", window=self.entry)
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event):
        c = theme.colors
        self.delete("bg")
        round_rect(self, 0, 0, event.width, event.height, event.height / 2,
                   fill=c.field, outline=c.field, tags="bg")
        self.tag_lower("bg")
        self.itemconfigure(self._win, width=max(event.width - 28, 10))


class Select(tk.Canvas):
    """Dropdown with a scrollable popup list."""

    def __init__(self, parent, variable, values=(), command=None, height=40, width=None):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=height,
                         cursor="hand2")
        if width:
            self.configure(width=width)
        self.var, self.values, self.command = variable, list(values), command
        self._popup, self._closed_at = None, 0.0
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._open)
        variable.trace_add("write", lambda *_: self._draw())

    def set_values(self, values):
        self.values = list(values)

    def _draw(self):
        c = theme.colors
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.delete("all")
        round_rect(self, 0, 0, w, h, h / 2, fill=c.field, outline=c.field)
        self.create_text(16, h / 2, text=self.var.get(), anchor="w", fill=c.text,
                         font=theme.font(10))
        self.create_line(w - 28, h / 2 - 2, w - 22, h / 2 + 3, w - 16, h / 2 - 2,
                         fill=c.muted, width=2)

    def _close(self, _event=None):
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
            self._closed_at = time.time()

    def _open(self, _event=None):
        if time.time() - self._closed_at < 0.2:
            return
        if self._popup is not None:
            self._close()
            return
        if not self.values:
            return
        c = theme.colors
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.configure(bg=c.border)
        lines = min(len(self.values), 9)
        frame = tk.Frame(top, bg=c.card)
        frame.pack(padx=1, pady=1, fill="both", expand=True)
        lb = tk.Listbox(frame, bd=0, highlightthickness=0, activestyle="none", bg=c.card,
                        fg=c.text, selectbackground=c.accent_soft, selectforeground=c.accent,
                        font=theme.font(10), height=lines, exportselection=False)
        lb.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        for value in self.values:
            lb.insert("end", "  " + str(value))
        if self.var.get() in self.values:
            index = self.values.index(self.var.get())
            lb.selection_set(index)
            lb.see(index)

        def choose(event):
            index = lb.nearest(event.y)
            if 0 <= index < len(self.values):
                self.var.set(self.values[index])
                self._close()
                if self.command:
                    self.command(self.values[index])

        lb.bind("<ButtonRelease-1>", choose)
        lb.bind("<Motion>", lambda e: (lb.selection_clear(0, "end"),
                                       lb.selection_set(lb.nearest(e.y))))
        for widget in (top, lb):
            widget.bind("<FocusOut>", self._close)
            widget.bind("<Escape>", self._close)
        self._popup = top
        x, y = self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + 4
        top.geometry(f"{self.winfo_width()}x{lines * 26 + 14}+{x}+{y}")
        top.focus_force()
        lb.focus_set()


class Progress(tk.Canvas):
    def __init__(self, parent, height=8):
        super().__init__(parent, bg=parent["bg"], highlightthickness=0, bd=0, height=height)
        self.value, self.maximum = 0, 1
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value, maximum):
        self.value, self.maximum = value, max(maximum, 1)
        self._draw()

    def _draw(self):
        c = theme.colors
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.delete("all")
        round_rect(self, 0, 0, w, h, h / 2, fill=c.track, outline="")
        fill = w * min(1, self.value / self.maximum)
        if fill > 0:
            round_rect(self, 0, 0, max(fill, h), h, h / 2, fill=c.accent, outline="")


def styled_listbox(parent, **kw):
    c = theme.colors
    return tk.Listbox(parent, bd=0, highlightthickness=0, activestyle="none", bg=c.card,
                      fg=c.text, selectbackground=c.accent_soft, selectforeground=c.accent,
                      font=theme.font(10), exportselection=False, **kw)


class ScrollFrame(tk.Frame):
    """Vertically scrollable frame; put children into `.inner`."""

    def __init__(self, parent):
        super().__init__(parent, bg=parent["bg"])
        self.canvas = tk.Canvas(self, bg=parent["bg"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=parent["bg"])
        self._win = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _event):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

    def _unbind_wheel(self, _event):
        for name in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(name)

    def _wheel(self, event):
        step = -1 if event.delta > 0 else 1
        if abs(event.delta) < 120:
            step *= 1
        self.canvas.yview_scroll(step * 2, "units")


class Modal(tk.Toplevel):
    def __init__(self, parent, title, width, height):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=theme.colors.bg)
        self.transient(parent)
        self.resizable(False, False)
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass

import tkinter as tk
from tkinter import filedialog

from ...core.system import total_ram_mb
from ...i18n import tr as _
from ..widgets import (Button, Card, Field, ScrollFrame, Segmented, Select, Slider,
                       label, switch_row)


class SettingsPage:
    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=parent["bg"])
        cfg = app.cfg
        label(self.frame, _("Settings"), 20, bold=True).pack(anchor="w", pady=(0, 12))
        scroll = ScrollFrame(self.frame)
        scroll.pack(fill="both", expand=True)
        inner = scroll.inner
        inner.columnconfigure((0, 1), weight=1, uniform="cols")

        def bind(key, var):
            var.trace_add("write", lambda *_a: self._store(key, var))
            return var

        left_col = tk.Frame(inner, bg=inner["bg"])
        right_col = tk.Frame(inner, bg=inner["bg"])
        left_col.grid(row=0, column=0, sticky="new", padx=(0, 7))
        right_col.grid(row=0, column=1, sticky="new", padx=(7, 0))

        def section(parent_col, title):
            c = Card(parent_col)
            c.pack(fill="x", pady=(0, 14))
            label(c.body, title, 12, bold=True).pack(anchor="w", pady=(0, 10))
            return c.body

        def captioned(parent_body, text):
            label(parent_body, text, 10, muted=True).pack(anchor="w", pady=(8, 2))

        max_ram = min(max(2048, (total_ram_mb() // 256) * 256), 65536)
        perf = section(left_col, _("Performance"))
        captioned(perf, _("Allocated memory"))
        Slider(perf, bind("ram", tk.IntVar(value=cfg["ram"])), 1024, max_ram, 256,
               lambda v: f"{v} MB").pack(fill="x")
        captioned(perf, _("Render distance"))
        Slider(perf, bind("render_distance", tk.IntVar(value=cfg["render_distance"])), 2, 32, 1,
               lambda v: _("{n} chunks").format(n=v)).pack(fill="x")
        captioned(perf, _("Frame rate limit"))
        Slider(perf, bind("max_fps", tk.IntVar(value=cfg["max_fps"])), 10, 260, 10,
               lambda v: "∞" if v >= 260 else f"{v} FPS").pack(fill="x")

        screen = section(left_col, _("Display"))
        size = tk.Frame(screen, bg=screen["bg"])
        size.pack(fill="x", pady=(0, 6))
        size.columnconfigure((0, 2), weight=1)
        Field(size, bind("width", tk.StringVar(value=str(cfg["width"])))).grid(row=0, column=0, sticky="ew")
        label(size, "×", 12, muted=True, anchor="center").grid(row=0, column=1, padx=8)
        Field(size, bind("height", tk.StringVar(value=str(cfg["height"])))).grid(row=0, column=2, sticky="ew")
        captioned(screen, _("Graphics"))
        Select(screen, bind("graphics", tk.StringVar(value=cfg["graphics"])),
               ["Fast", "Fancy", "Fabulous"]).pack(fill="x", pady=(0, 10))
        for key, text in (("fullscreen", _("Fullscreen")), ("vsync", "VSync"),
                          ("apply_video", _("Apply video settings on launch"))):
            switch_row(screen, text, bind(key, tk.BooleanVar(value=cfg[key]))).pack(fill="x", pady=5)

        java = section(right_col, "Java")
        label(java, _("Java 8, 17, 21 or 25 is chosen automatically for each version."), 9,
              muted=True, wraplength=330, justify="left").pack(anchor="w", pady=(0, 6))
        captioned(java, _("Custom Java path (optional)"))
        path_row = tk.Frame(java, bg=java["bg"])
        path_row.pack(fill="x")
        path_row.columnconfigure(0, weight=1)
        self.java_var = bind("java_path", tk.StringVar(value=cfg["java_path"]))
        Field(path_row, self.java_var).grid(row=0, column=0, sticky="ew")
        Button(path_row, "…", self._browse_java, height=40, width=48).grid(row=0, column=1, padx=(8, 0))
        captioned(java, _("Extra JVM arguments"))
        Field(java, bind("jvm_args", tk.StringVar(value=cfg["jvm_args"]))).pack(fill="x", pady=(0, 10))
        switch_row(java, _("Optimised JVM flags (G1GC)"),
                   bind("optimize_jvm", tk.BooleanVar(value=cfg["optimize_jvm"]))).pack(fill="x", pady=5)

        launcher = section(right_col, _("Launcher"))
        for key, text, hint in (
            ("fabric_api", _("Install Fabric API automatically"), _("For Fabric and Quilt instances")),
            ("auto_backup", _("Back up worlds before launch"), _("Keeps the last 5 archives")),
            ("hide_launcher", _("Hide launcher while playing"), ""),
        ):
            switch_row(launcher, text, bind(key, tk.BooleanVar(value=cfg[key])), hint).pack(fill="x", pady=5)
        captioned(launcher, _("Theme"))
        Segmented(launcher, [("light", _("Light")), ("dark", _("Dark"))], self._set_theme,
                  cfg["theme"]).pack(anchor="w", pady=(0, 4))
        captioned(launcher, _("Language"))
        Segmented(launcher, [("ru", "Русский"), ("en", "English")], self._set_language,
                  cfg["lang"]).pack(anchor="w")

    def _store(self, key, var):
        try:
            self.app.cfg[key] = var.get()
        except tk.TclError:
            pass

    def _browse_java(self):
        path = filedialog.askopenfilename(title="Java")
        if path:
            self.java_var.set(path)

    def _set_theme(self, value):
        self.app.cfg["theme"] = value
        self.app.root.after(10, self.app.rebuild)

    def _set_language(self, value):
        self.app.cfg["lang"] = value
        self.app.root.after(10, self.app.rebuild)

    def refresh(self):
        pass

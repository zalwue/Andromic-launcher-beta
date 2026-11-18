"""Colour palettes and font selection."""
import tkinter as tk
from tkinter import font as tkfont
from types import SimpleNamespace

PALETTES = {
    "light": dict(
        bg="#F2F4F7", card="#FFFFFF", field="#F0F2F5", field_hover="#E7EAEF",
        text="#17181C", muted="#8B909B", accent="#3482FF", accent_hover="#2A6FE0",
        accent_soft="#DDEAFF", on_accent="#FFFFFF", seg_bg="#E6E9EE", seg_active="#FFFFFF",
        track="#E1E4EA", border="#DDE0E6", danger="#F5483B", console_bg="#16181D",
        console_fg="#CBD0DA",
    ),
    "dark": dict(
        bg="#0C0D10", card="#18191E", field="#23252B", field_hover="#2C2F36",
        text="#F1F2F5", muted="#8C919C", accent="#3482FF", accent_hover="#4A92FF",
        accent_soft="#1D2C4A", on_accent="#FFFFFF", seg_bg="#23252B", seg_active="#3A3D46",
        track="#2C2F36", border="#2A2C33", danger="#FF5A4D", console_bg="#08090B",
        console_fg="#C4C9D3",
    ),
}

colors = SimpleNamespace(**PALETTES["light"])
_family = "TkDefaultFont"
_PREFERRED = ("MiSans", "HarmonyOS Sans", "Segoe UI Variable Text", "Segoe UI",
              "SF Pro Text", "Helvetica Neue", "Inter", "Roboto", "Noto Sans", "DejaVu Sans")


def set_theme(name: str) -> None:
    for key, value in PALETTES.get(name, PALETTES["light"]).items():
        setattr(colors, key, value)


def init_fonts(root: tk.Misc) -> None:
    global _family
    available = set(tkfont.families(root))
    for name in _PREFERRED:
        if name in available:
            _family = name
            break
    tkfont.nametofont("TkDefaultFont").configure(family=_family, size=10)


def font(size: int = 10, bold: bool = False) -> tuple:
    return (_family, size, "bold") if bold else (_family, size)


def mono() -> tuple:
    return ("Consolas", 10) if "Consolas" in tkfont.families() else ("Courier", 10)

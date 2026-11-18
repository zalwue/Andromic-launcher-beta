"""Head avatars rendered from skin files."""
import tkinter as tk
from pathlib import Path

_DEFAULT_ROWS = (
    "HHHHHHHH", "HHHHHHHH", "HSSSSSSH", "SSSSSSSS",
    "SWESSEWS", "SSSNNSSS", "SSMMMMSS", "SSSSSSSS",
)
_DEFAULT_COLORS = {"H": "#3B2A1B", "S": "#C08A66", "W": "#FFFFFF",
                   "E": "#3E4FA8", "N": "#A06B4C", "M": "#7A4A38"}


def _default_head(size: int) -> tk.PhotoImage:
    img = tk.PhotoImage(width=8, height=8)
    for y, row in enumerate(_DEFAULT_ROWS):
        for x, ch in enumerate(row):
            img.put(_DEFAULT_COLORS[ch], (x, y))
    zoom = max(1, size // 8)
    return img.zoom(zoom, zoom)


def head_image(skin: Path, size: int, cache: dict) -> tk.PhotoImage:
    """Face of a skin (with the hat layer) scaled to roughly `size` pixels."""
    key = (str(skin), skin.stat().st_mtime if skin.exists() else 0, size)
    if key in cache:
        return cache[key]
    image = None
    if skin.exists():
        try:
            source = tk.PhotoImage(file=str(skin))
            zoom = max(1, size // 8)
            image = tk.PhotoImage()
            image.tk.call(image.name, "copy", source.name, "-from", 8, 8, 16, 16, "-zoom", zoom, zoom)
            try:
                image.tk.call(image.name, "copy", source.name, "-from", 40, 8, 48, 16,
                              "-zoom", zoom, zoom, "-compositingrule", "overlay")
            except tk.TclError:
                pass
            cache[(key, "src")] = source
        except tk.TclError:
            image = None
    if image is None:
        image = _default_head(size)
    cache[key] = image
    return image

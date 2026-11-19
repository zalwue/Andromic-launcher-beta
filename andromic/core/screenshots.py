"""Screenshot discovery helpers for individual Minecraft instances."""
from pathlib import Path

from .instances import instance_dir

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def screenshot_dir(instance: dict) -> Path:
    return instance_dir(instance) / "screenshots"


def list_screenshots(instance: dict) -> list[Path]:
    folder = screenshot_dir(instance)
    if not folder.is_dir():
        return []
    files = []
    for path in folder.iterdir():
        try:
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                files.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return [path for _modified, path in sorted(files, reverse=True)]

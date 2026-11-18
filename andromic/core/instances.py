"""Named game instances and world backups."""
import re
import time
import zipfile
from pathlib import Path

from .paths import BACKUPS, INSTANCES


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "instance"


def unique_name(name: str, existing) -> str:
    taken = {n.lower() for n in existing}
    candidate, counter = name, 2
    while candidate.lower() in taken:
        candidate = f"{name} {counter}"
        counter += 1
    return candidate


def new_instance(name: str, mc: str, loader: str = "Vanilla",
                 loader_version: str = "", server: str = "") -> dict:
    return {"name": name, "mc": mc, "loader": loader, "lv": loader_version, "server": server}


def instance_dir(instance: dict) -> Path:
    return INSTANCES / safe_name(instance["name"])


def backup_worlds(instance: dict, keep: int = 5):
    """Zip the saves folder; returns the archive path or None if there are no worlds."""
    saves = instance_dir(instance) / "saves"
    if not saves.is_dir() or not any(saves.iterdir()):
        return None
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    prefix = safe_name(instance["name"])
    target = BACKUPS / f"{prefix}_{stamp}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for file in saves.rglob("*"):
            if file.is_file():
                z.write(file, file.relative_to(saves.parent))
    old = sorted(BACKUPS.glob(f"{prefix}_*.zip"))
    for stale in old[:-keep]:
        stale.unlink(missing_ok=True)
    return target

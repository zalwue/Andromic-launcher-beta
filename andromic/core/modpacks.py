""".mrpack (Modrinth modpack) installation."""
import json
import zipfile
from pathlib import Path

from .instances import instance_dir, new_instance, unique_name
from .net import download_many
from .reporter import Reporter


def _inside(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _loader_from(dependencies: dict, mc: str):
    if "fabric-loader" in dependencies:
        return "Fabric", dependencies["fabric-loader"]
    if "quilt-loader" in dependencies:
        return "Quilt", dependencies["quilt-loader"]
    if "neoforge" in dependencies:
        return "NeoForge", dependencies["neoforge"]
    if "forge" in dependencies:
        return "Forge", f"{mc}-{dependencies['forge']}"
    return "Vanilla", ""


def install_mrpack(path: Path, title: str, existing_names, rep: Reporter) -> dict:
    """Install a modpack into a fresh instance and return the instance record."""
    with zipfile.ZipFile(path) as z:
        index = json.loads(z.read("modrinth.index.json"))
        dependencies = index["dependencies"]
        mc = dependencies["minecraft"]
        loader, loader_version = _loader_from(dependencies, mc)
        instance = new_instance(unique_name(index.get("name") or title, existing_names),
                                mc, loader, loader_version)
        game_dir = instance_dir(instance)
        game_dir.mkdir(parents=True, exist_ok=True)

        items = []
        for entry in index["files"]:
            if entry.get("env", {}).get("client") == "unsupported":
                continue
            target = game_dir / entry["path"]
            if not _inside(game_dir, target):
                continue
            items.append((entry["downloads"][0], target,
                          entry.get("hashes", {}).get("sha1"), entry.get("fileSize")))
        download_many(items, rep, "Modpack files")

        for member in z.namelist():
            for prefix in ("overrides/", "client-overrides/"):
                if member.startswith(prefix) and not member.endswith("/"):
                    target = game_dir / member[len(prefix):]
                    if _inside(game_dir, target):
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(z.read(member))
    return instance

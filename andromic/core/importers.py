"""Safe import of Prism Launcher and MultiMC exported instances."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path, PurePosixPath

from .instances import instance_dir, new_instance, unique_name

_MAX_MEMBERS = 50000
_MAX_UNPACKED = 3 * 1024 * 1024 * 1024


def _loader_from_pack(pack: dict):
    mc = ""
    loader, loader_version = "Vanilla", ""
    forge_version = ""
    for component in pack.get("components", []):
        uid = str(component.get("uid", ""))
        version = str(component.get("version", ""))
        if uid == "net.minecraft":
            mc = version
        elif uid == "net.fabricmc.fabric-loader":
            loader, loader_version = "Fabric", version
        elif uid == "org.quiltmc.quilt-loader":
            loader, loader_version = "Quilt", version
        elif uid == "net.minecraftforge":
            loader, forge_version = "Forge", version
        elif uid == "net.neoforged":
            loader, loader_version = "NeoForge", version
    if not mc:
        raise ValueError("The archive does not declare a Minecraft version.")
    if loader == "Forge":
        loader_version = f"{mc}-{forge_version}"
    return mc, loader, loader_version


def _safe_target(base: Path, member: str) -> Path:
    # ZIP paths always use forward slashes; reject absolute and traversal paths.
    pure = PurePosixPath(member)
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts):
        raise ValueError(f"Unsafe path in archive: {member}")
    target = base.joinpath(*pure.parts)
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"Unsafe path in archive: {member}") from exc
    return target


def _find_pack_root(names: list[str]) -> str:
    candidates = [n for n in names if n.endswith("mmc-pack.json")]
    if not candidates:
        raise ValueError("This is not a Prism Launcher or MultiMC export (mmc-pack.json is missing).")
    # Prefer the shallowest matching metadata file.
    return min(candidates, key=lambda n: (n.count("/"), len(n)))[:-len("mmc-pack.json")]


def import_prism_multimc(path: Path, title: str, existing_names) -> dict:
    """Import an exported Prism/MultiMC ZIP; only files under overrides/ are copied."""
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_MEMBERS:
            raise ValueError("The archive contains too many files.")
        unpacked = sum(info.file_size for info in infos)
        if unpacked > _MAX_UNPACKED:
            raise ValueError("The unpacked archive is larger than the 3 GB import limit.")
        names = [info.filename for info in infos]
        root = _find_pack_root(names)
        metadata_name = root + "mmc-pack.json"
        try:
            pack = json.loads(archive.read(metadata_name).decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("The modpack metadata is damaged or unreadable.") from exc
        mc, loader, loader_version = _loader_from_pack(pack)
        suggested = pack.get("name") or path.stem or title
        instance = new_instance(unique_name(str(suggested), existing_names), mc, loader, loader_version)
        game_dir = instance_dir(instance)
        game_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        for info in infos:
            member = info.filename
            if info.is_dir() or not member.startswith(root + "overrides/"):
                continue
            relative = member[len(root + "overrides/"):]
            if relative.startswith(".minecraft/"):
                relative = relative[len(".minecraft/"):]
            if not relative:
                continue
            target = _safe_target(game_dir, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
            copied += 1
        if copied == 0:
            # An export may still be valid if it only contains metadata.
            game_dir.mkdir(parents=True, exist_ok=True)
    return instance


def import_archive(path: Path, existing_names) -> dict:
    """Import a Prism Launcher or MultiMC exported ZIP archive."""
    path = Path(path)
    if path.suffix.lower() != ".zip":
        raise ValueError("Only Prism Launcher and MultiMC ZIP exports are supported here.")
    return import_prism_multimc(path, path.stem, existing_names)

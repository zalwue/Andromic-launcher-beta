"""World and instance backup management.

This module complements the historical :func:`andromic.core.instances.backup_worlds`
helper.  New backups carry a small JSON manifest, can be verified, listed,
restored and pruned, and never write outside their target directory.
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from .instances import instance_dir, safe_name
from .paths import BACKUPS, path_inside, unique_path
from .system import OS

SCHEMA = 1
MANIFEST_NAME = "andromic-backup.json"
WORLD_PARTS = ("saves",)
INSTANCE_PARTS = ("saves", "mods", "config", "resourcepacks", "shaderpacks",
                  "options.txt", "optionsshaders.txt", "servers.dat", "servers.dat_old")
_SKIP_NAMES = {"session.lock"}
_MAX_MEMBERS = 100_000
_MAX_UNPACKED = 20 * 1024 * 1024 * 1024


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: Optional[datetime] = None) -> str:
    return (moment or _now()).strftime("%Y%m%d-%H%M%S")


def _parse_stamp(text: str) -> str:
    try:
        return datetime.strptime(text, "%Y%m%d-%H%M%S").replace(
            tzinfo=timezone.utc).isoformat(timespec="seconds")
    except ValueError:
        return ""


def _parts(scope: str) -> Sequence[str]:
    if scope == "instance":
        return INSTANCE_PARTS
    if scope == "worlds":
        return WORLD_PARTS
    raise ValueError("Unknown backup scope: expected 'worlds' or 'instance'")


def _iter_files(base: Path, parts: Sequence[str]) -> Iterable[Path]:
    for part in parts:
        source = base / part
        if source.is_file():
            yield source
        elif source.is_dir():
            for file in source.rglob("*"):
                try:
                    if file.is_file() and not file.is_symlink() and file.name not in _SKIP_NAMES:
                        yield file
                except OSError:
                    continue


def _safe_member(base: Path, member: str) -> Optional[Path]:
    pure = PurePosixPath(member.replace("\\", "/"))
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts):
        return None
    target = base.joinpath(*pure.parts)
    return target if path_inside(base, target) else None


def create_backup(instance: dict, scope: str = "worlds", note: str = "",
                  backup_root: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """Create a ZIP backup of an instance; returns ``None`` when it is empty."""
    base = instance_dir(instance)
    parts = _parts(scope)
    files = list(_iter_files(base, parts))
    if not files:
        return None
    root = Path(backup_root) if backup_root is not None else BACKUPS
    root.mkdir(parents=True, exist_ok=True)
    created = _now()
    prefix = safe_name(instance.get("name", "instance"))
    suffix = f"_{safe_name(note)}" if str(note).strip() else ""
    target = unique_path(root / f"{prefix}_{_stamp(created)}{suffix}.zip")
    manifest = {
        "schema": SCHEMA,
        "instance": instance.get("name", ""),
        "scope": scope,
        "note": str(note).strip(),
        "created": created.isoformat(timespec="seconds"),
        "timestamp": created.timestamp(),
        "platform": OS,
        "parts": list(parts),
    }
    total = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in files:
            relative = file.relative_to(base)
            archive.write(file, PurePosixPath(*relative.parts).as_posix())
            try:
                total += file.stat().st_size
            except OSError:
                pass
        manifest["files"] = len(files)
        manifest["bytes"] = total
        archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
    return target


def _read_manifest(archive: zipfile.ZipFile) -> Dict[str, Any]:
    try:
        raw = archive.read(MANIFEST_NAME)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (KeyError, ValueError, UnicodeDecodeError, OSError):
        return {}


def _legacy_metadata(path: Path) -> Dict[str, Any]:
    """Infer metadata for archives created by the older backup_worlds helper."""
    stem = path.stem
    name, _sep, stamp = stem.rpartition("_")
    if not name:
        name, stamp = stem, ""
    return {
        "instance": name,
        "scope": "worlds",
        "note": "",
        "created": _parse_stamp(stamp),
        "timestamp": 0,
        "platform": "",
        "legacy": True,
    }


def backup_info(path: Union[str, Path]) -> Dict[str, Any]:
    archive_path = Path(path)
    info: Dict[str, Any] = {
        "path": str(archive_path),
        "name": archive_path.name,
        "size": archive_path.stat().st_size if archive_path.exists() else 0,
        "instance": "",
        "scope": "worlds",
        "note": "",
        "created": "",
        "timestamp": 0,
        "files": 0,
        "bytes": 0,
        "valid": False,
        "error": "",
    }
    if not archive_path.is_file():
        info["error"] = "Backup file does not exist"
        return info
    try:
        with zipfile.ZipFile(archive_path) as archive:
            metadata = _read_manifest(archive) or _legacy_metadata(archive_path)
            names = archive.namelist()
            info.update({key: metadata.get(key, info.get(key))
                         for key in ("instance", "scope", "note", "created", "timestamp")})
            info["files"] = int(metadata.get("files") or len(names))
            info["bytes"] = int(metadata.get("bytes") or info["size"])
            info["valid"] = True
            if not info["created"]:
                info["created"] = _legacy_metadata(archive_path)["created"]
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        info["error"] = str(exc)
    return info


def list_backups(instance: Optional[dict] = None,
                 backup_root: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    root = Path(backup_root) if backup_root is not None else BACKUPS
    if not root.is_dir():
        return []
    wanted = instance.get("name", "") if instance else ""
    result = []
    for path in root.glob("*.zip"):
        info = backup_info(path)
        if wanted and info.get("instance") not in ("", wanted):
            continue
        result.append(info)
    result.sort(key=lambda item: (str(item.get("created", "")), item["name"]), reverse=True)
    return result


def verify_backup(path: Union[str, Path]) -> Dict[str, Any]:
    """Fully test a backup archive and return a structured result."""
    archive_path = Path(path)
    result = {"valid": False, "files": 0, "error": "", "path": str(archive_path)}
    try:
        with zipfile.ZipFile(archive_path) as archive:
            broken = archive.testzip()
            if broken:
                result["error"] = f"Damaged member: {broken}"
                return result
            result["files"] = len(archive.namelist())
            result["valid"] = True
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        result["error"] = str(exc)
    return result


def restore_backup(path: Union[str, Path], instance: Optional[dict] = None,
                   target: Optional[Union[str, Path]] = None,
                   overwrite: bool = True,
                   parts: Optional[Sequence[str]] = None) -> Path:
    """Restore a backup into an instance directory with traversal protection."""
    archive_path = Path(path)
    if target is None:
        if instance is None:
            raise ValueError("A restore target or instance is required")
        destination = instance_dir(instance)
    else:
        destination = Path(target)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_MEMBERS:
            raise ValueError("The backup contains too many files")
        if sum(info.file_size for info in infos) > _MAX_UNPACKED:
            raise ValueError("The backup is too large to restore")
        selected = []
        for info in infos:
            member = info.filename.replace("\\", "/")
            if info.is_dir() or member == MANIFEST_NAME:
                continue
            if parts and not any(member == part or member.startswith(part.rstrip("/") + "/")
                                 for part in parts):
                continue
            relative = PurePosixPath(member)
            if relative.name in _SKIP_NAMES:
                continue
            output = _safe_member(destination, member)
            if output is None:
                raise ValueError(f"Unsafe path in backup: {member}")
            if output.exists() and not overwrite:
                raise FileExistsError(str(output))
            selected.append((info, output))
        for info, output in selected:
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, output.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
    return destination


def delete_backup(path: Union[str, Path]) -> bool:
    target = Path(path)
    if not target.is_file():
        return False
    target.unlink()
    return True


def prune_backups(instance: Optional[dict] = None, keep: int = 5,
                  max_age_days: Optional[int] = None,
                  backup_root: Optional[Union[str, Path]] = None) -> List[Path]:
    """Delete old backups, keeping the newest ``keep`` and optionally by age."""
    keep = max(0, int(keep))
    backups = list_backups(instance, backup_root)
    removed: List[Path] = []
    now = _now()
    for index, info in enumerate(backups):
        path = Path(info["path"])
        expired = False
        if max_age_days is not None:
            created = info.get("created", "")
            try:
                moment = datetime.fromisoformat(str(created))
                if moment.tzinfo is None:
                    moment = moment.replace(tzinfo=timezone.utc)
                expired = moment < now - timedelta(days=max(0, int(max_age_days)))
            except ValueError:
                expired = False
        if index >= keep or expired:
            if delete_backup(path):
                removed.append(path)
    return removed


def backup_summary(instance: Optional[dict] = None,
                   backup_root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    backups = list_backups(instance, backup_root)
    return {
        "count": len(backups),
        "bytes": sum(int(item.get("size") or 0) for item in backups),
        "latest": backups[0] if backups else None,
    }

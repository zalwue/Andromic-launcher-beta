"""World (save) management and a small, dependency-free NBT reader/writer.

Minecraft stores world metadata in a gzip-compressed NBT ``level.dat`` file.
Only the subset needed by the launcher is modelled, but the reader/writer is
complete enough to round-trip real level files without losing tags.
"""
from __future__ import annotations

import gzip
import shutil
import struct
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Union

from .instances import instance_dir, safe_name
from .paths import path_inside, unique_path

_MAX_MEMBERS = 100_000
_MAX_UNPACKED = 10 * 1024 * 1024 * 1024
_GAME_TYPES = {0: "Survival", 1: "Creative", 2: "Adventure", 3: "Spectator"}
_DIFFICULTIES = {0: "Peaceful", 1: "Easy", 2: "Normal", 3: "Hard"}


@dataclass
class Tag:
    """A typed NBT tag.  ``tag_type`` follows the NBT specification."""
    tag_type: int
    value: Any


_TAG_NAMES = {
    0: "End", 1: "Byte", 2: "Short", 3: "Int", 4: "Long", 5: "Float",
    6: "Double", 7: "ByteArray", 8: "String", 9: "List", 10: "Compound",
    11: "IntArray", 12: "LongArray",
}


class _Reader:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def read(self, size: int) -> bytes:
        end = self.pos + size
        if end > len(self.data):
            raise ValueError("Unexpected end of NBT data")
        chunk = self.data[self.pos:end]
        self.pos = end
        return chunk

    def unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.read(size))[0]

    def u1(self) -> int:
        return self.unpack(">B")

    def i2(self) -> int:
        return self.unpack(">h")

    def i4(self) -> int:
        return self.unpack(">i")

    def i8(self) -> int:
        return self.unpack(">q")

    def string(self) -> str:
        length = self.unpack(">H")
        return self.read(length).decode("utf-8", errors="replace")


class _Writer:
    def __init__(self):
        self.parts: List[bytes] = []

    def write(self, data: bytes) -> None:
        self.parts.append(data)

    def pack(self, fmt: str, value) -> None:
        self.write(struct.pack(fmt, value))

    def string(self, text: str) -> None:
        data = str(text).encode("utf-8")
        if len(data) > 65535:
            raise ValueError("NBT string is too long")
        self.pack(">H", len(data))
        self.write(data)

    def data(self) -> bytes:
        return b"".join(self.parts)


def _read_tag(reader: _Reader, tag_type: int) -> Tag:
    if tag_type == 1:
        return Tag(1, reader.unpack(">b"))
    if tag_type == 2:
        return Tag(2, reader.i2())
    if tag_type == 3:
        return Tag(3, reader.i4())
    if tag_type == 4:
        return Tag(4, reader.i8())
    if tag_type == 5:
        return Tag(5, reader.unpack(">f"))
    if tag_type == 6:
        return Tag(6, reader.unpack(">d"))
    if tag_type == 7:
        length = reader.i4()
        return Tag(7, reader.read(max(0, length)))
    if tag_type == 8:
        return Tag(8, reader.string())
    if tag_type == 9:
        item_type = reader.u1()
        length = reader.i4()
        if length < 0 or length > 10_000_000:
            raise ValueError("Invalid NBT list length")
        return Tag(9, [_read_tag(reader, item_type) for _ in range(length)])
    if tag_type == 10:
        values: Dict[str, Tag] = {}
        while True:
            child_type = reader.u1()
            if child_type == 0:
                break
            name = reader.string()
            values[name] = _read_tag(reader, child_type)
        return Tag(10, values)
    if tag_type == 11:
        length = reader.i4()
        return Tag(11, [reader.i4() for _ in range(max(0, length))])
    if tag_type == 12:
        length = reader.i4()
        return Tag(12, [reader.i8() for _ in range(max(0, length))])
    raise ValueError(f"Unknown NBT tag type {tag_type}")


def _write_tag(writer: _Writer, tag: Tag) -> None:
    kind, value = tag.tag_type, tag.value
    if kind == 1:
        writer.pack(">b", int(value))
    elif kind == 2:
        writer.pack(">h", int(value))
    elif kind == 3:
        writer.pack(">i", int(value))
    elif kind == 4:
        writer.pack(">q", int(value))
    elif kind == 5:
        writer.pack(">f", float(value))
    elif kind == 6:
        writer.pack(">d", float(value))
    elif kind == 7:
        data = bytes(value)
        writer.pack(">i", len(data))
        writer.write(data)
    elif kind == 8:
        writer.string(value)
    elif kind == 9:
        items = list(value)
        item_type = items[0].tag_type if items else 0
        writer.pack(">B", item_type)
        writer.pack(">i", len(items))
        for item in items:
            _write_tag(writer, item)
    elif kind == 10:
        for name, child in value.items():
            writer.pack(">B", child.tag_type)
            writer.string(name)
            _write_tag(writer, child)
        writer.pack(">B", 0)
    elif kind == 11:
        writer.pack(">i", len(value))
        for item in value:
            writer.pack(">i", int(item))
    elif kind == 12:
        writer.pack(">i", len(value))
        for item in value:
            writer.pack(">q", int(item))
    else:
        raise ValueError(f"Unsupported NBT tag type {kind}")


def read_nbt_bytes(data: bytes) -> Tag:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    reader = _Reader(data)
    tag_type = reader.u1()
    reader.string()  # root name, normally empty
    return _read_tag(reader, tag_type)


def write_nbt_bytes(root: Tag, compress: bool = True) -> bytes:
    writer = _Writer()
    writer.pack(">B", root.tag_type)
    writer.string("")
    _write_tag(writer, root)
    payload = writer.data()
    return gzip.compress(payload, mtime=0) if compress else payload


def read_nbt_file(path: Union[str, Path]) -> Tag:
    return read_nbt_bytes(Path(path).read_bytes())


def write_nbt_file(path: Union[str, Path], root: Tag) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(write_nbt_bytes(root))
    return target


def tag_path(root: Tag, dotted: str) -> Optional[Tag]:
    current = root
    for part in dotted.split("."):
        if current.tag_type != 10:
            return None
        current = current.value.get(part)
        if current is None:
            return None
    return current


def tag_value(root: Tag, dotted: str, default=None):
    tag = tag_path(root, dotted)
    if tag is None:
        return default
    if tag.tag_type == 9:
        return [item.value for item in tag.value]
    return tag.value


def set_tag(root: Tag, dotted: str, tag: Tag) -> bool:
    parts = dotted.split(".")
    current = root
    for part in parts[:-1]:
        if current.tag_type != 10:
            return False
        child = current.value.get(part)
        if child is None or child.tag_type != 10:
            child = Tag(10, {})
            current.value[part] = child
        current = child
    if current.tag_type != 10:
        return False
    current.value[parts[-1]] = tag
    return True


def set_level_name(level_dat: Union[str, Path], name: str) -> bool:
    """Rename a world by updating ``Data.LevelName`` in level.dat."""
    path = Path(level_dat)
    if not path.is_file():
        return False
    root = read_nbt_file(path)
    if not set_tag(root, "Data.LevelName", Tag(8, str(name))):
        return False
    write_nbt_file(path, root)
    return True


def _timestamp(milliseconds) -> str:
    try:
        value = int(milliseconds) / 1000
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _read_level(path: Path) -> Dict[str, Any]:
    root = read_nbt_file(path)
    data = tag_path(root, "Data")
    if data is None or data.tag_type != 10:
        raise ValueError("level.dat has no Data compound")
    version = tag_path(root, "Data.Version")
    name = tag_value(root, "Data.Version.Name", "") if version else ""
    return {
        "name": tag_value(root, "Data.LevelName", path.parent.name),
        "last_played_ms": tag_value(root, "Data.LastPlayed", 0),
        "game_type": _GAME_TYPES.get(tag_value(root, "Data.GameType", 0), "Unknown"),
        "difficulty": _DIFFICULTIES.get(tag_value(root, "Data.Difficulty", 2), "Normal"),
        "hardcore": bool(tag_value(root, "Data.hardcore", 0)),
        "version": name,
        "data_version": tag_value(root, "Data.DataVersion", 0),
        "day_time": tag_value(root, "Data.DayTime", 0),
    }


def world_size(path: Union[str, Path]) -> int:
    total = 0
    for file in Path(path).rglob("*"):
        try:
            if file.is_file() and not file.is_symlink():
                total += file.stat().st_size
        except OSError:
            continue
    return total


def _saves(instance: dict) -> Path:
    return instance_dir(instance) / "saves"


def _world_path(instance: dict, folder: str) -> Path:
    saves = _saves(instance)
    if not folder or Path(folder).name != folder:
        raise ValueError("Invalid world folder name")
    target = saves / folder
    if not path_inside(saves, target):
        raise ValueError("World folder is outside the saves directory")
    return target


def read_level_info(world_dir: Union[str, Path]) -> Dict[str, Any]:
    """Read display metadata from a world directory, tolerating broken saves."""
    folder = Path(world_dir)
    info: Dict[str, Any] = {
        "folder": folder.name,
        "name": folder.name,
        "path": str(folder),
        "size": world_size(folder),
        "icon": str(folder / "icon.png") if (folder / "icon.png").is_file() else "",
        "error": "",
    }
    try:
        info.update(_read_level(folder / "level.dat"))
        info["last_played"] = _timestamp(info.get("last_played_ms"))
    except (OSError, ValueError, struct.error) as exc:
        info["error"] = str(exc)
        info["last_played"] = ""
    return info


def list_worlds(instance: dict) -> List[Dict[str, Any]]:
    saves = _saves(instance)
    if not saves.is_dir():
        return []
    worlds = []
    for child in saves.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                worlds.append(read_level_info(child))
        except OSError:
            continue
    worlds.sort(key=lambda item: (int(item.get("last_played_ms") or 0), item["folder"]),
                reverse=True)
    return worlds


def rename_world(instance: dict, folder: str, new_name: str,
                 rename_folder: bool = True) -> Path:
    """Rename a world folder and its in-game display name."""
    new_name = str(new_name).strip()
    if not new_name:
        raise ValueError("The world name cannot be empty")
    source = _world_path(instance, folder)
    if not source.is_dir():
        raise FileNotFoundError(f"World not found: {folder}")
    target = source
    if rename_folder:
        desired = safe_name(new_name)
        target = unique_path(source.parent / desired)
        if target != source:
            source.rename(target)
    if (target / "level.dat").is_file():
        set_level_name(target / "level.dat", new_name)
    return target


def duplicate_world(instance: dict, folder: str, new_name: Optional[str] = None) -> Path:
    source = _world_path(instance, folder)
    if not source.is_dir():
        raise FileNotFoundError(f"World not found: {folder}")
    name = str(new_name or f"{read_level_info(source)['name']} copy").strip()
    target = unique_path(source.parent / safe_name(name))
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("session.lock"))
    if (target / "level.dat").is_file():
        set_level_name(target / "level.dat", name)
    return target


def delete_world(instance: dict, folder: str) -> bool:
    target = _world_path(instance, folder)
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    return True


def _safe_member(base: Path, member: str) -> Optional[Path]:
    pure = PurePosixPath(member)
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts):
        return None
    target = base.joinpath(*pure.parts)
    return target if path_inside(base, target) else None


def export_world(instance: dict, folder: str, destination: Union[str, Path]) -> Path:
    """Export one world as a ZIP archive containing the world folder."""
    source = _world_path(instance, folder)
    if not source.is_dir():
        raise FileNotFoundError(f"World not found: {folder}")
    target = Path(destination)
    if target.is_dir():
        target = target / f"{safe_name(folder)}.zip"
    if target.suffix.lower() != ".zip":
        target = target.with_suffix(".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in source.rglob("*"):
            if file.is_file() and not file.is_symlink():
                archive.write(file, (PurePosixPath(folder) / PurePosixPath(*file.relative_to(source).parts)).as_posix())
    return target


def import_world(instance: dict, archive_path: Union[str, Path],
                 name: Optional[str] = None) -> Path:
    """Import a world ZIP, guarding against ZIP-slip and oversized archives."""
    archive_path = Path(archive_path)
    saves = _saves(instance)
    saves.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > _MAX_MEMBERS:
            raise ValueError("The archive contains too many files")
        if sum(info.file_size for info in infos) > _MAX_UNPACKED:
            raise ValueError("The archive is too large")
        names = [info.filename.replace("\\", "/") for info in infos if not info.is_dir()]
        level_candidates = [n for n in names if n == "level.dat" or n.endswith("/level.dat")]
        if not level_candidates:
            raise ValueError("The archive does not contain a Minecraft world (level.dat)")
        level_name = min(level_candidates, key=lambda n: (n.count("/"), len(n)))
        prefix = level_name[:-len("level.dat")]
        folder = (prefix.rstrip("/").split("/")[-1] if prefix else "") or name or archive_path.stem
        target = unique_path(saves / safe_name(folder))
        target.mkdir(parents=True, exist_ok=True)
        for info in infos:
            member = info.filename.replace("\\", "/")
            if info.is_dir():
                continue
            if prefix and not member.startswith(prefix):
                continue
            relative = member[len(prefix):] if prefix else member
            if not relative:
                continue
            destination = _safe_member(target, relative)
            if destination is None:
                raise ValueError(f"Unsafe path in world archive: {member}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, destination.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
    if not (target / "level.dat").is_file():
        shutil.rmtree(target, ignore_errors=True)
        raise ValueError("The world archive is damaged (level.dat is missing)")
    if name:
        set_level_name(target / "level.dat", str(name))
    return target

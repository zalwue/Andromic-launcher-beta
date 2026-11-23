"""Filesystem layout of the launcher data directory.

The module deliberately keeps the historical module-level constants (``ROOT``,
``VERSIONS`` ...), but also exposes small, testable helpers used by the newer
features.  All helpers accept an explicit root where it makes sense, so the
launcher can be tested without touching the real user profile.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional, Union

from .system import OS, data_dir

ROOT = data_dir()
VERSIONS = ROOT / "versions"
LIBRARIES = ROOT / "libraries"
ASSETS = ROOT / "assets"
RUNTIME = ROOT / "runtime"
INSTANCES = ROOT / "instances"
SKINS = ROOT / "skins"
BACKUPS = ROOT / "backups"
DOWNLOADS = ROOT / "downloads"
AUTHLIB_INJECTOR = DOWNLOADS / "authlib-injector.jar"
INSTALLERS = ROOT / "installers"
NATIVES = ROOT / "natives"
DIAGNOSTICS = ROOT / "diagnostics"
CACHE = ROOT / "cache"

CONFIG_FILE = ROOT / "config.json"
MANIFEST_CACHE = ROOT / "manifest_cache.json"
LOADER_REGISTRY = ROOT / "loaders.json"

# Relative directory names, used when a caller supplies a different root.
LAYOUT_NAMES = (
    "versions", "libraries", "assets", "runtime", "instances", "skins",
    "backups", "downloads", "installers", "natives", "diagnostics", "cache",
)


def layout(root: Optional[Union[str, Path]] = None) -> Dict[str, Path]:
    """Return the launcher directory layout for ``root`` (or the default root)."""
    base = Path(root) if root is not None else ROOT
    return {name: base / name for name in LAYOUT_NAMES}


def ensure_dirs(root: Optional[Union[str, Path]] = None) -> None:
    """Create every directory used by the launcher.

    ``root`` is optional and defaults to the real data directory.  Creating a
    custom root is useful for portable installs and for tests.
    """
    base = Path(root) if root is not None else ROOT
    base.mkdir(parents=True, exist_ok=True)
    for directory in layout(base).values():
        directory.mkdir(parents=True, exist_ok=True)


def long_path(path: Union[str, Path]) -> str:
    """Return a Windows extended-length path when the regular path is too long.

    Windows historically limits paths to 260 characters unless the process is
    long-path aware.  The ``\\\\?\\`` prefix removes that limit for absolute
    paths and is a no-op on macOS/Linux.
    """
    text = str(path)
    if OS != "windows" or text.startswith("\\\\?\\"):
        return text
    windows_absolute = os.path.isabs(text) or bool(re.match(r"^[A-Za-z]:[\\/]", text))
    if len(text) < 240 or not windows_absolute:
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text.lstrip("\\")
    return "\\\\?\\" + text


def is_writable(path: Union[str, Path]) -> bool:
    """Check that ``path`` is (or can be made) a writable directory."""
    directory = Path(path)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".andromic-", dir=long_path(directory),
                                         delete=True):
            return True
    except OSError:
        return False


def free_space_mb(path: Union[str, Path] = ROOT) -> int:
    """Free disk space in MiB for the volume containing ``path``."""
    try:
        usage = shutil.disk_usage(str(path))
        return int(usage.free // (1024 * 1024))
    except OSError:
        return 0


def _temporary_name(path: Path) -> Path:
    suffix = f".{os.getpid()}.{int(time.time() * 1000)}.tmp"
    return path.with_name(path.name + suffix)


def atomic_write_bytes(path: Union[str, Path], data: bytes) -> Path:
    """Write ``data`` atomically so an interrupted write cannot corrupt a file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_name(target)
    try:
        temporary.write_bytes(data)
        os.replace(long_path(temporary), long_path(target))
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass
    return target


def atomic_write_text(path: Union[str, Path], text: str, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, text.encode(encoding))


def safe_remove_tree(path: Union[str, Path]) -> bool:
    """Remove a directory tree, tolerating read-only files on Windows."""
    target = Path(path)
    if not target.exists():
        return False

    def onerror(func, name, _exc_info):
        try:
            os.chmod(name, 0o700)
            func(name)
        except OSError:
            pass

    shutil.rmtree(long_path(target), onerror=onerror)
    return True


def path_inside(base: Union[str, Path], target: Union[str, Path]) -> bool:
    """True when ``target`` resolves inside ``base`` (path traversal guard)."""
    try:
        Path(target).resolve().relative_to(Path(base).resolve())
        return True
    except (OSError, ValueError):
        return False


def unique_path(path: Union[str, Path]) -> Path:
    """Return ``path`` or ``name (2).ext`` / ``name (3).ext`` when it exists."""
    candidate = Path(path)
    if not candidate.exists():
        return candidate
    stem, suffix, parent = candidate.stem, candidate.suffix, candidate.parent
    counter = 2
    while True:
        alternative = parent / f"{stem} ({counter}){suffix}"
        if not alternative.exists():
            return alternative
        counter += 1

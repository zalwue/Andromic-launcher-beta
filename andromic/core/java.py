"""Java runtime selection, discovery and provisioning."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import RUNTIME_URL
from .net import DownloadCancelled, download, download_many, get_json
from .paths import RUNTIME
from .reporter import Reporter
from .system import (ARCH, JAVA_BIN, OS, POPEN_FLAGS, adoptium_target, make_executable,
                     mojang_runtime_key, normalize_path)


def guess_major(mc: str) -> Optional[int]:
    """Best-effort Java major version for a release id, used for display only."""
    nums = [int(n) for n in re.findall(r"\d+", mc.split("-")[0])]
    if not re.match(r"^\d+\.\d+", mc) or len(nums) < 2:
        return None
    if nums[0] >= 26:
        return 25
    minor = nums[1]
    patch = nums[2] if len(nums) > 2 else 0
    if minor >= 21 or (minor == 20 and patch >= 5):
        return 21
    if minor >= 17:
        return 17
    return 8


def find_java(root: Path) -> Optional[Path]:
    """Find a Java executable, treating inaccessible directories as unavailable."""
    root = Path(root)
    try:
        if not root.exists() or not root.is_dir():
            return None
        direct = root / "bin" / JAVA_BIN
        if direct.is_file():
            return direct
        candidates = sorted(root.glob(f"**/bin/{JAVA_BIN}"))
    except (OSError, PermissionError):
        return None
    if candidates:
        # Prefer a shallower path (e.g. jdk-21/bin/java over a bundled sample).
        return min(candidates, key=lambda p: (len(p.parts), str(p)))
    return None


def java_home_candidates() -> List[Path]:
    """Common JDK/JRE installation directories for Windows, macOS and Linux."""
    homes: List[Path] = []
    java_home = normalize_path(os.getenv("JAVA_HOME"))
    if java_home:
        try:
            homes.append(Path(java_home))
        except (OSError, ValueError):
            pass
    if OS == "windows":
        roots = [
            os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)"),
            os.getenv("LOCALAPPDATA") and str(Path(os.getenv("LOCALAPPDATA")) / "Programs"),
        ]
        vendors = ("Java", "Eclipse Adoptium", "Eclipse Foundation", "Microsoft",
                   "Zulu", "BellSoft", "Amazon Corretto", "Semeru")
        for base in roots:
            if not base:
                continue
            for vendor in vendors:
                folder = Path(base) / vendor
                try:
                    if folder.is_dir():
                        homes.extend(sorted((p for p in folder.iterdir() if p.is_dir()),
                                            reverse=True))
                except (OSError, PermissionError):
                    continue
    elif OS == "osx":
        mac_root = Path("/Library/Java/JavaVirtualMachines")
        try:
            if mac_root.is_dir():
                for bundle in sorted(mac_root.iterdir(), reverse=True):
                    homes.append(bundle / "Contents" / "Home")
        except (OSError, PermissionError):
            pass
    else:
        for base in (Path("/usr/lib/jvm"), Path("/usr/java"), Path("/opt/java")):
            try:
                if base.is_dir():
                    homes.extend(sorted((p for p in base.iterdir() if p.is_dir()), reverse=True))
            except (OSError, PermissionError):
                continue
    return homes


def java_candidates() -> List[Path]:
    """Every discoverable Java executable, de-duplicated, newest-looking first."""
    found: List[Path] = []
    seen = set()

    def add(path: Optional[Path]) -> None:
        if not path:
            return
        path = Path(path)
        try:
            if path.is_dir():
                path = find_java(path)
            if not path or not path.is_file():
                return
        except (OSError, PermissionError):
            return
        key = str(path).lower() if OS == "windows" else str(path)
        if key not in seen:
            seen.add(key)
            found.append(path)

    for home in java_home_candidates():
        add(home)
    path_env = os.getenv("PATH", "")
    for part in path_env.split(os.pathsep):
        if part:
            add(Path(part) / JAVA_BIN)
    add(Path(shutil.which(JAVA_BIN)) if shutil.which(JAVA_BIN) else None)
    return found


def java_major(path: Path) -> Optional[int]:
    """Read the major version from ``java -version`` without raising."""
    try:
        result = subprocess.run(
            [str(path), "-version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", timeout=6, creationflags=POPEN_FLAGS)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r'version "(\d+)(?:\.(\d+))?', result.stdout or "")
    if not match:
        return None
    major = int(match.group(1))
    if major == 1 and match.group(2):
        return int(match.group(2))
    return major


def find_system_java(min_major: Optional[int] = None) -> Optional[Path]:
    """Return the best installed Java, optionally requiring a minimum major."""
    fallback = None
    for candidate in java_candidates():
        major = java_major(candidate)
        if major is None:
            fallback = fallback or candidate
            continue
        if min_major is None or major >= min_major:
            return candidate
    return fallback


def _safe_extract_tar(archive: Path, dest: Path) -> None:
    """Extract a tar archive, using the safe data filter when available."""
    with tarfile.open(archive) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(dest, filter="data")
        else:  # Python < 3.12
            members = []
            for member in tar.getmembers():
                target = (dest / member.name).resolve()
                try:
                    target.relative_to(dest.resolve())
                except ValueError:
                    continue
                members.append(member)
            tar.extractall(dest, members=members)


def _safe_extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            try:
                target.relative_to(dest.resolve())
            except ValueError:
                continue
            z.extract(info, dest)


def _mojang_runtime(component: str, rep: Reporter) -> Optional[str]:
    dest = RUNTIME / f"{component}-{OS}-{ARCH}"
    java = find_java(dest)
    if java and (dest / ".complete").exists():
        return str(java)
    index = get_json(RUNTIME_URL)
    entry = index.get(mojang_runtime_key(), {}).get(component)
    if not entry:
        return None
    manifest = get_json(entry[0]["manifest"]["url"])
    items, executables, links = [], [], []
    for rel, info in manifest["files"].items():
        kind = info["type"]
        if kind == "directory":
            (dest / rel).mkdir(parents=True, exist_ok=True)
        elif kind == "file":
            raw = info["downloads"]["raw"]
            items.append((raw["url"], dest / rel, raw["sha1"], raw["size"]))
            if info.get("executable"):
                executables.append(dest / rel)
        elif kind == "link":
            links.append((dest / rel, info["target"]))
    download_many(items, rep, "Java runtime")
    for path in executables:
        make_executable(path)
    for link, target in links:
        try:
            if not link.exists() and not link.is_symlink():
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(target)
        except OSError:
            # Windows may deny symlink creation without developer mode; Mojang
            # runtimes normally contain real files there as well.
            pass
    (dest / ".complete").write_text("ok", encoding="utf-8")
    java = find_java(dest)
    return str(java) if java else None


def _adoptium_runtime(major: int, rep: Reporter) -> str:
    major = 17 if major == 16 else major
    dest = RUNTIME / f"temurin-{major}-{OS}-{ARCH}"
    java = find_java(dest)
    if java:
        return str(java)
    os_name, arch = adoptium_target()
    url = (f"https://api.adoptium.net/v3/binary/latest/{major}/ga/"
           f"{os_name}/{arch}/jre/hotspot/normal/eclipse")
    rep.status(f"Downloading Java {major}")
    archive = RUNTIME / f"temurin-{major}.archive"
    RUNTIME.mkdir(parents=True, exist_ok=True)
    # Streaming download with .part + retry + atomic rename (never fully in RAM).
    download(url, archive, timeout=600)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if zipfile.is_zipfile(archive):
            _safe_extract_zip(archive, dest)
        else:
            _safe_extract_tar(archive, dest)
    finally:
        archive.unlink(missing_ok=True)
    java = find_java(dest)
    if not java:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"Java {major} could not be installed")
    make_executable(java)
    return str(java)


def resolve_override(override: str) -> Optional[str]:
    """Validate a user supplied Java path (file or JAVA_HOME directory)."""
    value = normalize_path(override)
    if not value:
        return None
    path = Path(value)
    if path.is_dir():
        java = find_java(path)
        return str(java) if java else None
    if path.is_file():
        return str(path)
    return None


def ensure_java(version: dict, override: str, rep: Reporter) -> Tuple[str, int]:
    """Return (java executable, major version) for the given version metadata."""
    info = version.get("javaVersion", {})
    component = info.get("component", "jre-legacy")
    major = int(info.get("majorVersion", 8))
    custom = resolve_override(override)
    if custom:
        return custom, java_major(Path(custom)) or major
    if override:
        rep.log(f"Custom Java path is unavailable, using automatic selection: {override}")
    rep.status(f"Preparing Java {major}")
    try:
        path = _mojang_runtime(component, rep)
        if path:
            return path, major
    except DownloadCancelled:
        raise
    except Exception as exc:
        rep.log(f"Mojang runtime unavailable ({exc}); falling back to Temurin")
    return _adoptium_runtime(major, rep), major

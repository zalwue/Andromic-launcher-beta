"""Java runtime selection and provisioning."""
import re
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from .constants import RUNTIME_URL
from .net import download_many, get_json, http_get
from .paths import RUNTIME
from .reporter import Reporter
from .system import JAVA_BIN, OS, adoptium_target, make_executable, mojang_runtime_key


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
    if not root.exists():
        return None
    for candidate in root.glob(f"**/bin/{JAVA_BIN}"):
        return candidate
    return None


def _mojang_runtime(component: str, rep: Reporter) -> Optional[str]:
    dest = RUNTIME / component
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
            pass
    (dest / ".complete").write_text("ok")
    java = find_java(dest)
    return str(java) if java else None


def _adoptium_runtime(major: int, rep: Reporter) -> str:
    major = 17 if major == 16 else major
    dest = RUNTIME / f"temurin-{major}"
    java = find_java(dest)
    if java:
        return str(java)
    os_name, arch = adoptium_target()
    url = (f"https://api.adoptium.net/v3/binary/latest/{major}/ga/"
           f"{os_name}/{arch}/jre/hotspot/normal/eclipse")
    rep.status(f"Downloading Java {major}")
    archive = RUNTIME / f"temurin-{major}.archive"
    archive.write_bytes(http_get(url, 600))
    dest.mkdir(parents=True, exist_ok=True)
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as z:
                z.extractall(dest)
        else:
            with tarfile.open(archive) as t:
                t.extractall(dest)
    finally:
        archive.unlink(missing_ok=True)
    java = find_java(dest)
    if not java:
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(f"Java {major} could not be installed")
    make_executable(java)
    return str(java)


def ensure_java(version: dict, override: str, rep: Reporter) -> Tuple[str, int]:
    """Return (java executable, major version) for the given version metadata."""
    info = version.get("javaVersion", {})
    component = info.get("component", "jre-legacy")
    major = int(info.get("majorVersion", 8))
    if override and Path(override).exists():
        return override, major
    rep.status(f"Preparing Java {major}")
    try:
        path = _mojang_runtime(component, rep)
        if path:
            return path, major
    except Exception as exc:
        rep.log(f"Mojang runtime unavailable ({exc}); falling back to Temurin")
    return _adoptium_runtime(major, rep), major

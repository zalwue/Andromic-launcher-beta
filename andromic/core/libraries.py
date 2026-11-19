"""Library resolution, download and native extraction."""
import zipfile
from pathlib import Path
from typing import List, NamedTuple, Optional

from .constants import LIBRARIES_URL
from .net import download_many
from .paths import LIBRARIES, NATIVES
from .reporter import Reporter
from .rules import rules_ok
from .system import NATIVE_BITS, NATIVE_EXTS, OS


class LibFile(NamedTuple):
    url: Optional[str]
    path: Path
    sha1: Optional[str]
    size: Optional[int]
    native: bool


def maven_path(name: str) -> str:
    ext = "jar"
    if "@" in name:
        name, ext = name.split("@", 1)
    parts = name.split(":")
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else ""
    filename = f"{artifact}-{version}" + (f"-{classifier}" if classifier else "") + "." + ext
    return f"{group.replace('.', '/')}/{artifact}/{version}/{filename}"


def lib_key(name: str) -> tuple:
    parts = name.split("@")[0].split(":")
    return parts[0], parts[1], parts[3] if len(parts) > 3 else ""


def lib_files(lib: dict) -> List[LibFile]:
    if not rules_ok(lib.get("rules")):
        return []
    files = []
    downloads = lib.get("downloads")
    if downloads:
        artifact = downloads.get("artifact")
        if artifact and artifact.get("path"):
            files.append(LibFile(artifact.get("url"), LIBRARIES / artifact["path"],
                                 artifact.get("sha1"), artifact.get("size"), False))
        natives = lib.get("natives")
        classifier = natives.get(OS) if natives else None
        if classifier:
            classifier = classifier.replace("${arch}", NATIVE_BITS)
            entry = downloads.get("classifiers", {}).get(classifier)
            if entry:
                files.append(LibFile(entry.get("url"), LIBRARIES / entry["path"],
                                     entry.get("sha1"), entry.get("size"), True))
    else:
        base = lib.get("url", LIBRARIES_URL)
        if not base.endswith("/"):
            base += "/"
        rel = maven_path(lib["name"])
        files.append(LibFile(base + rel, LIBRARIES / rel, None, None, False))
    return files


def install_libraries(version: dict, rep: Reporter):
    """Download all libraries; returns (classpath entries, native archives)."""
    items, classpath, natives = [], [], []
    for lib in version["libraries"]:
        for f in lib_files(lib):
            (natives if f.native else classpath).append(f.path)
            if f.url:
                items.append((f.url, f.path, f.sha1, f.size))
            elif not f.path.exists():
                rep.log(f"Missing library (expected from installer): {f.path.name}")
    download_many(items, rep, "Libraries")
    return classpath, natives


def extract_natives(archives, version_id: str) -> Path:
    target = NATIVES / version_id
    target.mkdir(parents=True, exist_ok=True)
    # Remove stale native binaries from older loader/library combinations.
    for stale in target.iterdir():
        if stale.is_file() and stale.name.lower().endswith(NATIVE_EXTS):
            stale.unlink(missing_ok=True)
    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as z:
                for name in z.namelist():
                    if name.startswith("META-INF") or not name.endswith(NATIVE_EXTS):
                        continue
                    out = target / Path(name).name
                    if not out.exists():
                        out.write_bytes(z.read(name))
        except (zipfile.BadZipFile, OSError):
            continue
    return target

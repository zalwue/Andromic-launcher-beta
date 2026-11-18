"""Mod loader discovery and installation (Fabric, Quilt, Forge, NeoForge)."""
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from typing import List

from .constants import (FABRIC_META, FORGE_MAVEN, NEOFORGE_LEGACY_MAVEN,
                        NEOFORGE_MAVEN, QUILT_META)
from .net import download, get_json, http_get
from .paths import INSTALLERS, LOADER_REGISTRY, ROOT, VERSIONS
from .reporter import Reporter
from .system import POPEN_FLAGS


def _maven_versions(metadata_url: str) -> List[str]:
    root = ET.fromstring(http_get(metadata_url))
    return [node.text for node in root.iter("version")]


def _neoforge_matches(version: str, mc: str) -> bool:
    if not mc.startswith("1."):
        return version.startswith(mc + ".")
    parts = version.split("-")[0].split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return False
    return mc == (f"1.{major}" if minor == 0 else f"1.{major}.{minor}")


def loader_versions(loader: str, mc: str) -> List[str]:
    """Available loader versions for a Minecraft version, newest first."""
    if loader == "Fabric":
        return [e["loader"]["version"] for e in get_json(f"{FABRIC_META}/versions/loader/{mc}")]
    if loader == "Quilt":
        return [e["loader"]["version"] for e in get_json(f"{QUILT_META}/versions/loader/{mc}")]
    if loader == "Forge":
        versions = _maven_versions(f"{FORGE_MAVEN}/maven-metadata.xml")
        return [v for v in reversed(versions) if v.startswith(mc + "-")]
    if loader == "NeoForge":
        if mc == "1.20.1":
            versions = _maven_versions(f"{NEOFORGE_LEGACY_MAVEN}/maven-metadata.xml")
            return [v for v in reversed(versions) if v.startswith("1.20.1-")]
        versions = _maven_versions(f"{NEOFORGE_MAVEN}/maven-metadata.xml")
        return [v for v in reversed(versions) if _neoforge_matches(v, mc)]
    return []


def _installer_url(loader: str, mc: str, version: str) -> str:
    if loader == "Forge":
        return f"{FORGE_MAVEN}/{version}/forge-{version}-installer.jar"
    if mc == "1.20.1":
        return f"{NEOFORGE_LEGACY_MAVEN}/{version}/forge-{version}-installer.jar"
    return f"{NEOFORGE_MAVEN}/{version}/neoforge-{version}-installer.jar"


def _load_registry() -> dict:
    try:
        return json.loads(LOADER_REGISTRY.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _install_profile_loader(loader: str, mc: str, version: str) -> str:
    base = FABRIC_META if loader == "Fabric" else QUILT_META
    profile = get_json(f"{base}/versions/loader/{mc}/{version}/profile/json")
    version_id = profile["id"]
    target = VERSIONS / version_id
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{version_id}.json").write_text(json.dumps(profile), "utf-8")
    return version_id


def _run_installer(loader: str, mc: str, version: str, java: str, rep: Reporter) -> str:
    profiles = ROOT / "launcher_profiles.json"
    if not profiles.exists():
        profiles.write_text(json.dumps({"profiles": {}, "version": 3}), "utf-8")
    jar = INSTALLERS / f"{loader.lower()}-{version}-installer.jar"
    download(_installer_url(loader, mc, version), jar)
    before = set(os.listdir(VERSIONS))
    rep.log(f"Running {loader} installer")
    proc = subprocess.Popen(
        [java, "-jar", str(jar), "--installClient", str(ROOT)], cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", creationflags=POPEN_FLAGS)
    for line in proc.stdout:
        rep.log(line.rstrip())
    if proc.wait() != 0:
        raise RuntimeError(f"The {loader} installer failed; see the console for details")
    created = [d for d in set(os.listdir(VERSIONS)) - before
               if (VERSIONS / d / f"{d}.json").exists()]
    if not created:
        tail = version.split("-", 1)[-1]
        created = [d for d in os.listdir(VERSIONS)
                   if (version in d or tail in d) and loader.lower() in d.lower()]
    if not created:
        raise RuntimeError("Installed loader version could not be located")
    return sorted(created, key=len)[0]


def install_loader(loader: str, mc: str, version: str, java: str, rep: Reporter) -> str:
    """Install a loader (if needed) and return the version id to launch."""
    key = f"{loader}|{mc}|{version}"
    registry = _load_registry()
    known = registry.get(key)
    if known and (VERSIONS / known / f"{known}.json").exists():
        return known
    rep.status(f"Installing {loader} {version}")
    if loader in ("Fabric", "Quilt"):
        version_id = _install_profile_loader(loader, mc, version)
    else:
        version_id = _run_installer(loader, mc, version, java, rep)
    registry[key] = version_id
    LOADER_REGISTRY.write_text(json.dumps(registry), "utf-8")
    return version_id

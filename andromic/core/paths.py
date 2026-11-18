"""Filesystem layout of the launcher data directory."""
from .system import data_dir

ROOT = data_dir()
VERSIONS = ROOT / "versions"
LIBRARIES = ROOT / "libraries"
ASSETS = ROOT / "assets"
RUNTIME = ROOT / "runtime"
INSTANCES = ROOT / "instances"
SKINS = ROOT / "skins"
BACKUPS = ROOT / "backups"
DOWNLOADS = ROOT / "downloads"
INSTALLERS = ROOT / "installers"
NATIVES = ROOT / "natives"

CONFIG_FILE = ROOT / "config.json"
MANIFEST_CACHE = ROOT / "manifest_cache.json"
LOADER_REGISTRY = ROOT / "loaders.json"


def ensure_dirs() -> None:
    for d in (ROOT, VERSIONS, LIBRARIES, ASSETS, RUNTIME, INSTANCES, SKINS,
              BACKUPS, DOWNLOADS, INSTALLERS, NATIVES):
        d.mkdir(parents=True, exist_ok=True)

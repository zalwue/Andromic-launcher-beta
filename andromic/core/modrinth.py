"""Modrinth search and project installation."""
import json
import urllib.parse
from pathlib import Path
from typing import Callable, List, Optional, Set

from .constants import MODRINTH_API
from .net import download, get_json

KIND_DIRS = {"mod": "mods", "resourcepack": "resourcepacks", "shader": "shaderpacks"}

FPS_PRESETS = {
    "Fabric": ["fabric-api", "sodium", "lithium", "ferrite-core", "iris",
               "entityculling", "immediatelyfast"],
    "Quilt": ["qsl", "sodium", "lithium", "ferrite-core", "iris", "entityculling"],
    "Forge": ["embeddium", "ferrite-core", "oculus", "entityculling"],
    "NeoForge": ["sodium", "iris", "ferrite-core", "entityculling", "immediatelyfast"],
}


def mod_loaders(loader: str) -> List[str]:
    return {"Fabric": ["fabric"], "Quilt": ["quilt", "fabric"],
            "Forge": ["forge"], "NeoForge": ["neoforge"]}.get(loader, [])


def search(kind: str, query: str, mc: Optional[str], loader: str = "Vanilla") -> List[dict]:
    facets = [[f"project_type:{kind}"]]
    if mc and kind != "modpack":
        facets.append([f"versions:{mc}"])
    if kind == "mod" and loader != "Vanilla":
        facets.append([f"categories:{name}" for name in mod_loaders(loader)])
    params = urllib.parse.urlencode({"query": query, "facets": json.dumps(facets), "limit": 40})
    return get_json(f"{MODRINTH_API}/search?{params}")["hits"]


def project_versions(project: str, mc: Optional[str] = None,
                     loaders: Optional[List[str]] = None) -> List[dict]:
    params = {}
    if mc:
        params["game_versions"] = json.dumps([mc])
    if loaders:
        params["loaders"] = json.dumps(loaders)
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    return get_json(f"{MODRINTH_API}/project/{project}/version{query}")


def primary_file(version: dict) -> dict:
    return next((f for f in version["files"] if f.get("primary")), version["files"][0])


def install_project(project: str, dest: Path, mc: Optional[str] = None,
                    loaders: Optional[List[str]] = None, dependencies: bool = True,
                    log: Callable[[str], None] = print, _seen: Optional[Set[str]] = None,
                    _depth: int = 0) -> Optional[str]:
    """Install the newest compatible version of a project; returns the file name."""
    seen = _seen if _seen is not None else set()
    if project in seen or _depth > 4:
        return None
    seen.add(project)
    versions = project_versions(project, mc, loaders)
    if not versions:
        log(f"No compatible version found for {project}")
        return None
    version = versions[0]
    file = primary_file(version)
    download(file["url"], Path(dest) / file["filename"],
             file.get("hashes", {}).get("sha1"), file.get("size"))
    log(f"Installed {file['filename']}")
    if dependencies:
        for dep in version.get("dependencies", []):
            if dep.get("dependency_type") == "required" and dep.get("project_id"):
                install_project(dep["project_id"], dest, mc, loaders, True, log, seen, _depth + 1)
    return file["filename"]

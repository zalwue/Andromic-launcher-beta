"""Modrinth search and project installation."""
import json
import urllib.parse
from pathlib import Path
from typing import Callable, List, Optional, Set

from .constants import MODRINTH_API
from .net import download, download_many, get_json
from .reporter import Reporter

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


def project(project_id: str) -> dict:
    """Full Modrinth project metadata (no invented fields)."""
    return get_json(f"{MODRINTH_API}/project/{project_id}")


def search_hit_card(hit: dict) -> dict:
    """Normalise a search hit for display; only real returned fields."""
    return {
        "project_id": hit.get("project_id") or hit.get("id") or "",
        "slug": hit.get("slug", ""),
        "title": hit.get("title") or hit.get("name") or "",
        "description": hit.get("description", ""),
        "author": hit.get("author", ""),
        "icon_url": hit.get("icon_url") or "",
        "downloads": hit.get("downloads") if isinstance(hit.get("downloads"), int) else None,
        "follows": hit.get("follows") if isinstance(hit.get("follows"), int) else None,
        "project_type": hit.get("project_type", ""),
        "categories": hit.get("categories", []) or [],
        "versions": hit.get("versions", []) or [],
        "source": "Modrinth",
        "latest_version": hit.get("latest_version", ""),
    }


def _gather_project(project: str, mc: Optional[str], loaders: Optional[List[str]],
                    dependencies: bool, seen: Set[str], depth: int,
                    out: List[tuple], log: Callable[[str], None]) -> None:
    if project in seen or depth > 4:
        return
    seen.add(project)
    versions = project_versions(project, mc, loaders)
    if not versions:
        log(f"No compatible version found for {project}")
        return
    version = versions[0]
    file = primary_file(version)
    out.append((file["url"], file["filename"], file.get("hashes", {}).get("sha1"),
                file.get("size"), file["filename"]))
    if dependencies:
        for dep in version.get("dependencies", []):
            if dep.get("dependency_type") == "required" and dep.get("project_id"):
                _gather_project(dep["project_id"], mc, loaders, True, seen, depth + 1, out, log)


def install_project(project: str, dest: Path, mc: Optional[str] = None,
                    loaders: Optional[List[str]] = None, dependencies: bool = True,
                    log: Callable[[str], None] = print, _seen: Optional[Set[str]] = None,
                    _depth: int = 0) -> Optional[str]:
    """Install the newest compatible version of a project; returns the file name.

    Files are downloaded with the shared streaming pipeline honouring the
    configured download concurrency; dependencies are installed recursively.
    """
    seen = _seen if _seen is not None else set()
    if project in seen or _depth > 4:
        return None
    seen.add(project)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    versions = project_versions(project, mc, loaders)
    if not versions:
        log(f"No compatible version found for {project}")
        return None
    version = versions[0]
    file = primary_file(version)
    primary_name = file["filename"]

    gathered: List[tuple] = [(file["url"], file["filename"],
                              file.get("hashes", {}).get("sha1"), file.get("size"),
                              file["filename"])]
    if dependencies:
        for dep in version.get("dependencies", []):
            if dep.get("dependency_type") == "required" and dep.get("project_id"):
                _gather_project(dep["project_id"], mc, loaders, True, seen, _depth + 1,
                                gathered, log)

    items = [(url, dest / filename, sha1, size) for url, filename, sha1, size, _n in gathered]
    rep = Reporter(log=log)
    download_many(items, rep, "Mods", workers=None)
    for _url, _filename, _sha1, _size, name in gathered:
        log(f"Installed {name}")
    return primary_name

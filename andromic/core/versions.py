"""Version manifest handling and version metadata merging."""
import json
from typing import List

from .constants import MANIFEST_URL, MIN_VERSION
from .libraries import lib_key
from .net import download, get_json
from .paths import MANIFEST_CACHE, VERSIONS
from .reporter import Reporter


def fetch_manifest() -> List[dict]:
    try:
        data = get_json(MANIFEST_URL)
        MANIFEST_CACHE.write_text(json.dumps(data), "utf-8")
    except Exception:
        data = json.loads(MANIFEST_CACHE.read_text("utf-8"))
    return data["versions"]


def selectable_ids(manifest: List[dict], snapshots: bool = False) -> List[str]:
    """Release (and optionally snapshot) ids, newest first, down to MIN_VERSION."""
    ids = []
    for entry in manifest:
        if entry["type"] == "release" or (snapshots and entry["type"] == "snapshot"):
            ids.append(entry["id"])
        if entry["id"] == MIN_VERSION:
            break
    return ids


def ensure_vanilla(manifest: List[dict], mc: str, rep: Reporter) -> dict:
    meta = VERSIONS / mc / f"{mc}.json"
    if not meta.exists():
        entry = next((v for v in manifest if v["id"] == mc), None)
        if entry is None:
            raise RuntimeError(f"Version {mc} was not found in the manifest")
        download(entry["url"], meta, entry.get("sha1"))
    version = json.loads(meta.read_text("utf-8"))
    client = version["downloads"]["client"]
    rep.status(f"Client {mc}")
    download(client["url"], VERSIONS / mc / f"{mc}.jar", client.get("sha1"), client.get("size"))
    return version


def load_version(version_id: str) -> dict:
    """Load a version json, resolving `inheritsFrom` chains."""
    data = json.loads((VERSIONS / version_id / f"{version_id}.json").read_text("utf-8"))
    parent_id = data.get("inheritsFrom")
    if not parent_id:
        data["_root"] = version_id
        return data
    parent = load_version(parent_id)
    merged = dict(parent)
    for key, value in data.items():
        if key == "libraries":
            continue
        if key == "arguments":
            parent_args = parent.get("arguments", {})
            merged["arguments"] = {k: parent_args.get(k, []) + value.get(k, [])
                                   for k in ("game", "jvm")}
        else:
            merged[key] = value
    seen, libs = set(), []
    for lib in data.get("libraries", []) + parent.get("libraries", []):
        key = lib_key(lib["name"])
        if key not in seen:
            seen.add(key)
            libs.append(lib)
    merged["libraries"] = libs
    merged["id"] = version_id
    merged["_root"] = parent["_root"]
    return merged

"""GitHub Releases updater for official Andromic builds."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .. import __version__
from .paths import DOWNLOADS
from .system import OS

REPOSITORY = "zalwue/Andromic-launcher-beta"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
USER_AGENT = f"AndromicLauncher/{__version__}"


def _version_tuple(value: str):
    """Return a comparable key that orders prereleases before final releases."""
    text = str(value or "").strip().lstrip("vV").lower()
    match = re.match(
        r"^(\d+(?:\.\d+)*)(?:[-.]?(alpha|a|beta|b|rc)(?:[-.]?(\d+))?)?",
        text,
    )
    if not match:
        numbers = [int(part) for part in re.findall(r"\d+", text)[:4]]
        release = tuple(numbers or [0])
        return release, 3, 0
    release = [int(part) for part in match.group(1).split(".")]
    while len(release) > 1 and release[-1] == 0:
        release.pop()
    label = match.group(2)
    pre_rank = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}
    return tuple(release), pre_rank[label] if label else 3, int(match.group(3) or 0)


def is_newer(remote: str, local: str = __version__) -> bool:
    return _version_tuple(remote) > _version_tuple(local)


def _asset_for_current_os(assets: list[dict]) -> Optional[dict]:
    names = [(a, str(a.get("name", "")).lower()) for a in assets]
    if OS == "windows":
        matches = [a for a, n in names if "windows" in n and n.endswith(".exe")]
    elif OS == "osx":
        matches = [a for a, n in names if "macos" in n and n.endswith((".pkg", ".zip", ".dmg"))]
        # Prefer the native installer package when both formats are published.
        matches.sort(key=lambda a: 0 if str(a.get("name", "")).lower().endswith(".pkg") else 1)
    else:
        matches = [a for a, n in names if "linux" in n and n.endswith((".deb", ".zip", ".tar.gz", ".appimage"))]
        matches.sort(key=lambda a: 0 if str(a.get("name", "")).endswith(".zip") else 1)
    return matches[0] if matches else None


def check_latest_release() -> Optional[dict]:
    """Return release metadata only when a newer compatible release exists."""
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            release = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub Releases returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not check for updates: {exc}") from exc

    tag = str(release.get("tag_name", "")).strip()
    if not tag or release.get("draft") or release.get("prerelease") or not is_newer(tag):
        return None
    asset = _asset_for_current_os(release.get("assets") or [])
    return {
        "version": tag,
        "name": release.get("name") or tag,
        "url": release.get("html_url", ""),
        "notes": release.get("body", ""),
        "asset": asset,
        "published_at": release.get("published_at", ""),
    }


def download_update(release: dict, progress=None) -> Path:
    """Download the compatible release asset to the launcher's Downloads folder."""
    asset = release.get("asset") or {}
    url = asset.get("browser_download_url")
    filename = Path(str(asset.get("name", ""))).name
    if not url or not filename or filename in (".", ".."):
        raise RuntimeError("This release has no downloadable build for your operating system.")
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    target = DOWNLOADS / filename
    from .net import download
    size = asset.get("size") if isinstance(asset.get("size"), int) else None
    # Streaming .part + size verification + atomic replace + temporary retries.
    download(url, target, size=size, timeout=30,
             progress=(lambda done, total: progress(done, total)) if progress else None)
    return target

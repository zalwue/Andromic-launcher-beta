"""HTTP helpers and a parallel file downloader."""
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .. import __version__
from .reporter import Reporter

HEADERS = {"User-Agent": f"AndromicLauncher/{__version__}"}


def http_get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str):
    return json.loads(http_get(url).decode("utf-8"))


def download(url, dest, sha1=None, size=None, retries=3):
    """Download a file unless it already exists with the expected size."""
    dest = Path(dest)
    if dest.exists() and (size is None or dest.stat().st_size == size):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            data = http_get(url, 90)
            if sha1 and hashlib.sha1(data).hexdigest() != sha1:
                raise IOError(f"checksum mismatch: {url}")
            tmp = dest.with_name(dest.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5)


def download_many(items, rep: Reporter, label: str, workers: int = 24):
    """items: iterable of (url, dest, sha1, size)."""
    unique, seen = [], set()
    for item in items:
        if str(item[1]) not in seen:
            seen.add(str(item[1]))
            unique.append(item)
    total = len(unique)
    if not total:
        return
    rep.progress(0, total, label)
    done = 0
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(download, *item) for item in unique]
        for future in as_completed(futures):
            future.result()
            done += 1
            if done % 5 == 0 or done == total:
                rep.progress(done, total, label)

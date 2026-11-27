"""HTTP helpers and a parallel, streaming file downloader.

Stage 3 download pipeline
-------------------------
* files are streamed in chunks; nothing is ever read fully into memory
* downloads go to a temporary ``<name>.part`` file next to the target
* after a successful download SHA-1 (and, when known, exact size) is verified
* on success the ``.part`` file is atomically renamed over the target
* on error or cancellation the ``.part`` file is removed
* temporary network errors are retried with backoff
* already-correct files are not downloaded again
* a shared cancellation token can stop everything cleanly
* real progress: bytes done/total, current-file speed and ETA (never only
  "files completed" speed)
* bounded worker pools with user-selectable concurrency modes

Concurrency modes (persisted in config as ``download_threads`` /
``download_threads_manual``)::

    economy  -> 2 threads
    balanced -> 4 threads
    fast     -> 8 threads   (default)
    maximum  -> 12 threads
    manual   -> custom value (1..MAX_WORKERS), ``download_threads_manual``

The selected mode applies to every download path: Minecraft versions,
Java Runtime, libraries, assets, mods and modpacks.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Deque, List, Optional, Tuple

from .. import __version__
from .paths import long_path
from .reporter import Reporter

HEADERS = {"User-Agent": f"AndromicLauncher/{__version__}"}

# 64 KiB chunks: streaming without loading whole files into RAM.
CHUNK_SIZE = 64 * 1024
DEFAULT_TIMEOUT = 90
DEFAULT_RETRIES = 3

# ---------------------------------------------------------------------------
# Concurrency modes
# ---------------------------------------------------------------------------

THREAD_MODES = {
    "economy": 2,
    "balanced": 4,
    "fast": 8,
    "maximum": 12,
    "manual": None,  # custom value from ``download_threads_manual``
}
DEFAULT_THREAD_MODE = "fast"
DEFAULT_MANUAL_THREADS = 8
MIN_WORKERS = 1
MAX_WORKERS = 32  # hard cap: never spawn an unbounded number of threads

_thread_mode = DEFAULT_THREAD_MODE
_manual_threads = DEFAULT_MANUAL_THREADS
_lock = threading.Lock()


def normalize_thread_mode(mode) -> str:
    text = str(mode or "").strip().lower()
    aliases = {"eco": "economy", "2": "economy", "4": "balanced",
               "8": "fast", "12": "maximum", "max": "maximum", "custom": "manual"}
    text = aliases.get(text, text)
    return text if text in THREAD_MODES else DEFAULT_THREAD_MODE


def clamp_workers(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        number = DEFAULT_MANUAL_THREADS
    return max(MIN_WORKERS, min(MAX_WORKERS, number))


def set_thread_mode(mode, manual=None) -> str:
    """Set the global download concurrency mode; returns the normalised mode."""
    global _thread_mode, _manual_threads
    with _lock:
        _thread_mode = normalize_thread_mode(mode)
        if manual is not None:
            _manual_threads = clamp_workers(manual)
        return _thread_mode


def thread_mode() -> str:
    return _thread_mode


def manual_threads() -> int:
    return _manual_threads


def configured_workers(cfg: Optional[dict] = None) -> int:
    """Number of download workers for the current configuration."""
    if cfg is not None:
        return resolve_workers(None, cfg)
    with _lock:
        mode, manual = _thread_mode, _manual_threads
    return _workers_for(mode, manual)


def _workers_for(mode: str, manual: int) -> int:
    mode = normalize_thread_mode(mode)
    if mode == "manual":
        return clamp_workers(manual)
    workers = THREAD_MODES.get(mode)
    return clamp_workers(workers if workers is not None else DEFAULT_MANUAL_THREADS)


def resolve_workers(workers=None, cfg: Optional[dict] = None) -> int:
    """Explicit ``workers`` wins; otherwise use the configured mode."""
    if workers is not None:
        return clamp_workers(workers)
    if cfg is not None:
        mode = normalize_thread_mode(cfg.get("download_threads", DEFAULT_THREAD_MODE))
        manual = clamp_workers(cfg.get("download_threads_manual", DEFAULT_MANUAL_THREADS))
        return _workers_for(mode, manual)
    return configured_workers()


def apply_thread_config(cfg: Optional[dict]) -> int:
    """Apply ``download_threads*`` keys from a config dict; returns workers."""
    cfg = cfg or {}
    set_thread_mode(cfg.get("download_threads", DEFAULT_THREAD_MODE),
                    cfg.get("download_threads_manual", DEFAULT_MANUAL_THREADS))
    return configured_workers()


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

class DownloadCancelled(Exception):
    """Raised when a download is cancelled by the user."""


# Backwards/forwards-friendly alias.
Cancelled = DownloadCancelled


class DownloadError(IOError):
    """A download failed (network, size or checksum verification)."""


class ChecksumMismatch(DownloadError):
    """Downloaded content did not match the expected digest."""


class CancelToken:
    """Thread-safe cancellation token shared across all download workers."""

    def __init__(self):
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event.clear()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise DownloadCancelled()

    def wait(self, timeout: float) -> bool:
        """Sleep ``timeout`` seconds; return True if cancelled during wait."""
        return self._event.wait(timeout)


# Common alias name.
CancellationToken = CancelToken

_default_cancel: Optional[CancelToken] = None


def set_default_cancel(token: Optional[CancelToken]):
    """Install a process-wide cancellation token; returns the previous one."""
    global _default_cancel
    previous = _default_cancel
    _default_cancel = token
    return previous


def get_default_cancel() -> Optional[CancelToken]:
    return _default_cancel


def _active_cancel(cancel: Optional[CancelToken]) -> Optional[CancelToken]:
    return cancel if cancel is not None else _default_cancel


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

@dataclass
class DownloadProgress:
    label: str = ""
    done_bytes: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0            # aggregate bytes/sec over recent window
    eta_seconds: Optional[float] = None
    files_done: int = 0
    files_total: int = 0
    current_file: str = ""
    current_done_bytes: int = 0
    current_total_bytes: int = 0
    current_speed_bps: float = 0.0    # current file, not just finished files
    extra: dict = field(default_factory=dict)

    @property
    def fraction(self) -> float:
        if self.total_bytes > 0:
            return max(0.0, min(1.0, self.done_bytes / self.total_bytes))
        if self.files_total > 0:
            return max(0.0, min(1.0, self.files_done / self.files_total))
        return 0.0


def format_bytes(num: float) -> str:
    value = float(num or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_speed(bps: float) -> str:
    return format_bytes(max(0.0, bps or 0.0)) + "/s"


def format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0 or seconds != seconds:  # noqa: PLR0124
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class _SpeedWindow:
    """Rolling-window speed meter over real bytes written."""

    def __init__(self, window: float = 1.5):
        self.window = window
        self._samples: Deque[Tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def add(self, count: int) -> None:
        now = time.monotonic()
        with self._lock:
            self._samples.append((now, count))
            self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def speed(self) -> float:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if not self._samples:
                return 0.0
            span = max(self.window, now - self._samples[0][0], 1e-3)
            total = sum(count for _t, count in self._samples)
            return total / span


class _ProgressTracker:
    def __init__(self, label: str, files_total: int, total_bytes: int, rep: Optional[Reporter]):
        self.label = label
        self.files_total = files_total
        self.total_bytes = total_bytes
        self.rep = rep
        self.done_bytes = 0
        self.files_done = 0
        self._lock = threading.Lock()
        self._speed = _SpeedWindow()
        self._last_emit = 0.0

    def add_bytes(self, count: int, current_file: str = "",
                  current_done: int = 0, current_total: int = 0,
                  current_speed: float = 0.0) -> None:
        with self._lock:
            self.done_bytes += count
        self._speed.add(count)
        self._emit(current_file, current_done, current_total, current_speed, force=False)

    def file_finished(self, file_size: int = 0) -> None:
        with self._lock:
            self.files_done += 1
        self._emit("", 0, 0, 0.0, force=True)

    def _emit(self, current_file: str, current_done: int, current_total: int,
              current_speed: float, force: bool) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < 0.08:
            return
        self._last_emit = now
        if self.rep is None:
            return
        speed = self._speed.speed()
        with self._lock:
            done_bytes, files_done = self.done_bytes, self.files_done
        remaining = max(0, self.total_bytes - done_bytes) if self.total_bytes > 0 else None
        eta = (remaining / speed) if (remaining is not None and speed > 1) else None
        progress = DownloadProgress(
            label=self.label, done_bytes=done_bytes, total_bytes=self.total_bytes,
            speed_bps=speed, eta_seconds=eta, files_done=files_done,
            files_total=self.files_total, current_file=current_file,
            current_done_bytes=current_done, current_total_bytes=current_total,
            current_speed_bps=current_speed,
        )
        try:
            self.rep.download(progress)
        except Exception:
            pass

    def finish(self) -> None:
        self._emit("", 0, 0, 0.0, force=True)


# ---------------------------------------------------------------------------
# HTTP helpers (unchanged signatures, kept for compatibility)
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str):
    return json.loads(http_get(url).decode("utf-8"))


def post_json(url: str, payload: dict, timeout: int = 30):
    """POST a JSON document and decode the JSON response."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={**HEADERS, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------------------
# Core streaming download
# ---------------------------------------------------------------------------

def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _file_digest(path: Path, algorithm: str = "sha1") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _already_valid(dest: Path, sha1: Optional[str], size: Optional[int]) -> bool:
    try:
        if not dest.is_file():
            return False
        if size is not None and dest.stat().st_size != size:
            return False
        if sha1 and _file_digest(dest, "sha1") != sha1.lower():
            return False
    except OSError:
        return False
    return True


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, DownloadCancelled):
        return False
    if isinstance(exc, ChecksumMismatch):
        return True  # possibly a corrupted transfer; retry
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (408, 425, 429, 500, 502, 503, 504)
    if isinstance(exc, (urllib.error.URLError, ConnectionError, TimeoutError,
                        socket.timeout, http.client.HTTPException)):
        return True
    if isinstance(exc, OSError):
        # e.g. transient network hiccups; not a local permission problem
        return exc.errno in (None, 32, 104, 110, 10053, 10054, 10060)
    return False


def _sleep_backoff(seconds: float, token: Optional[CancelToken]) -> None:
    if token is not None:
        if token.wait(seconds):
            raise DownloadCancelled()
    else:
        time.sleep(seconds)


def _stream_once(url: str, part: Path, token: Optional[CancelToken],
                 on_bytes: Callable[[int], None], timeout: int) -> None:
    """Single attempt: stream ``url`` into ``part`` (truncating it)."""
    request = urllib.request.Request(url, headers=HEADERS)
    part.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=timeout) as response, \
            part.open("wb") as out:
        while True:
            if token is not None:
                token.raise_if_cancelled()
            chunk = response.read(CHUNK_SIZE)
            if not chunk:
                break
            out.write(chunk)
            on_bytes(len(chunk))
        out.flush()
        os.fsync(out.fileno())


def download(url, dest, sha1=None, size=None, retries=DEFAULT_RETRIES,
             cancel: Optional[CancelToken] = None,
             progress: Optional[Callable[[int, int], None]] = None,
             sha256: Optional[str] = None,
             timeout: int = DEFAULT_TIMEOUT,
             chunk_size: int = CHUNK_SIZE) -> Path:
    """Download ``url`` to ``dest`` with streaming, verification and atomic rename.

    ``sha1``/``size``: when provided, the downloaded ``.part`` file must match
    exactly before it replaces ``dest``.  A correct existing file is kept.
    ``cancel``: optional :class:`CancelToken`; cancellation removes ``.part``.
    ``progress``: optional ``(done_bytes, total_bytes)`` callback.
    Returns the final destination path.
    """
    dest = Path(dest)
    sha1 = sha1.lower() if isinstance(sha1, str) else sha1
    sha256 = sha256.lower() if isinstance(sha256, str) else sha256
    token = _active_cancel(cancel)
    if token is not None:
        token.raise_if_cancelled()

    # Never overwrite a correctly downloaded file without necessity.
    if _already_valid(dest, sha1, size):
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    _remove_quietly(part)

    last_error: Optional[BaseException] = None
    attempts = max(1, int(retries))
    for attempt in range(attempts):
        try:
            done = {"n": 0}

            def _on_bytes(count: int, _done=done) -> None:
                _done["n"] += count
                if progress is not None:
                    try:
                        progress(_done["n"], size or 0)
                    except Exception:
                        pass

            _stream_once(url, part, token, _on_bytes, timeout)
            if token is not None:
                token.raise_if_cancelled()
            actual_size = part.stat().st_size
            if size is not None and actual_size != size:
                raise DownloadError(
                    f"size mismatch for {url}: expected {size} bytes, got {actual_size}")
            if sha1 and _file_digest(part, "sha1") != sha1:
                raise ChecksumMismatch(f"SHA-1 mismatch: {url}")
            if sha256 and _file_digest(part, "sha256") != sha256:
                raise ChecksumMismatch(f"SHA-256 mismatch: {url}")
            if token is not None:
                token.raise_if_cancelled()
            os.replace(long_path(str(part)), long_path(str(dest)))  # atomic replace
            return dest
        except DownloadCancelled:
            _remove_quietly(part)
            raise
        except BaseException as exc:  # noqa: BLE001 - cleanup then decide retry
            _remove_quietly(part)
            last_error = exc
            if not _is_retryable(exc) or attempt == attempts - 1:
                raise
            _sleep_backoff(1.5 * (attempt + 1), token)
            if token is not None:
                token.raise_if_cancelled()
    raise DownloadError(str(last_error) if last_error else f"download failed: {url}")


def _download_one_streaming(url, dest, sha1, size, token, name,
                            tracker: "_ProgressTracker", retries: int) -> None:
    """Worker body for :func:`download_many`; reports real byte progress."""
    dest_p = Path(dest)
    sha1_s = sha1.lower() if isinstance(sha1, str) else sha1
    if _already_valid(dest_p, sha1_s, size):
        tracker.file_finished(size or 0)
        return
    dest_p.parent.mkdir(parents=True, exist_ok=True)
    part = dest_p.with_name(dest_p.name + ".part")
    _remove_quietly(part)
    last_error: Optional[BaseException] = None
    current_speed = _SpeedWindow()
    for attempt in range(max(1, retries)):
        try:
            done = {"n": 0}

            def _on_bytes(count: int, _done=done, _name=name) -> None:
                _done["n"] += count
                current_speed.add(count)
                tracker.add_bytes(count, _name, _done["n"], size or 0, current_speed.speed())

            _stream_once(url, part, token, _on_bytes, DEFAULT_TIMEOUT)
            if token is not None:
                token.raise_if_cancelled()
            actual_size = part.stat().st_size
            if size is not None and actual_size != size:
                raise DownloadError(
                    f"size mismatch for {url}: expected {size} bytes, got {actual_size}")
            if sha1_s and _file_digest(part, "sha1") != sha1_s:
                raise ChecksumMismatch(f"SHA-1 mismatch: {url}")
            if token is not None:
                token.raise_if_cancelled()
            os.replace(long_path(str(part)), long_path(str(dest_p)))
            tracker.file_finished(actual_size)
            return
        except DownloadCancelled:
            _remove_quietly(part)
            raise
        except BaseException as exc:  # noqa: BLE001
            _remove_quietly(part)
            last_error = exc
            if not _is_retryable(exc) or attempt == retries - 1:
                raise
            _sleep_backoff(1.5 * (attempt + 1), token)
            if token is not None:
                token.raise_if_cancelled()
    raise DownloadError(str(last_error) if last_error else "download failed")


def download_many(items, rep: Optional[Reporter], label: str,
                  workers: Optional[int] = None,
                  cancel: Optional[CancelToken] = None) -> None:
    """Download many files with a bounded pool; ``items`` are ``(url, dest, sha1, size)``.

    Duplicate destinations are downloaded once.  Progress reports real bytes
    (including bytes of in-flight files), current speed and ETA.
    """
    token = _active_cancel(cancel)
    unique: List[Tuple] = []
    seen = set()
    for item in items:
        key = str(item[1])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    total = len(unique)
    if not total:
        if rep is not None:
            rep.progress(0, 0, label)
        return

    known_total = 0
    for item in unique:
        size = item[3] if len(item) > 3 else None
        if isinstance(size, int) and size > 0:
            known_total += size

    tracker = _ProgressTracker(label, total, known_total, rep)
    if rep is not None:
        rep.progress(0, total, label)
    tracker._emit("", 0, 0, 0.0, force=True)

    pool_size = resolve_workers(workers)
    pool = ThreadPoolExecutor(max_workers=pool_size, thread_name_prefix="andromic-dl")
    futures = []
    try:
        for item in unique:
            if token is not None:
                token.raise_if_cancelled()
            url, dest = item[0], item[1]
            sha1 = item[2] if len(item) > 2 else None
            size = item[3] if len(item) > 3 else None
            name = Path(str(dest)).name
            futures.append(pool.submit(_download_one_streaming, url, dest, sha1, size,
                                       token, name, tracker, DEFAULT_RETRIES))
        for future in as_completed(futures):
            future.result()  # propagate first error
            if rep is not None:
                rep.progress(tracker.files_done, total, label)
    except BaseException:
        if token is not None:
            token.cancel()
        for future in futures:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        _sweep_parts(unique)
        raise
    else:
        pool.shutdown(wait=True)
    if token is not None and token.cancelled:
        _sweep_parts(unique)
    tracker.finish()
    if rep is not None:
        rep.progress(total, total, label)


def _sweep_parts(items) -> None:
    for item in items:
        base = Path(str(item[1]))
        _remove_quietly(base.with_name(base.name + ".part"))


def cancel_downloads(token: Optional[CancelToken]) -> None:
    if token is not None:
        token.cancel()

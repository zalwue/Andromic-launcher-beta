"""Launcher diagnostics: environment checks, log analysis and safe repairs."""
from __future__ import annotations

import os
import platform
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from .. import __version__
from . import crash
from .config import DEFAULTS, sanitize_settings
from .instances import instance_dir
from .paths import (BACKUPS, DIAGNOSTICS, ROOT,
                    RUNTIME, atomic_write_text, ensure_dirs, free_space_mb,
                    is_writable, layout)
from .system import ARCH, OS, data_dir, total_ram_mb

STATUS_ORDER = {"ok": 0, "warn": 1, "error": 2}


def _check(check_id: str, title: str, status: str, details: str, fix: str = "") -> dict:
    return {"id": check_id, "title": title, "status": status,
            "details": details, "fix": fix}


def _root(root: Optional[Union[str, Path]]) -> Path:
    return Path(root) if root is not None else ROOT


def system_summary(root: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    base = _root(root)
    return {
        "app_version": __version__,
        "os": OS,
        "platform": platform.platform(),
        "architecture": ARCH,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "data_dir": str(base),
        "default_data_dir": str(data_dir()),
        "total_ram_mb": total_ram_mb(),
        "free_space_mb": free_space_mb(base if base.exists() else base.parent),
    }


def check_directories(root: Optional[Union[str, Path]] = None) -> dict:
    base = _root(root)
    expected = layout(base)
    missing = [name for name, path in expected.items() if not path.is_dir()]
    unwritable = [name for name, path in expected.items() if path.is_dir() and not is_writable(path)]
    free = free_space_mb(base if base.exists() else base.parent)
    if unwritable:
        return _check("paths", "Data directories", "error",
                      "Not writable: " + ", ".join(unwritable),
                      "Check folder permissions or choose another data directory.")
    if missing:
        return _check("paths", "Data directories", "warn",
                      "Missing: " + ", ".join(missing),
                      "Run 'Apply safe fixes' to create the missing folders.")
    if free < 512:
        return _check("paths", "Data directories", "warn",
                      f"Only {free} MB of free disk space remain.",
                      "Free some disk space before installing a game version.")
    return _check("paths", "Data directories", "ok",
                  f"All {len(expected)} folders are writable; {free} MB free.")


def check_config(cfg: Optional[dict] = None, root: Optional[Union[str, Path]] = None) -> dict:
    config = dict(DEFAULTS)
    config.update(cfg or {})
    problems = []
    accounts = config.get("accounts") if isinstance(config.get("accounts"), list) else []
    instances_list = (config.get("instances")
                      if isinstance(config.get("instances"), list) else [])
    if config.get("theme") not in ("light", "dark"):
        problems.append("unknown theme")
    if not accounts:
        problems.append("no profiles")
    if not isinstance(config.get("instances"), list):
        problems.append("invalid instance list")
    if not isinstance(config.get("servers"), list):
        problems.append("invalid server list")
    try:
        ram = int(config.get("ram", 4096))
    except (TypeError, ValueError):
        problems.append("invalid RAM value")
        ram = 4096
    total = total_ram_mb()
    if ram > total:
        problems.append(f"RAM ({ram} MB) exceeds installed memory ({total} MB)")
    if ram < 512:
        problems.append("RAM is below the safe minimum")
    sanitized = sanitize_settings(config)
    changed = [key for key in ("width", "height", "ram", "render_distance", "max_fps")
               if str(config.get(key)) != str(sanitized.get(key))]
    if changed:
        problems.append("out-of-range: " + ", ".join(changed))
    custom_java = str(config.get("java_path", "")).strip()
    if custom_java and not Path(os.path.expanduser(custom_java)).exists():
        problems.append("custom Java path does not exist")
    if problems:
        return _check("config", "Configuration", "warn", "; ".join(problems),
                      "Review Settings or run 'Apply safe fixes'.")
    return _check("config", "Configuration", "ok",
                  f"{len(accounts)} profile(s), "
                  f"{len(instances_list)} instance(s), {ram} MB RAM.")


def check_java(cfg: Optional[dict] = None) -> dict:
    config = dict(DEFAULTS)
    config.update(cfg or {})
    from .java import find_java, find_system_java, java_major

    runtimes = []
    if RUNTIME.is_dir():
        runtimes = [p.name for p in RUNTIME.iterdir() if p.is_dir() and find_java(p)]
    custom = str(config.get("java_path", "")).strip()
    custom_ok = False
    if custom:
        path = Path(os.path.expanduser(custom))
        custom_ok = path.exists()
    system = find_system_java()
    if not custom_ok and not system and not runtimes:
        return _check("java", "Java runtime", "error",
                      "No Java runtime was found.",
                      "Install Java 17/21 or let Andromic download it on first launch.")
    parts = []
    if custom:
        parts.append("custom path " + ("valid" if custom_ok else "missing"))
    if system:
        parts.append(f"system Java {java_major(system) or '?'} ({system})")
    if runtimes:
        parts.append(f"{len(runtimes)} downloaded runtime(s)")
    if custom and not custom_ok:
        return _check("java", "Java runtime", "warn", "; ".join(parts),
                      "Clear the custom Java path in Settings.")
    return _check("java", "Java runtime", "ok", "; ".join(parts))


def check_instances(cfg: Optional[dict] = None) -> dict:
    config = dict(DEFAULTS)
    config.update(cfg or {})
    instances = config.get("instances")
    if not isinstance(instances, list):
        instances = []
    if not instances:
        return _check("instances", "Instances", "warn", "No instances have been created yet.",
                      "Create an instance on the Play page.")
    missing = []
    worlds = 0
    for instance in instances:
        try:
            folder = instance_dir(instance)
        except (KeyError, TypeError):
            missing.append(str(instance))
            continue
        if not folder.is_dir():
            missing.append(instance.get("name", "?"))
        else:
            saves = folder / "saves"
            if saves.is_dir():
                worlds += sum(1 for child in saves.iterdir() if child.is_dir())
    if missing:
        return _check("instances", "Instances", "warn",
                      f"{len(missing)} instance folder(s) missing: " + ", ".join(missing[:5]),
                      "Open the Play page and re-create or remove the broken instance.")
    return _check("instances", "Instances", "ok",
                  f"{len(instances)} instance(s), {worlds} world(s).")


def check_backups() -> dict:
    if not BACKUPS.is_dir():
        return _check("backups", "Backups", "warn", "The backup folder does not exist.",
                      "Create a backup or run 'Apply safe fixes'.")
    archives = list(BACKUPS.glob("*.zip"))
    if not archives:
        return _check("backups", "Backups", "ok", "No backups yet.")
    newest = max(archives, key=lambda p: p.stat().st_mtime)
    age_days = max(0, int((time.time() - newest.stat().st_mtime) // 86400))
    return _check("backups", "Backups", "ok",
                  f"{len(archives)} archive(s); newest is {age_days} day(s) old.")


def check_network(timeout: float = 3.0) -> dict:
    host = "piston-meta.mojang.com"
    started = time.time()
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            pass
        latency = int((time.time() - started) * 1000)
        return _check("network", "Network", "ok", f"{host} reachable ({latency} ms).")
    except OSError as exc:
        return _check("network", "Network", "warn", f"{host} is unreachable: {exc}",
                      "Check the connection; offline play still works if files are cached.")


def analyze_log(lines: Iterable[str]) -> Dict[str, Any]:
    lines = list(lines)
    hints = crash.analyze(lines)
    errors = [line for line in lines
              if any(marker in line.upper() for marker in
                     ("ERROR", "EXCEPTION", "CAUSED BY"))][-8:]
    return {"hints": hints, "errors": errors, "lines": len(lines)}


def analyze_latest_log(instance: Optional[dict] = None) -> Dict[str, Any]:
    if not instance:
        return {"hints": [], "errors": [], "lines": 0, "path": ""}
    path = instance_dir(instance) / "logs" / "latest.log"
    if not path.is_file():
        return {"hints": [], "errors": [], "lines": 0, "path": str(path)}
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
    except OSError as exc:
        return {"hints": [], "errors": [str(exc)], "lines": 0, "path": str(path)}
    result = analyze_log(lines[-4000:])
    result["path"] = str(path)
    return result


def run_diagnostics(root: Optional[Union[str, Path]] = None, cfg: Optional[dict] = None,
                    instance: Optional[dict] = None,
                    include_network: bool = False) -> Dict[str, Any]:
    """Run every safe check and return a JSON-serialisable report."""
    base = _root(root)
    checks = [check_directories(base), check_config(cfg, base), check_java(cfg),
              check_instances(cfg), check_backups()]
    if include_network:
        checks.append(check_network())
    log = analyze_latest_log(instance)
    if log["hints"] or log["errors"]:
        checks.append(_check("logs", "Latest game log", "warn",
                             f"{len(log['hints'])} hint(s), {len(log['errors'])} error line(s).",
                             "Open the Console or the log file for details."))
    elif log.get("path"):
        checks.append(_check("logs", "Latest game log", "ok", "No known crash patterns found."))
    status = max((item["status"] for item in checks),
                 key=lambda value: STATUS_ORDER.get(value, 0), default="ok")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "summary": system_summary(base),
        "checks": checks,
        "log": log,
    }


def format_report(report: Dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "Andromic Launcher diagnostics",
        "=" * 32,
        f"Generated: {report.get('generated_at', '')}",
        f"Status: {str(report.get('status', '')).upper()}",
        f"Version: {summary.get('app_version', '')}",
        f"OS: {summary.get('platform', '')} ({summary.get('architecture', '')})",
        f"Python: {summary.get('python', '')}",
        f"Data folder: {summary.get('data_dir', '')}",
        f"RAM: {summary.get('total_ram_mb', '')} MB, free disk: {summary.get('free_space_mb', '')} MB",
        "",
        "Checks",
        "-" * 32,
    ]
    for check in report.get("checks", []):
        lines.append(f"[{str(check.get('status', '')).upper():5}] {check.get('title', '')}")
        if check.get("details"):
            lines.append("        " + str(check["details"]))
        if check.get("fix"):
            lines.append("        Fix: " + str(check["fix"]))
    log = report.get("log") or {}
    if log.get("hints") or log.get("errors"):
        lines += ["", "Log analysis", "-" * 32]
        lines += ["Hint: " + hint for hint in log.get("hints", [])]
        lines += ["Error: " + error for error in log.get("errors", [])]
    return "\n".join(lines) + "\n"


def save_report(report: Dict[str, Any], directory: Optional[Union[str, Path]] = None) -> Path:
    target_dir = Path(directory) if directory is not None else DIAGNOSTICS
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = target_dir / f"diagnostics-{stamp}.txt"
    atomic_write_text(target, format_report(report))
    return target


def apply_safe_fixes(root: Optional[Union[str, Path]] = None) -> List[str]:
    """Create missing folders and remove stale partial downloads.

    This intentionally never deletes worlds, mods, profiles or configuration.
    """
    base = _root(root)
    actions = []
    before = {name for name, path in layout(base).items() if not path.is_dir()}
    ensure_dirs(base)
    for name in sorted(before):
        actions.append(f"Created folder: {name}")
    for folder in (base / "downloads", base / "backups"):
        if not folder.is_dir():
            continue
        for partial in folder.glob("*.part"):
            try:
                if time.time() - partial.stat().st_mtime > 3600:
                    partial.unlink()
                    actions.append(f"Removed stale partial file: {partial.name}")
            except OSError:
                continue
    return actions

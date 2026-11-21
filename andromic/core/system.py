"""Operating system, architecture and small platform helpers."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

if sys.platform.startswith("win"):
    OS = "windows"
elif sys.platform == "darwin":
    OS = "osx"
else:
    OS = "linux"

IS_WINDOWS = OS == "windows"
IS_MACOS = OS == "osx"
IS_LINUX = OS == "linux"


def _detect_architecture() -> str:
    """Prefer the native hardware architecture, including Apple Silicon under Rosetta."""
    machine = platform.machine().lower()
    if OS == "osx":
        try:
            arm_capable = subprocess.check_output(
                ["sysctl", "-n", "hw.optional.arm64"],
                stderr=subprocess.DEVNULL, text=True, timeout=2
            ).strip() == "1"
            if arm_capable:
                return "arm64"
        except (OSError, subprocess.SubprocessError):
            pass
    if OS == "windows":
        machine = (os.getenv("PROCESSOR_ARCHITEW6432")
                   or os.getenv("PROCESSOR_ARCHITECTURE") or machine).lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine in ("x86", "i386", "i686", "x86_64", "amd64"):
        return "x86" if machine in ("x86", "i386", "i686") else "x64"
    return "x64"


ARCH = _detect_architecture()

CLASSPATH_SEP = ";" if OS == "windows" else ":"
JAVA_BIN = "java.exe" if OS == "windows" else "java"
# CREATE_NO_WINDOW keeps the Java console hidden when the launcher is packaged.
POPEN_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if OS == "windows" else 0
NATIVE_EXTS = {
    "windows": (".dll",),
    "osx": (".dylib", ".jnilib"),
    "linux": (".so",),
}[OS]
NATIVE_BITS = "32" if ARCH == "x86" else "64"


def data_dir() -> Path:
    """Return the per-user launcher data directory for the current OS.

    ``ANDROMIC_DATA_DIR`` is intentionally supported as an escape hatch for
    portable installs and automated tests.
    """
    override = os.getenv("ANDROMIC_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if OS == "windows":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif OS == "osx":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Andromic"


def platform_key() -> str:
    """Stable key such as ``windows-x64`` or ``mac-os-arm64``."""
    return f"{OS}-{ARCH}"


def mojang_runtime_key() -> str:
    if OS == "windows":
        return {"x64": "windows-x64", "x86": "windows-x86", "arm64": "windows-arm64"}[ARCH]
    if OS == "osx":
        return "mac-os-arm64" if ARCH == "arm64" else "mac-os"
    return "linux-i386" if ARCH == "x86" else "linux"


def adoptium_target() -> tuple:
    os_name = {"windows": "windows", "osx": "mac", "linux": "linux"}[OS]
    arch = {"x64": "x64", "arm64": "aarch64", "x86": "x32"}[ARCH]
    return os_name, arch


def total_ram_mb() -> int:
    try:
        if OS == "windows":
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                    ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                    ("total_virt", ctypes.c_ulonglong), ("avail_virt", ctypes.c_ulonglong),
                    ("avail_ext", ctypes.c_ulonglong),
                ]

            status = MemStatus()
            status.length = ctypes.sizeof(status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.total_phys // (1024 * 1024))
        if OS == "linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return int(line.split()[1]) // 1024
        if OS == "osx":
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], stderr=subprocess.DEVNULL, text=True,
                timeout=3)
            return int(out.strip()) // (1024 * 1024)
    except Exception:
        pass
    # ``os.sysconf`` is a portable fallback on POSIX systems.
    try:
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            if pages > 0 and page_size > 0:
                return int(pages * page_size // (1024 * 1024))
    except (OSError, ValueError):
        pass
    return 8192


def open_path(path) -> bool:
    """Open a file or directory in the native file manager.

    Returns ``False`` instead of raising when no opener is available; this is
    common on minimal Linux installations and should never crash the launcher.
    """
    target = str(path)
    try:
        if OS == "windows":
            startfile = getattr(os, "startfile", None)
            if startfile is not None:
                startfile(target)
            else:  # pragma: no cover - only on unusual Windows Python builds
                subprocess.Popen(["cmd", "/c", "start", "", target], close_fds=True)
        elif OS == "osx":
            subprocess.Popen(["open", target], close_fds=True)
        else:
            opener = shutil.which("xdg-open")
            if not opener:
                return False
            subprocess.Popen([opener, target], close_fds=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def make_executable(path: Path) -> None:
    """Mark a file executable on POSIX; harmless on Windows."""
    if OS == "windows":
        return
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        pass


def which_all(names: List[str]) -> List[Path]:
    """Return every executable matching ``names`` from PATH, de-duplicated."""
    found: List[Path] = []
    seen = set()
    for name in names:
        location = shutil.which(name)
        if location:
            path = Path(location)
            key = str(path).lower() if OS == "windows" else str(path)
            if key not in seen:
                seen.add(key)
                found.append(path)
    return found


def normalize_path(value: Optional[str]) -> Optional[str]:
    """Expand ``~`` and environment variables in a user supplied path."""
    if not value:
        return value
    return os.path.expandvars(os.path.expanduser(str(value)))

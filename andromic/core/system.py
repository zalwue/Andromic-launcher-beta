"""Operating system and architecture helpers."""
import os
import subprocess
import sys
import platform
from pathlib import Path

if sys.platform.startswith("win"):
    OS = "windows"
elif sys.platform == "darwin":
    OS = "osx"
else:
    OS = "linux"

_machine = platform.machine().lower()
if _machine in ("arm64", "aarch64"):
    ARCH = "arm64"
elif _machine in ("x86", "i386", "i686"):
    ARCH = "x86"
else:
    ARCH = "x64"

CLASSPATH_SEP = ";" if OS == "windows" else ":"
JAVA_BIN = "java.exe" if OS == "windows" else "java"
POPEN_FLAGS = 0x08000000 if OS == "windows" else 0
NATIVE_EXTS = {
    "windows": (".dll",),
    "osx": (".dylib", ".jnilib"),
    "linux": (".so",),
}[OS]
NATIVE_BITS = "32" if ARCH == "x86" else "64"


def data_dir() -> Path:
    if OS == "windows":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif OS == "osx":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Andromic"


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
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"])
            return int(out) // (1024 * 1024)
    except Exception:
        pass
    return 8192


def open_path(path) -> None:
    path = str(path)
    if OS == "windows":
        os.startfile(path)
    elif OS == "osx":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def make_executable(path: Path) -> None:
    if OS != "windows":
        path.chmod(path.stat().st_mode | 0o111)

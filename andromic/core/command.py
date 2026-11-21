"""Construction of the Java command line used to start the game."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List

from .. import __version__
from .accounts import offline_uuid
from .paths import ASSETS, LIBRARIES
from .rules import expand_args
from .system import CLASSPATH_SEP, OS

_G1_FLAGS = [
    "-XX:+UseG1GC",
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200",
    "-XX:+DisableExplicitGC",
    "-XX:+UseStringDeduplication",
]


def _as_args(value) -> List[str]:
    """Normalise a list/string of extra arguments into a list of strings."""
    if not value:
        return []
    if isinstance(value, str):
        return value.split()
    return [str(item) for item in value]


def _dedupe(items: Iterable[str]) -> List[str]:
    result, seen = [], set()
    for item in items:
        text = str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def build_command(version: dict, version_id: str, java: str, settings: dict, nick: str,
                  game_dir, classpath: List[str], natives_dir, asset_index: str,
                  server: str = "", extra_jvm: List[str] = ()) -> List[str]:
    classpath_str = CLASSPATH_SEP.join(_dedupe(classpath))
    width = str(settings.get("width", "1280"))
    height = str(settings.get("height", "720"))
    mapping = {
        "auth_player_name": nick,
        "version_name": version_id,
        "game_directory": str(game_dir),
        "assets_root": str(ASSETS),
        "assets_index_name": asset_index,
        "auth_uuid": offline_uuid(nick).replace("-", ""),
        "auth_access_token": "0",
        "auth_session": "0",
        "clientid": "0",
        "auth_xuid": "0",
        "user_type": "legacy",
        "version_type": version.get("type", "release"),
        "user_properties": "{}",
        "natives_directory": str(natives_dir),
        "launcher_name": "Andromic",
        "launcher_version": __version__,
        "classpath": classpath_str,
        "library_directory": str(LIBRARIES),
        "classpath_separator": CLASSPATH_SEP,
        "game_assets": str(ASSETS / "virtual" / "legacy"),
        "resolution_width": width,
        "resolution_height": height,
        "quickPlayMultiplayer": server,
        "quickPlayPath": "", "quickPlaySingleplayer": "", "quickPlayRealms": "",
        "path": "",
    }
    supports_quick_play = "is_quick_play_multiplayer" in str(version.get("arguments", {}))
    features = {
        "has_custom_resolution": False,
        "is_quick_play_multiplayer": bool(server) and supports_quick_play,
    }

    if "arguments" in version:
        jvm = expand_args(version["arguments"].get("jvm", []), features, mapping)
        game = expand_args(version["arguments"].get("game", []), features, mapping)
    else:
        jvm = [f"-Djava.library.path={natives_dir}", "-cp", classpath_str]
        game = expand_args(version.get("minecraftArguments", "").split(), features, mapping)

    if settings.get("fullscreen"):
        game.append("--fullscreen")
    else:
        game += ["--width", width, "--height", height]
    if server and not supports_quick_play:
        # IPv6 addresses without brackets are ambiguous; keep the host intact
        # and fall back to the default port in that case.
        host, sep, port = server.rpartition(":")
        if not sep or not port.isdigit() or ":" in host:
            host, port = server, "25565"
        game += ["--server", host, "--port", port or "25565"]

    memory = [f"-Xmx{settings.get('ram', 4096)}M",
              f"-Xms{min(int(settings.get('ram', 4096)), 1024)}M"]
    tuning = list(_G1_FLAGS) if settings.get("optimize_jvm") else []
    user_args = _as_args(settings.get("jvm_args", ""))
    platform_args: List[str] = ["-Dfile.encoding=UTF-8"]
    if OS == "osx":
        # GLFW/LWJGL needs the JVM on macOS's first thread.
        if "-XstartOnFirstThread" not in user_args and "-XstartOnFirstThread" not in jvm:
            platform_args.append("-XstartOnFirstThread")
        platform_args.append("-Xdock:name=Minecraft")
        resource_root = Path(getattr(
            sys, "_MEIPASS", Path(__file__).resolve().parents[2]
        ))
        dock_icon = resource_root / "assets" / "icon.png"
        if dock_icon.is_file():
            platform_args.append(f"-Xdock:icon={dock_icon}")
    return [java, *memory, *tuning, *user_args, *_as_args(extra_jvm), *platform_args,
            *jvm, version["mainClass"], *game]

"""Construction of the Java command line used to start the game."""
from typing import List

from .accounts import offline_uuid
from .. import __version__
from .paths import ASSETS, LIBRARIES
from .rules import expand_args
from .system import CLASSPATH_SEP

_G1_FLAGS = [
    "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled", "-XX:MaxGCPauseMillis=200",
    "-XX:+UnlockExperimentalVMOptions", "-XX:+DisableExplicitGC",
    "-XX:G1NewSizePercent=30", "-XX:G1MaxNewSizePercent=40", "-XX:G1HeapRegionSize=8M",
]


def build_command(version: dict, version_id: str, java: str, settings: dict, nick: str,
                  game_dir, classpath: List[str], natives_dir, asset_index: str,
                  server: str = "", extra_jvm: List[str] = ()) -> List[str]:
    classpath_str = CLASSPATH_SEP.join(classpath)
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
        "resolution_width": str(settings["width"]),
        "resolution_height": str(settings["height"]),
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

    if settings["fullscreen"]:
        game.append("--fullscreen")
    else:
        game += ["--width", str(settings["width"]), "--height", str(settings["height"])]
    if server and not supports_quick_play:
        host, _, port = server.partition(":")
        game += ["--server", host, "--port", port or "25565"]

    memory = [f"-Xmx{settings['ram']}M", f"-Xms{min(settings['ram'], 1024)}M"]
    tuning = _G1_FLAGS if settings["optimize_jvm"] else []
    user_args = settings["jvm_args"].split()
    return [java, *memory, *tuning, *user_args, *extra_jvm, *jvm, version["mainClass"], *game]

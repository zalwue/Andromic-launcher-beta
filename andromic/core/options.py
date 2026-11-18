"""Reading and editing options.txt, resource pack lists and shader settings."""
import json
from pathlib import Path
from typing import Dict, List

from .accounts import SKIN_PACK_ENTRY

_GRAPHICS = {"Fast": 0, "Fancy": 1, "Fabulous": 2}


def read_options(path: Path) -> Dict[str, str]:
    options = {}
    if path.exists():
        for line in path.read_text("utf-8", errors="replace").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                options[key] = value
    return options


def write_options(path: Path, options: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{k}:{v}" for k, v in options.items()) + "\n", "utf-8")


def _parse_list(raw: str) -> List[str]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def apply_settings(game_dir: Path, settings: dict, skin_pack: bool) -> None:
    path = game_dir / "options.txt"
    options = read_options(path)
    if settings["apply_video"]:
        mode = _GRAPHICS.get(settings["graphics"], 1)
        options.update({
            "renderDistance": str(settings["render_distance"]),
            "maxFps": str(settings["max_fps"]),
            "enableVsync": "true" if settings["vsync"] else "false",
            "graphicsMode": str(mode),
            "fancyGraphics": "false" if mode == 0 else "true",
            "fullscreen": "true" if settings["fullscreen"] else "false",
        })
    packs = [p for p in _parse_list(options.get("resourcePacks", "[]")) if p != SKIN_PACK_ENTRY]
    if skin_pack:
        if "vanilla" not in packs:
            packs.insert(0, "vanilla")
        packs.append(SKIN_PACK_ENTRY)
    if skin_pack or "resourcePacks" in options:
        options["resourcePacks"] = json.dumps(packs, separators=(",", ":"))
    incompatible = [p for p in _parse_list(options.get("incompatibleResourcePacks", "[]"))
                    if p != SKIN_PACK_ENTRY]
    if "incompatibleResourcePacks" in options:
        options["incompatibleResourcePacks"] = json.dumps(incompatible, separators=(",", ":"))
    write_options(path, options)


def enabled_resource_packs(game_dir: Path) -> List[str]:
    raw = read_options(game_dir / "options.txt").get("resourcePacks", "[]")
    return [p[5:] for p in _parse_list(raw) if p.startswith("file/")]


def toggle_resource_pack(game_dir: Path, name: str) -> bool:
    """Enable or disable a resource pack; returns the new state."""
    path = game_dir / "options.txt"
    options = read_options(path)
    packs = _parse_list(options.get("resourcePacks", "[]"))
    entry = f"file/{name}"
    enabled = entry not in packs
    if enabled:
        if "vanilla" not in packs:
            packs.insert(0, "vanilla")
        packs.append(entry)
    else:
        packs.remove(entry)
    options["resourcePacks"] = json.dumps(packs, separators=(",", ":"))
    write_options(path, options)
    return enabled


def _update_properties(path: Path, values: Dict[str, str]) -> None:
    lines = path.read_text("utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    for index, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            lines[index] = f"{key}={remaining.pop(key)}"
    lines += [f"{k}={v}" for k, v in remaining.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")


def set_shader_pack(game_dir: Path, name: str) -> None:
    """Select a shader pack for both Iris and OptiFine."""
    _update_properties(game_dir / "config" / "iris.properties",
                       {"shaderPack": name, "enableShaders": "true"})
    _update_properties(game_dir / "optionsshaders.txt", {"shaderPack": name})

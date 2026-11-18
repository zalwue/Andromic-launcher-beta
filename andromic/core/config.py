"""Persistent launcher configuration."""
import json

from .accounts import new_account
from .paths import CONFIG_FILE

DEFAULTS = {
    "theme": "light",
    "lang": "ru",
    "ram": 4096,
    "width": "1280",
    "height": "720",
    "fullscreen": False,
    "render_distance": 12,
    "max_fps": 120,
    "vsync": True,
    "graphics": "Fancy",
    "apply_video": True,
    "java_path": "",
    "jvm_args": "",
    "optimize_jvm": True,
    "hide_launcher": False,
    "fabric_api": True,
    "auto_backup": False,
    "accounts": [],
    "account": "",
    "instances": [],
    "instance": "",
    "servers": [],
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    if not cfg["accounts"]:
        cfg["accounts"] = [new_account()]
    if cfg["account"] not in {a["id"] for a in cfg["accounts"]}:
        cfg["account"] = cfg["accounts"][0]["id"]
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
    except OSError:
        pass


def sanitize_settings(cfg: dict) -> dict:
    """Return a copy of the settings with numeric fields coerced to valid ints."""
    out = dict(cfg)
    for key, low in (("width", 320), ("height", 240)):
        try:
            out[key] = max(low, int(out[key]))
        except (TypeError, ValueError):
            out[key] = int(DEFAULTS[key])
    out["ram"] = max(512, int(out["ram"]))
    out["render_distance"] = int(out["render_distance"])
    out["max_fps"] = int(out["max_fps"])
    return out

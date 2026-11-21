"""Persistent launcher configuration."""
import json

from .accounts import new_account
from .paths import CONFIG_FILE

DEFAULTS = {
    "theme": "light",
    "accent_color": "#3482FF",
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
    "auto_backup_keep": 5,
    "accounts": [],
    "account": "",
    "instances": [],
    "instance": "",
    "servers": [],
    "rooms": [],
    "customization": {},
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    for key in ("accounts", "instances", "servers", "rooms"):
        if not isinstance(cfg.get(key), list):
            cfg[key] = []
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
    """Return settings with numeric values coerced and clamped to safe ranges."""
    out = dict(DEFAULTS)
    out.update(cfg)

    def bounded_int(key, low, high):
        try:
            value = int(out.get(key, DEFAULTS[key]))
        except (TypeError, ValueError, OverflowError):
            value = int(DEFAULTS[key])
        out[key] = min(high, max(low, value))

    bounded_int("width", 320, 16384)
    bounded_int("height", 240, 16384)
    bounded_int("ram", 512, 65536)
    bounded_int("render_distance", 2, 32)
    bounded_int("max_fps", 10, 260)
    bounded_int("auto_backup_keep", 1, 50)
    return out

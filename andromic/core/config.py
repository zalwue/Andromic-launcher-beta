"""Persistent launcher configuration."""
import json
import os

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
    # Downloads (Stage 3): concurrency mode + manual worker count.
    # Modes: economy(2) | balanced(4) | fast(8, default) | maximum(12) | manual
    "download_threads": "fast",
    "download_threads_manual": 8,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        loaded = json.loads(CONFIG_FILE.read_text("utf-8"))
        if isinstance(loaded, dict):
            cfg.update(loaded)
    except (OSError, ValueError):
        pass
    migrate_config(cfg)
    return cfg


def migrate_config(cfg: dict) -> dict:
    """Bring old/partial configs up to the Stage 3 schema in place.

    Unknown keys are preserved; malformed known keys are repaired; servers are
    normalised; download settings are validated.  Existing saved user data is
    never dropped wholesale.
    """
    # Containers must be lists.
    for key in ("accounts", "instances", "servers", "rooms"):
        if not isinstance(cfg.get(key), list):
            cfg[key] = []
    if not isinstance(cfg.get("customization"), dict):
        cfg["customization"] = {}
    # Fill any missing defaults (old configs from 2.0/2.1/2.2).
    for key, value in DEFAULTS.items():
        cfg.setdefault(key, _copy_default(value))
    # Servers: keep user entries, repair shape, drop unusable ones.
    cfg["servers"] = normalize_servers(cfg.get("servers"))
    # Download concurrency settings.
    mode = str(cfg.get("download_threads") or "fast").strip().lower()
    aliases = {"eco": "economy", "custom": "manual", "max": "maximum"}
    mode = aliases.get(mode, mode)
    cfg["download_threads"] = mode if mode in _THREAD_MODES else "fast"
    cfg["download_threads_manual"] = _clamp_int(
        cfg.get("download_threads_manual"), 1, _MAX_WORKERS, 8)
    # Accounts.
    if not cfg["accounts"]:
        cfg["accounts"] = [new_account()]
    valid_ids = {a.get("id") for a in cfg["accounts"] if isinstance(a, dict)}
    if cfg.get("account") not in valid_ids:
        first = next((a for a in cfg["accounts"] if isinstance(a, dict)), None)
        cfg["account"] = first.get("id") if first else ""
    return cfg


def _copy_default(value):
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


def normalize_servers(entries) -> list:
    """Normalise persisted server entries; keep valid data, repair the rest."""
    from .servers import normalize_server_entry
    if not isinstance(entries, list):
        return []
    out = []
    seen = set()
    for entry in entries:
        clean = normalize_server_entry(entry)
        if clean is None:
            continue
        key = clean["address"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _clamp_int(value, low, high, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return max(low, min(high, number))


_THREAD_MODES = ("economy", "balanced", "fast", "maximum", "manual")
_MAX_WORKERS = 32


def save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")
        # Ely.by access tokens live in config.json; keep it private on POSIX systems.
        if os.name != "nt":
            CONFIG_FILE.chmod(0o600)
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
    bounded_int("download_threads_manual", 1, 32)
    mode = str(out.get("download_threads") or "fast").strip().lower()
    out["download_threads"] = mode if mode in _THREAD_MODES else "fast"
    return out

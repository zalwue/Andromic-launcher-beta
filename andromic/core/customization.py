"""Theme presets, accent colours and launcher appearance customisation."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

PRESETS: Dict[str, Dict[str, Any]] = {
    "hyperos": {
        "label": "HyperOS", "theme": "light", "accent_color": "#3482FF",
        "density": "comfortable", "animations": True, "background": "",
        "corner_radius": 22, "font_scale": 100, "sidebar_position": "left", "wallpaper_path": "", "frosted_glass": True,
    },
    "midnight": {
        "label": "Midnight", "theme": "dark", "accent_color": "#7AA2FF",
        "density": "comfortable", "animations": True, "background": "",
        "corner_radius": 22, "font_scale": 100, "sidebar_position": "left", "wallpaper_path": "", "frosted_glass": True,
    },
    "forest": {
        "label": "Forest", "theme": "light", "accent_color": "#2E7D5B",
        "density": "compact", "animations": True, "background": "",
        "corner_radius": 18, "font_scale": 100, "sidebar_position": "left", "wallpaper_path": "", "frosted_glass": True,
    },
    "sunset": {
        "label": "Sunset", "theme": "dark", "accent_color": "#FF7A59",
        "density": "comfortable", "animations": True, "background": "",
        "corner_radius": 24, "font_scale": 105, "sidebar_position": "left", "wallpaper_path": "", "frosted_glass": True,
    },
    "mono": {
        "label": "Mono", "theme": "light", "accent_color": "#4A4A4A",
        "density": "compact", "animations": False, "background": "",
        "corner_radius": 14, "font_scale": 95, "sidebar_position": "left", "wallpaper_path": "", "frosted_glass": True,
    },
}

DEFAULT_CUSTOMIZATION: Dict[str, Any] = dict(PRESETS["hyperos"])
DEFAULT_CUSTOMIZATION["preset"] = "hyperos"

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def normalize_hex(value: Any, fallback: str = "#3482FF") -> str:
    """Accept ``#RGB``, ``#RRGGBB`` or the same without ``#``."""
    text = str(value or "").strip()
    match = _HEX_RE.match(text)
    if not match:
        return fallback
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return "#" + digits.upper()


def normalize_customization(data: Optional[dict]) -> Dict[str, Any]:
    source = dict(DEFAULT_CUSTOMIZATION)
    source.update(data or {})
    preset_name = str(source.get("preset") or "hyperos")
    if preset_name not in PRESETS:
        preset_name = "hyperos"
    merged = dict(PRESETS[preset_name])
    merged.update(data or {})
    merged["preset"] = preset_name
    merged["theme"] = "dark" if str(merged.get("theme")) == "dark" else "light"
    merged["accent_color"] = normalize_hex(merged.get("accent_color"))
    merged["background"] = (normalize_hex(merged.get("background"), "")
                            if str(merged.get("background") or "").strip() else "")
    merged["density"] = "compact" if str(merged.get("density")) == "compact" else "comfortable"
    merged["sidebar_position"] = ("right" if str(merged.get("sidebar_position")) == "right"
                                  else "left")
    merged["animations"] = bool(merged.get("animations", True))
    merged["frosted_glass"] = bool(merged.get("frosted_glass", True))
    merged["wallpaper_path"] = str(merged.get("wallpaper_path") or "").strip()
    try:
        radius = int(merged.get("corner_radius", 22))
    except (TypeError, ValueError):
        radius = 22
    merged["corner_radius"] = min(32, max(8, radius))
    try:
        scale = int(merged.get("font_scale", 100))
    except (TypeError, ValueError):
        scale = 100
    merged["font_scale"] = min(125, max(85, scale))
    merged.pop("label", None)
    return merged


def from_config(cfg: Optional[dict]) -> Dict[str, Any]:
    """Merge stored customisation with the legacy theme/accent settings."""
    config = cfg or {}
    custom = normalize_customization(config.get("customization"))
    custom["theme"] = "dark" if config.get("theme") == "dark" else custom["theme"]
    if config.get("accent_color"):
        custom["accent_color"] = normalize_hex(config.get("accent_color"),
                                               custom["accent_color"])
    return custom


def apply_preset(cfg: dict, name: str) -> Dict[str, Any]:
    if name not in PRESETS:
        raise ValueError(f"Unknown theme preset: {name}")
    custom = normalize_customization({"preset": name})
    cfg["customization"] = custom
    cfg["theme"] = custom["theme"]
    cfg["accent_color"] = custom["accent_color"]
    return custom


def save_customization(cfg: dict, data: dict) -> Dict[str, Any]:
    custom = normalize_customization(data)
    cfg["customization"] = custom
    cfg["theme"] = custom["theme"]
    cfg["accent_color"] = custom["accent_color"]
    return custom


def reset_customization(cfg: dict) -> Dict[str, Any]:
    return apply_preset(cfg, "hyperos")


def list_presets() -> list:
    return [{"id": key, **value} for key, value in PRESETS.items()]


def export_theme(custom: dict) -> str:
    payload = {"schema": 1, "app": "Andromic", "customization": normalize_customization(custom)}
    return json.dumps(payload, indent=2, ensure_ascii=False)


def import_theme(text: str) -> Dict[str, Any]:
    try:
        payload = json.loads(str(text))
    except (TypeError, ValueError) as exc:
        raise ValueError("The theme file is not valid JSON") from exc
    data = payload.get("customization") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("The theme file does not contain a customization object")
    return normalize_customization(data)


def relative_luminance(color: str) -> float:
    value = normalize_hex(color).lstrip("#")
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return round((light + 0.05) / (dark + 0.05), 2)


def readable_text(color: str) -> str:
    """Return black or white text with the better contrast for a background."""
    return "#000000" if contrast_ratio(color, "#000000") >= contrast_ratio(color, "#FFFFFF") else "#FFFFFF"


def css_values(custom: dict) -> Dict[str, str]:
    clean = normalize_customization(custom)
    values = {
        "accent": clean["accent_color"],
        "radius": f"{clean['corner_radius']}px",
        "font_scale": f"{clean['font_scale']}%",
        "density": clean["density"],
        "animations": "1" if clean["animations"] else "0",
        "on_accent": readable_text(clean["accent_color"]),
    }
    if clean.get("background"):
        values["background"] = clean["background"]
    return values

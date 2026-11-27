"""Colour palettes, font selection and the application stylesheet.

Stage 3: modern sans-serif typography (Inter preferred, then high-quality
system sans), antialiasing, DPI scaling, no unnecessary text shadows/outlines,
and a Liquid Glass layer with per-layer opacity independent of any background
image.  Glass still works when no background image is enabled.
"""
from types import SimpleNamespace

from PySide6.QtGui import QColor, QFont, QFontDatabase

from . import icons

PALETTES = {
    "light": dict(
        bg="#F2F4F7", card="#FFFFFF", field="#F0F2F5", field_hover="#E6E9EE",
        text="#17181C", muted="#5C6270", accent="#3482FF", accent_hover="#2A6FE0",
        accent_soft="#DDEAFF", on_accent="#FFFFFF", seg_bg="#E6E9EE", seg_active="#FFFFFF",
        track="#DFE3E9", border="#DDE0E6", danger="#F5483B",
    ),
    "dark": dict(
        # Deep navy base with cool blue surfaces and readable muted text.
        bg="#0A1220", card="#111D30", field="#17263D", field_hover="#203550",
        text="#EDF4FF", muted="#A4B4CA", accent="#6AA8FF", accent_hover="#8AB9FF",
        accent_soft="#1C3556", on_accent="#071426", seg_bg="#17263D", seg_active="#263D5D",
        track="#263B59", border="#2A4162", danger="#FF737A",
    ),
}

colors = SimpleNamespace(**PALETTES["light"])
current = "light"
_family = "Inter"
_mono = "Consolas"
# Modern sans-serif preference order. Inter first; then quality system sans.
# MiSans is a MIUIX system font, used only when already installed.
_PREFERRED = ("Inter", "Inter Variable", "MiSans", "HarmonyOS Sans",
              "Segoe UI Variable Text", "Segoe UI Variable", "SF Pro Text", "SF Pro Display",
              "Helvetica Neue", "Roboto", "Noto Sans", "Noto Sans CJK", "Ubuntu",
              "Cantarell", "DejaVu Sans", "Segoe UI", "Arial", "sans-serif")
_MONO = ("Cascadia Mono", "JetBrains Mono", "Consolas", "SF Mono", "Menlo",
         "DejaVu Sans Mono", "Courier New", "monospace")

# Appearance options controlled by the Customization page.
animations = True
density = "comfortable"
corner_radius = 22
font_scale = 100
background = ""
frosted_glass = True
# Liquid Glass per-layer opacity (0..1) + backdrop blur radius (px).
glass_window_opacity = 0.82
glass_panel_opacity = 0.58
glass_border_opacity = 0.55
glass_blur_radius = 18
background_image = ""
use_background_image = False
_font_family_override = ""


def set_theme(name: str, accent: str = "", custom: dict = None) -> None:
    global current, animations, density, corner_radius, font_scale, background, frosted_glass
    global glass_window_opacity, glass_panel_opacity, glass_border_opacity, glass_blur_radius
    global background_image, use_background_image, _font_family_override, _family
    custom = custom or {}
    current = name if name in PALETTES else "light"
    if custom.get("theme") in PALETTES:
        current = custom["theme"]
    palette = dict(PALETTES[current])
    accent_value = custom.get("accent_color") or accent
    candidate = QColor(str(accent_value)) if accent_value else QColor()
    if candidate.isValid():
        palette["accent"] = candidate.name(QColor.NameFormat.HexRgb)
        palette["accent_hover"] = candidate.darker(112).name(QColor.NameFormat.HexRgb)
        if current == "dark":
            soft = candidate.darker(260)
        else:
            soft = candidate.lighter(175)
        palette["accent_soft"] = soft.name(QColor.NameFormat.HexRgb)
    try:
        animations = bool(custom.get("animations", True))
    except (TypeError, ValueError):
        animations = True
    density = "compact" if custom.get("density") == "compact" else "comfortable"
    try:
        corner_radius = min(32, max(8, int(custom.get("corner_radius", 22))))
    except (TypeError, ValueError):
        corner_radius = 22
    try:
        font_scale = min(125, max(85, int(custom.get("font_scale", 100))))
    except (TypeError, ValueError):
        font_scale = 100
    background = ""
    frosted_glass = bool(custom.get("frosted_glass", True))
    bg_candidate = QColor(str(custom.get("background") or "")) if custom.get("background") else QColor()
    if bg_candidate.isValid():
        background = bg_candidate.name(QColor.NameFormat.HexRgb)
        palette["bg"] = background

    def _pct(key, default):
        try:
            return min(1.0, max(0.0, int(custom.get(key, default)) / 100.0))
        except (TypeError, ValueError):
            return default / 100.0

    glass_window_opacity = _pct("glass_window_opacity", 82)
    glass_panel_opacity = _pct("glass_panel_opacity", 58)
    glass_border_opacity = _pct("glass_border_opacity", 55)
    try:
        glass_blur_radius = min(48, max(0, int(custom.get("glass_blur_radius", 18))))
    except (TypeError, ValueError):
        glass_blur_radius = 18
    background_image = str(custom.get("background_image") or "").strip()
    use_background_image = bool(custom.get("use_background_image", False))
    _font_family_override = str(custom.get("font_family") or "").strip()
    for key, value in palette.items():
        setattr(colors, key, value)


def init_fonts() -> QFont:
    global _family, _mono
    available = set(QFontDatabase.families())
    _family = next((f for f in _PREFERRED if f in available), _family)
    if _font_family_override and _font_family_override in available:
        _family = _font_family_override
    _mono = next((f for f in _MONO if f in available), _mono)
    return font(10)


def set_font_family(name: str) -> None:
    global _family
    if name and name in set(QFontDatabase.families()):
        _family = name
    init_fonts()


def _quality(font: QFont) -> QFont:
    # Crisp antialiased text; never render text from upscaled low-res bitmaps.
    try:
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
    except Exception:
        try:
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        except Exception:
            pass
    try:
        font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    except Exception:
        pass
    return font


def font(size: float = 10, bold: bool = False) -> QFont:
    family = _font_family_override or _family
    f = QFont(family)
    # Point size scales with OS DPI; font_scale is an independent user factor.
    f.setPointSizeF(float(size) * (font_scale / 100.0))
    f.setBold(bold)
    # Sensible weights: bold -> semibold for modern look.
    try:
        f.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
    except Exception:
        pass
    return _quality(f)


def mono(size: float = 10) -> QFont:
    f = QFont(_mono)
    f.setPointSizeF(float(size) * (font_scale / 100.0))
    return _quality(f)


def _rgba(color: QColor, alpha: float) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{max(0, min(255, round(alpha * 255)))})"


def stylesheet() -> str:
    c = colors
    chevron = icons.chevron_file(c.muted)
    radius = corner_radius
    field_radius = max(8, radius - 6)
    compact = density == "compact"
    field_pad = "5px 12px" if compact else "8px 16px"
    field_height = "18px" if compact else "22px"
    item_pad = "6px 10px" if compact else "10px 12px"

    glass = frosted_glass
    if glass:
        window_bg = _rgba(QColor(c.bg), glass_window_opacity)
        # Card painting is done in Card.paintEvent (real backdrop blur);
        # stylesheet keeps it transparent.
        field_bg = _rgba(QColor(c.field), min(1.0, glass_panel_opacity + 0.18))
        field_focus_border = c.accent
    else:
        window_bg = c.bg
        field_bg = c.field
        field_focus_border = c.accent

    return f"""
QMainWindow {{ background: transparent; }}
#root {{ background: {window_bg}; }}
QDialog {{ background: {c.bg}; }}
QLabel {{ background: transparent; color: {c.text}; }}
QLabel[muted="true"] {{ color: {c.muted}; }}
QToolTip {{ background: {c.card}; color: {c.text}; border: 1px solid {c.border};
            padding: 6px 10px; border-radius: 8px; }}
QFrame#card {{ background: transparent; border: none; border-radius: {radius}px; }}

QLineEdit {{ background: {field_bg}; color: {c.text}; border: 1px solid transparent;
             border-radius: {field_radius}px; padding: {field_pad}; min-height: {field_height};
             selection-background-color: {c.accent}; selection-color: #FFFFFF; }}
QLineEdit:focus {{ border: 1px solid {field_focus_border}; }}

QComboBox {{ background: {field_bg}; color: {c.text}; border: 1px solid transparent;
             border-radius: {field_radius}px; padding: {field_pad}; min-height: {field_height}; }}
QComboBox:hover {{ background: {c.field_hover}; }}
QComboBox:on {{ border: 1px solid {c.accent}; }}
QComboBox::drop-down {{ border: none; width: 34px; subcontrol-origin: padding;
                        subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {c.card}; color: {c.text};
    border: 1px solid {c.border}; border-radius: {field_radius}px; padding: 6px; outline: 0; }}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 2px 10px; border-radius: 10px; }}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover
    {{ background: {c.accent_soft}; color: {c.accent}; }}

QListWidget {{ background: transparent; border: none; outline: 0; color: {c.text}; }}
QListWidget::item {{ padding: {item_pad}; border-radius: {max(6, radius - 10)}px; }}
QListWidget::item:hover:!selected {{ background: {c.field}; }}
QListWidget::item:selected {{ background: {c.accent_soft}; color: {c.accent}; }}

QTabWidget::pane {{ border: none; background: transparent; }}
QTabBar::tab {{ background: transparent; color: {c.muted}; padding: 8px 16px; border: none;
                border-radius: 10px; margin-right: 4px; }}
QTabBar::tab:selected {{ background: {c.accent_soft}; color: {c.accent}; }}

QPlainTextEdit {{ background: {c.card}; color: {c.text}; border: none;
                  border-radius: {radius}px; padding: 14px; }}

QProgressBar {{ background: {c.track}; border: none; border-radius: 4px;
                min-height: 8px; max-height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {c.accent}; border-radius: 4px; }}

QSlider::groove:horizontal {{ height: 6px; background: {c.track}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c.accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: #FFFFFF; border: 2px solid {c.accent};
                              width: 14px; height: 14px; margin: -7px 0; border-radius: 9px; }}

QScrollArea, QAbstractScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget {{ background: transparent; }}
#scrollInner, #navHolder {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {c.track}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c.muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {c.track}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMessageBox {{ background: {c.bg}; }}
QMessageBox QLabel {{ color: {c.text}; }}
QMessageBox QPushButton {{ background: {c.field}; color: {c.text}; border: none;
    border-radius: 16px; padding: 8px 22px; min-width: 70px; }}
QMessageBox QPushButton:hover {{ background: {c.field_hover}; }}
"""

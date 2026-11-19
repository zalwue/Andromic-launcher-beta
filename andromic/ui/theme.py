"""Colour palettes, font selection and the application stylesheet."""
from types import SimpleNamespace

from PySide6.QtGui import QColor, QFont, QFontDatabase

from . import icons

PALETTES = {
    "light": dict(
        bg="#F2F4F7", card="#FFFFFF", field="#F0F2F5", field_hover="#E6E9EE",
        text="#17181C", muted="#8B909B", accent="#3482FF", accent_hover="#2A6FE0",
        accent_soft="#DDEAFF", on_accent="#FFFFFF", seg_bg="#E6E9EE", seg_active="#FFFFFF",
        track="#DFE3E9", border="#DDE0E6", danger="#F5483B",
    ),
    "dark": dict(
        bg="#0C0D10", card="#18191E", field="#23252B", field_hover="#2C2F36",
        text="#F1F2F5", muted="#8C919C", accent="#3482FF", accent_hover="#4A92FF",
        accent_soft="#1D2C4A", on_accent="#FFFFFF", seg_bg="#23252B", seg_active="#3A3D46",
        track="#2C2F36", border="#2A2C33", danger="#FF5A4D",
    ),
}

colors = SimpleNamespace(**PALETTES["light"])
current = "light"
_family = "Segoe UI"
_mono = "Consolas"
_PREFERRED = ("MiSans", "HarmonyOS Sans", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text",
              "Helvetica Neue", "Inter", "Roboto", "Noto Sans", "DejaVu Sans")
_MONO = ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")


def set_theme(name: str, accent: str = "") -> None:
    global current
    current = name if name in PALETTES else "light"
    palette = dict(PALETTES[current])
    candidate = QColor(str(accent)) if accent else QColor()
    if candidate.isValid():
        palette["accent"] = candidate.name(QColor.NameFormat.HexRgb)
        palette["accent_hover"] = candidate.darker(112).name(QColor.NameFormat.HexRgb)
        if current == "dark":
            soft = candidate.darker(260)
        else:
            soft = candidate.lighter(175)
        palette["accent_soft"] = soft.name(QColor.NameFormat.HexRgb)
    for key, value in palette.items():
        setattr(colors, key, value)


def init_fonts() -> QFont:
    global _family, _mono
    available = set(QFontDatabase.families())
    _family = next((f for f in _PREFERRED if f in available), _family)
    _mono = next((f for f in _MONO if f in available), _mono)
    return font(10)


def font(size: float = 10, bold: bool = False) -> QFont:
    f = QFont(_family)
    f.setPointSizeF(float(size))
    f.setBold(bold)
    return f


def mono(size: float = 10) -> QFont:
    f = QFont(_mono)
    f.setPointSizeF(float(size))
    return f


def stylesheet() -> str:
    c = colors
    chevron = icons.chevron_file(c.muted)
    return f"""
QMainWindow, QDialog, #root {{ background: {c.bg}; }}
QLabel {{ background: transparent; color: {c.text}; }}
QLabel[muted="true"] {{ color: {c.muted}; }}
QToolTip {{ background: {c.card}; color: {c.text}; border: 1px solid {c.border};
            padding: 6px 10px; border-radius: 8px; }}
QFrame#card {{ background: {c.card}; border-radius: 22px; }}

QLineEdit {{ background: {c.field}; color: {c.text}; border: 2px solid transparent;
             border-radius: 16px; padding: 8px 16px; min-height: 22px;
             selection-background-color: {c.accent}; selection-color: #FFFFFF; }}
QLineEdit:focus {{ border: 2px solid {c.accent}; }}

QComboBox {{ background: {c.field}; color: {c.text}; border: 2px solid transparent;
             border-radius: 16px; padding: 8px 16px; min-height: 22px; }}
QComboBox:hover {{ background: {c.field_hover}; }}
QComboBox:on {{ border: 2px solid {c.accent}; }}
QComboBox::drop-down {{ border: none; width: 34px; subcontrol-origin: padding;
                        subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {c.card}; color: {c.text};
    border: 1px solid {c.border}; border-radius: 14px; padding: 6px; outline: 0; }}
QComboBox QAbstractItemView::item {{ min-height: 30px; padding: 2px 10px; border-radius: 10px; }}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover
    {{ background: {c.accent_soft}; color: {c.accent}; }}

QListWidget {{ background: transparent; border: none; outline: 0; color: {c.text}; }}
QListWidget::item {{ padding: 10px 12px; border-radius: 12px; }}
QListWidget::item:hover:!selected {{ background: {c.field}; }}
QListWidget::item:selected {{ background: {c.accent_soft}; color: {c.accent}; }}

QPlainTextEdit {{ background: {c.card}; color: {c.text}; border: none;
                  border-radius: 22px; padding: 14px; }}

QProgressBar {{ background: {c.track}; border: none; border-radius: 4px;
                min-height: 8px; max-height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {c.accent}; border-radius: 4px; }}

QSlider::groove:horizontal {{ height: 6px; background: {c.track}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c.accent}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: #FFFFFF; border: 2px solid {c.accent};
                              width: 14px; height: 14px; margin: -7px 0; border-radius: 9px; }}

QScrollArea, QAbstractScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget {{ background: transparent; }}
#scrollInner {{ background: transparent; }}
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

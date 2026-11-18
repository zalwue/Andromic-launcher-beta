"""Rounded head avatars rendered from skin files."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap

_DEFAULT_ROWS = (
    "HHHHHHHH", "HHHHHHHH", "HSSSSSSH", "SSSSSSSS",
    "SWESSEWS", "SSSNNSSS", "SSMMMMSS", "SSSSSSSS",
)
_DEFAULT_COLORS = {"H": "#3B2A1B", "S": "#C08A66", "W": "#FFFFFF",
                   "E": "#3E4FA8", "N": "#A06B4C", "M": "#7A4A38"}


def _face(skin: Path) -> QImage:
    face = QImage(8, 8, QImage.Format.Format_ARGB32)
    face.fill(Qt.GlobalColor.transparent)
    image = QImage(str(skin)) if skin.exists() else QImage()
    if image.isNull() or image.width() < 48:
        for y, row in enumerate(_DEFAULT_ROWS):
            for x, key in enumerate(row):
                face.setPixelColor(x, y, QColor(_DEFAULT_COLORS[key]))
        return face
    painter = QPainter(face)
    painter.drawImage(0, 0, image.copy(8, 8, 8, 8))
    painter.drawImage(0, 0, image.copy(40, 8, 8, 8))
    painter.end()
    return face


def head_pixmap(skin: Path, size: int) -> QPixmap:
    scaled = _face(skin).scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.FastTransformation)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, size * 0.24, size * 0.24)
    painter.setClipPath(clip)
    painter.drawImage(0, 0, scaled)
    painter.end()
    return result

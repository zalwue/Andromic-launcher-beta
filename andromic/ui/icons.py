"""Vector icons drawn with QPainter."""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from ..core.paths import ROOT


def draw(painter: QPainter, name: str, rect: QRectF, color: QColor) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.x(), rect.y())
    painter.scale(rect.width() / 24, rect.height() / 24)
    pen = QPen(color, 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if name == "play":
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([QPointF(8, 5.5), QPointF(19, 12), QPointF(8, 18.5)]))
    elif name == "content":
        for x, y in ((4, 4), (13, 4), (4, 13), (13, 13)):
            painter.drawRoundedRect(QRectF(x, y, 7, 7), 2, 2)
    elif name == "servers":
        painter.drawRoundedRect(QRectF(4, 4, 16, 6), 2.5, 2.5)
        painter.drawRoundedRect(QRectF(4, 14, 16, 6), 2.5, 2.5)
        painter.drawPoint(QPointF(8, 7))
        painter.drawPoint(QPointF(8, 17))
    elif name == "profiles":
        painter.drawEllipse(QPointF(12, 8), 4, 4)
        path = QPainterPath()
        path.moveTo(4.5, 20)
        path.cubicTo(4.5, 13.5, 19.5, 13.5, 19.5, 20)
        painter.drawPath(path)
    elif name == "settings":
        for y, x in ((7, 15), (12, 8), (17, 14)):
            painter.drawLine(QPointF(4, y), QPointF(20, y))
            painter.setBrush(color)
            painter.drawEllipse(QPointF(x, y), 2.4, 2.4)
            painter.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "console":
        painter.drawPolyline(QPolygonF([QPointF(5, 8), QPointF(10, 12), QPointF(5, 16)]))
        painter.drawLine(QPointF(12, 17), QPointF(19, 17))
    elif name == "worlds":
        painter.drawEllipse(QPointF(12, 12), 8, 8)
        painter.drawEllipse(QPointF(12, 12), 3.5, 8)
        painter.drawLine(QPointF(4, 12), QPointF(20, 12))
        painter.drawLine(QPointF(6, 7), QPointF(18, 7))
        painter.drawLine(QPointF(6, 17), QPointF(18, 17))
    elif name == "rooms":
        painter.drawRoundedRect(QRectF(3, 6, 12, 9), 3, 3)
        painter.drawPolyline(QPolygonF([QPointF(7, 15), QPointF(6, 19), QPointF(11, 15)]))
        painter.drawRoundedRect(QRectF(13, 11, 8, 7), 3, 3)
        painter.drawPolyline(QPolygonF([QPointF(18, 18), QPointF(19, 21), QPointF(15, 18)]))
    elif name == "customization":
        painter.drawEllipse(QPointF(12, 12), 8, 8)
        painter.setBrush(color)
        for x, y in ((8, 8), (16, 8), (8, 16), (16, 16)):
            painter.drawEllipse(QPointF(x, y), 1.6, 1.6)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(12, 12), 2.2, 2.2)
    elif name == "diagnostics":
        painter.drawPolyline(QPolygonF([QPointF(3, 12), QPointF(7, 12), QPointF(9, 7),
                                        QPointF(12, 18), QPointF(15, 10), QPointF(17, 12),
                                        QPointF(21, 12)]))
    painter.restore()


def chevron_file(color: str) -> str:
    """Write a small down-chevron PNG (used by combo boxes) and return its path."""
    cache = ROOT / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"chevron_{color.lstrip('#')}.png"
    if not path.exists():
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(QPolygonF([QPointF(10, 18), QPointF(24, 32), QPointF(38, 18)]))
        painter.end()
        pixmap.save(str(path), "PNG")
    return Path(path).as_posix()

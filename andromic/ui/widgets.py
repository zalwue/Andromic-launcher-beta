"""Reusable styled widgets: cards, buttons, switches, sliders and inputs."""
from typing import Callable, Iterable, Optional

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QPainterPath
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QGraphicsDropShadowEffect,
                               QHBoxLayout, QLabel, QLineEdit, QListView, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from . import icons, theme


def mix(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t),
                  round(a.alpha() + (b.alpha() - a.alpha()) * t))


def _animation(owner, callback, duration=150) -> QVariantAnimation:
    anim = QVariantAnimation(owner)
    anim.setDuration(duration if theme.animations else 0)
    anim.setEasingCurve(QEasingCurve(QEasingCurve.Type.OutCubic))
    anim.valueChanged.connect(callback)
    return anim


def label(text="", size=10, bold=False, muted=False, wrap=False) -> QLabel:
    widget = QLabel(text)
    widget.setFont(theme.font(size, bold))
    widget.setProperty("muted", muted)
    widget.setWordWrap(wrap)
    return widget


def page_title(text: str) -> QLabel:
    return label(text, 20, bold=True)


def hbox(spacing=8):
    widget = QWidget()
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    return widget, layout


class Card(QFrame):
    """Rounded opaque surface; add children to `.lay`. Liquid Glass removed."""

    def __init__(self, margins=(20, 18, 20, 18), spacing=10, shadow=True):
        super().__init__()
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(*margins)
        self.lay.setSpacing(spacing)
        self.lay.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        if shadow and theme.current == "light":
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(18)
            effect.setOffset(0, 2)
            effect.setColor(QColor(30, 45, 90, 22))
            self.setGraphicsEffect(effect)


class Button(QPushButton):
    def __init__(self, text="", kind="tonal", height=38, icon: Optional[str] = None,
                 anchor="center", size=10, bold=False):
        super().__init__(text)
        self.kind, self.icon_name, self.anchor = kind, icon, anchor
        self.size, self.bold = size, bold
        self._hover = 0.0
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._anim = _animation(self, self._set_hover, 140)
        self.setMinimumWidth(self.sizeHint().width())

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(theme.font(self.size, self.bold))
        width = metrics.horizontalAdvance(self.text()) + 40 + (28 if self.icon_name else 0)
        return QSize(width, self.height())

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.update()

    def set_text(self, text: str) -> None:
        self.setText(text)
        self.update()

    def _set_hover(self, value) -> None:
        self._hover = float(value)
        self.update()

    def _animate(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event) -> None:
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate(0.0)
        super().leaveEvent(event)

    def _scheme(self):
        c = theme.colors
        if not self.isEnabled():
            return QColor(c.field), QColor(c.field), QColor(c.muted), QColor(c.muted)
        table = {
            "primary": (QColor(c.accent), QColor(c.accent_hover), QColor(c.on_accent), QColor(c.on_accent)),
            "tonal": (QColor(c.field), QColor(c.field_hover), QColor(c.text), QColor(c.text)),
            "danger": (QColor(c.field), QColor(c.field_hover), QColor(c.danger), QColor(c.danger)),
            "ghost": (None, QColor(c.field), QColor(c.accent), QColor(c.accent)),
            "nav": (None, QColor(c.field), QColor(c.muted), QColor(c.text)),
            "nav_active": (QColor(c.accent_soft), QColor(c.accent_soft), QColor(c.accent), QColor(c.accent)),
        }
        return table[self.kind]

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        base, hover, fg, fg_hover = self._scheme()
        t = 1.0 if self.isDown() else self._hover
        if base is None:
            fill = QColor(hover)
            fill.setAlpha(round(255 * t))
        else:
            fill = mix(base, hover, t)
        rect = QRectF(self.rect())
        radius = 16 if self.kind.startswith("nav") else rect.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)
        color = mix(fg, fg_hover, t)
        left = 18.0
        if self.icon_name:
            icons.draw(painter, self.icon_name, QRectF(left, rect.height() / 2 - 10, 20, 20), color)
            left += 30
        painter.setPen(color)
        painter.setFont(theme.font(self.size, self.bold or self.kind == "nav_active"))
        if self.anchor == "left" or self.kind.startswith("nav"):
            text_rect = QRectF(left, 0, rect.width() - left, rect.height())
            flags = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        else:
            offset = 14 if self.icon_name else 0
            text_rect = QRectF(offset, 0, rect.width() - offset, rect.height())
            flags = Qt.AlignmentFlag.AlignCenter
        painter.drawText(text_rect, flags, self.text())


class Switch(QAbstractButton):
    def __init__(self, checked=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(48, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pos = 1.0 if checked else 0.0
        self._anim = _animation(self, self._set_pos, 160)
        self.toggled.connect(self._animate)

    def _set_pos(self, value) -> None:
        self._pos = float(value)
        self.update()

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        c = theme.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(mix(QColor(c.track), QColor(c.accent), self._pos))
        painter.drawRoundedRect(QRectF(0, 2, 48, 24), 12, 12)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QPointF(14 + 20 * self._pos, 14), 10, 10)


class ToggleRow(QWidget):
    def __init__(self, title: str, checked=False, hint=""):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(label(title, 10))
        if hint:
            texts.addWidget(label(hint, 9, muted=True))
        row.addLayout(texts, 1)
        self.switch = Switch(checked)
        row.addWidget(self.switch)

    def isChecked(self) -> bool:
        return self.switch.isChecked()

    def setChecked(self, value: bool) -> None:
        self.switch.setChecked(value)

    @property
    def toggled(self):
        return self.switch.toggled


class SliderRow(QWidget):
    changed = Signal(int)

    def __init__(self, low: int, high: int, step: int, value: int, fmt: Callable[[int], str]):
        super().__init__()
        self.step, self.fmt = step, fmt
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(low // step, high // step)
        self.slider.setValue(round(value / step))
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.value_label = label(fmt(self.value()), 10, bold=True)
        self.value_label.setMinimumWidth(96)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.slider, 1)
        row.addWidget(self.value_label)
        self.slider.valueChanged.connect(self._on_change)

    def value(self) -> int:
        return self.slider.value() * self.step

    def _on_change(self, _raw) -> None:
        self.value_label.setText(self.fmt(self.value()))
        self.changed.emit(self.value())


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, items: Iterable, value: Optional[str] = None, height=38):
        super().__init__()
        self.items = list(items)
        self.value = value if value is not None else self.items[0][0]
        metrics = QFontMetrics(theme.font(10, True))
        self.widths = [max(metrics.horizontalAdvance(text) + 36, 52) for _key, text in self.items]
        self.setMinimumWidth(sum(self.widths) + 8)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._from = self._to = self._target()
        self._t = 1.0
        self._anim = _animation(self, self._set_t, 200)

    def _index(self) -> int:
        return [k for k, _t in self.items].index(self.value)

    def _target(self):
        index = self._index()
        return 4 + sum(self.widths[:index]), self.widths[index]

    def set_value(self, value: str) -> None:
        """Select a value without emitting ``changed`` (used when refreshing)."""
        if value not in [key for key, _text in self.items] or value == self.value:
            return
        self._from = self._current()
        self.value = value
        self._to = self._target()
        self._t = 1.0
        self.update()

    def _set_t(self, value) -> None:
        self._t = float(value)
        self.update()

    def mousePressEvent(self, event) -> None:
        x = event.position().x() - 4
        for (key, _text), width in zip(self.items, self.widths):
            if 0 <= x <= width:
                if key != self.value:
                    self._from = self._current()
                    self.value = key
                    self._to = self._target()
                    self._anim.stop()
                    self._anim.setStartValue(0.0)
                    self._anim.setEndValue(1.0)
                    self._anim.start()
                    self.changed.emit(key)
                return
            x -= width

    def _current(self):
        return (self._from[0] + (self._to[0] - self._from[0]) * self._t,
                self._from[1] + (self._to[1] - self._from[1]) * self._t)

    def paintEvent(self, _event) -> None:
        c = theme.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        height = self.height()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c.seg_bg))
        painter.drawRoundedRect(QRectF(self.rect()), height / 2, height / 2)
        x, width = self._current()
        painter.setBrush(QColor(c.seg_active))
        painter.drawRoundedRect(QRectF(x, 4, width, height - 8), (height - 8) / 2, (height - 8) / 2)
        offset = 4.0
        for (key, text), item_width in zip(self.items, self.widths):
            active = key == self.value
            painter.setFont(theme.font(10, True))
            painter.setPen(QColor(c.text if active else c.muted))
            painter.drawText(QRectF(offset, 0, item_width, height), Qt.AlignmentFlag.AlignCenter, text)
            offset += item_width


class Field(QLineEdit):
    def __init__(self, text="", placeholder=""):
        super().__init__(text)
        self.setPlaceholderText(placeholder)
        self.setFont(theme.font(10))


class Select(QComboBox):
    """Combo box with a rounded popup; `picked` fires only on user choice."""

    picked = Signal(str)

    def __init__(self, values=(), value=""):
        super().__init__()
        self.setFont(theme.font(10))
        self.setMaxVisibleItems(9)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        view = QListView()
        self.setView(view)
        popup = view.window()
        popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                             | Qt.WindowType.NoDropShadowWindowHint)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.set_values(values)
        if value:
            self.set_value(value)
        self.textActivated.connect(self.picked)

    def wheelEvent(self, event) -> None:
        event.ignore()

    def set_values(self, values) -> None:
        current = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItems([str(v) for v in values])
        index = self.findText(current)
        if index >= 0:
            self.setCurrentIndex(index)
        self.blockSignals(False)

    def set_value(self, value: str) -> None:
        self.blockSignals(True)
        index = self.findText(value)
        if index < 0 and value:
            self.addItem(value)
            index = self.findText(value)
        self.setCurrentIndex(index)
        self.blockSignals(False)

    def value(self) -> str:
        return self.currentText()

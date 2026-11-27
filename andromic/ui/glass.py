"""Liquid Glass primitives: real translucency, real backdrop blur, fallbacks.

Qt itself has no cross-platform "blur what is behind this widget" for arbitrary
sibling content, so panels capture the window region behind them and paint a
genuinely *blurred* copy underneath a translucent tint — not a flat tinted
rectangle.  Where the *platform* exposes a compositor backdrop (Windows 11
DWM, macOS vibrancy, KDE blur), :func:`apply_system_backdrop` uses it; every
platform-specific call is feature-detected and fully guarded, with a clean
fallback (window translucency + in-app backdrop blur).  Nothing here claims a
fully working system blur on platforms that cannot provide it.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QPainter, QPainterPath,
                           QPixmap)

# ---------------------------------------------------------------------------
# Platform capability detection
# ---------------------------------------------------------------------------

def platform_name() -> str:
    try:
        return QGuiApplication.platformName() or sys.platform
    except Exception:
        return sys.platform


def translucency_supported() -> bool:
    """Window-level translucency availability (best effort, never raises)."""
    try:
        name = platform_name().lower()
        # headless test backends can't show a desktop behind us
        if name in ("offscreen", "minimal", "vnc"):
            return False
        return True
    except Exception:
        return False


def system_backdrop_supported() -> bool:
    """Whether a native compositor backdrop blur can even be attempted."""
    if not translucency_supported():
        return False
    if sys.platform.startswith("win"):
        return True          # Windows 10/11 DWM (we try DWMSBT_*; fallback inside)
    if sys.platform == "darwin":
        return True          # macOS vibrancy attempted; fallback if unavailable
    name = platform_name().lower()
    return name == "xcb"  # KDE X11 blur; Wayland is compositor-dependent (fallback)


# ---------------------------------------------------------------------------
# Real image blur (separable box blur, two passes) — not a flat colour
# ---------------------------------------------------------------------------

def _box_blur_pass(src: QImage, radius: int, horizontal: bool) -> QImage:
    w, h = src.width(), src.height()
    if w <= 0 or h <= 0 or radius <= 0:
        return src
    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    span = 2 * radius + 1
    for y in range(h):
        for x in range(w):
            r = g = b = a = 0
            for k in range(-radius, radius + 1):
                if horizontal:
                    sx = min(w - 1, max(0, x + k))
                    sy = y
                else:
                    sx = x
                    sy = min(h - 1, max(0, y + k))
                px = src.pixel(sx, sy)
                a += (px >> 24) & 0xFF
                r += (px >> 16) & 0xFF
                g += (px >> 8) & 0xFF
                b += px & 0xFF
            color = QColor(r // span, g // span, b // span, a // span)
            out.setPixel(x, y, color.rgba())
    return out


def blur_image(image: QImage, radius: int) -> QImage:
    """Real blur of a QImage.  Falls back to downscale+upscale if needed."""
    if image.isNull() or radius <= 0:
        return image
    src = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    # Pure-Python per-pixel blur is O(n*r); downscale first for big panels.
    if max(src.width(), src.height()) > 400:
        small = src.scaled(max(1, src.width() // 3), max(1, src.height() // 3),
                           Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    else:
        small = src
    eff_radius = max(1, int(radius * (small.width() / max(1, src.width()))))
    blurred = _box_blur_pass(small, eff_radius, True)
    blurred = _box_blur_pass(blurred, eff_radius, False)
    return blurred.scaled(src.width(), src.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)


def blur_pixmap(pixmap: QPixmap, radius: int) -> QPixmap:
    if pixmap.isNull() or radius <= 0:
        return pixmap
    return QPixmap.fromImage(blur_image(pixmap.toImage(), radius))


# ---------------------------------------------------------------------------
# Native compositor backdrop (guarded; returns whether it was applied)
# ---------------------------------------------------------------------------

def apply_system_backdrop(window, enabled: bool) -> bool:
    """Apply native translucency + backdrop blur to ``window`` if supported."""
    if window is None:
        return False
    try:
        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, bool(enabled))
    except Exception:
        pass
    if not enabled:
        return False
    if not system_backdrop_supported():
        return False
    applied = False
    # ---- Windows 11 DWM system backdrop ----
    if sys.platform.startswith("win"):
        try:
            import ctypes

            hwnd = int(window.winId())
            dwmapi = ctypes.windll.dwmapi
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            DWMWA_SYSTEMBACKDROP_TYPE = 38
            DWMSBT_TRANSIENTWINDOW = 3
            value = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                         ctypes.byref(value), ctypes.sizeof(value))
            backdrop = ctypes.c_int(DWMSBT_TRANSIENTWINDOW)
            result = dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE,
                                                  ctypes.byref(backdrop),
                                                  ctypes.sizeof(backdrop))

            class _Margins(ctypes.Structure):
                _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                            ("top", ctypes.c_int), ("bottom", ctypes.c_int)]

            margins = _Margins(-1, -1, -1, -1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
            applied = (result == 0)
        except Exception:
            applied = False
    # ---- macOS vibrancy (only if pyobjc-style bindings happen to exist) ----
    elif sys.platform == "darwin":
        try:
            import objc  # type: ignore

            native = window.windowHandle()
            view = native.nativeInterface() if hasattr(native, "nativeInterface") else None
            # Without guaranteed bindings we don't fake success.
            applied = False
            _ = objc, view
        except Exception:
            applied = False
    # ---- Linux / X11 / Wayland KDE blur hint (best effort) ----
    else:
        name = platform_name().lower()
        if name == "xcb":
            try:
                import ctypes

                x11 = ctypes.cdll.LoadLibrary("libX11.so.6")
                dpy = x11.XOpenDisplay(None)
                if dpy:
                    try:
                        atom = x11.XInternAtom(dpy, b"_KDE_NET_WM_BLUR_BEHIND_REGION", 1)
                        if atom:
                            x11.XChangeProperty(dpy, int(window.winId()), atom, 6, 32, 0,
                                                None, 0)
                            x11.XFlush(dpy)
                            applied = True
                    finally:
                        x11.XCloseDisplay(dpy)
            except Exception:
                applied = False
        # Wayland / other compositors: compositor-dependent; we don't claim
        # success without a verified backend. In-app backdrop blur is the
        # guaranteed fallback.
    return applied


def backdrop_capture(window, target: QRect, exclude: object = None) -> QPixmap:
    """Grab the window region ``target`` (no recursion guarding inside Qt)."""
    try:
        if window is None or target.width() <= 0 or target.height() <= 0:
            return QPixmap()
        return window.grab(target)
    except Exception:
        return QPixmap()

"""Appearance presets, accent colours and theme import/export."""
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QFileDialog, QHBoxLayout, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from ...core import customization
from ...i18n import tr as _
from ..widgets import (Button, Card, Field, Segmented, Select, SliderRow, ToggleRow, label,
                       page_title)


class CustomizationPage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        self.presets = customization.list_presets()
        self.selected_theme = app.cfg.get("theme", "light")
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(page_title(_("Customization")))

        columns = QHBoxLayout()
        columns.setSpacing(12)
        root.addLayout(columns, 1)

        presets = Card(margins=(14, 14, 14, 14), spacing=8)
        presets.lay.addWidget(label(_("Theme preset"), 12, bold=True))
        self.preset_select = Select([item["label"] for item in self.presets])
        self.preset_select.picked.connect(self._preset_picked)
        presets.lay.addWidget(self.preset_select)
        self.preset_hint = label("", 9, muted=True, wrap=True)
        presets.lay.addWidget(self.preset_hint)
        presets.lay.addSpacing(8)
        presets.lay.addWidget(label(_("Accent colour"), 10, muted=True))
        accent_row = QHBoxLayout()
        self.accent = Field("#3482FF")
        self.accent_button = Button(_("Choose accent colour"), "tonal", 36)
        self.accent_button.clicked.connect(lambda _c=False: self._choose_accent())
        accent_row.addWidget(self.accent, 1)
        accent_row.addWidget(self.accent_button)
        presets.lay.addLayout(accent_row)
        presets.lay.addWidget(label(_("Background colour (optional)"), 10, muted=True))
        background_row = QHBoxLayout()
        self.background = Field("")
        self.background_button = Button(_("Choose background colour"), "tonal", 36)
        self.background_button.clicked.connect(lambda _c=False: self._choose_background())
        clear = Button(_("Clear"), height=36)
        clear.clicked.connect(lambda _c=False: self.background.clear())
        background_row.addWidget(self.background, 1)
        background_row.addWidget(self.background_button)
        background_row.addWidget(clear)
        presets.lay.addLayout(background_row)
        presets.lay.addStretch()
        columns.addWidget(presets, 1)

        options = Card(margins=(16, 14, 16, 14), spacing=8)
        options.lay.addWidget(label(_("Appearance"), 12, bold=True))
        options.lay.addWidget(label(_("Sidebar position"), 10, muted=True))
        self.sidebar_position = Segmented([("left", _("Left")), ("right", _("Right"))], "left")
        options.lay.addWidget(self.sidebar_position, 0, Qt.AlignmentFlag.AlignLeft)
        options.lay.addWidget(label(_("Density"), 10, muted=True))
        self.density = Segmented([("comfortable", _("Comfortable")),
                                  ("compact", _("Compact"))], "comfortable")
        options.lay.addWidget(self.density, 0, Qt.AlignmentFlag.AlignLeft)
        self.animations = ToggleRow(_("Animations"), True)
        options.lay.addWidget(self.animations)
        self.glass = ToggleRow(_("Frosted Glass"), True,
                               _("Use translucent surfaces with real backdrop blur"))
        options.lay.addWidget(self.glass)
        # Liquid Glass: per-layer opacity + blur, independent of background image.
        options.lay.addWidget(label(_("Glass panel opacity"), 10, muted=True))
        self.glass_panel_opacity = SliderRow(0, 100, 5, 58, lambda v: f"{v}%")
        options.lay.addWidget(self.glass_panel_opacity)
        options.lay.addWidget(label(_("Glass window opacity"), 10, muted=True))
        self.glass_window_opacity = SliderRow(0, 100, 5, 82, lambda v: f"{v}%")
        options.lay.addWidget(self.glass_window_opacity)
        options.lay.addWidget(label(_("Glass border opacity"), 10, muted=True))
        self.glass_border_opacity = SliderRow(0, 100, 5, 55, lambda v: f"{v}%")
        options.lay.addWidget(self.glass_border_opacity)
        options.lay.addWidget(label(_("Backdrop blur"), 10, muted=True))
        self.glass_blur_radius = SliderRow(0, 48, 2, 18, lambda v: f"{v} px")
        options.lay.addWidget(self.glass_blur_radius)
        # Optional background image (glass works with or without it).
        options.lay.addWidget(label(_("Background image (optional)"), 10, muted=True))
        bg_row = QHBoxLayout()
        self.background_image = QLineEdit("")
        self.background_image.setPlaceholderText(_("Path to image"))
        bg_pick = QPushButton(_("Browse…"))
        bg_pick.clicked.connect(lambda _c=False: self._choose_background_image())
        bg_clear = QPushButton(_("Clear"))
        bg_clear.clicked.connect(lambda _c=False: self.background_image.clear())
        bg_row.addWidget(self.background_image, 1)
        bg_row.addWidget(bg_pick)
        bg_row.addWidget(bg_clear)
        options.lay.addLayout(bg_row)
        self.use_background_image = ToggleRow(_("Use background image"), False)
        options.lay.addWidget(self.use_background_image)
        # Typography: modern sans-serif, optional explicit family.
        options.lay.addWidget(label(_("Font family (empty = automatic)"), 10, muted=True))
        self.font_family = QLineEdit("")
        self.font_family.setPlaceholderText(_("Inter, system sans, …"))
        options.lay.addWidget(self.font_family)
        options.lay.addWidget(label(_("Corner radius"), 10, muted=True))
        self.radius = SliderRow(8, 32, 2, 22, lambda value: f"{value} px")
        options.lay.addWidget(self.radius)
        options.lay.addWidget(label(_("Font scale"), 10, muted=True))
        self.font_scale = SliderRow(85, 125, 5, 100, lambda value: f"{value}%")
        options.lay.addWidget(self.font_scale)
        options.lay.addStretch()
        columns.addWidget(options, 1)

        actions = QHBoxLayout()
        apply_button = Button(_("Apply theme"), "primary", 40)
        reset_button = Button(_("Reset theme"), "tonal", 40)
        export_button = Button(_("Export theme"), "tonal", 40)
        import_button = Button(_("Import theme"), "tonal", 40)
        apply_button.clicked.connect(lambda _c=False: self.apply())
        reset_button.clicked.connect(lambda _c=False: self.reset())
        export_button.clicked.connect(lambda _c=False: self.export())
        import_button.clicked.connect(lambda _c=False: self.import_theme())
        actions.addWidget(apply_button)
        actions.addWidget(reset_button)
        actions.addStretch()
        actions.addWidget(export_button)
        actions.addWidget(import_button)
        root.addLayout(actions)
        self.status = label("", 9, muted=True)
        root.addWidget(self.status)

    def _say(self, text):
        self.status.setText(text)

    def _preset_id(self):
        row = self.preset_select.currentIndex()
        return self.presets[row]["id"] if 0 <= row < len(self.presets) else "hyperos"

    def _preset_picked(self, _label):
        preset = next((item for item in self.presets
                       if item["label"] == _label), self.presets[0])
        self.preset_hint.setText(preset["label"])
        self.selected_theme = preset["theme"]
        self.accent.setText(preset["accent_color"])
        self.background.setText(preset.get("background", ""))
        self.radius.slider.setValue(int(preset["corner_radius"]) // self.radius.step)
        self.font_scale.slider.setValue(int(preset["font_scale"]) // self.font_scale.step)
        self.animations.setChecked(bool(preset["animations"]))
        self.density.set_value(preset.get("density", "comfortable"))

    def refresh(self):
        custom = customization.from_config(self.app.cfg)
        index = next((i for i, item in enumerate(self.presets)
                      if item["id"] == custom.get("preset")), 0)
        self.preset_select.setCurrentIndex(index)
        self.preset_hint.setText(self.presets[index]["label"])
        self.selected_theme = custom["theme"]
        self.accent.setText(custom["accent_color"])
        self.background.setText(custom.get("background", ""))
        self.glass.setChecked(bool(custom.get("frosted_glass", True)))
        self.glass_panel_opacity.slider.setValue(int(custom.get("glass_panel_opacity", 58)) // 5)
        self.glass_window_opacity.slider.setValue(int(custom.get("glass_window_opacity", 82)) // 5)
        self.glass_border_opacity.slider.setValue(int(custom.get("glass_border_opacity", 55)) // 5)
        self.glass_blur_radius.slider.setValue(int(custom.get("glass_blur_radius", 18)) // 2)
        self.background_image.setText(custom.get("background_image", ""))
        self.use_background_image.setChecked(bool(custom.get("use_background_image", False)))
        self.font_family.setText(custom.get("font_family", ""))
        self.radius.slider.setValue(int(custom["corner_radius"]) // self.radius.step)
        self.font_scale.slider.setValue(int(custom["font_scale"]) // self.font_scale.step)
        self.animations.setChecked(bool(custom["animations"]))
        self.density.set_value(custom.get("density", "comfortable"))
        self.sidebar_position.set_value(custom.get("sidebar_position", "left"))

    def _choose_accent(self):
        current = QColor(self.accent.text() or self.app.cfg.get("accent_color", "#3482FF"))
        color = QColorDialog.getColor(current, self.frame, _("Choose accent colour"))
        if color.isValid():
            self.accent.setText(color.name(QColor.NameFormat.HexRgb).upper())

    def _choose_background_image(self):
        path, _filter = QFileDialog.getOpenFileName(
            self.frame, _("Background image"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if path:
            self.background_image.setText(path)

    def _choose_background(self):
        current = QColor(self.background.text() or "#F2F4F7")
        color = QColorDialog.getColor(current, self.frame, _("Choose background colour"))
        if color.isValid():
            self.background.setText(color.name(QColor.NameFormat.HexRgb).upper())

    def _data(self):
        return {
            "preset": self._preset_id(),
            "theme": self.selected_theme,
            "accent_color": self.accent.text().strip(),
            "background": self.background.text().strip(),
            "frosted_glass": self.glass.isChecked(),
            "glass_panel_opacity": self.glass_panel_opacity.value(),
            "glass_window_opacity": self.glass_window_opacity.value(),
            "glass_border_opacity": self.glass_border_opacity.value(),
            "glass_blur_radius": self.glass_blur_radius.value(),
            "background_image": self.background_image.text().strip(),
            "use_background_image": self.use_background_image.isChecked(),
            "font_family": self.font_family.text().strip(),
            "density": "compact" if self.density.value == "compact" else "comfortable",
            "sidebar_position": self.sidebar_position.value,
            "animations": self.animations.isChecked(),
            "corner_radius": self.radius.value(),
            "font_scale": self.font_scale.value(),
        }

    def apply(self):
        try:
            customization.save_customization(self.app.cfg, self._data())
        except ValueError as exc:
            self.app.error(str(exc))
            return
        self.app.save()
        self._say(_("Theme applied"))
        QTimer.singleShot(0, self.app.rebuild)

    def reset(self):
        customization.reset_customization(self.app.cfg)
        self.app.save()
        self._say(_("Theme reset"))
        QTimer.singleShot(0, self.app.rebuild)

    def export(self):
        suggested = str(Path.home() / "andromic-theme.json")
        path, _filter = QFileDialog.getSaveFileName(self.frame, _("Export theme"), suggested,
                                                    "JSON (*.json)")
        if not path:
            return
        Path(path).write_text(customization.export_theme(self._data()), "utf-8")
        self._say(_("Theme exported: {name}").format(name=Path(path).name))

    def import_theme(self):
        path, _filter = QFileDialog.getOpenFileName(self.frame, _("Import theme"), "",
                                                    "JSON (*.json)")
        if not path:
            return
        try:
            data = customization.import_theme(Path(path).read_text("utf-8"))
            customization.save_customization(self.app.cfg, data)
        except (OSError, ValueError) as exc:
            self.app.error(str(exc))
            return
        self.app.save()
        self._say(_("Theme imported"))
        QTimer.singleShot(0, self.app.rebuild)

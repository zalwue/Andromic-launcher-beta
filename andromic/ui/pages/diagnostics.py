"""Diagnostics page: environment checks, report export and safe repairs."""
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from ...core import diagnostics
from ...core.paths import DIAGNOSTICS
from ...core.system import open_path
from ...i18n import tr as _
from ..widgets import Button, label, page_title


class DiagnosticsPage:
    def __init__(self, app):
        self.app = app
        self.report = None
        self.frame = QWidget()
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(page_title(_("Diagnostics")))
        top.addStretch()
        run = Button(_("Run diagnostics"), "primary", 38)
        save = Button(_("Save report"), "tonal", 38)
        copy = Button(_("Copy report"), "tonal", 38)
        fixes = Button(_("Apply safe fixes"), "tonal", 38)
        folder = Button(_("Data folder"), "ghost", 38)
        run.clicked.connect(lambda _c=False: self.run())
        save.clicked.connect(lambda _c=False: self.save())
        copy.clicked.connect(lambda _c=False: self.copy())
        fixes.clicked.connect(lambda _c=False: self.apply_fixes())
        folder.clicked.connect(lambda _c=False: open_path(DIAGNOSTICS))
        for button in (run, save, copy, fixes, folder):
            top.addWidget(button)
        root.addLayout(top)
        self.status = label(_("No diagnostics have been run yet"), 10, muted=True)
        root.addWidget(self.status)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self.text, 1)

    def _say(self, text):
        self.status.setText(text)

    def refresh(self):
        pass

    def run(self):
        self._say(_("Running diagnostics…"))
        instance = self.app.current_instance()

        def done(report):
            self.report = report
            self.text.setPlainText(diagnostics.format_report(report))
            self._say(_("Diagnostics completed") + f" — {report['status'].upper()}")
        self.app.run_async(
            lambda: diagnostics.run_diagnostics(cfg=dict(self.app.cfg), instance=instance),
            done)

    def save(self):
        if self.report is None:
            self.run()
            return
        try:
            path = diagnostics.save_report(self.report)
        except OSError as exc:
            self.app.error(str(exc))
            return
        self._say(_("Report saved: {name}").format(name=path.name))

    def copy(self):
        if self.report is None:
            self.run()
            return
        QApplication.clipboard().setText(diagnostics.format_report(self.report))
        self._say(_("Report copied to clipboard"))

    def apply_fixes(self):
        def done(actions):
            if actions:
                self._say(_("Safe fixes applied: {count}").format(count=len(actions)))
            else:
                self._say(_("No safe fixes were needed"))
            self.run()
        self.app.run_async(diagnostics.apply_safe_fixes, done)

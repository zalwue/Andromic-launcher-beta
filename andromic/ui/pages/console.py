from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from ...i18n import tr as _
from .. import theme
from ..widgets import Button, page_title


class ConsolePage:
    def __init__(self, app):
        self.app = app
        self.frame = QWidget()
        root = QVBoxLayout(self.frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        top = QHBoxLayout()
        top.addWidget(page_title(_("Console")))
        top.addStretch()
        clear = Button(_("Clear"), height=36)
        top.addWidget(clear)
        root.addLayout(top)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(theme.mono(10))
        self.text.setMaximumBlockCount(3000)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        root.addWidget(self.text, 1)
        clear.clicked.connect(self.text.clear)

    def append(self, line: str):
        self.text.appendPlainText(line)

    def refresh(self):
        pass

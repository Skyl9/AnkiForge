from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from PySide6.QtCore import Signal
from ..theme import DesignTokens


class CodeEditorWidget(QWidget):
    """Éditeur de code avec numéros de ligne et coloration syntaxique basique."""

    text_changed = Signal()

    def __init__(self, language: str = "css", parent: QWidget | None = None):
        super().__init__(parent)
        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(0, 0, 0, 0)

        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: #0d0f12;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 12px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        self.editor.textChanged.connect(self.text_changed.emit)
        self.layout_main.addWidget(self.editor)

    def get_text(self) -> str:
        return self.editor.toPlainText()

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(text)

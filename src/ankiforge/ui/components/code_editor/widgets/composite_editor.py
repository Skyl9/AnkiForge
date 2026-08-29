from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.code_editor.models import LintIssue
from ankiforge.ui.components.code_editor.widgets.native_editor import NativeCodeEditor
from ankiforge.ui.components.code_editor.widgets.status_bar import LintStatusBar
from ankiforge.ui.theme import DesignTokens


class CodeEditorWithGutter(QFrame):
    """
    Conteneur d'édition de code haut niveau encapsulant l'éditeur natif,
    la coloration syntaxique, la gouttière synchronisée avec pastilles de couleur,
    le linter temps réel, le formateur de code et la barre d'état.
    """

    textChanged = Signal()

    def __init__(
        self,
        placeholder: str = "",
        mode: str = "html",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("codeEditorWrapper")

        self.setStyleSheet(f"""
            QFrame#codeEditorWrapper {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#codeEditorWrapper:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Éditeur natif avec gouttière et coloration syntaxique
        self.native_editor = NativeCodeEditor(mode=mode, placeholder=placeholder, parent=self)
        self.native_editor.textChanged.connect(self.textChanged.emit)
        layout.addWidget(self.native_editor, 1)

        # Barre de statut de linter avec bouton de formatage
        self.lint_status_bar = LintStatusBar(self.native_editor, parent=self)
        layout.addWidget(self.lint_status_bar)

    @property
    def editor(self) -> NativeCodeEditor:
        """Permet l'accès transparent à l'instance NativeCodeEditor."""
        return self.native_editor

    def toPlainText(self) -> str:
        return self.native_editor.toPlainText()

    def setPlainText(self, text: str) -> None:
        self.native_editor.setPlainText(text)

    def insertPlainText(self, text: str) -> None:
        self.native_editor.insertPlainText(text)

    def clear(self) -> None:
        self.native_editor.clear()

    def set_known_fields(self, fields: list[str]) -> None:
        self.native_editor.set_known_fields(fields)

    def set_custom_classes(self, classes: list[str]) -> None:
        self.native_editor.set_custom_classes(classes)

    def get_lint_issues(self) -> list[LintIssue]:
        return self.native_editor.get_lint_issues()

    def jump_to_line(self, line_num: int) -> None:
        self.native_editor.jump_to_line(line_num)

    def format_code(self) -> None:
        self.native_editor.format_code()

    def refresh_theme(self) -> None:
        """Rafraîchit la coloration syntaxique et les styles lors d'un changement de thème."""
        self.native_editor.refresh_highlighter()

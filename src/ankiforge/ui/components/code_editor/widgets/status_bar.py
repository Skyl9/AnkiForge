from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from ankiforge.ui.components.code_editor.models import LintIssue
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

if TYPE_CHECKING:
    from ankiforge.ui.components.code_editor.widgets.native_editor import NativeCodeEditor


class LintStatusBar(QFrame):
    """Barre inférieure élégante affichant la synthèse du linter avec clic pour navigation et bouton formater."""

    def __init__(self, editor: NativeCodeEditor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("lintStatusBar")
        self.setFixedHeight(28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            QFrame#lintStatusBar {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border-top: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom-left-radius: {DesignTokens.RADIUS_SM}px;
                border-bottom-right-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(6)

        self.icon_lbl = QLabel()
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_lbl)

        self.status_lbl = QLabel("Syntaxe valide")
        self.status_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(self.status_lbl, 1)

        # Bouton Formater le code (Ctrl+Alt+L)
        self.format_btn = QPushButton("Formater")
        self.format_btn.setIcon(load_phosphor_icon("ph.magic-wand", color=DesignTokens.TEXT_SECONDARY))
        self.format_btn.setIconSize(QSize(13, 13))
        self.format_btn.setToolTip("Formater le document (Ctrl+Alt+L / Ctrl+Shift+I)")
        self.format_btn.setFixedHeight(20)
        self.format_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.format_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 500;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 1px 7px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.format_btn.clicked.connect(self.editor.format_code)
        layout.addWidget(self.format_btn)

        self.editor.lint_issues_changed.connect(self.update_status)
        self.update_status([])

    @Slot(list)
    def update_status(self, issues: list[LintIssue]) -> None:
        if not issues:
            self.icon_lbl.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
            self.status_lbl.setText("Syntaxe valide")
            self.status_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: 500;")
            self.setToolTip("Aucune anomalie détectée.")
        else:
            errors = [i for i in issues if i.severity == "error"]
            warnings = [i for i in issues if i.severity == "warning"]

            if errors:
                self.icon_lbl.setPixmap(load_phosphor_icon("ph.x-circle", color=DesignTokens.COLOR_RED).pixmap(14, 14))
                summary = f"{len(errors)} erreur{'s' if len(errors) > 1 else ''} : {errors[0].message}"
                self.status_lbl.setText(summary)
                self.status_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 11px; font-weight: 500;")
            else:
                self.icon_lbl.setPixmap(load_phosphor_icon("ph.warning", color=DesignTokens.COLOR_YELLOW).pixmap(14, 14))
                summary = f"{len(warnings)} avertissement{'s' if len(warnings) > 1 else ''} : {warnings[0].message}"
                self.status_lbl.setText(summary)
                self.status_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; font-weight: 500;")

            tooltip_text = "\n".join(f"• Ligne {iss.line} : {iss.message}" for iss in issues)
            self.setToolTip(f"Cliquez pour aller à la première anomalie :\n{tooltip_text}")

    def mousePressEvent(self, event: Any) -> None:
        issues = self.editor.get_lint_issues()
        if issues:
            self.editor.jump_to_line(issues[0].line)
        super().mousePressEvent(event)

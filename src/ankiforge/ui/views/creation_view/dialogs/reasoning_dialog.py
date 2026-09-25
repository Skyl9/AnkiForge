import logging

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.logger import redact_secrets

logger = logging.getLogger(__name__)


class ReasoningViewerDialog(QDialog):
    """
    Boîte de dialogue permettant d'inspecter les chaînes de pensée détaillées (CoT / reasoning)
    capturées par étape lors de la génération.
    """

    def __init__(self, thoughts: dict[int, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ReasoningViewerDialog")
        self.setWindowTitle("Chaînes de Pensée IA (Reasoning / CoT)")
        self.resize(720, 520)

        self._sanitized_thoughts: dict[int, str] = {step: redact_secrets(text) for step, text in thoughts.items()}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)

        title_lbl = QLabel("🧠 Réflexions et Raisonnements du Modèle")
        title_lbl.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-family: '{DesignTokens.FONT_MAIN}';")

        subtitle_lbl = QLabel("Consultez la chaîne de réflexion (Chain-of-Thought) capturée pour chaque étape LLM.")
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_MAIN}';")

        header_text_layout.addWidget(title_lbl)
        header_text_layout.addWidget(subtitle_lbl)
        header_layout.addLayout(header_text_layout, 1)

        self.btn_copy_all = SecondaryButton("Copier tout")
        self.btn_copy_all.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_all.setToolTip("Copier l'ensemble des réflexions du pipeline dans le presse-papiers")
        self.btn_copy_all.clicked.connect(self._on_copy_all)
        header_layout.addWidget(self.btn_copy_all)

        layout.addLayout(header_layout)

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(
            f"QTabWidget::pane {{ border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}\n"
            f"QTabBar::tab {{ background: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_MUTED}; "
            f"padding: 6px 14px; margin-right: 4px; border-top-left-radius: {DesignTokens.RADIUS_SM}px; "
            f"border-top-right-radius: {DesignTokens.RADIUS_SM}px; }}\n"
            f"QTabBar::tab:selected {{ background: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; }}"
        )

        for step_order, thought_text in sorted(self._sanitized_thoughts.items()):
            tab_content = QPlainTextEdit()
            tab_content.setReadOnly(True)
            tab_content.setPlainText(thought_text)
            tab_content.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; font-family: '{DesignTokens.FONT_CODE}'; border: none; padding: 10px;")
            tab_content.moveCursor(QTextCursor.MoveOperation.Start)
            self.tab_widget.addTab(tab_content, f"Étape {step_order} ({len(thought_text)} car.)")

        layout.addWidget(self.tab_widget, 1)

        btn_box = QHBoxLayout()
        self.btn_copy_current = SecondaryButton("Copier l'étape")
        self.btn_copy_current.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_current.clicked.connect(self._on_copy_current)

        self.btn_close = PrimaryButton("Fermer")
        self.btn_close.clicked.connect(self.accept)

        btn_box.addWidget(self.btn_copy_current)
        btn_box.addStretch()
        btn_box.addWidget(self.btn_close)
        layout.addLayout(btn_box)

    def _on_copy_current(self) -> None:
        curr = self.tab_widget.currentWidget()
        if isinstance(curr, QPlainTextEdit):
            text = curr.toPlainText()
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
                show_toast(self, "Réflexion de l'étape copiée dans le presse-papiers.")

    def _on_copy_all(self) -> None:
        combined = []
        for step_order, text in sorted(self._sanitized_thoughts.items()):
            combined.append(f"=== ÉTAPE {step_order} ===\n{text}")
        full_text = "\n\n".join(combined)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(full_text)
            show_toast(self, "Toutes les réflexions ont été copiées dans le presse-papiers.")

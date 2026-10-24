"""Onglet « Aide & Guides » des Paramètres AnkiForge (HelpTab).

Présente les accès rapides aux documentations visuelles intégrées, notamment
le Guide Visuel du Cycle de Vie Distribué (Anki ↔ AnkiForge), les raccourcis
clavier et l'assistance utilisateur. Conforme à l'ADR 0038.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.dialogs.doc_reader_dialog import DocReaderDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components import SettingsCard
from ankiforge.ui.widgets.settings_modal.dirty import SettingsDirtyMixin
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class HelpTab(SettingsDirtyMixin, QWidget):
    """Onglet dédié à l'aide, aux guides visuels et aux ressources d'assistance."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpTab")
        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── 1. CARTE PRINCIPALE : CYCLE DE VIE DISTRIBUÉ ─────────────────────
        self.card_lifecycle = SettingsCard(self.content_widget)
        card_lifecycle_layout = QVBoxLayout(self.card_lifecycle)
        card_lifecycle_layout.setContentsMargins(16, 14, 16, 14)
        card_lifecycle_layout.setSpacing(12)

        header_lifecycle = QHBoxLayout()
        header_lifecycle.setSpacing(12)

        icon_cycle = QLabel(self.card_lifecycle)
        cycle_pix = load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.ACCENT_PRIMARY)
        if not cycle_pix.isNull():
            icon_cycle.setPixmap(cycle_pix.pixmap(28, 28))
        header_lifecycle.addWidget(icon_cycle)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        lbl_cycle_title = QLabel(self.tr("Cycle de Vie Distribué (Anki ↔ AnkiForge)"), self.card_lifecycle)
        lbl_cycle_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(lbl_cycle_title)

        lbl_cycle_desc = QLabel(
            self.tr(
                "Découvrez comment articuler sereinement vos séances de travail : création et découpage RAG "
                "dans le Studio AnkiForge, validation en staging, export de cartes vers Anki et synchronisation "
                "sans risque de perte de données ni prolifération de cartes zombies."
            ),
            self.card_lifecycle,
        )
        lbl_cycle_desc.setWordWrap(True)
        lbl_cycle_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; line-height: 1.4;")
        title_col.addWidget(lbl_cycle_desc)
        header_lifecycle.addLayout(title_col, 1)
        card_lifecycle_layout.addLayout(header_lifecycle)

        actions_cycle = QHBoxLayout()
        actions_cycle.addStretch()

        self.btn_open_lifecycle = PrimaryButton(self.tr("Ouvrir le Guide Visuel"))
        self.btn_open_lifecycle.setAutoDefault(False)
        self.btn_open_lifecycle.clicked.connect(self._open_lifecycle_guide)
        actions_cycle.addWidget(self.btn_open_lifecycle)
        card_lifecycle_layout.addLayout(actions_cycle)

        layout.addWidget(self.card_lifecycle)

        # ── 2. CARTE : RACCOURCIS CLAVIER & ERGONOMIE ────────────────────────
        self.card_shortcuts = SettingsCard(self.content_widget)
        card_shortcuts_layout = QVBoxLayout(self.card_shortcuts)
        card_shortcuts_layout.setContentsMargins(16, 14, 16, 14)
        card_shortcuts_layout.setSpacing(12)

        header_shortcuts = QHBoxLayout()
        header_shortcuts.setSpacing(12)

        icon_shortcuts = QLabel(self.card_shortcuts)
        key_pix = load_phosphor_icon("ph.key", color=DesignTokens.TEXT_PRIMARY)
        if not key_pix.isNull():
            icon_shortcuts.setPixmap(key_pix.pixmap(26, 26))
        header_shortcuts.addWidget(icon_shortcuts)

        shortcuts_col = QVBoxLayout()
        shortcuts_col.setSpacing(2)

        lbl_shortcuts_title = QLabel(self.tr("Raccourcis Clavier & Navigation"), self.card_shortcuts)
        lbl_shortcuts_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        shortcuts_col.addWidget(lbl_shortcuts_title)

        lbl_shortcuts_desc = QLabel(
            self.tr("AnkiForge intègre plus de 90 raccourcis clavier déclaratifs organisés par portée (Application, Vue, Widget, Dialogue). Personnalisez vos combinaisons ou consultez la référence."),
            self.card_shortcuts,
        )
        lbl_shortcuts_desc.setWordWrap(True)
        lbl_shortcuts_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        shortcuts_col.addWidget(lbl_shortcuts_desc)
        header_shortcuts.addLayout(shortcuts_col, 1)
        card_shortcuts_layout.addLayout(header_shortcuts)

        actions_shortcuts = QHBoxLayout()
        actions_shortcuts.addStretch()

        self.btn_open_shortcuts_tab = SecondaryButton(self.tr("Personnaliser les raccourcis"))
        self.btn_open_shortcuts_tab.setAutoDefault(False)
        self.btn_open_shortcuts_tab.clicked.connect(self._go_to_shortcuts_tab)
        actions_shortcuts.addWidget(self.btn_open_shortcuts_tab)
        card_shortcuts_layout.addLayout(actions_shortcuts)

        layout.addWidget(self.card_shortcuts)

        # ── 3. CARTE : ASSISTANCE & SIGNALEMENT ──────────────────────────────
        self.card_assistance = SettingsCard(self.content_widget)
        card_assistance_layout = QVBoxLayout(self.card_assistance)
        card_assistance_layout.setContentsMargins(16, 14, 16, 14)
        card_assistance_layout.setSpacing(12)

        header_assist = QHBoxLayout()
        header_assist.setSpacing(12)

        icon_assist = QLabel(self.card_assistance)
        chat_pix = load_phosphor_icon("ph.chat-circle-dots", color=DesignTokens.COLOR_GREEN)
        if not chat_pix.isNull():
            icon_assist.setPixmap(chat_pix.pixmap(26, 26))
        header_assist.addWidget(icon_assist)

        assist_col = QVBoxLayout()
        assist_col.setSpacing(2)

        lbl_assist_title = QLabel(self.tr("Assistance & Retours"), self.card_assistance)
        lbl_assist_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        assist_col.addWidget(lbl_assist_title)

        lbl_assist_desc = QLabel(
            self.tr("Une question, une suggestion ou une anomalie constatée ? Utilisez les outils intégrés pour transmettre un retour ou consulter les rapports d'erreurs."),
            self.card_assistance,
        )
        lbl_assist_desc.setWordWrap(True)
        lbl_assist_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        assist_col.addWidget(lbl_assist_desc)
        header_assist.addLayout(assist_col, 1)
        card_assistance_layout.addLayout(header_assist)

        actions_assist = QHBoxLayout()
        actions_assist.addStretch()

        self.btn_open_feedback = SecondaryButton(self.tr("Signaler une idée ou un bug"))
        self.btn_open_feedback.setAutoDefault(False)
        self.btn_open_feedback.clicked.connect(self._open_feedback_dialog)
        actions_assist.addWidget(self.btn_open_feedback)
        card_assistance_layout.addLayout(actions_assist)

        layout.addWidget(self.card_assistance)

        layout.addStretch()
        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _open_lifecycle_guide(self) -> None:
        """Ouvre le dialogue du guide visuel du cycle de vie distribué."""
        dlg = DocReaderDialog.open_guide("cycle_de_vie_distribue.md", parent=self.window())
        dlg.show()

    def _go_to_shortcuts_tab(self) -> None:
        """Bascule sur l'onglet Clavier de la modale des Paramètres."""
        parent_modal = self.parentWidget()
        while parent_modal is not None and not hasattr(parent_modal, "select_tab"):
            parent_modal = parent_modal.parentWidget()
        if parent_modal is not None and hasattr(parent_modal, "select_tab"):
            parent_modal.select_tab(7)

    def _open_feedback_dialog(self) -> None:
        """Ouvre la boîte de dialogue de feedback."""
        from ankiforge.ui.dialogs.feedback_dialog import FeedbackDialog

        dlg = FeedbackDialog(parent=self.window())
        dlg.exec()

    def has_pending_changes(self) -> bool:
        """L'onglet d'aide est informatif et n'a pas de paramètres persistés."""
        return False

"""Dialogue modal interactif de capture d'une séquence de touches.

Permet de remapper une action en capturant en temps réel l'appui réel au clavier
(y compris modificateurs et touches mortes), avec contrôle immédiat de la liste noire
et des conflits intra-portée.
Conforme à l'ADR 0013 et à l'ADR 0032 (notamment §9).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.shortcuts.catalog import (
    get_shortcut_definition,
    validate_shortcut_override,
)
from ankiforge.ui.shortcuts.models import ShortcutId
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def key_event_to_sequence_str(event: QKeyEvent) -> str:
    """Traduit un QKeyEvent en chaîne textuelle standardisée de raccourci AnkiForge.

    Gère les modificateurs (Ctrl, Alt, Shift, Meta), les touches mortes (^, `, ~, etc.)
    et les touches de contrôle spéciales.
    """
    key = event.key()
    if key in (
        Qt.Key.Key_Control,
        Qt.Key.Key_Shift,
        Qt.Key.Key_Alt,
        Qt.Key.Key_Meta,
        Qt.Key.Key_AltGr,
    ):
        return ""

    modifiers = event.modifiers()
    parts: list[str] = []
    if modifiers & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if modifiers & Qt.KeyboardModifier.AltModifier:
        parts.append("Alt")
    if modifiers & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    if modifiers & Qt.KeyboardModifier.MetaModifier:
        parts.append("Meta")

    # Prise en charge explicite des touches mortes
    if Qt.Key.Key_Dead_Grave.value <= key <= Qt.Key.Key_Dead_Semivoiced_Sound.value:
        dead_map: dict[int, str] = {
            Qt.Key.Key_Dead_Circumflex.value: "^",
            Qt.Key.Key_Dead_Grave.value: "`",
            Qt.Key.Key_Dead_Tilde.value: "~",
            Qt.Key.Key_Dead_Acute.value: "´",
            Qt.Key.Key_Dead_Diaeresis.value: "¨",
        }
        key_str = dead_map.get(int(key), event.text() or "^")
    else:
        key_str = QKeySequence(key).toString(QKeySequence.SequenceFormat.PortableText)

    if not key_str and event.text():
        key_str = event.text()

    if key_str:
        parts.append(key_str)
        return "+".join(parts)
    return ""


class ShortcutCaptureDialog(QDialog):
    """Dialogue de capture d'un raccourci clavier par frappe directe."""

    def __init__(
        self,
        shortcut_id: ShortcutId,
        current_sequence: str,
        current_overrides: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.shortcut_id = shortcut_id
        self._current_sequence = current_sequence
        self._current_overrides = current_overrides
        self.captured_sequence: str = current_sequence

        self.definition = get_shortcut_definition(shortcut_id)

        self.setWindowTitle(self.tr("Modifier le raccourci"))
        self.setFixedWidth(460)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._setup_ui()
        self._validate_and_display(current_sequence)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. En-tête avec titre et icône
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel(self)
        icon_pixmap = load_phosphor_icon("ph.key", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24)
        icon_lbl.setPixmap(icon_pixmap)
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel(self.definition.title, self)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;")
        title_vbox.addWidget(title_lbl)

        cat_lbl = QLabel(
            tr("Catégorie : %1 • Portée : %2", self.definition.category.value, self.definition.scope.name),
            self,
        )
        cat_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        title_vbox.addWidget(cat_lbl)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 2. Zone d'instructions
        self.lbl_instruction = QLabel(
            self.tr("Appuyez sur la combinaison de touches souhaitée au clavier..."),
            self,
        )
        self.lbl_instruction.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(self.lbl_instruction)

        # 3. Zone d'affichage central de la séquence
        self.preview_card = QWidget(self)
        self.preview_card.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: 2px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 16px;
            }}
        """)
        card_layout = QVBoxLayout(self.preview_card)
        card_layout.setContentsMargins(8, 12, 8, 12)
        card_layout.setSpacing(6)

        self.lbl_sequence_display = QLabel(self._current_sequence or self.tr("Aucune touche"), self.preview_card)
        self.lbl_sequence_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sequence_display.setStyleSheet(f"""
            color: {DesignTokens.TEXT_PRIMARY};
            font-family: '{DesignTokens.FONT_CODE}';
            font-size: 20px;
            font-weight: bold;
            border: none;
            background: transparent;
        """)
        card_layout.addWidget(self.lbl_sequence_display)

        layout.addWidget(self.preview_card)

        # 4. Message de validation / statut
        self.lbl_status = QLabel("", self)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(f"font-size: 11.5px; color: {DesignTokens.COLOR_GREEN}; font-weight: 500;")
        layout.addWidget(self.lbl_status)

        # 5. Pied de page avec actions
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        self.btn_reset_default = SecondaryButton(self.tr("Défaut"))
        self.btn_reset_default.setAutoDefault(False)
        self.btn_reset_default.setToolTip(self.tr("Restaurer la valeur par défaut du catalogue"))
        self.btn_reset_default.clicked.connect(self._on_reset_default_clicked)
        footer_layout.addWidget(self.btn_reset_default)

        footer_layout.addStretch()

        self.btn_cancel = SecondaryButton(self.tr("Annuler"))
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(self.btn_cancel)

        self.btn_validate = PrimaryButton(self.tr("Valider"))
        self.btn_validate.setAutoDefault(False)
        self.btn_validate.setDefault(False)
        self.btn_validate.clicked.connect(self.accept)
        footer_layout.addWidget(self.btn_validate)

        layout.addLayout(footer_layout)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_LG}px;
            }}
        """)

    def _validate_and_display(self, seq: str) -> None:
        """Contrôle la validité de la séquence et met à jour l'affichage en temps réel."""
        self.lbl_sequence_display.setText(seq)
        is_valid, msg = validate_shortcut_override(self.shortcut_id, seq, self._current_overrides)

        if is_valid:
            self.captured_sequence = seq
            self.lbl_status.setText(self.tr("✓ Combinaison valide"))
            self.lbl_status.setStyleSheet(f"font-size: 11.5px; color: {DesignTokens.COLOR_GREEN}; font-weight: 500;")
            self.preview_card.setStyleSheet(f"""
                QWidget {{
                    background-color: {DesignTokens.BG_MAIN};
                    border: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    padding: 16px;
                }}
            """)
            self.btn_validate.setEnabled(True)
        else:
            self.captured_sequence = ""
            self.lbl_status.setText(msg)
            self.lbl_status.setStyleSheet(f"font-size: 11.5px; color: {DesignTokens.COLOR_RED}; font-weight: 500;")
            self.preview_card.setStyleSheet(f"""
                QWidget {{
                    background-color: {DesignTokens.BG_MAIN};
                    border: 2px solid {DesignTokens.COLOR_RED};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                    padding: 16px;
                }}
            """)
            self.btn_validate.setEnabled(False)

    def _on_reset_default_clicked(self) -> None:
        """Restaure la valeur par défaut."""
        default_seq = self.definition.default_sequence
        self._validate_and_display(default_seq)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
            event.accept()
            return

        seq = key_event_to_sequence_str(event)
        if seq:
            self._validate_and_display(seq)
            event.accept()
            return

        # Modificateur seul enfoncé
        modifiers = event.modifiers()
        parts: list[str] = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")
        if parts:
            self.lbl_sequence_display.setText("+".join(parts) + "+...")
            self.lbl_status.setText(self.tr("Maintenez et appuyez sur une touche..."))
            self.lbl_status.setStyleSheet(f"font-size: 11.5px; color: {DesignTokens.TEXT_MUTED};")
            event.accept()
            return

        super().keyPressEvent(event)

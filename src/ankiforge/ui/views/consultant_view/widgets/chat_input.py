"""
Widget de saisie de chat hautement interactif pour le Consultant IA.
Prend en charge :
- L'autocomplétion non-bloquante et sécurisée des commandes Slash (/) et des mentions (@).
- L'envoi direct via la touche Entrée (et saut de ligne via Shift+Entrée).
- La navigation fluide dans le popup d'autocomplétion sans conflit d'événements.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.consultant_view.widgets.mention_completer import MentionCompleter

logger = logging.getLogger(__name__)


class ConsultantChatInput(QPlainTextEdit):
    """Zone de saisie enrichie pour le chat du Consultant IA."""

    send_requested = Signal()
    mention_completed = Signal(str, str)  # m_type, m_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.completer = MentionCompleter(self)
        self.completer.setWidget(self)
        self.completer.mention_selected.connect(self._on_completion_activated)

        self.setFixedHeight(50)
        self.setPlaceholderText("Posez une question, tapez '@' pour attacher ou '/' pour les commandes rapides...")
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                border: none;
                background: transparent;
                font-size: 13px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

    def textUnderCursor(self) -> tuple[str, str]:
        """Récupère le préfixe et le caractère déclencheur (@ ou /) sous le curseur."""
        tc = self.textCursor()
        pos = tc.positionInBlock()
        block_text = tc.block().text()
        text_before = block_text[:pos]

        # 1. Vérification commande Slash en début de ligne
        if text_before.startswith("/"):
            return "/", text_before[1:]

        # 2. Vérification mention @
        last_at = text_before.rfind("@")
        if last_at != -1 and (last_at == 0 or text_before[last_at - 1].isspace()):
            candidate = text_before[last_at + 1 :]
            if " " not in candidate:
                return "@", candidate

        return "", ""

    def keyPressEvent(self, e: QKeyEvent) -> None:
        popup = self.completer.popup()

        # 1. Si la popup de complétion est ouverte, lui déléguer les touches de sélection
        if popup is not None and popup.isVisible():
            if e.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                e.ignore()
                return
            elif e.key() == Qt.Key.Key_Escape:
                popup.hide()
                e.accept()
                return

        # 2. Gestion de la touche Entrée pour l'envoi direct (Shift+Entrée pour nouvelle ligne)
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            e.accept()
            self.send_requested.emit()
            return

        # 3. Traitement normal de la touche
        super().keyPressEvent(e)

        # 4. Évaluation du déclencheur d'autocomplétion
        trigger, prefix = self.textUnderCursor()

        if trigger in ("/", "@"):
            self.completer.update_completions(prefix, trigger_char=trigger)

            if popup is not None:
                model = self.completer.model()
                if model and model.rowCount() > 0:
                    popup.setCurrentIndex(model.index(0, 0))
                    cr = self.cursorRect()
                    cr.setWidth(320)
                    self.completer.complete(cr)
                else:
                    popup.hide()
        else:
            if popup is not None and popup.isVisible():
                popup.hide()

    @Slot(str, str)
    def _on_completion_activated(self, m_type: str, m_id: str) -> None:
        """Insère ou remplace le texte lors de la validation d'une suggestion."""
        popup = self.completer.popup()
        if popup is not None and popup.isVisible():
            popup.hide()

        tc = self.textCursor()

        if m_type == "slash":
            # Remplacer tout le texte par la commande slash
            self.setPlainText(m_id)
            # Positionner le curseur à la fin
            tc.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(tc)
        else:
            # Remplacement de la mention @
            pos = tc.positionInBlock()
            block_text = tc.block().text()
            text_before = block_text[:pos]
            last_at = text_before.rfind("@")
            if last_at != -1:
                tc.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, pos - last_at)
                tc.removeSelectedText()

        self.mention_completed.emit(m_type, m_id)

    def setText(self, text: str) -> None:
        """Compatibilité avec setPlainText."""
        self.setPlainText(text)

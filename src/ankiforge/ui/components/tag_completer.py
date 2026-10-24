"""Composant d'autocomplétion inline riche pour les tags (style IDE).

Fournit un menu contextuel (popover) affichant la hiérarchie :: des tags,
le compteur de notes associées, la navigation au clavier (flèches, Tab, Entrée)
et la validation immédiate par la barre d'espace selon l'ADR 0040.
Conforme aux Règles 2, 7, 8, 18, 19 et 20 de GEMINI.md et DESIGN.md.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.tags import is_provenance_tag, normalize_tag_input

logger = logging.getLogger(__name__)


class TagCompleterItemWidget(QWidget):
    """Widget de rangée personnalisée pour une suggestion d'autocomplétion de tag."""

    def __init__(self, tag: str, count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("tag", color=DesignTokens.ACCENT_PRIMARY).pixmap(12, 12))
        ico.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(ico)

        # Tag avec segments hiérarchiques stylés
        tag_lbl = QLabel()
        parts = tag.split("::")
        sep_html = f'<span style="color: {DesignTokens.TEXT_MUTED}; font-weight: normal;">::</span>'
        tag_html = sep_html.join(f'<span style="color: {DesignTokens.TEXT_PRIMARY};">{p}</span>' for p in parts)
        tag_lbl.setText(tag_html)
        tag_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        tag_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(tag_lbl, stretch=1)

        # Compteur de cartes
        count_lbl = QLabel(tr("%1 note%2", count, "s" if count > 1 else ""))
        count_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 8))
        count_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        layout.addWidget(count_lbl)


class TagCompleterPopup(QFrame):
    """Fenêtre popover flottante affichant la liste des suggestions de tags."""

    tag_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.list_widget = QListWidget(self)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QListWidget::item {{
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 1px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        tag = item.data(Qt.ItemDataRole.UserRole)
        if tag:
            self.tag_selected.emit(tag)


class TagAutocompleter(QObject):
    """Moteur d'autocomplétion attaché à un QLineEdit pour la saisie de tags."""

    tag_confirmed = Signal(str)

    def __init__(
        self,
        line_edit: QLineEdit,
        deck_id: int | None = None,
        single_tag_mode: bool = False,
        allow_provenance: bool = False,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or line_edit)
        self.line_edit = line_edit
        self.deck_id = deck_id
        self.single_tag_mode = single_tag_mode
        self.allow_provenance = allow_provenance

        self.popup = TagCompleterPopup()
        self.popup.tag_selected.connect(self._on_tag_selected)

        self._tags_cache: dict[str, int] = {}
        self.refresh_tags()

        self.line_edit.textEdited.connect(self._on_text_edited)
        self.line_edit.installEventFilter(self)

    def set_deck_id(self, deck_id: int | None) -> None:
        """Modifie la portée du paquet (Tag Scope) et actualise le catalogue."""
        self.deck_id = deck_id
        self.refresh_tags()

    def refresh_tags(self) -> None:
        """Recharge les tags de la portée active."""
        try:
            raw_counts = NoteRepository().get_tags_with_counts(self.deck_id)
            if not self.allow_provenance:
                self._tags_cache = {t: c for t, c in raw_counts.items() if not is_provenance_tag(t)}
            else:
                self._tags_cache = raw_counts
        except Exception as e:
            logger.debug("TagAutocompleter.refresh_tags : %s", e)
            self._tags_cache = {}

    def _get_current_token(self) -> tuple[str, int, int]:
        """Extrait le jeton de tag actuellement en cours de frappe sous le curseur."""
        text = self.line_edit.text()
        cursor = self.line_edit.cursorPosition()

        if self.single_tag_mode:
            return text.strip(), 0, len(text)

        # Recherche des délimiteurs (espaces ou virgules)
        start = 0
        for i in range(cursor - 1, -1, -1):
            if text[i] in (" ", ","):
                start = i + 1
                break

        end = len(text)
        for i in range(cursor, len(text)):
            if text[i] in (" ", ","):
                end = i
                break

        token = text[start:end].strip()
        return token, start, end

    def _on_text_edited(self, text: str) -> None:
        token, _, _ = self._get_current_token()
        self.trigger_completion(token)

    def trigger_completion(self, prefix: str) -> None:
        """Déclenche la recherche et l'affichage des suggestions selon le préfixe."""
        query = prefix.lower().strip()
        if not query:
            self.hide_popup()
            return

        matching: list[tuple[str, int]] = []
        for tag, count in self._tags_cache.items():
            if query in tag.lower():
                matching.append((tag, count))

        # Trier : d'abord ceux qui commencent par query, puis par fréquence décroissante
        matching.sort(key=lambda pair: (not pair[0].lower().startswith(query), -pair[1], pair[0]))

        if not matching:
            self.hide_popup()
            return

        self.popup.list_widget.clear()
        for tag, count in matching[:10]:
            item = QListWidgetItem(self.popup.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, tag)
            row_widget = TagCompleterItemWidget(tag, count, self.popup.list_widget)
            item.setSizeHint(row_widget.sizeHint())
            self.popup.list_widget.addItem(item)
            self.popup.list_widget.setItemWidget(item, row_widget)

        self.popup.list_widget.setCurrentRow(0)

        # Positionner sous le QLineEdit
        pos = self.line_edit.mapToGlobal(QPoint(0, self.line_edit.height()))
        self.popup.setFixedWidth(max(self.line_edit.width(), 260))
        self.popup.setFixedHeight(min(len(matching) * 30 + 10, 220))
        self.popup.move(pos)
        self.popup.show()

    def hide_popup(self) -> None:
        """Referme la fenêtre contextuelle d'autocomplétion."""
        if self.popup.isVisible():
            self.popup.hide()

    def _on_tag_selected(self, tag: str) -> None:
        """Insère le tag sélectionné dans le champ de saisie."""
        if self.single_tag_mode:
            self.line_edit.setText(tag)
            self.hide_popup()
            self.tag_confirmed.emit(tag)
            self.line_edit.clear()
        else:
            token, start, end = self._get_current_token()
            full_text = self.line_edit.text()
            new_text = full_text[:start] + tag + full_text[end:]
            self.line_edit.setText(new_text)
            self.line_edit.setCursorPosition(start + len(tag))
            self.hide_popup()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Intercepte les touches de navigation et validation (Tab, Entrée, Flèches, Espace)."""
        if watched == self.line_edit and isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress:
            key = event.key()

            # Flèche bas
            if key == Qt.Key.Key_Down:
                if self.popup.isVisible():
                    row = self.popup.list_widget.currentRow()
                    if row < self.popup.list_widget.count() - 1:
                        self.popup.list_widget.setCurrentRow(row + 1)
                    return True

            # Flèche haut
            elif key == Qt.Key.Key_Up:
                if self.popup.isVisible():
                    row = self.popup.list_widget.currentRow()
                    if row > 0:
                        self.popup.list_widget.setCurrentRow(row - 1)
                    return True

            # Tab ou Entrée / Return : validation
            elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.popup.isVisible():
                    current_item = self.popup.list_widget.currentItem()
                    if current_item:
                        tag = current_item.data(Qt.ItemDataRole.UserRole)
                        if tag:
                            self._on_tag_selected(tag)
                            return True
                elif self.single_tag_mode:
                    raw = self.line_edit.text().strip()
                    if raw:
                        clean = normalize_tag_input(raw)
                        if clean:
                            self.tag_confirmed.emit(clean)
                            self.line_edit.clear()
                            return True

            # Espace : validation réactive selon l'ADR 0040
            elif key == Qt.Key.Key_Space:
                if self.single_tag_mode:
                    if self.popup.isVisible() and self.popup.list_widget.currentItem():
                        tag = self.popup.list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
                        if tag:
                            self._on_tag_selected(tag)
                            return True
                    raw = self.line_edit.text().strip()
                    if raw:
                        clean = normalize_tag_input(raw)
                        if clean:
                            self.tag_confirmed.emit(clean)
                            self.line_edit.clear()
                            self.hide_popup()
                            return True
                    return True  # Évite d'insérer un blanc superflu
                elif self.popup.isVisible() and self.popup.list_widget.currentItem():
                    tag = self.popup.list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
                    if tag:
                        self._on_tag_selected(tag)
                        self.line_edit.insert(" ")
                        return True

            # Échap : fermeture du popup
            elif key == Qt.Key.Key_Escape and self.popup.isVisible():
                self.hide_popup()
                return True

        return super().eventFilter(watched, event)

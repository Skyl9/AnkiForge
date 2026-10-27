"""Widget dédié à l'affichage de création de carte pour le Garde-Fou.

Destiné aux patches de création (`note_create`, `batch_note_create`) qui n'ont pas
d'état « avant » et ne méritent donc pas une comparaison champ par champ (diff).
Affiche simplement les champs, le paquet, le type de note et les tags de la nouvelle carte.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DeckModel, NoteTypeModel
from ankiforge.ui.components import Badge, SecondaryButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.model_select_window import ModelSelectWindow
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class TagBadgeButton(QPushButton):
    """Badge de tag cliquable avec croix de suppression."""

    tag_removed = Signal(str)

    def __init__(self, tag: str, parent: QWidget | None = None) -> None:
        super().__init__(f"✕ {tag}", parent)
        self.tag = tag
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_PURPLE_BG};
                color: {DesignTokens.COLOR_PURPLE_TEXT};
                border: 1px solid {DesignTokens.COLOR_PURPLE_BORDER};
                border-radius: 9999px;
                padding: 0 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_PURPLE_BORDER};
                color: white;
            }}
        """)
        self.clicked.connect(lambda: self.tag_removed.emit(self.tag))


class CardCreateFieldRow(QFrame):
    """Champ éditable d'une nouvelle carte (nom + valeur modifiable)."""

    value_changed = Signal(str, str)  # field_name, new_value

    def __init__(self, field_name: str, field_value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.field_name = field_name

        self.setObjectName("CardCreateFieldRow")
        self.setStyleSheet(f"""
            QFrame#CardCreateFieldRow {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 6px;
            }}
        """)
        self._setup_ui(field_value)

    def _setup_ui(self, field_value: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        lbl_name = QLabel(self.field_name.upper())
        lbl_name.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: {DesignTokens.ACCENT_PRIMARY};
            border: none;
            background: transparent;
        """)
        header.addWidget(lbl_name)

        word_count = len(field_value.split()) if field_value else 0
        badge_words = Badge(tr("%1 mots", word_count), variant="neutral")
        header.addWidget(badge_words)
        header.addStretch()
        layout.addLayout(header)

        self.value_edit = QPlainTextEdit()
        self.value_edit.setPlainText(field_value)
        self.value_edit.setMaximumHeight(100)
        self.value_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                border: none;
                background-color: transparent;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                font-family: {DesignTokens.FONT_CODE};
            }}
        """)
        self.value_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.value_edit, 1)

    def _on_text_changed(self) -> None:
        self.value_changed.emit(self.field_name, self.value_edit.toPlainText())

    @property
    def value(self) -> str:
        """Retourne la valeur courante du champ."""
        return self.value_edit.toPlainText()


class CardCreateViewWidget(QWidget):
    """Vue d'affichage et d'édition de création de carte pour le Garde-Fou.

    Destiné aux patches de création (`note_create`, `batch_note_create`) qui n'ont pas
    d'état « avant » et ne méritent donc pas une comparaison champ par champ (diff).
    Permet d'éditer les champs, les tags (en badges modifiables), le paquet et le type de note,
    avec un aperçu rendu via CardPreviewWidget.
    """

    content_edited = Signal(object)  # dict[str, str] ou dict complet

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch_type: str = "note_create"
        self._fields: dict[str, str] = {}
        self._note_type: NoteTypeModel | None = None
        self._deck: DeckModel | None = None
        self._tags: list[str] = []
        self._field_rows: dict[str, CardCreateFieldRow] = {}
        self._notes_list: list[dict[str, Any]] = []
        self._current_note_index: int = 0
        self._tag_badges: list[TagBadgeButton] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # ── En-tête (titre + métadonnées) ──────────────────────────────
        header = QFrame()
        header.setObjectName("CardCreateHeader")
        header.setStyleSheet(f"""
            QFrame#CardCreateHeader {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 12px;
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(6, 6, 6, 6)
        header_layout.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.plus-circle", color=DesignTokens.COLOR_GREEN).pixmap(18, 18))
        header_layout.addWidget(ico)

        self.lbl_title = QLabel(tr("Nouvelle carte"))
        self.lbl_title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        header_layout.addWidget(self.lbl_title, 1)

        self.lbl_deck = QLabel()
        self.lbl_deck.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        header_layout.addWidget(self.lbl_deck)

        self.lbl_note_type = QLabel()
        self.lbl_note_type.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        header_layout.addWidget(self.lbl_note_type)

        self.btn_change_deck = SecondaryButton(tr("Changer le paquet"))
        self.btn_change_deck.setIcon(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_SECONDARY))
        self.btn_change_deck.setFixedHeight(28)
        self.btn_change_deck.clicked.connect(self._on_change_deck)
        header_layout.addWidget(self.btn_change_deck)

        self.btn_change_note_type = SecondaryButton(tr("Changer le type de note"))
        self.btn_change_note_type.setIcon(load_phosphor_icon("ph.note", color=DesignTokens.TEXT_SECONDARY))
        self.btn_change_note_type.setFixedHeight(28)
        self.btn_change_note_type.clicked.connect(self._on_change_note_type)
        header_layout.addWidget(self.btn_change_note_type)

        main_layout.addWidget(header)

        # ── Navigation lot (cachée si pas batch) ───────────────────────
        self.nav_widget = QWidget()
        self.nav_widget.setVisible(False)
        self.nav_row = QHBoxLayout(self.nav_widget)
        self.nav_row.setContentsMargins(0, 0, 0, 0)
        self.nav_row.setSpacing(6)

        self.btn_nav_prev = SecondaryButton(tr("Précédent"))
        self.btn_nav_prev.setFixedHeight(28)
        self.btn_nav_prev.clicked.connect(self._go_prev)
        self.nav_row.addWidget(self.btn_nav_prev)

        self.lbl_nav_pos = QLabel()
        self.lbl_nav_pos.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        self.nav_row.addWidget(self.lbl_nav_pos)

        self.btn_nav_next = SecondaryButton(tr("Suivant"))
        self.btn_nav_next.setFixedHeight(28)
        self.btn_nav_next.clicked.connect(self._go_next)
        self.nav_row.addWidget(self.btn_nav_next)

        self.nav_row.addStretch()
        main_layout.addWidget(self.nav_widget)

        # ── Champs de la carte ─────────────────────────────────────────
        self.fields_scroll = QScrollArea()
        self.fields_scroll.setWidgetResizable(True)
        self.fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.fields_scroll.setStyleSheet("background-color: transparent;")

        self.fields_content = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_content)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(0)
        self.fields_layout.addStretch()

        self.fields_scroll.setWidget(self.fields_content)
        self.fields_scroll.setMaximumHeight(300)
        main_layout.addWidget(self.fields_scroll, 1)

        # ── Tags en badges modifiables ─────────────────────────────────
        tags_card = QFrame()
        tags_card.setObjectName("CardCreateTags")
        tags_card.setStyleSheet(f"""
            QFrame#CardCreateTags {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 10px;
            }}
        """)
        tags_layout = QHBoxLayout(tags_card)
        tags_layout.setContentsMargins(8, 6, 8, 6)
        tags_layout.setSpacing(6)

        lbl_tags_title = QLabel(tr("TAGS"))
        lbl_tags_title.setStyleSheet(f"font-size: 10px; font-weight: 700; letter-spacing: 0.5px; color: {DesignTokens.ACCENT_PRIMARY};")
        tags_layout.addWidget(lbl_tags_title)

        self.tags_container = QWidget()
        self.tags_flow = QHBoxLayout(self.tags_container)
        self.tags_flow.setContentsMargins(0, 0, 0, 0)
        self.tags_flow.setSpacing(4)
        self.tags_flow.addStretch()
        tags_layout.addWidget(self.tags_container, 1)

        self.new_tag_edit = QLineEdit()
        self.new_tag_edit.setPlaceholderText(tr("Ajouter un tag…"))
        self.new_tag_edit.setFixedHeight(24)
        self.new_tag_edit.returnPressed.connect(self._on_new_tag_added)
        self.new_tag_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 10px;
                padding: 0 6px;
            }}
        """)
        tags_layout.addWidget(self.new_tag_edit)
        main_layout.addWidget(tags_card)

        # ── Aperçu via CardPreviewWidget ───────────────────────────────
        preview_card = QFrame()
        preview_card.setObjectName("CardCreatePreview")
        preview_card.setStyleSheet(f"""
            QFrame#CardCreatePreview {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(8, 6, 8, 6)
        preview_layout.setSpacing(4)

        preview_header = QHBoxLayout()
        preview_header.setContentsMargins(0, 0, 0, 0)
        preview_header.setSpacing(6)

        prev_icon = QLabel()
        prev_icon.setPixmap(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        preview_header.addWidget(prev_icon)

        prev_lbl = QLabel(tr("APERÇU"))
        prev_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED};")
        preview_header.addWidget(prev_lbl)
        preview_header.addStretch()
        preview_layout.addLayout(preview_header)

        self.preview_widget = CardPreviewWidget(parent=self, show_header=False)
        self.preview_widget.setMinimumHeight(160)
        self.preview_widget.setMaximumHeight(320)
        preview_layout.addWidget(self.preview_widget, 1)
        main_layout.addWidget(preview_card)

    def set_patch(self, patch: Any) -> None:
        """Configure l'affichage à partir d'un patch staged (`note_create` ou `batch_note_create`)."""
        from ankiforge.services.ai.staged_patch_registry import staged_payload_of

        if hasattr(patch, "patch_type"):
            p_type = patch.patch_type
            payload = staged_payload_of(patch)
        else:
            p_type = patch.get("patch_type") or patch.get("type", "note_create")
            raw_pl = patch.get("diff_payload") or patch
            if isinstance(raw_pl, str):
                try:
                    payload = json.loads(raw_pl)
                except Exception:
                    payload = {}
            elif isinstance(raw_pl, dict):
                payload = raw_pl
            else:
                payload = {}

        p_type = str(p_type).lower().strip()
        self._patch_type = p_type

        content = payload.get("modified") if isinstance(payload.get("modified"), dict) else payload
        if not isinstance(content, dict):
            content = {}

        is_batch = p_type == "batch_note_create"
        self.nav_widget.setVisible(is_batch)

        if is_batch:
            notes = payload.get("notes") or content.get("notes") or []
            self._display_batch(notes, payload)
        else:
            self._notes_list = []
            self._display_single(content, payload)

        self.lbl_title.setText(tr("Lot de création — %1 note(s)", len(self._notes_list)) if is_batch else tr("Nouvelle carte"))

    def _display_single(self, content: dict[str, Any], payload: dict[str, Any]) -> None:
        """Affiche une création de note unitaire."""
        fields = content.get("fields") or content.get("fields_dict") or {}
        if not isinstance(fields, dict):
            fields = {}
        self._fields = {str(k): str(v) for k, v in fields.items()}

        deck_name = content.get("deck_name") or content.get("deck") or payload.get("deck_name") or payload.get("deck") or ""
        self._deck = DeckModel.get_or_none(DeckModel.name == str(deck_name).strip()) if deck_name else None

        nt_name = content.get("note_type_name") or content.get("note_type") or payload.get("note_type_name") or payload.get("note_type") or ""
        self._note_type = NoteTypeModel.get_or_none(NoteTypeModel.name == str(nt_name).strip()) if nt_name else None

        raw_tags = content.get("tags") or payload.get("tags") or []
        if isinstance(raw_tags, str):
            self._tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, (list, tuple)):
            self._tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        else:
            self._tags = []

        self._refresh_fields()
        self._refresh_metadata()
        self._refresh_tags()
        self._refresh_preview()
        self._update_nav()

    def _display_batch(self, notes: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        """Affiche un lot de création de notes avec navigation."""
        self._notes_list = notes
        self._current_note_index = 0
        if notes:
            self._display_single(notes[0], payload)
        else:
            self._fields = {}
            self._refresh_fields()
            self._refresh_metadata()
            self._refresh_tags()
            self._refresh_preview()
            self._update_nav()

    def _refresh_fields(self) -> None:
        """Construit les lignes de champs éditables."""
        while self.fields_layout.count() > 1:
            item = self.fields_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_rows.clear()

        if not self._fields:
            lbl_empty = QLabel(tr("Aucun champ défini"))
            lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic;")
            self.fields_layout.insertWidget(self.fields_layout.count() - 1, lbl_empty)
            return

        for f_name in self._fields:
            row = CardCreateFieldRow(field_name=f_name, field_value=self._fields[f_name], parent=self.fields_content)
            row.value_changed.connect(self._on_field_changed)
            self._field_rows[f_name] = row
            self.fields_layout.insertWidget(self.fields_layout.count() - 1, row)

    def _refresh_metadata(self) -> None:
        """Met à jour les libellés de paquet et de type de note."""
        deck_name = self._deck.name if self._deck else tr("Non défini")
        nt_name = self._note_type.name if self._note_type else tr("Non défini")
        self.lbl_deck.setText(tr("Paquet : %1", deck_name))
        self.lbl_note_type.setText(tr("Type de note : %1", nt_name))

    def _refresh_tags(self) -> None:
        """Affiche les tags sous forme de badges cliquables."""
        for badge in self._tag_badges:
            self.tags_flow.removeWidget(badge)
            badge.deleteLater()
        self._tag_badges.clear()

        for tag in self._tags:
            badge = TagBadgeButton(tag, parent=self.tags_container)
            badge.tag_removed.connect(self._on_tag_removed)
            self.tags_flow.insertWidget(self.tags_flow.count() - 1, badge)
            self._tag_badges.append(badge)

    def _refresh_preview(self) -> None:
        """Rend l'aperçu de la carte via CardPreviewWidget."""
        nt = self._note_type
        if nt is None:
            # Crée un modèle temporaire pour l'aperçu si aucun n'est trouvé
            fields = list(self._fields.keys()) or ["Front", "Back"]
            templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]
            nt = NoteTypeModel(
                name=tr("Aperçu temporaire"),
                fields_schema=json.dumps(fields, ensure_ascii=False),
                templates=json.dumps(templates, ensure_ascii=False),
                css_style="",
            )

        self.preview_widget.update_preview(note_type=nt, fields_dict=self._fields)

    def _on_field_changed(self, field_name: str, new_val: str) -> None:
        """Répercute la modification d'un champ et notifie le contenu modifié."""
        self._fields[field_name] = new_val
        self.content_edited.emit(self.get_modified_content())
        self._refresh_preview()

    def _on_tag_removed(self, tag: str) -> None:
        """Supprime un tag et notifie le contenu modifié."""
        if tag in self._tags:
            self._tags.remove(tag)
            self._refresh_tags()
            self.content_edited.emit(self.get_modified_content())

    def _on_new_tag_added(self) -> None:
        """Ajoute le tag saisi dans le champ d'ajout."""
        text = self.new_tag_edit.text().strip()
        if not text or text in self._tags:
            self.new_tag_edit.clear()
            return
        self._tags.append(text)
        self.new_tag_edit.clear()
        self._refresh_tags()
        self.content_edited.emit(self.get_modified_content())

    def _update_nav(self) -> None:
        """Met à jour l'état des boutons de navigation et la position."""
        total = len(self._notes_list)
        self.lbl_nav_pos.setText(tr("%1 / %2", self._current_note_index + 1, max(1, total)))
        self.btn_nav_prev.setEnabled(total > 1 and self._current_note_index > 0)
        self.btn_nav_next.setEnabled(total > 1 and self._current_note_index < total - 1)

    def _go_prev(self) -> None:
        if self._current_note_index > 0:
            self._current_note_index -= 1
            self._display_single(self._notes_list[self._current_note_index], {})

    def _go_next(self) -> None:
        if self._current_note_index < len(self._notes_list) - 1:
            self._current_note_index += 1
            self._display_single(self._notes_list[self._current_note_index], {})

    def _on_change_deck(self) -> None:
        """Ouvre le sélecteur de paquet pour modifier le deck cible de la carte."""
        current_id = self._deck.id if self._deck else None
        dlg = DeckSelectWindow(selected_deck_id=current_id, parent=self)
        dlg.deck_selected.connect(self._on_deck_selected)
        dlg.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        """Applique le nouveau paquet sélectionné."""
        self._deck = DeckModel.get_or_none(DeckModel.id == deck_id)
        self._refresh_metadata()
        self._refresh_preview()
        self.content_edited.emit(self.get_modified_content())

    def _on_change_note_type(self) -> None:
        """Ouvre le sélecteur de type de note pour modifier le modèle cible."""
        current_id = self._note_type.id if self._note_type else None
        dlg = ModelSelectWindow(current_model_id=current_id, parent=self)
        dlg.model_selected.connect(self._on_note_type_selected)
        dlg.show()

    def _on_note_type_selected(self, model_id: int, model_name: str) -> None:
        """Applique le nouveau type de note sélectionné."""
        self._note_type = NoteTypeModel.get_or_none(NoteTypeModel.id == model_id)
        self._refresh_metadata()
        self._refresh_preview()
        self.content_edited.emit(self.get_modified_content())

    def get_modified_content(self) -> dict[str, Any]:
        """Retourne le contenu complet de la carte à créer (champs, tags, deck, note_type)."""
        content: dict[str, Any] = dict(self._fields)
        content["tags"] = list(self._tags)
        if self._deck:
            content["deck_name"] = self._deck.name
        if self._note_type:
            content["note_type_name"] = self._note_type.name
        return content

    def get_fields_dict(self) -> dict[str, str]:
        """Retourne le dictionnaire des champs de la carte."""
        return dict(self._fields)

    def get_tags(self) -> list[str]:
        """Retourne la liste des tags."""
        return list(self._tags)

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles au profil de thème actif."""
        self.style().unpolish(self)
        self.style().polish(self)
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "refresh_theme"):
            self.preview_widget.refresh_theme(profile)

    def cleanup(self) -> None:
        """Libère les ressources (CardPreviewWidget)."""
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "cleanup"):
            self.preview_widget.cleanup()

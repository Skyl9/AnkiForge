"""Widget d'affichage dédié pour les créations de notes (note_create, batch_note_create).

Affiche la nouvelle carte (champs, paquet, type de note, tags) sans comparaison avant/après,
puisque pour une création il n'y a pas d'état « avant ».
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DeckModel, NoteTypeModel, StagedPatchModel
from ankiforge.services.ai.staged_patch_registry import staged_payload_of
from ankiforge.ui.components import Badge
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class FieldDisplayRow(QFrame):
    """Ligne d'affichage d'un champ unique (lecture seule, sans diff)."""

    def __init__(
        self,
        field_name: str,
        field_value: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self._value = field_value
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setObjectName("FieldDisplayRow")
        self.setStyleSheet(f"""
            QFrame#FieldDisplayRow {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # En-tête : nom du champ + compteur de mots
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        lbl_field = QLabel(self.field_name.upper())
        lbl_field.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: {DesignTokens.ACCENT_PRIMARY};
            border: none;
            background: transparent;
        """)
        header_layout.addWidget(lbl_field)

        # Compteur de mots
        word_count = len(self._value.split()) if self._value else 0
        self.lbl_words = QLabel(tr("%1 mot(s)", word_count))
        self.lbl_words.setStyleSheet(f"""
            font-size: 10px;
            color: {DesignTokens.TEXT_MUTED};
            font-family: {DesignTokens.FONT_CODE};
            border: none;
            background: transparent;
        """)
        header_layout.addWidget(self.lbl_words)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Valeur du champ (lecture seule, avec sélection possible)
        self.value_browser = QTextEdit()
        self.value_browser.setPlainText(self._value)
        self.value_browser.setReadOnly(True)
        self.value_browser.setMinimumHeight(50)
        self.value_browser.setMaximumHeight(120)
        self.value_browser.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 6px;
            }}
        """)
        layout.addWidget(self.value_browser)


class NoteCreationWidget(QWidget):
    """Widget d'affichage pour la création de note(s) sans diff."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch: StagedPatchModel | None = None
        self._field_rows: list[FieldDisplayRow] = []
        self._batch_cards: list[dict[str, Any]] = []
        self._active_batch_index: int = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # ── 1. En-tête de création ──────────────────────────────────────
        self.header_card = QFrame()
        self.header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        header_layout = QHBoxLayout(self.header_card)
        header_layout.setContentsMargins(8, 8, 8, 8)
        header_layout.setSpacing(8)

        self.icon_badge = QLabel()
        self.icon_badge.setPixmap(load_phosphor_icon("ph.plus-circle", color=DesignTokens.COLOR_GREEN).pixmap(24, 24))
        header_layout.addWidget(self.icon_badge)

        self.lbl_title = QLabel(tr("Nouvelle carte"))
        self.lbl_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        header_layout.addWidget(self.lbl_title, 1)

        self.badge_mode = Badge(tr("CRÉATION"), variant="success")
        header_layout.addWidget(self.badge_mode)
        layout.addWidget(self.header_card)

        # ── 2. Sélecteur de carte (pour batch_note_create multi-cartes) ──
        self.batch_selector_bar = QFrame()
        self.batch_selector_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        batch_layout = QHBoxLayout(self.batch_selector_bar)
        batch_layout.setContentsMargins(8, 6, 8, 6)
        batch_layout.setSpacing(8)

        lbl_card = QLabel(tr("Carte :"))
        lbl_card.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        batch_layout.addWidget(lbl_card)

        from ankiforge.ui.components import StyledComboBox

        self.batch_selector = StyledComboBox()
        self.batch_selector.setMinimumWidth(200)
        self.batch_selector.currentIndexChanged.connect(self._on_batch_card_selected)
        batch_layout.addWidget(self.batch_selector, 1)

        self.lbl_batch_info = QLabel()
        self.lbl_batch_info.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        batch_layout.addWidget(self.lbl_batch_info)

        self.batch_selector_bar.hide()
        layout.addWidget(self.batch_selector_bar)

        # ── 3. Métadonnées (Paquet, Type de note, Tags) ─────────────────
        self.meta_card = QFrame()
        self.meta_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        meta_layout = QVBoxLayout(self.meta_card)
        meta_layout.setContentsMargins(12, 10, 12, 10)
        meta_layout.setSpacing(8)

        # Paquet
        deck_row = QHBoxLayout()
        deck_row.setSpacing(8)
        deck_icon = QLabel()
        deck_icon.setPixmap(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        deck_row.addWidget(deck_icon)

        lbl_deck_label = QLabel(tr("Paquet :"))
        lbl_deck_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        deck_row.addWidget(lbl_deck_label)

        self.lbl_deck_value = QLabel()
        self.lbl_deck_value.setStyleSheet(f"font-size: 12px; font-weight: 500; color: {DesignTokens.TEXT_PRIMARY};")
        deck_row.addWidget(self.lbl_deck_value)
        deck_row.addStretch()
        meta_layout.addLayout(deck_row)

        # Type de note
        nt_row = QHBoxLayout()
        nt_row.setSpacing(8)
        nt_icon = QLabel()
        nt_icon.setPixmap(load_phosphor_icon("ph.cardholder", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        nt_row.addWidget(nt_icon)

        lbl_nt_label = QLabel(tr("Type de note :"))
        lbl_nt_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        nt_row.addWidget(lbl_nt_label)

        self.lbl_nt_value = QLabel()
        self.lbl_nt_value.setStyleSheet(f"font-size: 12px; font-weight: 500; color: {DesignTokens.TEXT_PRIMARY};")
        nt_row.addWidget(self.lbl_nt_value)
        nt_row.addStretch()
        meta_layout.addLayout(nt_row)

        # Tags
        tags_row = QHBoxLayout()
        tags_row.setSpacing(8)
        tags_icon = QLabel()
        tags_icon.setPixmap(load_phosphor_icon("ph.tag", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        tags_row.addWidget(tags_icon)

        lbl_tags_label = QLabel(tr("Tags :"))
        lbl_tags_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        tags_row.addWidget(lbl_tags_label)

        self.lbl_tags_value = QLabel()
        self.lbl_tags_value.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE};")
        self.lbl_tags_value.setWordWrap(True)
        tags_row.addWidget(self.lbl_tags_value, 1)
        meta_layout.addLayout(tags_row)

        layout.addWidget(self.meta_card)

        # ── 4. Zone de défilement pour les champs ───────────────────────
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background-color: transparent;")

        self.scroll_content = QWidget()
        self.fields_layout = QVBoxLayout(self.scroll_content)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(0)
        self.fields_layout.addStretch()

        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area, 1)

        # ── 5. Édition directe (optionnelle pour retouches) ─────────────
        self.edit_card = QFrame()
        self.edit_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        edit_layout = QVBoxLayout(self.edit_card)
        edit_layout.setContentsMargins(12, 12, 12, 12)
        edit_layout.setSpacing(8)

        lbl_edit = QLabel(tr("Retouches rapides (optionnel) :"))
        lbl_edit.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        edit_layout.addWidget(lbl_edit)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(tr("Tags (séparés par des virgules)"))
        self.tags_edit.setFixedHeight(30)
        self.tags_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 0 8px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        edit_layout.addWidget(self.tags_edit)
        layout.addWidget(self.edit_card)

    def set_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les données du patch de création."""
        self._patch = patch
        payload = staged_payload_of(patch)
        p_type = patch.patch_type.lower().strip()

        # Nettoyage des champs précédents
        for row in self._field_rows:
            row.deleteLater()
        self._field_rows.clear()

        # Détermination : création unitaire ou par lot
        if p_type == "batch_note_create":
            self._setup_batch_view(payload)
        else:
            self._setup_single_view(payload)

    def _setup_single_view(self, payload: dict[str, Any]) -> None:
        """Configure l'affichage pour une création unitaire (note_create)."""
        self.lbl_title.setText(tr("Nouvelle carte"))
        self.badge_mode.setText(tr("CRÉATION"))
        self.badge_mode.set_variant("success")

        # Paquet
        deck_name = str(payload.get("deck_name") or payload.get("deck") or "")
        deck = DeckModel.get_or_none(DeckModel.name == deck_name) if deck_name else None
        self.lbl_deck_value.setText(deck.name if deck else (deck_name or tr("—")))

        # Type de note
        nt_name = str(payload.get("note_type_name") or payload.get("note_type") or "")
        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name) if nt_name else None
        self.lbl_nt_value.setText(nt.name if nt else (nt_name or tr("—")))

        # Tags
        raw_tags = payload.get("tags") or []
        if isinstance(raw_tags, str):
            tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, (list, tuple)):
            tags_list = [str(t).strip() for t in raw_tags if str(t).strip()]
        else:
            tags_list = []
        self.lbl_tags_value.setText(", ".join(tags_list) if tags_list else tr("Aucun"))
        self.tags_edit.setText(", ".join(tags_list))

        # Champs
        fields = payload.get("fields") or payload.get("fields_dict") or payload.get("content_dict") or {}
        if isinstance(fields, str):
            try:
                import json

                fields = json.loads(fields)
            except Exception:
                fields = {}

        if isinstance(fields, dict):
            for field_name, field_value in fields.items():
                val_str = str(field_value) if field_value is not None else ""
                row = FieldDisplayRow(field_name, val_str)
                self._field_rows.append(row)
                self.fields_layout.insertWidget(self.fields_layout.count() - 1, row)

    def _setup_batch_view(self, payload: dict[str, Any]) -> None:
        """Configure l'affichage pour une création par lot (batch_note_create)."""
        self.lbl_title.setText(tr("Lot de création"))
        self.badge_mode.setText(tr("CRÉATION PAR LOT"))
        self.badge_mode.set_variant("accent")

        notes_list = payload.get("notes") or []
        if not isinstance(notes_list, list):
            notes_list = []

        self._batch_cards = [n for n in notes_list if isinstance(n, dict)]
        self._active_batch_index = 0

        self.batch_selector.blockSignals(True)
        self.batch_selector.clear()
        for idx, note_item in enumerate(self._batch_cards):
            nt_name = str(note_item.get("note_type") or note_item.get("note_type_name") or "?")
            self.batch_selector.addItem(tr("Carte %1 / %2 — %3", idx + 1, len(self._batch_cards), nt_name))
        self.batch_selector.blockSignals(False)

        self.lbl_batch_info.setText(tr("%1 carte(s) dans ce lot", len(self._batch_cards)))
        self.batch_selector_bar.show()

        if self._batch_cards:
            self._display_batch_card(0)

    def _on_batch_card_selected(self, index: int) -> None:
        if 0 <= index < len(self._batch_cards):
            self._active_batch_index = index
            self._display_batch_card(index)

    def _display_batch_card(self, index: int) -> None:
        """Affiche les détails d'une carte spécifique du lot."""
        # Nettoyage champs précédents
        for row in self._field_rows:
            row.deleteLater()
        self._field_rows.clear()

        note_item = self._batch_cards[index]

        # Paquet
        deck_name = str(note_item.get("deck") or note_item.get("deck_name") or "")
        deck = DeckModel.get_or_none(DeckModel.name == deck_name) if deck_name else None
        self.lbl_deck_value.setText(deck.name if deck else (deck_name or tr("—")))

        # Type de note
        nt_name = str(note_item.get("note_type") or note_item.get("note_type_name") or "")
        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name) if nt_name else None
        self.lbl_nt_value.setText(nt.name if nt else (nt_name or tr("—")))

        # Tags
        default_tags_raw = note_item.get("default_tags") or []
        item_tags_raw = note_item.get("tags") or []
        if isinstance(default_tags_raw, str):
            default_tags = [t.strip() for t in default_tags_raw.split(",") if t.strip()]
        elif isinstance(default_tags_raw, (list, tuple)):
            default_tags = [str(t).strip() for t in default_tags_raw if str(t).strip()]
        else:
            default_tags = []

        if isinstance(item_tags_raw, str):
            item_tags = [t.strip() for t in item_tags_raw.split(",") if t.strip()]
        elif isinstance(item_tags_raw, (list, tuple)):
            item_tags = [str(t).strip() for t in item_tags_raw if str(t).strip()]
        else:
            item_tags = []

        combined_tags = list(dict.fromkeys(default_tags + item_tags))
        self.lbl_tags_value.setText(", ".join(combined_tags) if combined_tags else tr("Aucun"))
        self.tags_edit.setText(", ".join(combined_tags))

        # Champs
        fields = note_item.get("fields") or note_item.get("content_dict") or {}
        if isinstance(fields, str):
            try:
                import json

                fields = json.loads(fields)
            except Exception:
                fields = {}

        if isinstance(fields, dict):
            for field_name, field_value in fields.items():
                val_str = str(field_value) if field_value is not None else ""
                row = FieldDisplayRow(field_name, val_str)
                self._field_rows.append(row)
                self.fields_layout.insertWidget(self.fields_layout.count() - 1, row)

    def get_modified_content(self) -> dict[str, Any]:
        """Retourne le payload mis à jour avec les retouches utilisateur (tags)."""
        if not self._patch:
            return {}

        payload = dict(staged_payload_of(self._patch))
        p_type = self._patch.patch_type.lower().strip()

        edited_tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]

        if p_type == "batch_note_create":
            if self._batch_cards and 0 <= self._active_batch_index < len(self._batch_cards):
                note_item = self._batch_cards[self._active_batch_index]
                note_item["tags"] = edited_tags
                payload["notes"] = self._batch_cards
        else:
            payload["tags"] = edited_tags

        return payload

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les couleurs au profil de thème."""
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        text_muted = getattr(profile, "text_muted", DesignTokens.TEXT_MUTED)

        self.header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)

        self.batch_selector_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)

        self.meta_card.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        self.edit_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {border_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        self.tags_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-radius: 4px;
                color: {text_primary};
                font-size: 11px;
                padding: 0 8px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        for row in self._field_rows:
            row.setStyleSheet(f"""
                QFrame#FieldDisplayRow {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {border_color};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    margin-bottom: 6px;
                }}
            """)
            row.value_browser.setStyleSheet(f"""
                QTextEdit {{
                    border: 1px solid {border_color};
                    border-radius: 4px;
                    background-color: {bg_input};
                    color: {text_primary};
                    font-size: 11px;
                    padding: 6px;
                }}
            """)
            row.lbl_words.setStyleSheet(f"""
                font-size: 10px;
                color: {text_muted};
                font-family: {DesignTokens.FONT_CODE};
                border: none;
                background: transparent;
            """)

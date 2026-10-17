"""Composant de comparaison sémantique de cartes champ par champ avec édition directe et aperçu live.

Fournit une visualisation en deux colonnes (Base active BDD vs Proposition Agent MCP),
un diff mot-à-mot intra-ligne, l'édition en direct des champs et un onglet d'aperçu Anki réel.
"""

from __future__ import annotations

import difflib
import html
import json
import logging
import re
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel, StagedPatchModel
from ankiforge.services.ai.consultant_engine import robust_json_loads
from ankiforge.ui.components import Badge
from ankiforge.ui.components.inputs import StyledComboBox
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def compute_field_word_diff_html(original: str, modified: str) -> str:
    """Calcule un diff mot-à-mot intra-ligne avec suppressions rouges barrées et ajouts verts.

    Args:
        original: Texte de la base de données.
        modified: Texte proposé par l'agent.

    Returns:
        Chaîne HTML sécurisée avec balises span stylisées.
    """
    if not original and not modified:
        return f"<span style='color: {DesignTokens.TEXT_MUTED}; font-style: italic;'>Vide</span>"

    orig_tokens = re.findall(r"\S+|\s+", original)
    mod_tokens = re.findall(r"\S+|\s+", modified)

    matcher = difflib.SequenceMatcher(None, orig_tokens, mod_tokens)
    result_diff: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result_diff.append(html.escape("".join(orig_tokens[i1:i2])))
        elif tag == "delete":
            del_text = html.escape("".join(orig_tokens[i1:i2]))
            result_diff.append(
                f"<span style='background-color: {DesignTokens.COLOR_RED_BG}; color: {DesignTokens.COLOR_RED}; text-decoration: line-through; border-radius: 2px; padding: 1px 2px;'>{del_text}</span>"
            )
        elif tag == "insert":
            ins_text = html.escape("".join(mod_tokens[j1:j2]))
            result_diff.append(
                f"<span style='background-color: {DesignTokens.COLOR_GREEN_BG}; color: {DesignTokens.COLOR_GREEN}; font-weight: 600; border-radius: 2px; padding: 1px 2px;'>{ins_text}</span>"
            )
        elif tag == "replace":
            del_text = html.escape("".join(orig_tokens[i1:i2]))
            ins_text = html.escape("".join(mod_tokens[j1:j2]))
            result_diff.append(
                f"<span style='background-color: {DesignTokens.COLOR_RED_BG}; "
                f"color: {DesignTokens.COLOR_RED}; text-decoration: line-through; "
                f"border-radius: 2px; padding: 1px 2px;'>{del_text}</span> "
                f"<span style='background-color: {DesignTokens.COLOR_GREEN_BG}; "
                f"color: {DesignTokens.COLOR_GREEN}; font-weight: 600; "
                f"border-radius: 2px; padding: 1px 2px;'>{ins_text}</span>"
            )

    return "".join(result_diff).replace("\n", "<br>")


class FieldSemanticDiffRow(QFrame):
    """Ligne individuelle comparant un champ donné entre la base active et la proposition."""

    content_changed = Signal(str, str)  # field_name, new_value

    def __init__(
        self,
        field_name: str,
        original_value: str,
        modified_value: str,
        is_applied: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self._orig_val = original_value
        self._mod_val = modified_value
        self.is_applied = is_applied

        self._setup_ui()

    @property
    def is_modified(self) -> bool:
        """Indique si la valeur proposée diffère de la valeur d'origine."""
        return self._orig_val.strip() != self.current_modified_value.strip()

    @property
    def current_modified_value(self) -> str:
        """Retourne la valeur actuelle contenue dans l'éditeur de droite."""
        if hasattr(self, "mod_editor"):
            return self.mod_editor.toPlainText()
        return self._mod_val

    def _setup_ui(self) -> None:
        self.setObjectName("FieldSemanticDiffRow")
        self.setStyleSheet(f"""
            QFrame#FieldSemanticDiffRow {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 8px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # 1. En-tête de champ (Nom + Badge d'état + Compteur de mots)
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

        # Badge d'état
        self.status_badge = Badge(
            tr("Modifié") if self.is_modified else tr("Identique"),
            variant="warning" if self.is_modified else "neutral",
        )
        header_layout.addWidget(self.status_badge)

        # Compteur comparatif de mots
        orig_words = len(self._orig_val.split()) if self._orig_val else 0
        mod_words = len(self._mod_val.split()) if self._mod_val else 0
        self.lbl_words = QLabel(tr("%1 ➔ %2 mots", orig_words, mod_words))
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

        # 2. Deux colonnes côte-à-côte
        cols_layout = QHBoxLayout()
        cols_layout.setContentsMargins(0, 0, 0, 0)
        cols_layout.setSpacing(8)

        # Colonne Gauche : BDD (Lecture seule)
        left_col = QFrame()
        left_col.setObjectName("left_col")
        left_col.setStyleSheet(f"""
            QFrame#left_col {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
        """)
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(4)

        lbl_left = QLabel(tr("⏮️ Base active (BDD)"))
        lbl_left.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 600;
            color: {DesignTokens.COLOR_RED};
            border: none;
            background: transparent;
        """)
        left_layout.addWidget(lbl_left)

        self.orig_browser = QTextBrowser()
        self.orig_browser.setMinimumHeight(60)
        self.orig_browser.setMaximumHeight(140)
        self.orig_browser.setHtml(compute_field_word_diff_html(self._orig_val, self._mod_val))
        self.orig_browser.setStyleSheet(f"""
            QTextBrowser {{
                border: none;
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
            }}
        """)
        left_layout.addWidget(self.orig_browser, 1)
        cols_layout.addWidget(left_col, 1)

        # Colonne Droite : Proposition Agent MCP (Éditable en direct)
        right_col = QFrame()
        right_col.setObjectName("right_col")
        right_col.setStyleSheet(f"""
            QFrame#right_col {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QFrame#right_col:focus-within {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(4)

        lbl_right = QLabel(tr("✨ Proposition Agent MCP (Éditable)"))
        lbl_right.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 600;
            color: {DesignTokens.COLOR_GREEN};
            border: none;
            background: transparent;
        """)
        right_layout.addWidget(lbl_right)

        self.mod_editor = QPlainTextEdit()
        self.mod_editor.setMinimumHeight(60)
        self.mod_editor.setMaximumHeight(140)
        self.mod_editor.setPlainText(self._mod_val)
        self.mod_editor.setReadOnly(self.is_applied)
        self.mod_editor.setStyleSheet(f"""
            QPlainTextEdit {{
                border: none;
                background-color: transparent;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
            }}
        """)
        self.mod_editor.textChanged.connect(self._on_text_changed)
        right_layout.addWidget(self.mod_editor, 1)
        cols_layout.addWidget(right_col, 1)

        layout.addLayout(cols_layout)

    def _on_text_changed(self) -> None:
        new_text = self.mod_editor.toPlainText()
        self._mod_val = new_text

        # Mise à jour du badge et compteur
        is_mod = self._orig_val.strip() != new_text.strip()
        self.status_badge.setText(tr("Modifié") if is_mod else tr("Identique"))
        self.status_badge.set_variant("warning" if is_mod else "neutral")

        orig_words = len(self._orig_val.split()) if self._orig_val else 0
        mod_words = len(new_text.split()) if new_text else 0
        self.lbl_words.setText(tr("%1 ➔ %2 mots", orig_words, mod_words))

        # Rafraîchit le diff visuel de la colonne gauche
        self.orig_browser.setHtml(compute_field_word_diff_html(self._orig_val, new_text))

        self.content_changed.emit(self.field_name, new_text)


class CardSemanticDiffWidget(QWidget):
    """Composant visuel de diff sémantique champ par champ avec double colonne et rendu live.

    Supporte les propositions unitaires ('card', 'note_create') et les scissions atomiques ('split').
    """

    content_edited = Signal(object)  # dict[str, str] ou list[dict[str, str]]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._note_type: NoteTypeModel | None = None
        self._patch_type: str = "card"
        self._original: dict[str, Any] = {}
        self._modified: dict[str, Any] | list[dict[str, Any]] = {}
        self._split_cards: list[dict[str, Any]] = []
        self._active_split_index: int = 0
        self._is_applied: bool = False
        self._field_rows: dict[str, FieldSemanticDiffRow] = {}

        self._setup_ui()

    @property
    def is_split(self) -> bool:
        """Indique si la proposition courante est une scission multi-cartes."""
        return self._patch_type in ("split", "card_split") and isinstance(self._modified, list)

    def get_field_rows(self) -> dict[str, FieldSemanticDiffRow]:
        """Retourne le dictionnaire des lignes de champs couramment affichées."""
        return self._field_rows

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Onglets principaux : Diff vs Aperçu Live
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                background-color: {DesignTokens.BG_PANEL};
            }}
            QTabBar::tab {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 6px 14px;
                margin-right: 2px;
                font-size: 11px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: 600;
                border-color: {DesignTokens.BORDER_COLOR};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        # ── 1. Onglet Diff Comparatif ─────────────────────────
        self.diff_tab = QWidget()
        diff_tab_layout = QVBoxLayout(self.diff_tab)
        diff_tab_layout.setContentsMargins(6, 6, 6, 6)
        diff_tab_layout.setSpacing(6)

        # Barre supérieure pour sélection de scission (visible uniquement si split)
        self.split_bar = QWidget()
        split_layout = QHBoxLayout(self.split_bar)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(8)

        lbl_split = QLabel(tr("🔀 Carte atomique :"))
        lbl_split.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY};")
        split_layout.addWidget(lbl_split)

        self.split_selector = StyledComboBox()
        self.split_selector.currentIndexChanged.connect(self._on_split_card_selected)
        split_layout.addWidget(self.split_selector, 1)
        split_layout.addStretch()

        self.split_bar.hide()
        diff_tab_layout.addWidget(self.split_bar)

        # Zone de défilement pour les champs
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
        diff_tab_layout.addWidget(self.scroll_area, 1)

        self.tab_widget.addTab(self.diff_tab, load_phosphor_icon("ph.columns", color=DesignTokens.TEXT_SECONDARY), tr("Comparaison champ par champ"))

        # ── 2. Onglet Aperçu Live Anki ────────────────────────
        self.preview_tab = QWidget()
        preview_layout = QVBoxLayout(self.preview_tab)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_widget = CardPreviewWidget(parent=self.preview_tab, show_header=True)
        preview_layout.addWidget(self.preview_widget)

        self.tab_widget.addTab(self.preview_tab, load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_SECONDARY), tr("Aperçu Anki Live"))
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tab_widget)

    def set_diff(
        self,
        original: dict[str, Any] | str,
        modified: dict[str, Any] | list[dict[str, Any]] | str,
        note_type: NoteTypeModel | None = None,
        is_applied: bool = False,
        patch_type: str = "card",
    ) -> None:
        """Injecte les données d'origine et modifiées à comparer."""
        self._note_type = note_type
        self._is_applied = is_applied
        self._patch_type = patch_type.lower().strip()

        # Normalisation original
        if isinstance(original, str):
            try:
                self._original = robust_json_loads(original)
            except Exception:
                self._original = {"Front": original}
        elif isinstance(original, dict):
            self._original = dict(original)
        else:
            self._original = {}

        # Normalisation modified
        if isinstance(modified, str):
            try:
                parsed = robust_json_loads(modified)
                self._modified = parsed
            except Exception:
                self._modified = {"Front": modified}
        elif isinstance(modified, (dict, list)):
            self._modified = modified
        else:
            self._modified = {}

        if self.is_split and isinstance(self._modified, list):
            self._split_cards = self._modified
            self._active_split_index = 0
            self.split_selector.blockSignals(True)
            self.split_selector.clear()
            for idx in range(len(self._split_cards)):
                self.split_selector.addItem(tr("Carte atomique %1 sur %2", idx + 1, len(self._split_cards)))
            self.split_selector.blockSignals(False)
            self.split_bar.show()
            self._populate_fields(self._split_cards[0])
        else:
            self.split_bar.hide()
            self._split_cards = []
            curr_mod = self._modified if isinstance(self._modified, dict) else {}
            self._populate_fields(curr_mod)

        self._refresh_preview()

    def set_patch(self, patch: StagedPatchModel | dict[str, Any]) -> None:
        """Extrait automatiquement les composantes d'un patch staged et configure le visualiseur."""
        if isinstance(patch, StagedPatchModel):
            p_type = patch.patch_type
            is_applied = patch.status == "applied"
            payload = {}
            if patch.diff_payload:
                try:
                    payload = json.loads(patch.diff_payload) if isinstance(patch.diff_payload, str) else patch.diff_payload
                except Exception:
                    payload = {}
        else:
            p_type = patch.get("patch_type") or patch.get("type", "card")
            is_applied = patch.get("status") == "applied"
            payload = patch.get("diff_payload") or patch

        orig = payload.get("original", {})
        mod = payload.get("modified", {})
        if not mod and "fields" in payload:
            mod = payload["fields"]

        # Résolution du modèle de note
        note_type = None
        nt_name = payload.get("model_name") or payload.get("note_type_name")
        if nt_name:
            note_type = NoteTypeModel.get_or_none(NoteTypeModel.name == str(nt_name).strip())

        self.set_diff(original=orig, modified=mod, note_type=note_type, is_applied=is_applied, patch_type=p_type)

    def _populate_fields(self, mod_dict: dict[str, Any]) -> None:
        """Construit les lignes de comparaison champ par champ."""
        # Nettoyage des anciennes lignes
        while self.fields_layout.count() > 1:
            item = self.fields_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_rows.clear()

        # Fusion ordonnée des noms de champs
        all_field_names: list[str] = []
        if self._note_type and self._note_type.fields_schema:
            try:
                schema = json.loads(self._note_type.fields_schema) if isinstance(self._note_type.fields_schema, str) else self._note_type.fields_schema
                if isinstance(schema, list):
                    all_field_names.extend([str(f) for f in schema])
            except Exception:
                pass

        for k in list(self._original.keys()) + list(mod_dict.keys()):
            if k not in all_field_names and not k.startswith("_"):
                all_field_names.append(k)

        if not all_field_names:
            all_field_names = ["Front", "Back"]

        for f_name in all_field_names:
            orig_val = str(self._original.get(f_name, ""))
            mod_val = str(mod_dict.get(f_name, ""))

            row = FieldSemanticDiffRow(
                field_name=f_name,
                original_value=orig_val,
                modified_value=mod_val,
                is_applied=self._is_applied,
                parent=self.scroll_content,
            )
            row.content_changed.connect(self._on_row_content_changed)
            self._field_rows[f_name] = row
            # Insère avant le stretch final
            self.fields_layout.insertWidget(self.fields_layout.count() - 1, row)

    def _on_row_content_changed(self, field_name: str, new_val: str) -> None:
        """Gère la répercussion d'une retouche utilisateur."""
        if self.is_split and self._split_cards:
            self._split_cards[self._active_split_index][field_name] = new_val
            self.content_edited.emit(self.get_modified_content())
        elif isinstance(self._modified, dict):
            self._modified[field_name] = new_val
            self.content_edited.emit(self.get_modified_content())

        if self.tab_widget.currentIndex() == 1:
            self._refresh_preview()

    def _on_split_card_selected(self, index: int) -> None:
        """Bascule sur une autre carte atomique lors d'une scission."""
        if 0 <= index < len(self._split_cards):
            self._active_split_index = index
            self._populate_fields(self._split_cards[index])
            self._refresh_preview()

    def _on_tab_changed(self, index: int) -> None:
        """Rafraîchit l'aperçu Anki Live si l'utilisateur bascule sur le 2e onglet."""
        if index == 1:
            self._refresh_preview()

    def get_modified_content(self) -> dict[str, Any] | list[dict[str, Any]]:
        """Retourne la structure complète modifiée (dict unitaire ou liste de dicts scindés)."""
        if self.is_split and self._split_cards:
            # Synchronise la carte active avec les éditeurs
            curr = dict(self._split_cards[self._active_split_index])
            for f_name, row in self._field_rows.items():
                curr[f_name] = row.current_modified_value
            self._split_cards[self._active_split_index] = curr
            return list(self._split_cards)

        res: dict[str, Any] = dict(self._modified) if isinstance(self._modified, dict) else {}
        for f_name, row in self._field_rows.items():
            res[f_name] = row.current_modified_value
        return res

    def get_fields_dict(self) -> dict[str, str]:
        """Retourne les champs de la carte actuellement inspectée pour le rendu Anki."""
        res: dict[str, str] = {}
        for f_name, row in self._field_rows.items():
            res[f_name] = row.current_modified_value
        return res

    def _refresh_preview(self) -> None:
        """Met à jour l'instance interne de CardPreviewWidget."""
        fields = self.get_fields_dict()
        self.preview_widget.update_preview(note_type=self._note_type, fields_dict=fields)

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit les styles et l'aperçu rendu selon le thème actif."""
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "refresh_theme"):
            self.preview_widget.refresh_theme(profile)
        self._refresh_preview()

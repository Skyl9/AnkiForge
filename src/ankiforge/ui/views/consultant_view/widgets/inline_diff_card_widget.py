"""
Widget de Diff Inline intégré directement dans le message de chat.

Permet à l'utilisateur de comparer les champs d'une carte (Recto, Verso),
d'éditer directement le texte proposé avant validation, de scinder des cartes
et d'appliquer ou annuler les modifications en 1 clic.
"""

from __future__ import annotations

import difflib
import html
import json
import logging
import re
import uuid
import weakref
from typing import Any

from peewee import fn
from PySide6.QtCore import QSettings, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.ui.components import Badge, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def get_saved_diff_view_mode() -> str:
    """Récupère le mode de vue diff mémorisé (défaut: 'unified')."""
    settings = QSettings("AnkiForge", "AnkiForge")
    val = settings.value("consultant/diff_view_mode", None)
    if val:
        return str(val)
    try:
        from ankiforge.repositories import SettingRepository

        repo_val = SettingRepository().get_setting("consultant_diff_view_mode")
        if repo_val:
            return str(repo_val)
    except Exception:
        pass
    return "unified"


def save_saved_diff_view_mode(mode: str) -> None:
    """Sauvegarde le mode de vue diff pour les sessions futures."""
    settings = QSettings("AnkiForge", "AnkiForge")
    settings.setValue("consultant/diff_view_mode", mode)
    try:
        from ankiforge.repositories import SettingRepository

        SettingRepository().set_setting("consultant_diff_view_mode", mode)
    except Exception:
        pass


def compute_word_diff_html(original: str, modified: str, show_deletions: bool = True) -> str:
    """Calcule un diff mot à mot (word-level diff) formaté en HTML colorisé."""
    if not original and not modified:
        return "<span style='color: gray;'><i>Vide</i></span>"

    if not show_deletions:
        # Unification totale : texte unifié fluide sans ratures avec surlignage vert discret sur les ajouts
        if not original:
            return html.escape(modified).replace("\n", "<br>")
        orig_tokens = re.findall(r"\S+|\s+", original)
        mod_tokens = re.findall(r"\S+|\s+", modified)
        matcher = difflib.SequenceMatcher(None, orig_tokens, mod_tokens)
        result: list[str] = []
        for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                result.append(html.escape("".join(mod_tokens[j1:j2])))
            elif tag in ("insert", "replace"):
                ins_text = html.escape("".join(mod_tokens[j1:j2]))
                result.append(f"<span style='background-color: rgba(34, 197, 94, 0.18); color: {DesignTokens.COLOR_GREEN}; font-weight: 600; border-radius: 2px; padding: 1px 2px;'>{ins_text}</span>")
        return "".join(result).replace("\n", "<br>")

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
                f"<span style='background-color: rgba(239, 68, 68, 0.2); color: {DesignTokens.COLOR_RED}; text-decoration: line-through; border-radius: 2px; padding: 1px 2px;'>{del_text}</span>"
            )
        elif tag == "insert":
            ins_text = html.escape("".join(mod_tokens[j1:j2]))
            result_diff.append(f"<span style='background-color: rgba(34, 197, 94, 0.22); color: {DesignTokens.COLOR_GREEN}; font-weight: 600; border-radius: 2px; padding: 1px 2px;'>{ins_text}</span>")
        elif tag == "replace":
            del_text = html.escape("".join(orig_tokens[i1:i2]))
            ins_text = html.escape("".join(mod_tokens[j1:j2]))
            result_diff.append(
                f"<span style='background-color: rgba(239, 68, 68, 0.2); color: {DesignTokens.COLOR_RED}; text-decoration: line-through; border-radius: 2px; padding: 1px 2px;'>{del_text}</span> "
            )
            result_diff.append(f"<span style='background-color: rgba(34, 197, 94, 0.22); color: {DesignTokens.COLOR_GREEN}; font-weight: 600; border-radius: 2px; padding: 1px 2px;'>{ins_text}</span>")

    return "".join(result_diff).replace("\n", "<br>")


class FieldDiffWidget(QFrame):
    """
    Composant d'affichage d'un champ avec support des modes :
    - Vue Unifiée (diff mot à mot fusionné)
    - Vue Côte à Côte (2 colonnes : Actuel vs Proposition Éditable)
    - Vue Édition Directe pleine largeur
    """

    def __init__(
        self,
        field_name: str,
        original_val: str,
        modified_val: str,
        is_applied: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self.original_val = original_val
        self.modified_val = modified_val
        self.is_applied = is_applied
        self.show_deletions = False  # Par défaut : Unification Totale (sans mots supprimés barrés)
        self._is_editing = False
        self.current_mode = get_saved_diff_view_mode()
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            FieldDiffWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # En-tête du champ
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        lbl_name = QLabel(f"<b>{html.escape(self.field_name)}</b>")
        lbl_name.setStyleSheet(f"font-size: 11px; color: {DesignTokens.ACCENT_PRIMARY}; border: none; background: transparent;")
        header.addWidget(lbl_name)

        # Compteur comparatif de mots
        words_orig = len(self.original_val.split()) if self.original_val else 0
        words_mod = len(self.modified_val.split()) if self.modified_val else 0
        self.lbl_badge = QLabel(f"{words_orig} ➔ {words_mod} mots")
        self.lbl_badge.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; border: none; background: transparent;")
        header.addWidget(self.lbl_badge)
        header.addStretch()

        # Bouton d'affichage des ratures (visible en mode unifié)
        self.btn_toggle_deletions = QPushButton("🔍 Ratures")
        self.btn_toggle_deletions.setFixedHeight(20)
        self.btn_toggle_deletions.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_deletions.setToolTip("Afficher/masquer les mots supprimés barrés")
        self.btn_toggle_deletions.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 3px;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                padding: 1px 6px;
            }}
            QPushButton:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton[active="true"] {{
                background-color: rgba(239, 68, 68, 0.15);
                border-color: {DesignTokens.COLOR_RED};
                color: {DesignTokens.COLOR_RED};
                font-weight: 600;
            }}
        """)
        self.btn_toggle_deletions.clicked.connect(self._toggle_deletions)
        self.btn_toggle_deletions.setVisible(self.current_mode == "unified" and not self.is_applied)
        header.addWidget(self.btn_toggle_deletions)

        self.btn_mode_toggle = QPushButton("✏️ Modifier")
        self.btn_mode_toggle.setFixedHeight(20)
        self.btn_mode_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 3px;
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 10px;
                padding: 1px 6px;
            }}
            QPushButton:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.btn_mode_toggle.clicked.connect(self._toggle_edit_mode)
        header.addWidget(self.btn_mode_toggle)
        layout.addLayout(header)

        # Stack de visualisation (Diff Unifié vs Côte à Côte vs Éditeur Pleine Largeur)
        self.stack = QStackedWidget()

        # ── 1. Index 0 : Vue Unifiée (diff mot à mot) ────────────────────────
        diff_html = html.escape(self.modified_val).replace("\n", "<br>") if self.is_applied else compute_word_diff_html(self.original_val, self.modified_val, show_deletions=self.show_deletions)
        self.diff_label = QLabel()
        self.diff_label.setWordWrap(True)
        self.diff_label.setTextFormat(Qt.TextFormat.RichText)
        self.diff_label.setText(diff_html)
        self.diff_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.diff_label.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 8px;
                font-size: 11px;
            }}
        """)
        self.stack.addWidget(self.diff_label)

        # ── 2. Index 1 : Vue Côte à Côte (2 colonnes) ────────────────────────
        self.side_by_side_widget = QWidget()
        sbs_layout = QHBoxLayout(self.side_by_side_widget)
        sbs_layout.setContentsMargins(0, 0, 0, 0)
        sbs_layout.setSpacing(8)

        # Colonne Gauche : Actuel (Original)
        col_orig = QFrame()
        col_orig.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
        """)
        col_orig_layout = QVBoxLayout(col_orig)
        col_orig_layout.setContentsMargins(6, 6, 6, 6)
        col_orig_layout.setSpacing(4)
        lbl_orig_header = QLabel("⏮️ Actuel (Original)")
        lbl_orig_header.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.COLOR_RED}; border: none; background: transparent;")
        col_orig_layout.addWidget(lbl_orig_header)

        self.orig_text_browser = QTextBrowser()
        self.orig_text_browser.setMaximumHeight(85)
        self.orig_text_browser.setPlainText(self.original_val)
        self.orig_text_browser.setStyleSheet(f"font-size: 11px; border: none; background: transparent; color: {DesignTokens.TEXT_SECONDARY};")
        col_orig_layout.addWidget(self.orig_text_browser, 1)

        # Colonne Droite : Proposition IA (Éditable)
        col_mod = QFrame()
        col_mod.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 4px;
            }}
        """)
        col_mod_layout = QVBoxLayout(col_mod)
        col_mod_layout.setContentsMargins(6, 6, 6, 6)
        col_mod_layout.setSpacing(4)
        lbl_mod_header = QLabel("✨ Proposition IA (Éditable)")
        lbl_mod_header.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")
        col_mod_layout.addWidget(lbl_mod_header)

        self.sbs_editor = QTextEdit()
        self.sbs_editor.setMaximumHeight(85)
        self.sbs_editor.setPlainText(self.modified_val)
        self.sbs_editor.setStyleSheet(f"font-size: 11px; border: none; background: transparent; color: {DesignTokens.TEXT_PRIMARY};")
        self.sbs_editor.textChanged.connect(self._on_sbs_text_changed)
        col_mod_layout.addWidget(self.sbs_editor, 1)

        sbs_layout.addWidget(col_orig, 1)
        sbs_layout.addWidget(col_mod, 1)
        self.stack.addWidget(self.side_by_side_widget)

        # ── 3. Index 2 : Vue Édition Pleine Largeur ─────────────────────────
        self.editor = QTextEdit()
        self.editor.setPlainText(self.modified_val)
        self.editor.setMaximumHeight(85)
        self.editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.editor.textChanged.connect(self._on_editor_text_changed)
        self.stack.addWidget(self.editor)

        layout.addWidget(self.stack)

    def _on_sbs_text_changed(self) -> None:
        new_val = self.sbs_editor.toPlainText()
        self.modified_val = new_val
        self.editor.blockSignals(True)
        self.editor.setPlainText(new_val)
        self.editor.blockSignals(False)
        self._refresh_diff_and_badge()

    def _on_editor_text_changed(self) -> None:
        new_val = self.editor.toPlainText()
        self.modified_val = new_val
        self.sbs_editor.blockSignals(True)
        self.sbs_editor.setPlainText(new_val)
        self.sbs_editor.blockSignals(False)
        self._refresh_diff_and_badge()

    def _refresh_diff_and_badge(self) -> None:
        if self.is_applied:
            self.diff_label.setText(html.escape(self.modified_val).replace("\n", "<br>"))
            self.btn_toggle_deletions.setVisible(False)
        else:
            diff_html = compute_word_diff_html(self.original_val, self.modified_val, show_deletions=self.show_deletions)
            self.diff_label.setText(diff_html)
            self.btn_toggle_deletions.setVisible(self.current_mode == "unified")

        words_orig = len(self.original_val.split()) if self.original_val else 0
        words_mod = len(self.modified_val.split()) if self.modified_val else 0
        self.lbl_badge.setText(f"{words_orig} ➔ {words_mod} mots")

    def _toggle_deletions(self) -> None:
        """Bascule l'affichage des ratures rouges barrées (True) vs Unification Totale (False)."""
        self.show_deletions = not self.show_deletions
        self.btn_toggle_deletions.setProperty("active", self.show_deletions)
        self.btn_toggle_deletions.style().unpolish(self.btn_toggle_deletions)
        self.btn_toggle_deletions.style().polish(self.btn_toggle_deletions)
        self._refresh_diff_and_badge()

    def set_applied(self, applied: bool) -> None:
        """Marque le champ comme officiellement appliqué en BDD (unification totale pure)."""
        self.is_applied = applied
        if applied:
            self.original_val = self.modified_val
            self.orig_text_browser.setPlainText(self.modified_val)
        self._refresh_diff_and_badge()

    def set_view_mode(self, mode: str) -> None:
        self.current_mode = mode
        self._is_editing = False
        self.btn_mode_toggle.setText("✏️ Modifier")
        self.btn_toggle_deletions.setVisible(mode == "unified" and not self.is_applied)
        if mode in ["split", "side_by_side"]:
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)
            self._refresh_diff_and_badge()

    def _toggle_edit_mode(self) -> None:
        self._is_editing = not self._is_editing
        if self._is_editing:
            self.stack.setCurrentIndex(2)
            self.btn_mode_toggle.setText("👁️ Diff")
            self.editor.setFocus()
        else:
            self._refresh_diff_and_badge()
            self.set_view_mode(self.current_mode)

    def get_current_value(self) -> str:
        """Retourne la valeur actuellement saisie dans l'éditeur."""
        return self.modified_val


class SplitCardItemWidget(QFrame):
    """Widget représentant une carte fille dans une scission atomique avec sélection."""

    def __init__(self, index: int, card_data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.card_data = card_data
        self.field_editors: dict[str, QTextEdit] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            SplitCardItemWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.chk_include = QCheckBox(f"Carte atomique #{self.index + 1}")
        self.chk_include.setChecked(True)
        self.chk_include.setStyleSheet(f"font-weight: 600; font-size: 11px; color: {DesignTokens.TEXT_PRIMARY};")
        header.addWidget(self.chk_include)
        header.addStretch()
        layout.addLayout(header)

        # Affichage des champs de la carte scindée (côte à côte si 2 champs)
        valid_fields = [(str(k), v) for k, v in self.card_data.items() if str(k).lower() not in ["id", "note_id"]]
        if len(valid_fields) == 2:
            cols_layout = QHBoxLayout()
            cols_layout.setContentsMargins(0, 0, 0, 0)
            cols_layout.setSpacing(8)
            for k, v in valid_fields:
                col = QVBoxLayout()
                col.setSpacing(2)
                lbl_f = QLabel(f"<b>{k} :</b>")
                lbl_f.setStyleSheet(f"font-size: 10px; color: {DesignTokens.ACCENT_PRIMARY}; border: none; background: transparent;")
                col.addWidget(lbl_f)
                editor = QTextEdit()
                editor.setPlainText(str(v))
                editor.setMaximumHeight(65)
                editor.setStyleSheet(f"""
                    QTextEdit {{
                        background-color: {DesignTokens.BG_INPUT};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        border-radius: 3px;
                        padding: 4px;
                        font-size: 11px;
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                """)
                self.field_editors[k] = editor
                col.addWidget(editor)
                cols_layout.addLayout(col, 1)
            layout.addLayout(cols_layout)
        else:
            for k, v in valid_fields:
                lbl_f = QLabel(f"<b>{k} :</b>")
                lbl_f.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
                layout.addWidget(lbl_f)
                editor = QTextEdit()
                editor.setPlainText(str(v))
                editor.setMaximumHeight(50)
                editor.setStyleSheet(f"""
                    QTextEdit {{
                        background-color: {DesignTokens.BG_INPUT};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        border-radius: 3px;
                        padding: 4px;
                        font-size: 11px;
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                """)
                self.field_editors[k] = editor
                layout.addWidget(editor)

    def is_selected(self) -> bool:
        return self.chk_include.isChecked()

    def get_card_data(self) -> dict[str, Any]:
        res = dict(self.card_data)
        for k, ed in self.field_editors.items():
            res[k] = ed.toPlainText()
        return res


class InlineDiffCardWidget(QFrame):
    """
    Carte interactive de diff intégrée dans un message de chat.
    Comporte un Garde-Fou humain direct ([ ✅ Appliquer ], [ ❌ Rejeter ], [ 👁️ Inspecteur ]).
    """

    applied = Signal(str)
    rejected = Signal(str)
    reverted = Signal(str)
    open_editor_requested = Signal(int)
    inspect_requested = Signal(dict)

    _active_instances: weakref.WeakSet[InlineDiffCardWidget] = weakref.WeakSet()

    def __init__(self, patch_data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        InlineDiffCardWidget._active_instances.add(self)
        self.patch_data = patch_data
        self.field_widgets: list[FieldDiffWidget] = []
        self.split_widgets: list[SplitCardItemWidget] = []
        self.is_applied: bool = bool(patch_data.get("is_applied", False))
        self.current_view_mode: str = get_saved_diff_view_mode()
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            InlineDiffCardWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_MD}px;
                margin-top: 8px;
                margin-bottom: 4px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # ── 1. En-tête de la proposition ─────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title = self.patch_data.get("title", "Proposition de Modification")
        lbl_title = QLabel(f"<b>🛡️ {html.escape(title)}</b>")
        lbl_title.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        header.addWidget(lbl_title)
        header.addStretch()

        self.status_badge = Badge("🛡️ En attente", variant="status")
        header.addWidget(self.status_badge)
        layout.addLayout(header)

        # ── 2. Bandeau d'explication de l'IA (si fourni) ──────────────────────
        explanation = self.patch_data.get("explanation", "")
        if explanation:
            exp_frame = QFrame()
            exp_frame.setObjectName("ExpBanner")
            exp_frame.setStyleSheet(f"""
                QFrame#ExpBanner {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 4px;
                }}
            """)
            exp_layout = QHBoxLayout(exp_frame)
            exp_layout.setContentsMargins(8, 6, 8, 6)
            exp_layout.setSpacing(8)

            lbl_bulb = QLabel()
            lbl_bulb.setPixmap(load_phosphor_icon("ph.lightbulb-filament", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
            lbl_bulb.setStyleSheet("border: none; background: transparent;")
            exp_layout.addWidget(lbl_bulb)

            lbl_exp = QLabel(f"<b>Intention de l'IA :</b> {html.escape(explanation)}")
            lbl_exp.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
            lbl_exp.setWordWrap(True)
            exp_layout.addWidget(lbl_exp, 1)
            layout.addWidget(exp_frame)

        # ── 3. Barre de Sélection de Mode (Unifié vs Côte à Côte) ────────────
        mode_control_layout = QHBoxLayout()
        mode_control_layout.setContentsMargins(0, 2, 0, 4)
        mode_control_layout.setSpacing(6)

        lbl_view_mode = QLabel("Vue :")
        lbl_view_mode.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-weight: 500; border: none; background: transparent;")
        mode_control_layout.addWidget(lbl_view_mode)

        btn_mode_style = f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 500;
                padding: 3px 10px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton[active="true"] {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: #ffffff;
                font-weight: 600;
            }}
        """

        self.btn_view_unified = QPushButton("📑 Vue Unifiée")
        self.btn_view_unified.setFixedHeight(24)
        self.btn_view_unified.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_unified.setStyleSheet(btn_mode_style)
        self.btn_view_unified.clicked.connect(lambda: self.set_view_mode("unified"))

        self.btn_view_split = QPushButton("⫴ Vue Côte à côte")
        self.btn_view_split.setFixedHeight(24)
        self.btn_view_split.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_split.setStyleSheet(btn_mode_style)
        self.btn_view_split.clicked.connect(lambda: self.set_view_mode("split"))

        mode_control_layout.addWidget(self.btn_view_unified)
        mode_control_layout.addWidget(self.btn_view_split)
        mode_control_layout.addStretch()
        layout.addLayout(mode_control_layout)

        # ── 4. Corps : Champs Comparés ou Scission ───────────────────────────
        p_type = self.patch_data.get("type", "card")
        orig = self.patch_data.get("original", {})
        mod = self.patch_data.get("modified", {})

        note_id = self.patch_data.get("note_id") or self.patch_data.get("metadata", {}).get("note_id")

        # Vérifier si la carte est déjà appliquée en BDD (purgeant tout cache ou artefact résiduel)
        if note_id and not self.is_applied:
            try:
                note_rec = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note_rec:
                    act_v = note_rec.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                    if act_v and act_v.content:
                        db_content = json.loads(act_v.content) if isinstance(act_v.content, str) else act_v.content
                        if not orig:
                            # Charger l'ancienne version si disponible
                            prev_v = note_rec.versions.where(NoteVersionModel.version_number < act_v.version_number).order_by(NoteVersionModel.version_number.desc()).first()
                            orig = json.loads(prev_v.content) if prev_v and prev_v.content else dict(db_content)

                        # Détecter si la note en BDD a déjà la valeur de la proposition modifiée
                        if (
                            isinstance(mod, dict)
                            and isinstance(db_content, dict)
                            and all(str(db_content.get(k, "")).strip() == str(v).strip() for k, v in mod.items() if str(k).lower() not in ["id", "note_id"])
                        ):
                            self.is_applied = True
            except Exception as e:
                logger.debug("Vérification BDD diff note #%s: %s", note_id, e)

        if self.is_applied:
            self.status_badge.setText("✅ Appliqué en BDD")

        if p_type == "split" and isinstance(mod, list):
            # Mode Scission : affichage de chaque carte atomique fille
            lbl_split_intro = QLabel(f"Cette note est scindée en {len(mod)} cartes atomiques. Vous pouvez ajuster ou décocher :")
            lbl_split_intro.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
            layout.addWidget(lbl_split_intro)

            for idx, c_data in enumerate(mod):
                if isinstance(c_data, dict):
                    sc_widget = SplitCardItemWidget(idx, c_data, parent=self)
                    self.split_widgets.append(sc_widget)
                    layout.addWidget(sc_widget)

        elif p_type == "card" and isinstance(mod, dict):
            # Mode Carte : affichage comparatif par champ avec word-diff et direct edit
            all_keys: list[str] = []
            if isinstance(orig, dict):
                for k in orig:
                    if k not in all_keys and str(k).lower() not in ["id", "note_id"]:
                        all_keys.append(k)
            for k in mod:
                if k not in all_keys and str(k).lower() not in ["id", "note_id"]:
                    all_keys.append(k)

            if not all_keys:
                all_keys = ["Front", "Back"]

            for field_key in all_keys:
                o_val = str(orig.get(field_key, "")) if isinstance(orig, dict) else ""
                m_val = str(mod.get(field_key, "")) if isinstance(mod, dict) else ""
                fw = FieldDiffWidget(field_key, o_val, m_val, is_applied=self.is_applied, parent=self)
                self.field_widgets.append(fw)
                layout.addWidget(fw)

        else:
            # Fallback : Vue texte / CSS
            self.diff_view = QTextBrowser()
            self.diff_view.setMaximumHeight(160)
            self.diff_view.setStyleSheet(f"""
                QTextBrowser {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 6px;
                    font-family: {DesignTokens.FONT_CODE};
                    font-size: 11px;
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
            """)
            raw_text = str(mod) if not isinstance(mod, dict | list) else json.dumps(mod, ensure_ascii=False, indent=2)
            self.diff_view.setPlainText(raw_text)
            layout.addWidget(self.diff_view)

        # ── 4. Boutons d'Action Directs ──────────────────────────────────────
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)

        self.btn_apply = PrimaryButton("Appliquer")
        self.btn_apply.setFixedHeight(26)
        self.btn_apply.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        actions_layout.addWidget(self.btn_apply)

        self.btn_reject = SecondaryButton("Rejeter")
        self.btn_reject.setFixedHeight(26)
        self.btn_reject.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.COLOR_RED))
        self.btn_reject.clicked.connect(self._on_reject_clicked)
        actions_layout.addWidget(self.btn_reject)

        self.btn_open_editor = QPushButton("Ouvrir dans l'Éditeur ↗")
        self.btn_open_editor.setFixedHeight(26)
        self.btn_open_editor.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_editor.setToolTip("Naviguer vers cette carte dans l'onglet Édition")
        self.btn_open_editor.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 3px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.btn_open_editor.clicked.connect(self._on_open_editor_clicked)
        actions_layout.addWidget(self.btn_open_editor)

        # Alias pour compatibilité ascendante
        self.btn_inspect = self.btn_open_editor

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        if self.is_applied:
            self.btn_apply.setText("Annuler (Revert)")
            self.btn_apply.setIcon(load_phosphor_icon("ph.arrow-u-up-left", color=DesignTokens.COLOR_YELLOW))
            try:
                self.btn_apply.clicked.disconnect()
            except Exception:
                pass
            self.btn_apply.clicked.connect(self._on_revert_clicked)
            self.btn_reject.setEnabled(False)

        self.set_view_mode(self.current_view_mode, propagate=False)

    def set_view_mode(self, mode: str, propagate: bool = True) -> None:
        """Bascule tous les champs entre la Vue Unifiée et la Vue Côte à côte et mémorise le choix."""
        self.current_view_mode = mode
        if propagate:
            save_saved_diff_view_mode(mode)
            for card in list(InlineDiffCardWidget._active_instances):
                if card is not self and card.current_view_mode != mode:
                    card.set_view_mode(mode, propagate=False)

        is_unified = mode == "unified"
        self.btn_view_unified.setProperty("active", is_unified)
        self.btn_view_split.setProperty("active", not is_unified)
        self.btn_view_unified.style().unpolish(self.btn_view_unified)
        self.btn_view_unified.style().polish(self.btn_view_unified)
        self.btn_view_split.style().unpolish(self.btn_view_split)
        self.btn_view_split.style().polish(self.btn_view_split)

        for fw in self.field_widgets:
            fw.set_view_mode(mode)

    @Slot()
    def _on_apply_clicked(self) -> None:
        """Applique la modification en base de données en tenant compte des retouches faites en direct."""
        p_type = self.patch_data.get("type", "card")
        metadata = self.patch_data.get("metadata", {})
        note_id = self.patch_data.get("note_id") or metadata.get("note_id")

        try:
            if p_type == "css":
                model_name = metadata.get("note_type_name", "")
                snippet = metadata.get("snippet", str(self.patch_data.get("modified", "")))
                nt = NoteTypeModel.get_or_none(NoteTypeModel.name == model_name) if model_name else NoteTypeModel.select().first()
                if nt:
                    with db.atomic():
                        nt.css_style = (nt.css_style or "") + f"\n\n/* Appliqué depuis le Chat */\n{snippet}"
                        nt.save()
                    self.status_badge.setText("✅ Appliqué en BDD")
                    self.btn_apply.setEnabled(False)
                    self.btn_reject.setEnabled(False)
                    self.applied.emit(f"CSS validé pour {nt.name}")
                    show_toast(self, f"Style CSS appliqué sur '{nt.name}' !")

            elif p_type == "card" and note_id:
                # Récupérer les valeurs effectives des champs (potentiellement retouchées par l'utilisateur)
                final_modified: dict[str, Any] = {}
                if self.field_widgets:
                    for fw in self.field_widgets:
                        final_modified[fw.field_name] = fw.get_current_value()
                else:
                    raw_mod = self.patch_data.get("modified", {})
                    final_modified = raw_mod if isinstance(raw_mod, dict) else {"Front": str(raw_mod)}

                note = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note:
                    with db.atomic():
                        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                        if active_v:
                            active_v.is_active = False
                            active_v.save()
                        new_v_num = (note.versions.select(fn.MAX(NoteVersionModel.version_number)).scalar() or 1) + 1
                        NoteVersionModel.create(
                            note=note,
                            version_number=new_v_num,
                            content=json.dumps(final_modified, ensure_ascii=False),
                            source="consultant_inline",
                            is_active=True,
                        )
                    self.is_applied = True
                    self.patch_data["is_applied"] = True
                    self.status_badge.setText("✅ Appliqué en BDD")
                    self.btn_apply.setText("Annuler (Revert)")
                    self.btn_apply.setIcon(load_phosphor_icon("ph.arrow-u-up-left", color=DesignTokens.COLOR_YELLOW))
                    try:
                        self.btn_apply.clicked.disconnect()
                    except Exception:
                        pass
                    self.btn_apply.clicked.connect(self._on_revert_clicked)
                    self.btn_reject.setEnabled(False)

                    # Basculer tous les champs en unification totale propre sans ratures
                    for fw in self.field_widgets:
                        fw.set_applied(True)

                    # Sauvegarder l'état appliqué dans ConsultantMessageModel pour les prochaines sessions
                    try:
                        from ankiforge.database.models import ConsultantMessageModel

                        db_msgs = ConsultantMessageModel.select().where(ConsultantMessageModel.staged_diffs_json.is_null(False)).order_by(ConsultantMessageModel.id.desc()).limit(10)
                        for m in db_msgs:
                            if m.staged_diffs_json and str(note.id) in m.staged_diffs_json:
                                st = json.loads(m.staged_diffs_json)
                                st["is_applied"] = True
                                m.staged_diffs_json = json.dumps(st, ensure_ascii=False)
                                m.save()
                                break
                    except Exception as ex_db:
                        logger.debug("Mise à jour staged_diffs_json BDD : %s", ex_db)

                    self.applied.emit(f"Note #{note.id} refactorisée")
                    show_toast(self, f"Note #{note.id} mise à jour en BDD (version {new_v_num}) !")

            elif p_type == "split" and note_id:
                # Récupérer les cartes cochées par l'utilisateur
                cards_to_apply: list[dict[str, Any]] = []
                if self.split_widgets:
                    for sw in self.split_widgets:
                        if sw.is_selected():
                            cards_to_apply.append(sw.get_card_data())
                else:
                    cards_list = self.patch_data.get("modified", [])
                    cards_to_apply = cards_list if isinstance(cards_list, list) else []

                note = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note and cards_to_apply:
                    card_rel = note.cards.first()
                    target_deck = card_rel.deck if card_rel else DeckModel.select().first()
                    with db.atomic():
                        for c_data in cards_to_apply:
                            new_note = NoteModel.create(
                                guid=str(uuid.uuid4())[:12],
                                note_type=note.note_type,
                                tags=note.tags,
                                status="pending",
                            )
                            NoteVersionModel.create(
                                note=new_note,
                                version_number=1,
                                content=json.dumps(c_data, ensure_ascii=False),
                                source="consultant_split_inline",
                                is_active=True,
                            )
                            if target_deck:
                                CardModel.create(note=new_note, deck=target_deck, template_index=0)
                        note.status = "archived"
                        note.save()
                    self.status_badge.setText("✅ Appliqué en BDD")
                    self.btn_apply.setEnabled(False)
                    self.btn_reject.setEnabled(False)
                    self.applied.emit(f"Note #{note.id} scindée en {len(cards_to_apply)} cartes")
                    show_toast(self, f"Note #{note.id} scindée en {len(cards_to_apply)} cartes atomiques !")

        except Exception as e:
            logger.error("Erreur application inline diff : %s", e)
            show_toast(self, f"Erreur d'application : {e}", is_error=True)

    @Slot()
    def _on_revert_clicked(self) -> None:
        """Annule l'application du patch et restaure la version précédente en BDD."""
        p_type = self.patch_data.get("type", "card")
        orig = self.patch_data.get("original", {})
        metadata = self.patch_data.get("metadata", {})
        note_id = self.patch_data.get("note_id") or metadata.get("note_id")

        try:
            if p_type == "card" and note_id:
                note = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note:
                    with db.atomic():
                        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                        if active_v:
                            active_v.is_active = False
                            active_v.save()
                        new_v_num = (note.versions.select(fn.MAX(NoteVersionModel.version_number)).scalar() or 1) + 1
                        NoteVersionModel.create(
                            note=note,
                            version_number=new_v_num,
                            content=json.dumps(orig, ensure_ascii=False) if isinstance(orig, dict | list) else str(orig),
                            source="consultant_revert",
                            is_active=True,
                        )
            self.is_applied = False
            self.patch_data["is_applied"] = False
            for fw in self.field_widgets:
                fw.set_applied(False)
            self.status_badge.setText("↩️ Annulé")
            self.btn_apply.setText("Appliquer")
            self.btn_apply.setIcon(load_phosphor_icon("ph.check", color="white"))
            try:
                self.btn_apply.clicked.disconnect()
            except Exception:
                pass
            self.btn_apply.clicked.connect(self._on_apply_clicked)
            self.btn_reject.setEnabled(True)
            self.reverted.emit(f"Modification de la note #{note_id} annulée")
            show_toast(self, "Modification annulée avec succès !")
        except Exception as e:
            logger.error("Erreur lors de l'annulation du patch : %s", e)
            show_toast(self, f"Erreur d'annulation : {e}", is_error=True)

    @Slot()
    def _on_reject_clicked(self) -> None:
        """Rejette la proposition inline."""
        self.status_badge.setText("❌ Rejeté")
        self.btn_apply.setEnabled(False)
        self.btn_reject.setEnabled(False)
        self.rejected.emit("Proposition inline rejetée")
        show_toast(self, "Proposition rejetée.")

    @Slot()
    def _on_open_editor_clicked(self) -> None:
        """Déclenche la navigation vers l'onglet Édition pour la note concernée."""
        metadata = self.patch_data.get("metadata", {})
        note_id = self.patch_data.get("note_id") or metadata.get("note_id")
        if note_id:
            try:
                nid = int(note_id)
                self.open_editor_requested.emit(nid)
                self.inspect_requested.emit(self.patch_data)
                return
            except (ValueError, TypeError):
                pass
        show_toast(self, "Identifiant de note indisponible pour l'ouverture dans l'Éditeur.", is_error=True)

    @Slot()
    def _on_inspect_clicked(self) -> None:
        """Transmet la proposition ou navigue vers l'Éditeur."""
        self._on_open_editor_clicked()

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
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel, StagedPatchModel
from ankiforge.services.ai.consultant_engine import robust_json_loads
from ankiforge.services.ai.staged_patch_registry import staged_payload_of
from ankiforge.ui.components import Badge, IconButton, SecondaryButton, StyledComboBox
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def evaluate_wozniak_card(card_fields: dict[str, Any]) -> tuple[bool, int, list[str]]:
    """Évalue l'atomicité et la conformité d'une carte aux règles de formulation de Wozniak.

    Args:
        card_fields: Dictionnaire des champs de la carte (Front/Back, etc.).

    Returns:
        tuple (est_conforme, score_qualite, liste_anomalies)
    """
    front = str(card_fields.get("Front") or card_fields.get("Recto") or card_fields.get("question") or "")
    back = str(card_fields.get("Back") or card_fields.get("Verso") or card_fields.get("reponse") or "")

    issues: list[str] = []
    score = 100

    front_words = len(front.split())
    back_words = len(back.split())

    if front_words > 25:
        issues.append(tr("Règle #4 (Atomicité) : Question trop verbeuse (%1 mots > 25).", front_words))
        score -= 25
    if back_words > 35:
        issues.append(tr("Règle #4 (Atomicité) : Réponse trop verbeuse (%1 mots > 35).", back_words))
        score -= 30
    if any(pattern in back for pattern in ("\n-", "\n*", "<ul", "<ol")):
        issues.append(tr("Règle #4 (Minimum Information) : Présence d'une liste dans la réponse."))
        score -= 20
    if front.strip() and back.strip() and front.strip().lower() == back.strip().lower():
        issues.append(tr("Règle #6 (Clarté) : Question et réponse identiques."))
        score -= 40

    is_compliant = len(issues) == 0
    return is_compliant, max(0, score), issues


def compute_field_word_diff_html(original: str, modified: str) -> str:
    """Calcule un diff mot-à-mot intra-ligne avec suppressions rouges barrées et ajouts verts.

    Args:
        original: Texte de la base de données.
        modified: Texte proposé par l'agent.

    Returns:
        Chaîne HTML sécurisée avec balises span stylisées.
    """
    if not original and not modified:
        return f"<span style='color: {DesignTokens.TEXT_MUTED}; font-style: italic;'>{tr('Vide')}</span>"

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
        self.lbl_words = QLabel(tr("%1 → %2 mots", orig_words, mod_words))
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
        left_layout.setContentsMargins(8, 6, 8, 6)
        left_layout.setSpacing(4)

        left_header = QHBoxLayout()
        left_header.setContentsMargins(0, 0, 0, 0)
        left_header.setSpacing(6)

        left_icon = QLabel()
        left_icon.setPixmap(load_phosphor_icon("ph.database", color=DesignTokens.COLOR_RED).pixmap(14, 14))
        left_header.addWidget(left_icon)

        lbl_left = QLabel(tr("Base active (BDD)"))
        lbl_left.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 600;
            color: {DesignTokens.COLOR_RED};
            border: none;
            background: transparent;
        """)
        left_header.addWidget(lbl_left)
        left_header.addStretch()
        left_layout.addLayout(left_header)

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
        right_layout.setContentsMargins(8, 6, 8, 6)
        right_layout.setSpacing(4)

        right_header = QHBoxLayout()
        right_header.setContentsMargins(0, 0, 0, 0)
        right_header.setSpacing(6)

        right_icon = QLabel()
        right_icon.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
        right_header.addWidget(right_icon)

        lbl_right = QLabel(tr("Proposition Agent MCP (Éditable)"))
        lbl_right.setStyleSheet(f"""
            font-size: 10px;
            font-weight: 600;
            color: {DesignTokens.COLOR_GREEN};
            border: none;
            background: transparent;
        """)
        right_header.addWidget(lbl_right)
        right_header.addStretch()
        right_layout.addLayout(right_header)

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
        self.lbl_words.setText(tr("%1 → %2 mots", orig_words, mod_words))

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
        self._model_data: dict[str, Any] = {}
        self._migration_data: dict[str, Any] = {}
        self._css_data: dict[str, Any] = {}
        self._original_tags: list[str] = []
        self._modified_tags: list[str] = []
        self._tags_row: FieldSemanticDiffRow | None = None
        self._create_template_editors: list[tuple[QLineEdit, QPlainTextEdit, QPlainTextEdit]] = []
        self._mapping_combos: dict[str, StyledComboBox] = {}
        self._batch_view: BatchNoteCreateView | None = None

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

        self.diff_stack = QStackedWidget()

        # --- Page 0 : Diff de cartes / scissions / créations de notes ---
        self.card_diff_page = QWidget()
        card_page_layout = QVBoxLayout(self.card_diff_page)
        card_page_layout.setContentsMargins(0, 0, 0, 0)
        card_page_layout.setSpacing(6)

        # Barre supérieure pour sélection de scission (visible uniquement si split)
        self.split_bar = QWidget()
        split_layout = QHBoxLayout(self.split_bar)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(8)

        split_icon = QLabel()
        split_icon.setPixmap(load_phosphor_icon("ph.arrows-split", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        split_layout.addWidget(split_icon)

        lbl_split = QLabel(tr("Carte atomique :"))
        lbl_split.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY};")
        split_layout.addWidget(lbl_split)

        self.split_selector = StyledComboBox()
        self.split_selector.currentIndexChanged.connect(self._on_split_card_selected)
        split_layout.addWidget(self.split_selector, 1)

        self.wozniak_badge = Badge(tr("Conforme Wozniak (Atomicité R4/R5)"), variant="success")
        split_layout.addWidget(self.wozniak_badge)

        split_layout.addStretch()

        self.split_bar.hide()
        card_page_layout.addWidget(self.split_bar)

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
        card_page_layout.addWidget(self.scroll_area, 1)

        self.diff_stack.addWidget(self.card_diff_page)

        # --- Page 1 : Diff de modèles de note (création, migration, refactor, css) ---
        self.model_diff_page = QWidget()
        model_page_layout = QVBoxLayout(self.model_diff_page)
        model_page_layout.setContentsMargins(0, 0, 0, 0)
        model_page_layout.setSpacing(6)

        self.model_scroll_area = QScrollArea()
        self.model_scroll_area.setWidgetResizable(True)
        self.model_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.model_scroll_area.setStyleSheet("background-color: transparent;")

        self.model_scroll_content = QWidget()
        self.model_layout = QVBoxLayout(self.model_scroll_content)
        self.model_layout.setContentsMargins(0, 0, 0, 0)
        self.model_layout.setSpacing(10)

        self.model_scroll_area.setWidget(self.model_scroll_content)
        model_page_layout.addWidget(self.model_scroll_area, 1)

        self.diff_stack.addWidget(self.model_diff_page)

        diff_tab_layout.addWidget(self.diff_stack, 1)

        self.tab_widget.addTab(self.diff_tab, load_phosphor_icon("ph.columns", color=DesignTokens.TEXT_SECONDARY), tr("Comparaison champ par champ"))

        # ── 2. Onglet Aperçu Comparatif Anki (Dédoublé) ───────
        self.preview_tab = QWidget()
        preview_layout = QVBoxLayout(self.preview_tab)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(6)

        # Barre supérieure de commandes partagée
        self.preview_toolbar = QFrame()
        self.preview_toolbar.setObjectName("preview_toolbar")
        self.preview_toolbar.setStyleSheet(f"""
            QFrame#preview_toolbar {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
            }}
        """)
        toolbar_layout = QHBoxLayout(self.preview_toolbar)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(8)

        icon_toolbar = QLabel()
        icon_toolbar.setPixmap(load_phosphor_icon("ph.columns", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        toolbar_layout.addWidget(icon_toolbar)

        lbl_toolbar = QLabel(tr("Aperçu dédoublé"))
        lbl_toolbar.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            color: {DesignTokens.TEXT_MUTED};
            text-transform: uppercase;
            letter-spacing: 0.5px;
        """)
        toolbar_layout.addWidget(lbl_toolbar)

        # Sélecteur partagé de gabarit multi-cartes
        self.shared_card_selector = StyledComboBox()
        self.shared_card_selector.setMinimumWidth(120)
        self.shared_card_selector.setFixedHeight(26)
        self.shared_card_selector.currentIndexChanged.connect(self._on_shared_card_selected)
        self.shared_card_selector.hide()
        toolbar_layout.addWidget(self.shared_card_selector)

        toolbar_layout.addStretch()

        # Sélecteur d'appareil partagé
        device_container = QWidget()
        device_layout = QHBoxLayout(device_container)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(2)

        self._shared_device_mode = "desktop"
        self.btn_device_desktop = IconButton("monitor", tooltip=tr("Mode Bureau (100% largeur)"), size=24)
        self.btn_device_desktop.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px;")
        self.btn_device_desktop.clicked.connect(lambda: self._on_shared_device_mode("desktop"))

        self.btn_device_tablet = IconButton("ph.device-tablet", tooltip=tr("Mode Tablette (768px)"), size=24)
        self.btn_device_tablet.setStyleSheet("background-color: transparent; border-radius: 4px;")
        self.btn_device_tablet.clicked.connect(lambda: self._on_shared_device_mode("tablet"))

        self.btn_device_mobile = IconButton("ph.device-mobile", tooltip=tr("Mode Mobile (375px)"), size=24)
        self.btn_device_mobile.setStyleSheet("background-color: transparent; border-radius: 4px;")
        self.btn_device_mobile.clicked.connect(lambda: self._on_shared_device_mode("mobile"))

        device_layout.addWidget(self.btn_device_desktop)
        device_layout.addWidget(self.btn_device_tablet)
        device_layout.addWidget(self.btn_device_mobile)
        toolbar_layout.addWidget(device_container)

        # Bascule de thème partagée
        self.btn_shared_theme = IconButton("ph.sun", tooltip=tr("Basculer le thème"), size=24)
        self.btn_shared_theme.clicked.connect(self._on_shared_toggle_theme)
        toolbar_layout.addWidget(self.btn_shared_theme)

        # Bascule Recto/Verso partagée
        self.btn_shared_toggle_side = SecondaryButton(tr("Voir Verso"))
        self.btn_shared_toggle_side.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_shared_toggle_side.setFixedHeight(28)
        self.btn_shared_toggle_side.setStyleSheet("""
            QPushButton {
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_shared_toggle_side.clicked.connect(self._on_shared_toggle_side)
        toolbar_layout.addWidget(self.btn_shared_toggle_side)

        preview_layout.addWidget(self.preview_toolbar)

        # Splitter horizontal pour les deux cartes côte-à-côte
        self.preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.preview_splitter.setChildrenCollapsible(False)

        # --- Panneau Gauche : Carte Originale (BDD) ---
        self.orig_card_frame = QFrame()
        self.orig_card_frame.setObjectName("orig_card_frame")
        self.orig_card_frame.setStyleSheet(f"""
            QFrame#orig_card_frame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        orig_card_layout = QVBoxLayout(self.orig_card_frame)
        orig_card_layout.setContentsMargins(0, 0, 0, 0)
        orig_card_layout.setSpacing(0)

        orig_header = QFrame()
        orig_header.setObjectName("orig_preview_header")
        orig_header.setStyleSheet(f"""
            QFrame#orig_preview_header {{
                background-color: {DesignTokens.BG_INPUT};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-top-left-radius: {DesignTokens.RADIUS_SM}px;
                border-top-right-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        orig_header_layout = QHBoxLayout(orig_header)
        orig_header_layout.setContentsMargins(8, 6, 8, 6)
        orig_header_layout.setSpacing(6)

        orig_icon = QLabel()
        orig_icon.setPixmap(load_phosphor_icon("ph.database", color=DesignTokens.COLOR_RED).pixmap(14, 14))
        orig_header_layout.addWidget(orig_icon)

        orig_badge = Badge(tr("Originale (BDD)"), variant="neutral")
        orig_header_layout.addWidget(orig_badge)

        self.lbl_orig_preview_words = QLabel()
        self.lbl_orig_preview_words.setStyleSheet(f"""
            font-size: 10px;
            color: {DesignTokens.TEXT_MUTED};
            font-family: {DesignTokens.FONT_CODE};
        """)
        orig_header_layout.addWidget(self.lbl_orig_preview_words)
        orig_header_layout.addStretch()

        orig_card_layout.addWidget(orig_header)

        self.preview_orig = CardPreviewWidget(parent=self.orig_card_frame, show_header=False)
        self.preview_orig.controls_container.hide()
        orig_card_layout.addWidget(self.preview_orig, 1)

        self.preview_splitter.addWidget(self.orig_card_frame)

        # --- Panneau Droit : Carte Proposée (Agent MCP) ---
        self.mod_card_frame = QFrame()
        self.mod_card_frame.setObjectName("mod_card_frame")
        self.mod_card_frame.setStyleSheet(f"""
            QFrame#mod_card_frame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        mod_card_layout = QVBoxLayout(self.mod_card_frame)
        mod_card_layout.setContentsMargins(0, 0, 0, 0)
        mod_card_layout.setSpacing(0)

        mod_header = QFrame()
        mod_header.setObjectName("mod_preview_header")
        mod_header.setStyleSheet(f"""
            QFrame#mod_preview_header {{
                background-color: {DesignTokens.BG_INPUT};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-top-left-radius: {DesignTokens.RADIUS_SM}px;
                border-top-right-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        mod_header_layout = QHBoxLayout(mod_header)
        mod_header_layout.setContentsMargins(8, 6, 8, 6)
        mod_header_layout.setSpacing(6)

        mod_icon = QLabel()
        mod_icon.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
        mod_header_layout.addWidget(mod_icon)

        mod_badge = Badge(tr("Proposée (Agent MCP)"), variant="success")
        mod_header_layout.addWidget(mod_badge)

        self.lbl_mod_preview_words = QLabel()
        self.lbl_mod_preview_words.setStyleSheet(f"""
            font-size: 10px;
            color: {DesignTokens.TEXT_MUTED};
            font-family: {DesignTokens.FONT_CODE};
        """)
        mod_header_layout.addWidget(self.lbl_mod_preview_words)
        mod_header_layout.addStretch()

        mod_card_layout.addWidget(mod_header)

        self.preview_mod = CardPreviewWidget(parent=self.mod_card_frame, show_header=False)
        self.preview_mod.controls_container.hide()
        mod_card_layout.addWidget(self.preview_mod, 1)

        # Rétrocompatibilité : self.preview_widget pointe vers la carte modifiée
        self.preview_widget = self.preview_mod

        self.preview_splitter.addWidget(self.mod_card_frame)
        self.preview_splitter.setSizes([500, 500])

        preview_layout.addWidget(self.preview_splitter, 1)

        self.tab_widget.addTab(self.preview_tab, load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_SECONDARY), tr("Aperçu Anki Dédoublé"))
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tab_widget)

    def set_diff(
        self,
        original: dict[str, Any] | str,
        modified: dict[str, Any] | list[dict[str, Any]] | str,
        note_type: NoteTypeModel | None = None,
        is_applied: bool = False,
        patch_type: str = "card",
        original_tags: list[str] | str | None = None,
        modified_tags: list[str] | str | None = None,
    ) -> None:
        """Injecte les données d'origine et modifiées à comparer."""
        self._note_type = note_type
        self._is_applied = is_applied
        self._patch_type = patch_type.lower().strip()

        if isinstance(original_tags, list):
            self._original_tags = [str(t) for t in original_tags if str(t).strip()]
        elif isinstance(original_tags, str):
            self._original_tags = [t for t in original_tags.split() if t]
        else:
            self._original_tags = []

        if isinstance(modified_tags, list):
            self._modified_tags = [str(t) for t in modified_tags if str(t).strip()]
        elif isinstance(modified_tags, str):
            self._modified_tags = [t for t in modified_tags.split() if t]
        else:
            self._modified_tags = []

        if hasattr(self, "diff_stack"):
            self.diff_stack.setCurrentIndex(0)
        self.tab_widget.setTabText(0, tr("Comparaison champ par champ"))

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
            self._split_cards = [dict(c) for c in self._modified if isinstance(c, dict)]
            self._active_split_index = 0
            self.split_selector.blockSignals(True)
            self.split_selector.clear()
            for idx in range(len(self._split_cards)):
                self.split_selector.addItem(tr("Carte atomique %1 sur %2", idx + 1, len(self._split_cards)))
            self.split_selector.blockSignals(False)
            self.split_bar.show()
            self._update_wozniak_badge()
            if self._split_cards:
                self._populate_fields(self._split_cards[0])
        else:
            self.split_bar.hide()
            self._split_cards = []
            curr_mod = self._modified if isinstance(self._modified, dict) else {}
            self._populate_fields(curr_mod)

        self._refresh_preview()

    def set_model_diff(
        self,
        p_type: str,
        payload: dict[str, Any],
        target_id: int = 0,
        is_applied: bool = False,
    ) -> None:
        """Configure l'affichage pour une mutation de modèle de note ou de feuille CSS."""
        self._patch_type = p_type
        self._is_applied = is_applied

        if hasattr(self, "diff_stack"):
            self.diff_stack.setCurrentIndex(1)
        self.tab_widget.setTabText(0, tr("Diff Modèle de Note"))

        while self.model_layout.count() > 0:
            item = self.model_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if p_type == "note_type_create":
            self._setup_note_type_create_view(payload)
        elif p_type == "note_type_change":
            self._setup_note_type_change_view(payload)
        elif p_type in ("model", "note_type"):
            self._setup_model_refactor_view(payload, target_id=target_id)
        elif p_type in ("css", "css_tune"):
            self._setup_css_tune_view(payload, target_id=target_id)

        self.model_layout.addStretch()
        self._refresh_preview()

    def _setup_batch_note_create_view(self, payload: dict[str, Any]) -> None:
        if hasattr(self, "diff_stack"):
            self.diff_stack.setCurrentIndex(1)
        if hasattr(self, "tab_widget"):
            self.tab_widget.setTabText(0, tr("Lot de création"))
        while hasattr(self, "model_layout") and self.model_layout.count() > 0:
            item = self.model_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if self._batch_view is None:
            self._batch_view = BatchNoteCreateView()
        if hasattr(self._batch_view, "set_payload"):
            self._batch_view.set_payload(payload)
        if hasattr(self, "model_layout"):
            self.model_layout.addWidget(self._batch_view)
            self.model_layout.addStretch()
        try:
            self._refresh_preview()
        except Exception:
            pass

    def set_patch(self, patch: StagedPatchModel | dict[str, Any]) -> None:
        """Extrait automatiquement les composantes d'un patch staged et configure le visualiseur."""
        if isinstance(patch, StagedPatchModel):
            p_type = patch.patch_type
            is_applied = patch.status == "applied"
            payload = staged_payload_of(patch)
            target_id = patch.target_id
        else:
            p_type = patch.get("patch_type") or patch.get("type", "card")
            is_applied = patch.get("status") == "applied"
            raw_pl = patch.get("diff_payload") or patch
            if isinstance(raw_pl, str):
                try:
                    payload = robust_json_loads(raw_pl)
                except Exception:
                    payload = {}
            elif isinstance(raw_pl, dict):
                payload = raw_pl
            else:
                payload = {}
            target_id = patch.get("target_id") or payload.get("note_id") or 0

        p_type = str(p_type).lower().strip()
        self._patch_type = p_type
        self._is_applied = is_applied

        # 1. Type Modèle de Note / CSS / Migration
        if p_type in ("note_type_create", "note_type_change", "model", "note_type", "css", "css_tune"):
            self.set_model_diff(p_type=p_type, payload=payload, target_id=target_id, is_applied=is_applied)
            return

        # 2b. Lot de création de notes
        if p_type == "batch_note_create":
            self._patch_type = p_type
            self._is_applied = is_applied
            self._setup_batch_note_create_view(payload)
            return

        # 2. Type Carte / Scission / Création unitaire ou par lot
        orig = payload.get("original", {})
        mod = payload.get("modified") or payload.get("new_cards") or payload.get("cards") or {}
        if not mod and "fields" in payload:
            mod = payload["fields"]

        # Résolution du modèle de note
        note_type = None
        nt_name = payload.get("model_name") or payload.get("note_type_name")
        if nt_name:
            note_type = NoteTypeModel.get_or_none(NoteTypeModel.name == str(nt_name).strip())

        if not note_type and target_id:
            target_note = NoteModel.get_or_none(NoteModel.id == target_id)
            if target_note:
                note_type = target_note.note_type
                if not orig:
                    active_v = target_note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                    if active_v and active_v.content:
                        try:
                            orig = robust_json_loads(active_v.content)
                        except Exception:
                            orig = {"Front": active_v.content}

        orig_tags = payload.get("original_tags")
        mod_tags = payload.get("modified_tags")
        self.set_diff(
            original=orig,
            modified=mod,
            note_type=note_type,
            is_applied=is_applied,
            patch_type=p_type,
            original_tags=orig_tags,
            modified_tags=mod_tags,
        )

    def _setup_note_type_create_view(self, payload: dict[str, Any]) -> None:
        """Construit l'interface de révision pour la création d'un type de note."""
        model_data = payload.get("model_data") or (payload.get("modified") if isinstance(payload.get("modified"), dict) and "name" in payload.get("modified", {}) else None) or payload
        name = str(model_data.get("name") or payload.get("name") or "").strip()
        desc = str(model_data.get("description") or payload.get("description") or "").strip()
        fields_schema = model_data.get("fields_schema") or payload.get("fields_schema") or []
        if isinstance(fields_schema, str):
            try:
                fields_schema = json.loads(fields_schema)
            except Exception:
                fields_schema = [fields_schema]
        if not isinstance(fields_schema, list):
            fields_schema = []

        templates = model_data.get("templates") or payload.get("templates") or []
        if isinstance(templates, str):
            try:
                templates = json.loads(templates)
            except Exception:
                templates = []
        if not isinstance(templates, list):
            templates = []

        css_style = str(model_data.get("css_style") or model_data.get("css") or payload.get("css_style") or payload.get("css") or "")
        on_conflict = str(model_data.get("on_conflict") or payload.get("on_conflict") or "error")

        self._model_data = {
            "name": name,
            "description": desc,
            "fields_schema": fields_schema,
            "templates": templates,
            "css_style": css_style,
            "on_conflict": on_conflict,
        }

        # En-tête
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 12px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.plus-circle", color=DesignTokens.COLOR_GREEN).pixmap(18, 18))
        h_layout.addWidget(ico)

        lbl_title = QLabel(tr("Création de type de note — '%1'", name or tr("Sans nom")))
        lbl_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        h_layout.addWidget(lbl_title, 1)

        badge_type = Badge(tr("Nouveau modèle"), variant="success")
        h_layout.addWidget(badge_type)
        self.model_layout.addWidget(header_card)

        # Nom & Description
        info_card = QFrame()
        info_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(6)

        lbl_nm = QLabel(tr("NOM DU MODÈLE"))
        lbl_nm.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        info_layout.addWidget(lbl_nm)

        self.nt_create_name = QLineEdit(name)
        self.nt_create_name.setReadOnly(self._is_applied)
        self.nt_create_name.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 4px 8px;
            }}
        """)
        self.nt_create_name.textChanged.connect(self._on_model_content_changed)
        info_layout.addWidget(self.nt_create_name)

        lbl_ds = QLabel(tr("DESCRIPTION / INSTRUCTIONS POUR L'IA"))
        lbl_ds.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED};")
        info_layout.addWidget(lbl_ds)

        self.nt_create_desc = QPlainTextEdit(desc)
        self.nt_create_desc.setReadOnly(self._is_applied)
        self.nt_create_desc.setMaximumHeight(60)
        self.nt_create_desc.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 4px;
            }}
        """)
        self.nt_create_desc.textChanged.connect(self._on_model_content_changed)
        info_layout.addWidget(self.nt_create_desc)
        self.model_layout.addWidget(info_card)

        # Schéma des champs
        fields_card = QFrame()
        fields_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        fields_layout = QVBoxLayout(fields_card)
        fields_layout.setContentsMargins(10, 8, 10, 8)
        fields_layout.setSpacing(6)

        fields_header = QHBoxLayout()
        lbl_fc = QLabel(tr("CHAMPS DU MODÈLE (UN PAR LIGNE)"))
        lbl_fc.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        fields_header.addWidget(lbl_fc)
        fields_header.addStretch()
        badge_fc = Badge(tr("%1 champs", len(fields_schema)), variant="neutral")
        fields_header.addWidget(badge_fc)
        fields_layout.addLayout(fields_header)

        self.nt_create_fields = QPlainTextEdit("\n".join(str(f) for f in fields_schema))
        self.nt_create_fields.setReadOnly(self._is_applied)
        self.nt_create_fields.setMaximumHeight(90)
        self.nt_create_fields.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.COLOR_GREEN};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                font-weight: 600;
                padding: 6px;
            }}
        """)
        self.nt_create_fields.textChanged.connect(self._on_model_content_changed)
        fields_layout.addWidget(self.nt_create_fields)
        self.model_layout.addWidget(fields_card)

        # Style CSS
        css_card = QFrame()
        css_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        css_layout = QVBoxLayout(css_card)
        css_layout.setContentsMargins(10, 8, 10, 8)
        css_layout.setSpacing(6)

        css_header = QHBoxLayout()
        lbl_css = QLabel(tr("FEUILLE DE STYLE CSS"))
        lbl_css.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        css_header.addWidget(lbl_css)
        css_header.addStretch()
        badge_css = Badge("CSS", variant="info")
        css_header.addWidget(badge_css)
        css_layout.addLayout(css_header)

        self.nt_create_css = QPlainTextEdit(css_style)
        self.nt_create_css.setReadOnly(self._is_applied)
        self.nt_create_css.setMinimumHeight(70)
        self.nt_create_css.setMaximumHeight(120)
        self.nt_create_css.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 6px;
            }}
        """)
        self.nt_create_css.textChanged.connect(self._on_model_content_changed)
        css_layout.addWidget(self.nt_create_css)
        self.model_layout.addWidget(css_card)

        # Gabarits (Templates)
        tmpls_card = QFrame()
        tmpls_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        tmpls_layout = QVBoxLayout(tmpls_card)
        tmpls_layout.setContentsMargins(10, 8, 10, 8)
        tmpls_layout.setSpacing(8)

        tmpls_header = QHBoxLayout()
        lbl_t = QLabel(tr("GABARITS RECTO / VERSO (TEMPLATES)"))
        lbl_t.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        tmpls_header.addWidget(lbl_t)
        tmpls_header.addStretch()
        badge_tmpls = Badge(tr("%1 gabarits", len(templates)), variant="neutral")
        tmpls_header.addWidget(badge_tmpls)
        tmpls_layout.addLayout(tmpls_header)

        self._create_template_editors = []
        for idx, t in enumerate(templates):
            t_box = QFrame()
            t_box.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                }}
            """)
            tb_layout = QVBoxLayout(t_box)
            tb_layout.setContentsMargins(6, 6, 6, 6)
            tb_layout.setSpacing(4)

            t_name = str(t.get("name") if isinstance(t, dict) else tr("Carte %1", idx + 1))
            qfmt = str(t.get("qfmt", "") if isinstance(t, dict) else "")
            afmt = str(t.get("afmt", "") if isinstance(t, dict) else "")

            lbl_tname = QLabel(tr("Nom du gabarit %1 :", idx + 1))
            lbl_tname.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.TEXT_MUTED};")
            tb_layout.addWidget(lbl_tname)

            name_edit = QLineEdit(t_name)
            name_edit.setReadOnly(self._is_applied)
            name_edit.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
            name_edit.textChanged.connect(self._on_model_content_changed)
            tb_layout.addWidget(name_edit)

            cols = QHBoxLayout()
            col_q = QVBoxLayout()
            lbl_q = QLabel(tr("Recto (Front / Question) :"))
            lbl_q.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.COLOR_RED};")
            col_q.addWidget(lbl_q)
            q_edit = QPlainTextEdit(qfmt)
            q_edit.setReadOnly(self._is_applied)
            q_edit.setMaximumHeight(70)
            q_edit.setStyleSheet(
                f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;"
            )
            q_edit.textChanged.connect(self._on_model_content_changed)
            col_q.addWidget(q_edit)
            cols.addLayout(col_q, 1)

            col_a = QVBoxLayout()
            lbl_a = QLabel(tr("Verso (Back / Réponse) :"))
            lbl_a.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.COLOR_GREEN};")
            col_a.addWidget(lbl_a)
            a_edit = QPlainTextEdit(afmt)
            a_edit.setReadOnly(self._is_applied)
            a_edit.setMaximumHeight(70)
            a_edit.setStyleSheet(
                f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;"
            )
            a_edit.textChanged.connect(self._on_model_content_changed)
            col_a.addWidget(a_edit)
            cols.addLayout(col_a, 1)

            tb_layout.addLayout(cols)
            tmpls_layout.addWidget(t_box)
            self._create_template_editors.append((name_edit, q_edit, a_edit))

        self.model_layout.addWidget(tmpls_card)

    def _setup_note_type_change_view(self, payload: dict[str, Any]) -> None:
        """Construit l'interface de révision pour la migration d'un lot de notes vers un autre type."""
        note_ids = payload.get("note_ids") or []
        target_model_name = str(payload.get("target_model") or payload.get("target_model_name") or "")
        target_model_id = payload.get("target_model_id")
        mapping_champs = payload.get("mapping_champs") if isinstance(payload.get("mapping_champs"), dict) else {}
        warnings = payload.get("warnings") or []

        target_nt = (
            NoteTypeModel.get_or_none(NoteTypeModel.name == target_model_name) if target_model_name else (NoteTypeModel.get_or_none(NoteTypeModel.id == target_model_id) if target_model_id else None)
        )
        source_nt: NoteTypeModel | None = None
        if note_ids:
            fn = NoteModel.get_or_none(NoteModel.id == note_ids[0])
            if fn:
                source_nt = fn.note_type

        source_fields: list[str] = []
        if source_nt and source_nt.fields_schema:
            try:
                s_parsed = json.loads(source_nt.fields_schema) if isinstance(source_nt.fields_schema, str) else source_nt.fields_schema
                if isinstance(s_parsed, list):
                    source_fields = [str(f) for f in s_parsed]
            except Exception:
                pass
        if not source_fields and mapping_champs:
            source_fields = list(mapping_champs.keys())
        if not source_fields:
            source_fields = ["Front", "Back"]

        target_fields: list[str] = []
        if target_nt and target_nt.fields_schema:
            try:
                t_parsed = json.loads(target_nt.fields_schema) if isinstance(target_nt.fields_schema, str) else target_nt.fields_schema
                if isinstance(t_parsed, list):
                    target_fields = [str(f) for f in t_parsed]
            except Exception:
                pass
        if not target_fields and mapping_champs:
            target_fields = list(mapping_champs.values())
        if not target_fields:
            target_fields = ["Recto", "Verso"]

        self._migration_data = {
            "note_ids": note_ids,
            "target_model": target_model_name or (target_nt.name if target_nt else ""),
            "target_model_id": target_model_id or (target_nt.id if target_nt else None),
            "mapping_champs": dict(mapping_champs),
            "warnings": warnings,
        }

        # En-tête
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 12px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.arrows-left-right", color=DesignTokens.COLOR_YELLOW).pixmap(18, 18))
        h_layout.addWidget(ico)

        lbl_title = QLabel(tr("Migration vers le type de note '%1'", target_model_name or (target_nt.name if target_nt else "")))
        lbl_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        h_layout.addWidget(lbl_title, 1)

        badge_type = Badge(tr("%1 note(s)", len(note_ids)), variant="warning")
        h_layout.addWidget(badge_type)
        self.model_layout.addWidget(header_card)

        # Modèles Source ➔ Cible
        models_card = QFrame()
        models_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        m_layout = QHBoxLayout(models_card)
        m_layout.setContentsMargins(10, 8, 10, 8)
        m_layout.setSpacing(8)

        s_name = source_nt.name if source_nt else tr("Modèle Source")
        lbl_s = QLabel(tr("Source : %1", s_name))
        lbl_s.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_MUTED};")
        m_layout.addWidget(lbl_s)

        arrow = QLabel(tr("➔"))
        arrow.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY};")
        m_layout.addWidget(arrow)

        t_name = target_model_name or (target_nt.name if target_nt else tr("Modèle Cible"))
        lbl_t = QLabel(tr("Cible : %1", t_name))
        lbl_t.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {DesignTokens.COLOR_GREEN};")
        m_layout.addWidget(lbl_t)
        m_layout.addStretch()

        self.model_layout.addWidget(models_card)

        # Avertissements éventuels
        if warnings:
            warn_card = QFrame()
            warn_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.COLOR_YELLOW_BG};
                    border: 1px solid {DesignTokens.COLOR_YELLOW};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 6px 10px;
                }}
            """)
            w_layout = QVBoxLayout(warn_card)
            w_layout.setContentsMargins(6, 6, 6, 6)
            w_layout.setSpacing(4)
            for w_msg in warnings:
                w_row = QHBoxLayout()
                w_ico = QLabel()
                w_ico.setPixmap(load_phosphor_icon("ph.warning", color=DesignTokens.COLOR_YELLOW).pixmap(14, 14))
                w_row.addWidget(w_ico)
                w_lbl = QLabel(str(w_msg))
                w_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.COLOR_YELLOW}; font-weight: 500;")
                w_row.addWidget(w_lbl, 1)
                w_layout.addLayout(w_row)
            self.model_layout.addWidget(warn_card)

        # Correspondance des champs (Mapping)
        map_card = QFrame()
        map_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        map_layout = QVBoxLayout(map_card)
        map_layout.setContentsMargins(10, 8, 10, 8)
        map_layout.setSpacing(8)

        map_header = QHBoxLayout()
        lbl_m = QLabel(tr("CORRESPONDANCE DES CHAMPS (SOURCE ➔ CIBLE)"))
        lbl_m.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        map_header.addWidget(lbl_m)
        map_header.addStretch()
        map_layout.addLayout(map_header)

        self._mapping_combos = {}
        for sf in source_fields:
            row_frame = QFrame()
            row_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    padding: 4px 8px;
                }}
            """)
            r_layout = QHBoxLayout(row_frame)
            r_layout.setContentsMargins(6, 4, 6, 4)
            r_layout.setSpacing(8)

            lbl_source = QLabel(sf)
            lbl_source.setMinimumWidth(100)
            lbl_source.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
            r_layout.addWidget(lbl_source)

            arr = QLabel(tr("➔"))
            arr.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
            r_layout.addWidget(arr)

            combo = StyledComboBox()
            combo.addItem(tr("(Non mappé / Perte de donnée)"), "")
            for tf in target_fields:
                combo.addItem(tf, tf)

            preselected = mapping_champs.get(sf, "")
            if not preselected and sf in target_fields:
                preselected = sf
            if preselected:
                idx = combo.findData(preselected)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.addItem(preselected, preselected)
                    combo.setCurrentIndex(combo.count() - 1)

            is_mapped = bool(combo.currentData())
            status_b = Badge(tr("Mappé") if is_mapped else tr("Perte de donnée"), variant="success" if is_mapped else "danger")

            def _make_combo_handler(cb: StyledComboBox, b: Badge, src_field: str) -> Callable[[int], None]:
                def _handler(_i: int) -> None:
                    mapped = bool(cb.currentData())
                    b.setText(tr("Mappé") if mapped else tr("Perte de donnée"))
                    b.set_variant("success" if mapped else "danger")
                    self._migration_data["mapping_champs"][src_field] = cb.currentData() or None
                    self._on_model_content_changed()

                return _handler

            combo.currentIndexChanged.connect(_make_combo_handler(combo, status_b, sf))
            r_layout.addWidget(combo, 1)
            r_layout.addWidget(status_b)

            map_layout.addWidget(row_frame)
            self._mapping_combos[sf] = combo

        self.model_layout.addWidget(map_card)

    def _setup_model_refactor_view(self, payload: dict[str, Any], target_id: int = 0) -> None:
        """Construit l'interface pour le refactor / l'évolution d'un modèle de note existant."""
        nt_name = str(payload.get("note_type_name") or payload.get("name") or "").strip()
        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name) if nt_name else (NoteTypeModel.get_or_none(NoteTypeModel.id == target_id) if target_id else None)
        if nt and not nt_name:
            nt_name = nt.name

        orig_dict = payload.get("original") or {}
        if not orig_dict and nt:
            orig_dict = {
                "css_style": nt.css_style or "",
                "fields_schema": json.loads(nt.fields_schema) if nt.fields_schema else [],
                "templates": json.loads(nt.templates) if nt.templates else [],
                "description": nt.description or "",
            }

        mod_dict = payload.get("modified") or {}
        if isinstance(mod_dict, str):
            try:
                mod_dict = json.loads(mod_dict)
            except Exception:
                mod_dict = {"css_style": mod_dict}
        if not isinstance(mod_dict, dict):
            mod_dict = {}

        self._model_data = dict(mod_dict)
        self._note_type = nt

        # En-tête
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 12px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        h_layout.addWidget(ico)

        lbl_title = QLabel(tr("Évolution du modèle de note — '%1'", nt_name or tr("Modèle")))
        lbl_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        h_layout.addWidget(lbl_title, 1)

        badge_type = Badge(tr("Évolution"), variant="info")
        h_layout.addWidget(badge_type)
        self.model_layout.addWidget(header_card)

        # Diff des Champs (Schema)
        orig_fields: list[str] = orig_dict.get("fields_schema") or orig_dict.get("fields") or []
        mod_fields: list[str] = mod_dict.get("fields_schema") or mod_dict.get("fields") or orig_fields
        if isinstance(orig_fields, str):
            try:
                orig_fields = json.loads(orig_fields)
            except Exception:
                orig_fields = []
        if isinstance(mod_fields, str):
            try:
                mod_fields = json.loads(mod_fields)
            except Exception:
                mod_fields = []

        fields_card = QFrame()
        fields_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        f_layout = QVBoxLayout(fields_card)
        f_layout.setContentsMargins(10, 8, 10, 8)
        f_layout.setSpacing(6)

        f_hdr = QHBoxLayout()
        lbl_fh = QLabel(tr("SCHÉMA DES CHAMPS (AVANT ➔ APRÈS)"))
        lbl_fh.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        f_hdr.addWidget(lbl_fh)
        f_hdr.addStretch()

        added_f = [f for f in mod_fields if f not in orig_fields]
        removed_f = [f for f in orig_fields if f not in mod_fields]
        if added_f:
            f_hdr.addWidget(Badge(tr("+ %1", len(added_f)), variant="success"))
        if removed_f:
            f_hdr.addWidget(Badge(tr("- %1", len(removed_f)), variant="danger"))
        f_layout.addLayout(f_hdr)

        self.nt_model_fields = QPlainTextEdit("\n".join(str(f) for f in mod_fields))
        self.nt_model_fields.setReadOnly(self._is_applied)
        self.nt_model_fields.setMaximumHeight(80)
        self.nt_model_fields.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 6px;
            }}
        """)
        self.nt_model_fields.textChanged.connect(self._on_model_content_changed)
        f_layout.addWidget(self.nt_model_fields)
        self.model_layout.addWidget(fields_card)

        # Diff CSS
        orig_css = str(orig_dict.get("css_style") or orig_dict.get("css") or "")
        mod_css = str(mod_dict.get("css_style") or mod_dict.get("css") or orig_css)

        css_card = QFrame()
        css_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        css_layout = QVBoxLayout(css_card)
        css_layout.setContentsMargins(10, 8, 10, 8)
        css_layout.setSpacing(6)

        c_hdr = QHBoxLayout()
        lbl_ch = QLabel(tr("FEUILLE DE STYLE CSS (DIFF COMPARATIF)"))
        lbl_ch.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        c_hdr.addWidget(lbl_ch)
        c_hdr.addStretch()
        css_layout.addLayout(c_hdr)

        cols_css = QHBoxLayout()
        left_css_box = QVBoxLayout()
        lbl_l = QLabel(tr("Actuel (BDD) :"))
        lbl_l.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.COLOR_RED};")
        left_css_box.addWidget(lbl_l)
        tb_css = QTextBrowser()
        tb_css.setMinimumHeight(70)
        tb_css.setMaximumHeight(120)
        tb_css.setHtml(compute_field_word_diff_html(orig_css, mod_css))
        tb_css.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; font-family: {DesignTokens.FONT_CODE}; font-size: 10px;")
        left_css_box.addWidget(tb_css)
        cols_css.addLayout(left_css_box, 1)

        right_css_box = QVBoxLayout()
        lbl_r = QLabel(tr("Proposé (Éditable) :"))
        lbl_r.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.COLOR_GREEN};")
        right_css_box.addWidget(lbl_r)
        self.nt_model_css = QPlainTextEdit(mod_css)
        self.nt_model_css.setReadOnly(self._is_applied)
        self.nt_model_css.setMinimumHeight(70)
        self.nt_model_css.setMaximumHeight(120)
        self.nt_model_css.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; "
            f"font-family: {DesignTokens.FONT_CODE}; "
            f"font-size: 10px; padding: 4px;"
        )
        self.nt_model_css.textChanged.connect(self._on_model_content_changed)
        right_css_box.addWidget(self.nt_model_css)
        cols_css.addLayout(right_css_box, 1)

        css_layout.addLayout(cols_css)
        self.model_layout.addWidget(css_card)

        # Description
        desc_val = str(mod_dict.get("description") or orig_dict.get("description") or "")
        desc_card = QFrame()
        desc_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        d_layout = QVBoxLayout(desc_card)
        d_layout.setContentsMargins(10, 8, 10, 8)
        d_layout.setSpacing(4)
        lbl_d = QLabel(tr("DESCRIPTION POUR L'IA"))
        lbl_d.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {DesignTokens.TEXT_MUTED};")
        d_layout.addWidget(lbl_d)

        self.nt_model_desc = QPlainTextEdit(desc_val)
        self.nt_model_desc.setReadOnly(self._is_applied)
        self.nt_model_desc.setMaximumHeight(50)
        self.nt_model_desc.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        self.nt_model_desc.textChanged.connect(self._on_model_content_changed)
        d_layout.addWidget(self.nt_model_desc)
        self.model_layout.addWidget(desc_card)

    def _setup_css_tune_view(self, payload: dict[str, Any], target_id: int = 0) -> None:
        """Construit l'interface pour un ajustement de style CSS."""
        meta = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
        nt_name = str(meta.get("note_type_name") or payload.get("note_type_name") or "").strip()
        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name) if nt_name else (NoteTypeModel.get_or_none(NoteTypeModel.id == target_id) if target_id else None)
        if nt and not nt_name:
            nt_name = nt.name

        orig_css = str(payload.get("original") or (nt.css_style if nt else "") or "")
        snippet = str(meta.get("snippet") or payload.get("snippet") or "")
        mod_css = str(payload.get("modified") or (orig_css + ("\n\n" + snippet if snippet else "")))

        self._css_data = {"original": orig_css, "modified": mod_css, "note_type_name": nt_name}
        self._note_type = nt

        # En-tête
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 12px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.paint-brush", color=DesignTokens.COLOR_BLUE).pixmap(18, 18))
        h_layout.addWidget(ico)

        lbl_title = QLabel(tr("Ajustement de style CSS — Modèle '%1'", nt_name or tr("Modèle")))
        lbl_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        h_layout.addWidget(lbl_title, 1)

        badge_type = Badge("CSS", variant="info")
        h_layout.addWidget(badge_type)
        self.model_layout.addWidget(header_card)

        # Diff 2 colonnes
        css_card = QFrame()
        css_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        c_layout = QVBoxLayout(css_card)
        c_layout.setContentsMargins(10, 8, 10, 8)
        c_layout.setSpacing(6)

        cols_css = QHBoxLayout()
        left_box = QVBoxLayout()
        lbl_l = QLabel(tr("CSS actuel (BDD) :"))
        lbl_l.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.COLOR_RED};")
        left_box.addWidget(lbl_l)
        tb_css = QTextBrowser()
        tb_css.setMinimumHeight(100)
        tb_css.setHtml(compute_field_word_diff_html(orig_css, mod_css))
        tb_css.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        left_box.addWidget(tb_css)
        cols_css.addLayout(left_box, 1)

        right_box = QVBoxLayout()
        lbl_r = QLabel(tr("CSS ajusté (Éditable) :"))
        lbl_r.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.COLOR_GREEN};")
        right_box.addWidget(lbl_r)
        self.nt_css_tune_editor = QPlainTextEdit(mod_css)
        self.nt_css_tune_editor.setReadOnly(self._is_applied)
        self.nt_css_tune_editor.setMinimumHeight(100)
        self.nt_css_tune_editor.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; "
            f"font-family: {DesignTokens.FONT_CODE}; "
            f"font-size: 11px; padding: 6px;"
        )
        self.nt_css_tune_editor.textChanged.connect(self._on_model_content_changed)
        right_box.addWidget(self.nt_css_tune_editor)
        cols_css.addLayout(right_box, 1)

        c_layout.addLayout(cols_css)
        self.model_layout.addWidget(css_card)

    def _on_model_content_changed(self) -> None:
        """Notifie l'édition directe d'un modèle et rafraîchit l'aperçu si nécessaire."""
        content = self.get_modified_content()
        self.content_edited.emit(content)
        if self.tab_widget.currentIndex() == 1:
            self._refresh_preview()

    def _update_wozniak_badge(self) -> None:
        """Évalue l'atomicité et la conformité Wozniak de la carte atomique courante."""
        if not hasattr(self, "wozniak_badge"):
            return
        if not self.is_split or not self._split_cards or not (0 <= self._active_split_index < len(self._split_cards)):
            self.wozniak_badge.hide()
            return
        self.wozniak_badge.show()
        curr_card = self._split_cards[self._active_split_index]
        is_compliant, score, issues = evaluate_wozniak_card(curr_card)
        if is_compliant:
            self.wozniak_badge.setText(tr("Conforme Wozniak (Atomicité R4/R5)"))
            self.wozniak_badge.set_variant("success")
            self.wozniak_badge.setToolTip(tr("Score: %1/100 · Carte atomique concise et univoque.", score))
        else:
            self.wozniak_badge.setText(tr("Non-conforme Wozniak (%1/100)", score))
            self.wozniak_badge.set_variant("warning")
            self.wozniak_badge.setToolTip("\n".join(issues))

    def _populate_fields(self, mod_dict: dict[str, Any]) -> None:
        """Construit les lignes de comparaison champ par champ."""
        # Nettoyage des anciennes lignes
        while self.fields_layout.count() > 1:
            item = self.fields_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_rows.clear()
        self._tags_row = None

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

        # Prise en charge des tags si spécifiés dans le patch
        if self._original_tags or self._modified_tags:
            orig_tags_str = " ".join(self._original_tags) if isinstance(self._original_tags, list) else str(self._original_tags)
            mod_tags_str = " ".join(self._modified_tags) if isinstance(self._modified_tags, list) else str(self._modified_tags)
            tags_row = FieldSemanticDiffRow(
                field_name=tr("Tags"),
                original_value=orig_tags_str,
                modified_value=mod_tags_str,
                is_applied=self._is_applied,
                parent=self.scroll_content,
            )
            tags_row.content_changed.connect(self._on_tags_content_changed)
            self._tags_row = tags_row
            self.fields_layout.insertWidget(self.fields_layout.count() - 1, tags_row)

    def _on_tags_content_changed(self, field_name: str, new_val: str) -> None:
        """Gère la retouche utilisateur sur la ligne des tags."""
        self._modified_tags = [t.strip() for t in new_val.split() if t.strip()]
        self.content_edited.emit(self.get_modified_content())

    def _on_row_content_changed(self, field_name: str, new_val: str) -> None:
        """Gère la répercussion d'une retouche utilisateur."""
        if self.is_split and self._split_cards:
            self._split_cards[self._active_split_index][field_name] = new_val
            self._update_wozniak_badge()
            self.content_edited.emit(self.get_modified_content())
        elif isinstance(self._modified, dict):
            self._modified[field_name] = new_val
            self.content_edited.emit(self.get_modified_content())

        if self.tab_widget.currentIndex() == 1:
            self._refresh_preview()

    def _on_split_card_selected(self, index: int) -> None:
        """Bascule sur une autre carte atomique lors d'une scission."""
        if 0 <= self._active_split_index < len(self._split_cards):
            for f_name, row in self._field_rows.items():
                self._split_cards[self._active_split_index][f_name] = row.current_modified_value

        if 0 <= index < len(self._split_cards):
            self._active_split_index = index
            self._populate_fields(self._split_cards[index])
            self._update_wozniak_badge()
            self._refresh_preview()

    def _on_tab_changed(self, index: int) -> None:
        """Rafraîchit l'aperçu Anki Live si l'utilisateur bascule sur le 2e onglet."""
        if index == 1:
            self._refresh_preview()

    def get_modified_content(self) -> dict[str, Any] | list[dict[str, Any]] | str | None:
        """Retourne la structure complète modifiée (dict unitaire, liste de dicts scindés ou modèle)."""
        if self._patch_type == "batch_note_create" and self._batch_view is not None and hasattr(self._batch_view, "get_modified_content"):
            return self._batch_view.get_modified_content()
        if self._patch_type in ("split", "card_split") and self._split_cards:
            curr = dict(self._split_cards[self._active_split_index])
            for f_name, row in self._field_rows.items():
                curr[f_name] = row.current_modified_value
            self._split_cards[self._active_split_index] = curr
            return list(self._split_cards)

        if self._patch_type == "note_type_create":
            fields = [line.strip() for line in self.nt_create_fields.toPlainText().splitlines() if line.strip()] if hasattr(self, "nt_create_fields") else self._model_data.get("fields_schema", [])
            tmpls: list[dict[str, str]] = []
            if hasattr(self, "_create_template_editors") and self._create_template_editors:
                for ne, qe, ae in self._create_template_editors:
                    tmpls.append(
                        {
                            "name": ne.text().strip(),
                            "qfmt": qe.toPlainText(),
                            "afmt": ae.toPlainText(),
                        }
                    )
            else:
                raw_t = self._model_data.get("templates", [])
                tmpls = raw_t if isinstance(raw_t, list) else []

            res = dict(self._model_data)
            res.update(
                {
                    "name": self.nt_create_name.text().strip() if hasattr(self, "nt_create_name") else self._model_data.get("name", ""),
                    "description": self.nt_create_desc.toPlainText().strip() if hasattr(self, "nt_create_desc") else self._model_data.get("description", ""),
                    "fields_schema": fields,
                    "templates": tmpls,
                    "css_style": self.nt_create_css.toPlainText() if hasattr(self, "nt_create_css") else self._model_data.get("css_style", ""),
                }
            )
            return res

        if self._patch_type == "note_type_change":
            mapping: dict[str, str] = {}
            if hasattr(self, "_mapping_combos") and self._mapping_combos:
                for sf, combo in self._mapping_combos.items():
                    val = combo.currentData()
                    if val:
                        mapping[sf] = str(val)
            else:
                mapping = dict(self._migration_data.get("mapping_champs", {}))

            res = dict(self._migration_data)
            res["mapping_champs"] = mapping
            return res

        if self._patch_type in ("model", "note_type"):
            res = dict(self._model_data)
            if hasattr(self, "nt_model_fields"):
                res["fields_schema"] = [line.strip() for line in self.nt_model_fields.toPlainText().splitlines() if line.strip()]
            if hasattr(self, "nt_model_css"):
                res["css_style"] = self.nt_model_css.toPlainText()
            if hasattr(self, "nt_model_desc"):
                res["description"] = self.nt_model_desc.toPlainText().strip()
            return res

        if self._patch_type in ("css", "css_tune"):
            if hasattr(self, "nt_css_tune_editor"):
                return self.nt_css_tune_editor.toPlainText()
            return self._css_data.get("modified", "")

        res = dict(self._modified) if isinstance(self._modified, dict) else {}
        for f_name, row in self._field_rows.items():
            if not f_name.startswith("_"):
                res[f_name] = row.current_modified_value
        return res

    def get_modified_tags(self) -> list[str]:
        """Retourne la liste des tags modifiés."""
        return list(self._modified_tags)

    def get_original_fields_dict(self) -> dict[str, str]:
        """Retourne les champs de la note originale (Base active BDD)."""
        res: dict[str, str] = {}
        if isinstance(self._original, dict):
            for k, v in self._original.items():
                if not k.startswith("_"):
                    res[k] = str(v) if v is not None else ""
        return res

    def get_fields_dict(self) -> dict[str, str]:
        """Retourne les champs de la carte actuellement inspectée pour le rendu Anki."""
        res: dict[str, str] = {}
        for f_name, row in self._field_rows.items():
            if not f_name.startswith("_"):
                res[f_name] = row.current_modified_value
        return res

    def _refresh_preview(self) -> None:
        """Met à jour les deux instances internes de CardPreviewWidget (Originale vs Modifiée)."""
        if self._patch_type in ("note_type_create", "note_type_change", "model", "note_type", "css", "css_tune"):
            self._refresh_model_preview()
            return

        orig_fields = self.get_original_fields_dict()
        mod_fields = self.get_fields_dict()

        if hasattr(self, "preview_orig") and hasattr(self, "preview_mod"):
            # Synchronise l'orientation recto/verso
            self.preview_orig.is_recto = self.preview_mod.is_recto
            self.preview_orig._sync_toggle_side()
            self._sync_shared_toggle_side_button()

            self.preview_orig.update_preview(note_type=self._note_type, fields_dict=orig_fields)
            self.preview_mod.update_preview(note_type=self._note_type, fields_dict=mod_fields)

        orig_words = sum(len(v.split()) for v in orig_fields.values())
        mod_words = sum(len(v.split()) for v in mod_fields.values())
        if hasattr(self, "lbl_orig_preview_words"):
            self.lbl_orig_preview_words.setText(tr("%1 mots", orig_words))
        if hasattr(self, "lbl_mod_preview_words"):
            self.lbl_mod_preview_words.setText(tr("%1 mots", mod_words))

        self._sync_shared_card_selector()

    def _refresh_model_preview(self) -> None:
        """Met à jour l'aperçu Anki dédoublé pour les patchs touchant aux modèles de note."""
        if not hasattr(self, "preview_orig") or not hasattr(self, "preview_mod"):
            return

        self.preview_orig.is_recto = self.preview_mod.is_recto
        self.preview_orig._sync_toggle_side()
        self._sync_shared_toggle_side_button()

        if self._patch_type == "note_type_create":
            raw_content = self.get_modified_content()
            content = raw_content if isinstance(raw_content, dict) else {}
            name = str(content.get("name") or tr("Nouveau Modèle"))
            raw_fields = content.get("fields_schema") or ["Front", "Back"]
            fields = [f.strip() for f in raw_fields.splitlines() if f.strip()] if isinstance(raw_fields, str) else list(raw_fields)
            if not fields:
                fields = ["Front", "Back"]

            templates = content.get("templates") or [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]
            css = str(content.get("css_style") or "")

            temp_nt = NoteTypeModel(
                name=name,
                fields_schema=json.dumps(fields, ensure_ascii=False),
                templates=json.dumps(templates, ensure_ascii=False) if isinstance(templates, list) else str(templates),
                css_style=css,
            )
            sample_fields = {str(f): f"Exemple {f}" for f in fields}
            self.preview_orig.update_preview(note_type=None, fields_dict={})
            self.preview_mod.update_preview(note_type=temp_nt, fields_dict=sample_fields)
            if hasattr(self, "lbl_orig_preview_words"):
                self.lbl_orig_preview_words.setText(tr("(Inexistant en BDD)"))
            if hasattr(self, "lbl_mod_preview_words"):
                self.lbl_mod_preview_words.setText(tr("Modèle : %1", name))

        elif self._patch_type == "note_type_change":
            raw_content = self.get_modified_content()
            content = raw_content if isinstance(raw_content, dict) else {}
            target_name = str(content.get("target_model") or "")
            target_nt = NoteTypeModel.get_or_none(NoteTypeModel.name == target_name)
            note_ids = content.get("note_ids") or []
            source_note = NoteModel.get_or_none(NoteModel.id == note_ids[0]) if note_ids else None
            source_nt = source_note.note_type if source_note else None
            mapping = content.get("mapping_champs") if isinstance(content.get("mapping_champs"), dict) else {}

            s_fields = json.loads(source_nt.fields_schema) if source_nt and source_nt.fields_schema else ["Front", "Back"]
            s_content: dict[str, str] = {}
            if source_note:
                v = source_note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if v and v.content:
                    try:
                        s_content = json.loads(v.content)
                    except Exception:
                        pass
            if not s_content:
                s_content = {str(f): f"Exemple {f}" for f in s_fields}

            t_content: dict[str, str] = {}
            for s_k, t_k in mapping.items():
                if t_k:
                    t_content[str(t_k)] = s_content.get(str(s_k), f"[{s_k}]")

            self.preview_orig.update_preview(note_type=source_nt, fields_dict=s_content)
            self.preview_mod.update_preview(note_type=target_nt, fields_dict=t_content)
            if hasattr(self, "lbl_orig_preview_words"):
                self.lbl_orig_preview_words.setText(source_nt.name if source_nt else tr("Source"))
            if hasattr(self, "lbl_mod_preview_words"):
                self.lbl_mod_preview_words.setText(target_name)

        elif self._patch_type in ("model", "note_type"):
            raw_content = self.get_modified_content()
            content = raw_content if isinstance(raw_content, dict) else {}
            orig_nt = self._note_type
            raw_fields = content.get("fields_schema") or (json.loads(orig_nt.fields_schema) if orig_nt and orig_nt.fields_schema else ["Front", "Back"])
            templates = content.get("templates") or (json.loads(orig_nt.templates) if orig_nt and orig_nt.templates else [])
            css = str(content.get("css_style") or (orig_nt.css_style if orig_nt else ""))

            temp_nt = NoteTypeModel(
                name=orig_nt.name if orig_nt else "Modèle",
                fields_schema=json.dumps(raw_fields, ensure_ascii=False) if isinstance(raw_fields, list) else str(raw_fields),
                templates=json.dumps(templates, ensure_ascii=False) if isinstance(templates, list) else str(templates),
                css_style=css,
            )
            sample_orig = {str(f): f"Exemple {f}" for f in (json.loads(orig_nt.fields_schema) if orig_nt and orig_nt.fields_schema else ["Front", "Back"])}
            sample_mod = {str(f): f"Exemple {f}" for f in raw_fields}

            self.preview_orig.update_preview(note_type=orig_nt, fields_dict=sample_orig)
            self.preview_mod.update_preview(note_type=temp_nt, fields_dict=sample_mod)
            if hasattr(self, "lbl_orig_preview_words"):
                self.lbl_orig_preview_words.setText(tr("Actuel : %1", orig_nt.name if orig_nt else ""))
            if hasattr(self, "lbl_mod_preview_words"):
                self.lbl_mod_preview_words.setText(tr("Évolution : %1", temp_nt.name))

        elif self._patch_type in ("css", "css_tune"):
            orig_nt = self._note_type
            mod_css = str(self.get_modified_content())
            temp_nt = NoteTypeModel(
                name=orig_nt.name if orig_nt else "Modèle",
                fields_schema=orig_nt.fields_schema if orig_nt else '["Front", "Back"]',
                templates=orig_nt.templates if orig_nt else "[]",
                css_style=mod_css,
            )
            sample = {str(f): f"Exemple {f}" for f in (json.loads(orig_nt.fields_schema) if orig_nt and orig_nt.fields_schema else ["Front", "Back"])}
            self.preview_orig.update_preview(note_type=orig_nt, fields_dict=sample)
            self.preview_mod.update_preview(note_type=temp_nt, fields_dict=sample)
            if hasattr(self, "lbl_orig_preview_words"):
                self.lbl_orig_preview_words.setText(tr("CSS actuel"))
            if hasattr(self, "lbl_mod_preview_words"):
                self.lbl_mod_preview_words.setText(tr("CSS ajusté"))

        self._sync_shared_card_selector()

    def _sync_shared_card_selector(self) -> None:
        """Met à jour le sélecteur partagé de gabarit si le modèle de note en compte plusieurs."""
        if not hasattr(self, "shared_card_selector"):
            return

        templates: list[Any] = []
        if self._note_type and self._note_type.templates:
            try:
                templates = json.loads(self._note_type.templates) if isinstance(self._note_type.templates, str) else self._note_type.templates
            except Exception:
                templates = []
        if not isinstance(templates, list):
            templates = []

        if len(templates) > 1:
            self.shared_card_selector.blockSignals(True)
            self.shared_card_selector.clear()
            for idx, tmpl in enumerate(templates):
                name = tmpl.get("name", tr("Carte %1", idx + 1)) if isinstance(tmpl, dict) else tr("Carte %1", idx + 1)
                self.shared_card_selector.addItem(name)
            if hasattr(self, "preview_mod"):
                curr_idx = self.preview_mod.current_template_index
                if 0 <= curr_idx < self.shared_card_selector.count():
                    self.shared_card_selector.setCurrentIndex(curr_idx)
            self.shared_card_selector.blockSignals(False)
            self.shared_card_selector.show()
        else:
            self.shared_card_selector.hide()

    def _on_shared_card_selected(self, index: int) -> None:
        """Sélectionne le même gabarit (template) sur les deux cartes en parallèle."""
        if hasattr(self, "preview_orig"):
            self.preview_orig.set_selected_template_index(index)
        if hasattr(self, "preview_mod"):
            self.preview_mod.set_selected_template_index(index)

    def _on_shared_toggle_side(self) -> None:
        """Bascule simultanément le Recto/Verso des deux cartes (Originale et Proposée)."""
        if hasattr(self, "preview_orig"):
            self.preview_orig.flip_card()
        if hasattr(self, "preview_mod"):
            self.preview_mod.flip_card()
        self._sync_shared_toggle_side_button()

    def _sync_shared_toggle_side_button(self) -> None:
        """Met à jour le texte et l'icône du bouton partagé Recto/Verso."""
        if not hasattr(self, "btn_shared_toggle_side") or not hasattr(self, "preview_mod"):
            return
        if self.preview_mod.is_recto:
            self.btn_shared_toggle_side.setText(tr("Voir Verso"))
            self.btn_shared_toggle_side.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        else:
            self.btn_shared_toggle_side.setText(tr("Masquer Verso"))
            self.btn_shared_toggle_side.setIcon(load_phosphor_icon("ph.eye-slash", color=DesignTokens.TEXT_PRIMARY))

    def _on_shared_toggle_theme(self) -> None:
        """Bascule simultanément le thème (sombre/clair) des deux cartes."""
        if hasattr(self, "preview_orig"):
            self.preview_orig._toggle_theme()
        if hasattr(self, "preview_mod"):
            self.preview_mod._toggle_theme()
            icon_name = "sun" if self.preview_mod._is_preview_dark else "moon"
            if hasattr(self, "btn_shared_theme"):
                self.btn_shared_theme.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))

    def _on_shared_device_mode(self, mode: str) -> None:
        """Applique le mode d'affichage appareil simultanément aux deux cartes."""
        self._shared_device_mode = mode
        if hasattr(self, "preview_orig"):
            self.preview_orig.set_device_mode(mode)
        if hasattr(self, "preview_mod"):
            self.preview_mod.set_device_mode(mode)

        inactive_style = "background-color: transparent; border-radius: 4px;"
        active_style = f"background-color: {DesignTokens.BG_HOVER}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px;"

        if hasattr(self, "btn_device_desktop"):
            self.btn_device_desktop.setStyleSheet(active_style if mode == "desktop" else inactive_style)
        if hasattr(self, "btn_device_tablet"):
            self.btn_device_tablet.setStyleSheet(active_style if mode == "tablet" else inactive_style)
        if hasattr(self, "btn_device_mobile"):
            self.btn_device_mobile.setStyleSheet(active_style if mode == "mobile" else inactive_style)

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit les styles et l'aperçu rendu selon le thème actif."""
        if hasattr(self, "preview_orig") and hasattr(self.preview_orig, "refresh_theme"):
            self.preview_orig.refresh_theme(profile)
        if hasattr(self, "preview_mod") and hasattr(self.preview_mod, "refresh_theme"):
            self.preview_mod.refresh_theme(profile)
        self._refresh_preview()

    def cleanup(self) -> None:
        """Arrête les chargements Chromium et libère les ressources WebEngine."""
        if hasattr(self, "preview_orig") and hasattr(self.preview_orig, "cleanup"):
            self.preview_orig.cleanup()
        if hasattr(self, "preview_mod") and hasattr(self.preview_mod, "cleanup"):
            self.preview_mod.cleanup()


class BatchNoteCreateView(QWidget):
    """Vue tabulaire paginée pour les lots batch_note_create dans le Garde-Fou."""

    content_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._notes: list[dict[str, Any]] = []
        self._current_index: int = 0
        self._patch_payload: dict[str, Any] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.lbl_title = QLabel(tr("Lot de création — 0 note(s)"))
        self.lbl_title.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        header.addWidget(self.lbl_title)
        header.addStretch()
        self.lbl_count = QLabel(tr("0 / 0"))
        self.lbl_count.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        header.addWidget(self.lbl_count)
        layout.addLayout(header)

        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        self.btn_prev = SecondaryButton(tr("Précédent"))
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next = SecondaryButton(tr("Suivant"))
        self.btn_next.clicked.connect(self._go_next)
        nav.addWidget(self.btn_prev)
        nav.addStretch()
        nav.addWidget(self.btn_next)
        layout.addLayout(nav)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels([tr("Champ"), tr("Valeur")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        tags_header = QHBoxLayout()
        tags_header.setContentsMargins(0, 4, 0, 0)
        lbl_tags = QLabel(tr("Tags du lot"))
        lbl_tags.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY};")
        tags_header.addWidget(lbl_tags)
        tags_header.addStretch()
        layout.addLayout(tags_header)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(tr("tag1, tag2"))
        self.tags_edit.textChanged.connect(self._on_tags_changed)
        layout.addWidget(self.tags_edit)

        self._update_nav()

    def set_payload(self, payload: dict[str, Any]) -> None:
        self._patch_payload = payload or {}
        notes = payload.get("notes") or payload.get("modified", {}).get("notes") or []
        if isinstance(notes, list):
            self._notes = [n for n in notes if isinstance(n, dict)]
        else:
            self._notes = []
        self._current_index = 0
        self.lbl_title.setText(tr("Lot de création — %1 note(s)", len(self._notes)))
        tags = payload.get("tags") or payload.get("default_tags") or []
        if isinstance(tags, list):
            self.tags_edit.setText(", ".join(str(t) for t in tags))
        elif isinstance(tags, str):
            self.tags_edit.setText(tags)
        else:
            self.tags_edit.setText("")
        self._render_current()

    def _render_current(self) -> None:
        self.table.clearContents()
        self.lbl_count.setText(tr("%1 / %2", self._current_index + 1, max(1, len(self._notes))))
        self._update_nav()
        if not self._notes:
            self.table.setRowCount(0)
            return
        note = self._notes[self._current_index]
        fields = note.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}
        rows = list(fields.items())
        self.table.setRowCount(len(rows))
        for r, (k, v) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(k)))
            self.table.setItem(r, 1, QTableWidgetItem(str(v)))
        info_item = QTableWidgetItem(f"Type: {note.get('note_type', '')} | Deck: {note.get('deck', '')}")
        self.table.setRowCount(len(rows) + 1)
        self.table.setItem(len(rows), 0, QTableWidgetItem(tr("Métadonnées")))
        self.table.setItem(len(rows), 1, info_item)
        self.table.item(len(rows), 0).setFlags(self.table.item(len(rows), 0).flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.item(len(rows), 1).setFlags(self.table.item(len(rows), 1).flags() & ~Qt.ItemFlag.ItemIsEditable)

    def _update_nav(self) -> None:
        total = len(self._notes)
        self.btn_prev.setEnabled(total > 1 and self._current_index > 0)
        self.btn_next.setEnabled(total > 1 and self._current_index < total - 1)

    def _go_prev(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._render_current()

    def _go_next(self) -> None:
        if self._current_index < len(self._notes) - 1:
            self._current_index += 1
            self._render_current()

    def _on_tags_changed(self, text: str) -> None:
        tags = [t.strip() for t in text.split(",") if t.strip()]
        if "modified" not in self._patch_payload or not isinstance(self._patch_payload.get("modified"), dict):
            self._patch_payload["modified"] = {}
        self._patch_payload["modified"]["tags"] = tags
        self._patch_payload["tags"] = tags
        self.content_changed.emit(self._patch_payload)

    def get_modified_content(self) -> dict[str, Any]:
        return self._patch_payload

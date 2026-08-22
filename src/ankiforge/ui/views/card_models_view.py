"""
Vue Card Models (Atelier de Modèles de Cartes & Design System) — Pilier 3 d'AnkiForge.
- Panneau Gauche (300px) :
  - Onglet 1 « Modèles » : Liste des modèles Peewee avec recherche, ajout, duplication, import JSON, suppression.
  - Onglet 2 « Snippets » : Bibliothèque de composants modulaires réutilisables (Callouts, Badges, QCM, KaTeX, Code).
- Panneau Central :
  - Barre d'action supérieure TOUJOURS FIXE au sommet de l'onglet avec relief et ombres subtiles.
  - Splitter vertical permettant un redimensionnement libre en hauteur entre la zone supérieure (champs + aides repliables) et la zone inférieure (éditeurs de code).
  - Volet d'aides repliable (Collider / Accordéon) avec filtres de catégories, compteur compact et FlowLayout fluide dans QScrollArea.
  - Gestion multi-templates (Carte 1, Carte 2, +, Renommer, Dupliquer, Supprimer).
  - Sous-onglets de code style IDE avec affordance tactile et micro-retour au clic (Style CSS, HTML Recto, HTML Verso).
- Panneau Droit : Live Preview WebEngine Triple-Mode (Recto/Verso, Clair/Sombre, Données Live / Carte Témoin SQLite).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.cards.card_model_io import CardModelIO
from ankiforge.services.cards.snippet_library import CSSConflictResolver, SnippetItem
from ankiforge.ui.components import (
    DangerButton,
    FlowWidget,
    GlowLineEdit,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.components.code_editor import CodeEditorWithGutter
from ankiforge.ui.components.snippet_drawer import SnippetLibraryDrawer
from ankiforge.ui.dialogs.css_conflict_dialog import CSSConflictDialog
from ankiforge.ui.dialogs.model_import_dialog import ModelImportDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.cloze_manager import is_template_cloze
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def extract_css_classes(css_text: str) -> list[str]:
    """Extrait la liste unique des classes CSS définies dans la feuille de style."""
    if not css_text:
        return []
    matches = re.findall(r"\.([a-zA-Z_-][a-zA-Z0-9_\-]*)", css_text)
    excluded = {
        "hover",
        "active",
        "focus",
        "visited",
        "disabled",
        "first-child",
        "last-child",
        "nth-child",
        "before",
        "after",
    }
    classes: list[str] = []
    for cls in matches:
        if cls not in classes and cls not in excluded and not cls.isdigit():
            classes.append(cls)
    return classes


class TagPillButton(QPushButton):
    """Bouton style pilule avec relief, halo subtil et affordance tactile."""

    def __init__(
        self,
        text: str,
        variant: str = "field",  # "field" | "cloze" | "css" | "structure" | "condition"
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        if variant == "cloze":
            bg_tint = "rgba(168, 85, 247, 0.12)"
            border_color = "rgba(168, 85, 247, 0.45)"
            text_color = "#c084fc"
        elif variant == "css":
            bg_tint = "rgba(6, 182, 212, 0.12)"
            border_color = "rgba(6, 182, 212, 0.45)"
            text_color = "#67e8f9"
        elif variant == "structure":
            bg_tint = "rgba(245, 158, 11, 0.12)"
            border_color = "rgba(245, 158, 11, 0.45)"
            text_color = "#fcd34d"
        elif variant == "condition":
            bg_tint = "rgba(16, 185, 129, 0.12)"
            border_color = "rgba(16, 185, 129, 0.45)"
            text_color = "#6ee7b7"
        else:  # field
            bg_tint = "rgba(99, 102, 241, 0.10)"
            border_color = "rgba(99, 102, 241, 0.40)"
            text_color = "#a5b4fc"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_tint};
                border: 1px solid {border_color};
                border-radius: 12px;
                color: {text_color};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                font-weight: 600;
                padding: 1px 9px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {DesignTokens.BG_ACTIVE};
                padding-top: 2px;
            }}
        """)


class SubTabButton(QPushButton):
    """Bouton d'onglet style IDE avec relief et affordance tactile."""

    def __init__(self, text: str, icon_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.icon_name = icon_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        if active:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 14px;
                    font-size: 11px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.TEXT_SECONDARY};
                    border: 1px solid transparent;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 14px;
                    font-size: 11px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                }}
                QPushButton:pressed {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    padding-top: 5px;
                }}
            """)


class ResponsiveTopActionBar(QFrame):
    """Barre d'action supérieure adaptative pour l'éditeur de modèles de cartes."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("topActionBar")
        self.setFixedHeight(38)
        self.setStyleSheet(f"""
            QFrame#topActionBar {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Badge Icône
        self.lbl_editor_icon = QLabel()
        self.lbl_editor_icon.setPixmap(load_phosphor_icon("ph.swatches", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        self.lbl_editor_icon.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.lbl_editor_icon)

        # Titre du Modèle
        self.lbl_editor_title = QLabel("Modèle sélectionné")
        self.lbl_editor_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        self.lbl_editor_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.lbl_editor_title, 1)

        # Boutons d'action
        self.btn_export_json = SecondaryButton("Exporter JSON")
        self.btn_export_json.setIcon(load_phosphor_icon("ph.export", color=DesignTokens.TEXT_PRIMARY))
        self.btn_export_json.setFixedHeight(28)
        self.btn_export_json.setToolTip("Exporter le modèle au format JSON standardisé AnkiForge")

        self.btn_refresh = SecondaryButton("Rafraîchir")
        self.btn_refresh.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_refresh.setFixedHeight(28)
        self.btn_refresh.setToolTip("Actualiser la prévisualisation temps réel")

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save.setFixedHeight(28)
        self.btn_save.setToolTip("Sauvegarder les modifications du modèle")

        layout.addWidget(self.btn_export_json)
        layout.addWidget(self.btn_refresh)
        layout.addWidget(self.btn_save)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        w = self.width()
        if w < 480:
            self.btn_export_json.setText("")
            self.btn_export_json.setFixedWidth(28)
            self.btn_refresh.setText("")
            self.btn_refresh.setFixedWidth(28)
            if w < 360:
                self.btn_save.setText("")
                self.btn_save.setFixedWidth(28)
            else:
                self.btn_save.setText("Sauvegarder")
                self.btn_save.setMinimumWidth(0)
                self.btn_save.setMaximumWidth(16777215)
        else:
            self.btn_export_json.setText("Exporter JSON")
            self.btn_export_json.setMinimumWidth(0)
            self.btn_export_json.setMaximumWidth(16777215)
            self.btn_refresh.setText("Rafraîchir")
            self.btn_refresh.setMinimumWidth(0)
            self.btn_refresh.setMaximumWidth(16777215)
            self.btn_save.setText("Sauvegarder")
            self.btn_save.setMinimumWidth(0)
            self.btn_save.setMaximumWidth(16777215)


class CardModelsView(QWidget):
    """
    Vue Card Models (Atelier de Modèles de Cartes) — Conforme Pilier 3 d'AnkiForge.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_model: Optional[NoteTypeModel] = None
        self._templates_list: List[Dict[str, Any]] = []
        self._current_template_idx: int = 0
        self._is_syncing_template: bool = False
        self._current_helper_cat: str = "Tous"
        self.helper_category_buttons: Dict[str, QPushButton] = {}
        self._last_active_editor: str = "front"

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # =========================================================================
        # 1. PANNEAU GAUCHE : Onglet 1 Modèles & Onglet 2 Snippets (260px)
        # =========================================================================
        self.left_panel = IdePanel(detachable=True)
        self.left_panel.setMinimumWidth(240)

        # --- Tab 1 : Modèles Disponibles ---
        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(8, 8, 8, 8)
        list_layout.setSpacing(6)

        self.model_search_input = GlowLineEdit(placeholder="Rechercher un modèle...")
        self.model_search_input.setObjectName("modelSearchInput")
        self.model_search_input.setProperty("role", "search")
        self.model_search_input.textChanged.connect(self._filter_models_list)
        list_layout.addWidget(self.model_search_input)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 7px 9px;
                margin: 2px 0px;
                border: 1px solid transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-weight: 500;
                font-size: 12px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
            }}
        """)
        list_layout.addWidget(self.list_widget, 1)

        # Toolbar inférieure (Nouveau, Dupliquer, Importer, Supprimer)
        list_toolbar = QVBoxLayout()
        list_toolbar.setSpacing(5)

        row_actions1 = QHBoxLayout()
        row_actions1.setSpacing(5)

        self.btn_new = PrimaryButton("Nouveau")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color="white"))
        self.btn_new.setFixedHeight(28)

        self.btn_duplicate = SecondaryButton("Dupliquer")
        self.btn_duplicate.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_duplicate.setFixedHeight(28)

        row_actions1.addWidget(self.btn_new, 1)
        row_actions1.addWidget(self.btn_duplicate, 1)
        list_toolbar.addLayout(row_actions1)

        row_actions2 = QHBoxLayout()
        row_actions2.setSpacing(5)

        self.btn_import_json = SecondaryButton("Importer")
        self.btn_import_json.setIcon(load_phosphor_icon("ph.download-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_json.setFixedHeight(28)
        self.btn_import_json.setToolTip("Importer un modèle au format JSON standardisé")

        self.btn_del = DangerButton("Supprimer", ghost=True)
        self.btn_del.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_del.setFixedHeight(28)

        row_actions2.addWidget(self.btn_import_json, 1)
        row_actions2.addWidget(self.btn_del, 1)
        list_toolbar.addLayout(row_actions2)

        list_layout.addLayout(list_toolbar)

        self.left_panel.add_tab("Modèles", list_content, "ph.swatches", closable=False)

        # --- Tab 2 : Bibliothèque de Snippets ---
        self.snippet_drawer = SnippetLibraryDrawer()
        self.snippet_drawer.snippet_selected.connect(self._on_insert_snippet)
        self.left_panel.add_tab("Snippets", self.snippet_drawer, "ph.sparkle", closable=False)

        self.main_splitter.addWidget(self.left_panel)

        # =========================================================================
        # 2. PANNEAU CENTRAL : Éditeur avec Top Action Bar Responsive & Splitter Vertical
        # =========================================================================
        self.editor_panel = IdePanel(detachable=True)

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(8, 8, 8, 8)
        editor_layout.setSpacing(6)

        # 1. TOP ACTION BAR : RESPONSIVE (38px), FIXE ET AVEC RELIEF ISOLÉ
        self.top_action_bar = ResponsiveTopActionBar()
        self.lbl_editor_icon = self.top_action_bar.lbl_editor_icon
        self.lbl_editor_title = self.top_action_bar.lbl_editor_title
        self.btn_export_json = self.top_action_bar.btn_export_json
        self.btn_refresh = self.top_action_bar.btn_refresh
        self.btn_save = self.top_action_bar.btn_save

        editor_layout.addWidget(self.top_action_bar)

        # 2. SPLITTER VERTICAL PERMETTANT UN REDIMENSIONNEMENT LIBRE EN HAUTEUR
        self.editor_vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.editor_vertical_splitter.setStyleSheet(f"""
            QSplitter::handle:vertical {{
                background-color: {DesignTokens.BORDER_COLOR};
                height: 4px;
                margin: 2px 0px;
                border-radius: 2px;
            }}
            QSplitter::handle:vertical:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # --- ZONE SUPÉRIEURE : Champs de données + Volet d'Aides Repliable (Collider) ---
        top_resizable_container = QWidget()
        top_res_layout = QVBoxLayout(top_resizable_container)
        top_res_layout.setContentsMargins(0, 0, 0, 2)
        top_res_layout.setSpacing(5)

        # Champs de données
        fields_row = QHBoxLayout()
        fields_row.setSpacing(6)

        lbl_fields = QLabel("CHAMPS :")
        lbl_fields.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        fields_row.addWidget(lbl_fields)

        self.fields_input = StyledLineEdit()
        self.fields_input.setFixedHeight(26)
        self.fields_input.setText("Front, Back")
        fields_row.addWidget(self.fields_input, 1)

        top_res_layout.addLayout(fields_row)

        # Volet d'Aides d'Insertion Repliable (Collider / Accordéon)
        self.helpers_frame = QFrame()
        self.helpers_frame.setObjectName("helpersFrame")
        self.helpers_frame.setStyleSheet(f"""
            QFrame#helpersFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        helpers_layout = QVBoxLayout(self.helpers_frame)
        helpers_layout.setContentsMargins(6, 4, 6, 4)
        helpers_layout.setSpacing(4)

        # En-tête Collider (Bouton replier/déplier + Titre + Compteur + Filtres de catégories compacts)
        helpers_header = QHBoxLayout()
        helpers_header.setContentsMargins(0, 0, 0, 0)
        helpers_header.setSpacing(4)

        self.btn_collapse_helpers = IconButton("ph.caret-down", tooltip="Replier / Déplier le volet d'aides", size=18)
        self.btn_collapse_helpers.clicked.connect(self._toggle_helpers_collapsed)
        helpers_header.addWidget(self.btn_collapse_helpers)

        lbl_helpers_title = QLabel("AIDES :")
        lbl_helpers_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        helpers_header.addWidget(lbl_helpers_title)

        self.lbl_helpers_count = QLabel("0")
        self.lbl_helpers_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_helpers_count.setFixedHeight(18)
        self.lbl_helpers_count.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.lbl_helpers_count.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 9px;
                padding: 0px 5px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        helpers_header.addWidget(self.lbl_helpers_count)
        helpers_header.addStretch()

        # Boutons filtres de catégories compacts
        cat_definitions = [
            ("Tous", "ph.squares-four", "Tous"),
            ("Champs", "ph.brackets-curly", "Champs"),
            ("Cloze", "ph.eye-slash", "Cloze"),
            ("Classes CSS", "ph.paint-brush", "CSS"),
            ("Structure", "ph.tree-structure", "Structure"),
        ]

        for cat_id, icon_name, label_str in cat_definitions:
            btn = QPushButton(label_str)
            btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))
            btn.setFixedHeight(20)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Filtrer : {cat_id}")
            btn.clicked.connect(lambda _, c=cat_id: self._on_helper_category_selected(c))
            self.helper_category_buttons[cat_id] = btn
            helpers_header.addWidget(btn)

        helpers_layout.addLayout(helpers_header)

        # Zone scrollable pour le FlowWidget
        self.tags_scroll_area = QScrollArea()
        self.tags_scroll_area.setWidgetResizable(True)
        self.tags_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tags_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.tags_scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.tags_container = FlowWidget(margin=0, h_spacing=6, v_spacing=6)
        self.tags_container.setObjectName("tagsContainer")
        self.tags_container.setStyleSheet("QWidget#tagsContainer { background: transparent; border: none; }")
        self.tags_flow_layout = self.tags_container.flow_layout
        self.tags_scroll_area.setWidget(self.tags_container)

        helpers_layout.addWidget(self.tags_scroll_area, 1)
        top_res_layout.addWidget(self.helpers_frame, 1)

        self.editor_vertical_splitter.addWidget(top_resizable_container)

        # --- ZONE INFÉRIEURE : Multi-Templates + Onglets + Éditeurs de Code ---
        bottom_resizable_container = QWidget()
        bottom_res_layout = QVBoxLayout(bottom_resizable_container)
        bottom_res_layout.setContentsMargins(0, 2, 0, 0)
        bottom_res_layout.setSpacing(5)

        # Multi-Templates ('Gabarit / Carte')
        card_sel_widget = QWidget()
        card_sel_widget.setObjectName("cardSelWidget")
        card_sel_widget.setStyleSheet("QWidget#cardSelWidget { background: transparent; border: none; }")
        card_sel_row = QHBoxLayout(card_sel_widget)
        card_sel_row.setContentsMargins(0, 2, 0, 2)
        card_sel_row.setSpacing(6)

        lbl_card_sel = QLabel("GABARIT :")
        lbl_card_sel.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        card_sel_row.addWidget(lbl_card_sel)

        self.card_selector_combo = StyledComboBox()
        self.card_selector_combo.setFixedWidth(140)
        self.card_selector_combo.setFixedHeight(26)
        self.card_selector_combo.currentIndexChanged.connect(self._on_template_index_changed)
        card_sel_row.addWidget(self.card_selector_combo)

        self.btn_add_card_tmpl = IconButton("ph.plus", tooltip="Ajouter un nouveau gabarit de carte", size=22)
        self.btn_dup_card_tmpl = IconButton("ph.copy", tooltip="Dupliquer le gabarit actuel", size=22)
        self.btn_rename_card_tmpl = IconButton("ph.pencil-simple", tooltip="Renommer le gabarit", size=22)
        self.btn_del_card_tmpl = IconButton("ph.trash", tooltip="Supprimer ce gabarit", size=22)

        card_sel_row.addWidget(self.btn_add_card_tmpl)
        card_sel_row.addWidget(self.btn_dup_card_tmpl)
        card_sel_row.addWidget(self.btn_rename_card_tmpl)
        card_sel_row.addWidget(self.btn_del_card_tmpl)
        card_sel_row.addStretch()

        bottom_res_layout.addWidget(card_sel_widget)

        # Sous-onglets de code style IDE (CSS, HTML Recto, HTML Verso) avec relief
        subtabs_container = QFrame()
        subtabs_container.setObjectName("subtabsContainer")
        subtabs_container.setStyleSheet(f"""
            QFrame#subtabsContainer {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 1px solid {DesignTokens.BORDER_LIGHT};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 4px;
            }}
        """)
        subtabs_row = QHBoxLayout(subtabs_container)
        subtabs_row.setContentsMargins(4, 2, 4, 2)
        subtabs_row.setSpacing(4)

        self.btn_subtab_css = SubTabButton("Style CSS", "ph.file-css")
        self.btn_subtab_front = SubTabButton("HTML Recto", "ph.file-html")
        self.btn_subtab_back = SubTabButton("HTML Verso", "ph.file-html")

        subtabs_row.addWidget(self.btn_subtab_css)
        subtabs_row.addWidget(self.btn_subtab_front)
        subtabs_row.addWidget(self.btn_subtab_back)
        subtabs_row.addStretch()

        bottom_res_layout.addWidget(subtabs_container)

        # Stacked Editors (CSS, Front HTML, Back HTML)
        self.editor_stack = QStackedWidget()

        self.css_editor_wrapper = CodeEditorWithGutter(
            placeholder=".card { font-family: arial; text-align: center; }",
            mode="css",
        )
        self.editor_stack.addWidget(self.css_editor_wrapper)

        self.front_html_wrapper = CodeEditorWithGutter(
            placeholder="{{Front}}",
            mode="html",
        )
        self.editor_stack.addWidget(self.front_html_wrapper)

        self.back_html_wrapper = CodeEditorWithGutter(
            placeholder='{{FrontSide}}\n<hr id="answer">\n{{Back}}',
            mode="html",
        )
        self.editor_stack.addWidget(self.back_html_wrapper)

        bottom_res_layout.addWidget(self.editor_stack, 1)

        self.editor_vertical_splitter.addWidget(bottom_resizable_container)

        # Répartition initiale : 110px haut (champs + aides), 450px bas (éditeurs)
        self.editor_vertical_splitter.setSizes([110, 450])
        self.editor_vertical_splitter.setStretchFactor(0, 0)
        self.editor_vertical_splitter.setStretchFactor(1, 1)
        editor_layout.addWidget(self.editor_vertical_splitter, 1)

        self.editor_panel.add_tab("Éditeur de Modèle", editor_content, "ph.pencil-simple", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        # =========================================================================
        # 3. PANNEAU DROIT : Live Preview WebEngine Triple-Mode
        # =========================================================================
        self.preview_panel = IdePanel(detachable=True)
        self.preview_panel.setMinimumWidth(240)

        preview_content = QWidget()
        preview_layout = QVBoxLayout(preview_content)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(6)

        # Barre supérieure de sélection de la source de test
        witness_bar = QHBoxLayout()
        witness_bar.setContentsMargins(8, 8, 8, 0)
        witness_bar.setSpacing(6)

        lbl_witness = QLabel("TÉMOIN :")
        lbl_witness.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        witness_bar.addWidget(lbl_witness)

        self.note_witness_combo = StyledComboBox()
        self.note_witness_combo.setFixedHeight(26)
        self.note_witness_combo.addItem("Données d'exemple automatiques", userData=None)
        self.note_witness_combo.currentIndexChanged.connect(self._on_witness_note_changed)
        witness_bar.addWidget(self.note_witness_combo, 1)

        preview_layout.addLayout(witness_bar)

        # Composant WebEngine Anki Preview
        self.card_preview_widget = CardPreviewWidget()
        preview_layout.addWidget(self.card_preview_widget, 1)

        self.preview_panel.add_tab("Live Preview Modèle", preview_content, "ph.monitor", closable=False)
        self.main_splitter.addWidget(self.preview_panel)

        self.main_splitter.setSizes([260, 520, 360])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setStretchFactor(2, 1)
        self.editor_vertical_splitter.setSizes([110, 450])
        self._switch_subtab(0)

    def _connect_signals(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.btn_new.clicked.connect(self._on_new_model)
        self.btn_duplicate.clicked.connect(self._on_duplicate_model)
        self.btn_import_json.clicked.connect(self._on_import_json)
        self.btn_del.clicked.connect(self._on_delete_model)

        self.btn_export_json.clicked.connect(self._on_export_json)
        self.btn_refresh.clicked.connect(self._update_preview)
        self.btn_save.clicked.connect(self._on_save_model)

        self.btn_add_card_tmpl.clicked.connect(self._on_add_template)
        self.btn_dup_card_tmpl.clicked.connect(self._on_dup_template)
        self.btn_rename_card_tmpl.clicked.connect(self._on_rename_template)
        self.btn_del_card_tmpl.clicked.connect(self._on_del_template)

        self.fields_input.textChanged.connect(self._on_fields_changed)

        self.btn_subtab_css.clicked.connect(lambda: self._switch_subtab(0))
        self.btn_subtab_front.clicked.connect(lambda: self._switch_subtab(1))
        self.btn_subtab_back.clicked.connect(lambda: self._switch_subtab(2))

        self.front_html_wrapper.editor.cursorPositionChanged.connect(lambda: self._set_last_active_editor("front"))
        self.back_html_wrapper.editor.cursorPositionChanged.connect(lambda: self._set_last_active_editor("back"))
        self.css_editor_wrapper.editor.cursorPositionChanged.connect(lambda: self._set_last_active_editor("css"))

        self.css_editor_wrapper.editor.textChanged.connect(self._on_css_code_changed)
        self.front_html_wrapper.editor.textChanged.connect(self._on_code_changed)
        self.back_html_wrapper.editor.textChanged.connect(self._on_code_changed)

    def _set_last_active_editor(self, ed_type: str) -> None:
        self._last_active_editor = ed_type

    def _switch_subtab(self, index: int) -> None:
        self.editor_stack.setCurrentIndex(index)
        self.btn_subtab_css.set_active(index == 0)
        self.btn_subtab_front.set_active(index == 1)
        self.btn_subtab_back.set_active(index == 2)
        if index == 1:
            self._last_active_editor = "front"
        elif index == 2:
            self._last_active_editor = "back"
        elif index == 0:
            self._last_active_editor = "css"

    def _on_code_changed(self) -> None:
        if self._is_syncing_template:
            return
        self._sync_current_template_from_editors()
        self._update_preview()

    def _on_css_code_changed(self) -> None:
        self._on_code_changed()
        self._update_tags_toolbar()

    def _sync_current_template_from_editors(self) -> None:
        if 0 <= self._current_template_idx < len(self._templates_list):
            self._templates_list[self._current_template_idx]["qfmt"] = self.front_html_wrapper.toPlainText()
            self._templates_list[self._current_template_idx]["afmt"] = self.back_html_wrapper.toPlainText()

    def _filter_models_list(self, query: str) -> None:
        q = query.lower().strip()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            model = item.data(Qt.ItemDataRole.UserRole)
            if not q or (model and q in model.name.lower()):
                item.setHidden(False)
            else:
                item.setHidden(True)

    def refresh_data(self) -> None:
        """Recharge la liste des modèles depuis la base Peewee."""
        try:
            self.list_widget.blockSignals(True)
            self.list_widget.clear()

            models = list(NoteTypeModel.select())
            for m in models:
                is_m_cloze = False
                tmpl_count = 1
                if m.templates:
                    try:
                        t_list = json.loads(m.templates)
                        if isinstance(t_list, list):
                            tmpl_count = len(t_list)
                            if is_template_cloze(t_list):
                                is_m_cloze = True
                    except Exception:
                        pass  # nosec B110
                if not is_m_cloze and any(w in m.name.lower() for w in ("cloze", "trou", "texte à trou")):
                    is_m_cloze = True

                icon_str = "ph.eye-slash" if is_m_cloze else "ph.cards"
                type_label = "Cloze" if is_m_cloze else f"{tmpl_count} carte{'s' if tmpl_count > 1 else ''}"
                item = QListWidgetItem(f"{m.name}  ({type_label})")
                item.setIcon(load_phosphor_icon(icon_str, color=DesignTokens.ACCENT_PRIMARY))
                item.setToolTip(f"Modèle : {m.name}\nType : {'Texte à trous (Cloze)' if is_m_cloze else 'Standard'}\nGabarits : {tmpl_count}")
                item.setData(Qt.ItemDataRole.UserRole, m)
                self.list_widget.addItem(item)

            self.list_widget.blockSignals(False)

            if models and not self._current_model:
                self.list_widget.setCurrentRow(0)

        except Exception as e:
            logger.warning("Erreur refresh_data card_models_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    def _is_cloze_active(self) -> bool:
        """Détermine si le modèle sélectionné utilise des occlusions de type Cloze."""
        if is_template_cloze(self._templates_list):
            return True
        if self._current_model and any(w in self._current_model.name.lower() for w in ("cloze", "trou", "texte à trou")):
            return True
        raw_fields = [f.strip().lower() for f in self.fields_input.text().split(",") if f.strip()]
        return any("cloze" in f for f in raw_fields)

    @Slot()
    def _toggle_helpers_collapsed(self) -> None:
        """Replie ou déplie le volet d'aides (Collider)."""
        is_hidden = self.tags_scroll_area.isHidden()
        if is_hidden:
            self.tags_scroll_area.show()
            self.btn_collapse_helpers.setIcon(load_phosphor_icon("ph.caret-down", color=DesignTokens.TEXT_PRIMARY))
            self.btn_collapse_helpers.setToolTip("Replier le volet d'aides")
            self.helpers_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.helpers_frame.setMaximumHeight(16777215)
            self.helpers_frame.setMinimumHeight(0)
            self.editor_vertical_splitter.setSizes([140, 420])
        else:
            self.tags_scroll_area.hide()
            self.btn_collapse_helpers.setIcon(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_PRIMARY))
            self.btn_collapse_helpers.setToolTip("Déplier le volet d'aides")
            self.helpers_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.helpers_frame.setFixedHeight(34)
            self.editor_vertical_splitter.setSizes([70, 500])

    @Slot()
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_model = None
            self.lbl_editor_title.setText("Aucun modèle sélectionné")
            return

        model: Optional[NoteTypeModel] = current.data(Qt.ItemDataRole.UserRole)
        if not model:
            return

        self._current_model = model
        self.lbl_editor_title.setText(f"Modèle : {model.name}")

        # Décompilation des champs schema JSON
        if model.fields_schema:
            try:
                parsed_fields = json.loads(model.fields_schema)
                if isinstance(parsed_fields, list):
                    self.fields_input.setText(", ".join(parsed_fields))
                else:
                    self.fields_input.setText("Front, Back")
            except Exception:
                self.fields_input.setText("Front, Back")
        else:
            self.fields_input.setText("Front, Back")

        default_css = (
            ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n  color: #1e293b;\n  background-color: #ffffff;\n}\n\n.cloze {\n  font-weight: bold;\n  color: #3b82f6;\n}"
        )
        self.css_editor_wrapper.setPlainText(model.css_style or default_css)

        # Décompilation des templates JSON
        self._templates_list = []
        if model.templates:
            try:
                parsed_tmpl = json.loads(model.templates)
                if isinstance(parsed_tmpl, list) and parsed_tmpl:
                    self._templates_list = parsed_tmpl
            except Exception:
                pass  # nosec B110

        if not self._templates_list:
            self._templates_list = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": '{{FrontSide}}<br><hr id="answer"><br>{{Back}}'}]

        self._current_template_idx = 0
        self._populate_template_selector()
        self._load_current_template_to_editors()

        self._update_witness_notes_combo()
        self._update_tags_toolbar()
        self._update_preview()

    def _populate_template_selector(self) -> None:
        self.card_selector_combo.blockSignals(True)
        self.card_selector_combo.clear()
        for idx, tmpl in enumerate(self._templates_list):
            name = tmpl.get("name", f"Carte {idx + 1}")
            self.card_selector_combo.addItem(name, userData=idx)
        self.card_selector_combo.setCurrentIndex(self._current_template_idx)
        self.card_selector_combo.blockSignals(False)

    def _load_current_template_to_editors(self) -> None:
        if not (0 <= self._current_template_idx < len(self._templates_list)):
            return

        self._is_syncing_template = True
        tmpl = self._templates_list[self._current_template_idx]
        self.front_html_wrapper.setPlainText(tmpl.get("qfmt", ""))
        self.back_html_wrapper.setPlainText(tmpl.get("afmt", ""))
        self._is_syncing_template = False

    @Slot(int)
    def _on_template_index_changed(self, index: int) -> None:
        if index < 0 or index >= len(self._templates_list):
            return
        self._sync_current_template_from_editors()
        self._current_template_idx = index
        self._load_current_template_to_editors()
        self._update_tags_toolbar()
        self._update_preview()

    @Slot()
    def _on_add_template(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Gabarit", "Nom du gabarit de carte (ex: Carte 2) :")
        if ok and name.strip():
            self._sync_current_template_from_editors()
            new_tmpl = {
                "name": name.strip(),
                "qfmt": "{{Front}}",
                "afmt": '{{FrontSide}}<br><hr id="answer"><br>{{Back}}',
            }
            self._templates_list.append(new_tmpl)
            self._current_template_idx = len(self._templates_list) - 1
            self._populate_template_selector()
            self._load_current_template_to_editors()
            self._update_tags_toolbar()
            self._update_preview()
            show_toast(self, f"Gabarit '{name.strip()}' ajouté.")

    @Slot()
    def _on_dup_template(self) -> None:
        if not (0 <= self._current_template_idx < len(self._templates_list)):
            return
        self._sync_current_template_from_editors()
        current = self._templates_list[self._current_template_idx]
        dup_name = f"{current.get('name', 'Carte')} (Copie)"
        new_tmpl = {
            "name": dup_name,
            "qfmt": current.get("qfmt", ""),
            "afmt": current.get("afmt", ""),
        }
        self._templates_list.append(new_tmpl)
        self._current_template_idx = len(self._templates_list) - 1
        self._populate_template_selector()
        self._load_current_template_to_editors()
        self._update_tags_toolbar()
        self._update_preview()
        show_toast(self, f"Gabarit dupliqué sous '{dup_name}'.")

    @Slot()
    def _on_rename_template(self) -> None:
        if not (0 <= self._current_template_idx < len(self._templates_list)):
            return
        current_name = self._templates_list[self._current_template_idx].get("name", "")
        name, ok = QInputDialog.getText(self, "Renommer le Gabarit", "Nouveau nom :", text=current_name)
        if ok and name.strip():
            self._templates_list[self._current_template_idx]["name"] = name.strip()
            self._populate_template_selector()
            show_toast(self, "Gabarit renommé.")

    @Slot()
    def _on_del_template(self) -> None:
        if len(self._templates_list) <= 1:
            QMessageBox.warning(self, "Suppression impossible", "Un modèle doit comporter au moins un gabarit de carte.")
            return

        current_name = self._templates_list[self._current_template_idx].get("name", "")
        res = QMessageBox.question(
            self,
            "Supprimer le Gabarit",
            f"Voulez-vous vraiment supprimer le gabarit '{current_name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self._templates_list.pop(self._current_template_idx)
            self._current_template_idx = max(0, self._current_template_idx - 1)
            self._populate_template_selector()
            self._load_current_template_to_editors()
            self._update_tags_toolbar()
            self._update_preview()
            show_toast(self, "Gabarit supprimé.")

    def _update_witness_notes_combo(self) -> None:
        self.note_witness_combo.blockSignals(True)
        self.note_witness_combo.clear()
        self.note_witness_combo.addItem("Données d'exemple automatiques", userData=None)

        if self._current_model:
            notes = list(NoteModel.select().where(NoteModel.note_type == self._current_model).limit(15))
            for note in notes:
                version = NoteVersionModel.get_or_none(note=note, is_active=True)
                summary = f"Note #{note.id}"
                if version and version.content:
                    try:
                        content_dict = json.loads(version.content)
                        first_val = next(iter(content_dict.values()), "")
                        if first_val:
                            summary += f" : {first_val[:28]}..."
                    except Exception:
                        pass  # nosec B110
                self.note_witness_combo.addItem(summary, userData=note.id)

        self.note_witness_combo.blockSignals(False)

    @Slot(int)
    def _on_witness_note_changed(self, index: int) -> None:
        self._update_preview()

    @Slot(SnippetItem)
    def _on_insert_snippet(self, snippet: SnippetItem, target: Optional[str] = None) -> None:
        """Insère un snippet modulaire à la position actuelle du curseur avec fusion CSS intelligente."""
        existing_css = self.css_editor_wrapper.toPlainText()
        conflicts = CSSConflictResolver.find_conflicts(existing_css, snippet.css_style)

        html_to_insert = snippet.html_template
        css_to_insert = snippet.css_style

        if conflicts:
            dialog = CSSConflictDialog(conflicting_classes=conflicts, snippet_name=snippet.name, parent=self)
            if dialog.exec() == CSSConflictDialog.DialogCode.Accepted:
                action = dialog.selected_action
                if action == "rename":
                    # Créer un mapping de renommage unique
                    mapping = {cls_name: f"{cls_name}-v2" for cls_name in conflicts}
                    html_to_insert, css_to_insert = CSSConflictResolver.rename_classes(
                        html=snippet.html_template,
                        css=snippet.css_style,
                        class_mapping=mapping,
                    )
                    merged_css = CSSConflictResolver.merge_css(existing_css, css_to_insert, strategy="append")
                    self.css_editor_wrapper.setPlainText(merged_css)
                elif action == "replace":
                    merged_css = CSSConflictResolver.merge_css(existing_css, css_to_insert, strategy="replace", replace_classes=conflicts)
                    self.css_editor_wrapper.setPlainText(merged_css)
                elif action == "html_only":
                    pass  # N'ajoute pas de CSS
            else:
                return  # Annulé par l'utilisateur
        else:
            if snippet.css_style and snippet.css_style.strip() not in existing_css:
                merged_css = CSSConflictResolver.merge_css(existing_css, css_to_insert, strategy="append")
                self.css_editor_wrapper.setPlainText(merged_css)

        # Déterminer la cible d'insertion HTML basée sur la position / sélection active
        if target == "back" or (target is None and (self._last_active_editor == "back" or self.editor_stack.currentIndex() == 2)):
            target_wrapper = self.back_html_wrapper
            target_idx = 2
        else:
            target_wrapper = self.front_html_wrapper
            target_idx = 1

        # Insérer exactement à la position du curseur
        cursor = target_wrapper.editor.textCursor()
        cursor.insertText(html_to_insert)
        target_wrapper.editor.setTextCursor(cursor)

        self._switch_subtab(target_idx)
        target_wrapper.editor.setFocus()

        show_toast(self, f"Snippet « {snippet.name} » inséré au curseur.")
        self._update_tags_toolbar()
        self._update_preview()

    @Slot(str)
    def _on_helper_category_selected(self, cat_name: str) -> None:
        self._current_helper_cat = cat_name
        self._update_tags_toolbar()

    @Slot()
    def _on_fields_changed(self) -> None:
        self._update_tags_toolbar()

    def _update_tags_toolbar(self) -> None:
        """Met à jour dynamiquement les balises et classes CSS détectées avec FlowLayout."""
        is_cloze = self._is_cloze_active()

        # 1. Mise à jour de l'état et de la visibilité des boutons de filtres de catégories
        if "Cloze" in self.helper_category_buttons:
            self.helper_category_buttons["Cloze"].setVisible(is_cloze)
            if not is_cloze and self._current_helper_cat == "Cloze":
                self._current_helper_cat = "Tous"

        for cat_name, btn in self.helper_category_buttons.items():
            is_selected = cat_name == self._current_helper_cat
            if is_selected:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_ACTIVE};
                        border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                        color: {DesignTokens.TEXT_PRIMARY};
                        font-size: 10px;
                        font-weight: bold;
                        padding: 2px 8px;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                    QPushButton:pressed {{
                        padding-top: 3px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_INPUT};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        color: {DesignTokens.TEXT_MUTED};
                        font-size: 10px;
                        padding: 2px 8px;
                        border-radius: {DesignTokens.RADIUS_SM}px;
                    }}
                    QPushButton:hover {{
                        background-color: {DesignTokens.BG_HOVER};
                        border-color: {DesignTokens.BORDER_LIGHT};
                        color: {DesignTokens.TEXT_PRIMARY};
                    }}
                    QPushButton:pressed {{
                        background-color: {DesignTokens.BG_ACTIVE};
                        padding-top: 3px;
                    }}
                """)

        # 2. Nettoyage complet du FlowWidget
        self.tags_container.clear()

        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Front", "Back"]

        # Synchronisation des champs et classes avec les éditeurs et linters
        self.front_html_wrapper.set_known_fields(raw_fields)
        self.back_html_wrapper.set_known_fields(raw_fields)
        css_text = self.css_editor_wrapper.toPlainText()
        detected_classes = extract_css_classes(css_text)
        self.front_html_wrapper.set_custom_classes(detected_classes)
        self.back_html_wrapper.set_custom_classes(detected_classes)
        self.css_editor_wrapper.set_custom_classes(detected_classes)

        active_cat = self._current_helper_cat

        # 3. Génération des balises selon la catégorie active
        # Catégorie 1 : Champs standards
        if active_cat in ("Tous", "Champs"):
            for f in raw_fields:
                tag_str = f"{{{{{f}}}}}"
                btn = TagPillButton(tag_str, variant="field")
                btn.setToolTip(f"Insérer le champ {tag_str}")
                btn.clicked.connect(lambda _, t=tag_str: self._insert_tag_to_active_editor(t))
                self.tags_flow_layout.addWidget(btn)

        # Catégorie 2 : Occlusions Cloze (affichées uniquement si modèle Cloze)
        if is_cloze and active_cat in ("Tous", "Cloze"):
            for f in raw_fields:
                cloze_str = f"{{{{cloze:{f}}}}}"
                btn_c = TagPillButton(cloze_str, variant="cloze")
                btn_c.setToolTip(f"Insérer l'occlusion {cloze_str}")
                btn_c.clicked.connect(lambda _, t=cloze_str: self._insert_tag_to_active_editor(t))
                self.tags_flow_layout.addWidget(btn_c)

        # Catégorie 3 : Classes CSS Détectées
        if active_cat in ("Tous", "Classes CSS"):
            css_text = self.css_editor_wrapper.toPlainText()
            detected_classes = extract_css_classes(css_text)
            for cls_name in detected_classes:
                btn_cls = TagPillButton(f".{cls_name}", variant="css")
                btn_cls.setToolTip(f"Insérer le conteneur <div class='{cls_name}'></div> ou la règle CSS .{cls_name}")
                btn_cls.clicked.connect(lambda _, c=cls_name: self._insert_css_class_to_active_editor(c))
                self.tags_flow_layout.addWidget(btn_cls)

        # Catégorie 4 : Structure & Conditions
        if active_cat in ("Tous", "Structure"):
            btn_fs = TagPillButton("{{FrontSide}}", variant="structure")
            btn_fs.setToolTip("Insérer le rappel du recto au verso")
            btn_fs.clicked.connect(lambda: self._insert_tag_to_active_editor("{{FrontSide}}"))
            self.tags_flow_layout.addWidget(btn_fs)

            btn_hr = TagPillButton('<hr id="answer">', variant="structure")
            btn_hr.setToolTip("Insérer la ligne séparatrice de réponse Anki")
            btn_hr.clicked.connect(lambda: self._insert_tag_to_active_editor('<hr id="answer">'))
            self.tags_flow_layout.addWidget(btn_hr)

            # Conditions d'affichage Anki pour chaque champ
            for f in raw_fields:
                cond_tag = f"{{{{#{f}}}}}"
                btn_cond = TagPillButton(cond_tag, variant="condition")
                btn_cond.setToolTip(f"Insérer le bloc conditionnel si '{f}' n'est pas vide")
                cond_snippet = f"{{{{#{f}}}}}\n  {{{{{f}}}}}\n{{{{/{f}}}}}"
                btn_cond.clicked.connect(lambda _, s=cond_snippet: self._insert_tag_to_active_editor(s))
                self.tags_flow_layout.addWidget(btn_cond)

        # Mettre à jour le compteur d'éléments dans le badge d'en-tête
        total_pills = self.tags_flow_layout.count()
        self.lbl_helpers_count.setText(f"{total_pills}")
        self.tags_container.updateGeometry()

    def _insert_tag_to_active_editor(self, tag_str: str) -> None:
        active_idx = self.editor_stack.currentIndex()
        if active_idx == 1:
            self.front_html_wrapper.insertPlainText(tag_str)
        elif active_idx == 2:
            self.back_html_wrapper.insertPlainText(tag_str)
        elif active_idx == 0:
            self.css_editor_wrapper.insertPlainText(tag_str)

    def _insert_css_class_to_active_editor(self, class_name: str) -> None:
        """Insère une classe CSS selon l'éditeur actuellement actif."""
        active_idx = self.editor_stack.currentIndex()
        if active_idx in (1, 2):  # HTML Front ou Back
            tag = f'<div class="{class_name}">\n  \n</div>'
            if active_idx == 1:
                self.front_html_wrapper.insertPlainText(tag)
            else:
                self.back_html_wrapper.insertPlainText(tag)
        elif active_idx == 0:  # CSS
            rule = f"\n.{class_name} {{\n  \n}}\n"
            self.css_editor_wrapper.insertPlainText(rule)

    @Slot()
    def _update_preview(self) -> None:
        """Met à jour l'aperçu WebEngine temps réel (CardPreviewWidget)."""
        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Front", "Back"]

        # 1. Vérifier si une note témoin réelle SQLite est sélectionnée
        selected_note_id = self.note_witness_combo.currentData()
        mock_fields: Dict[str, str] = {}

        if selected_note_id:
            version = NoteVersionModel.get_or_none(NoteVersionModel.note_id == selected_note_id, is_active=True)
            if version and version.content:
                try:
                    mock_fields = json.loads(version.content)
                except Exception:
                    mock_fields = {}

        if not mock_fields:
            for f in raw_fields:
                f_lower = f.lower()
                if "cloze" in f_lower or "texte" in f_lower:
                    mock_fields[f] = "La capitale de la France est {{c1::Paris::Ville}}."
                elif "front" in f_lower or "recto" in f_lower:
                    mock_fields[f] = "Quelle est la capitale de la France ?"
                elif "back" in f_lower or "verso" in f_lower or "extra" in f_lower:
                    mock_fields[f] = "Paris est la capitale et la plus grande ville de France."
                else:
                    mock_fields[f] = f"Valeur de test pour {f}"

        self._sync_current_template_from_editors()
        css = self.css_editor_wrapper.toPlainText()

        self.card_preview_widget.update_preview(
            note_type=self._current_model,
            fields_dict=mock_fields,
            override_templates=self._templates_list,
            override_css=css,
        )

    @Slot()
    def _on_new_model(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau modèle de carte", "Nom du modèle :")
        if ok and name.strip():
            try:
                default_tmpl = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": '{{FrontSide}}<br><hr id="answer"><br>{{Back}}'}]
                new_model = NoteTypeModel.create(
                    name=name.strip(),
                    fields_schema=json.dumps(["Front", "Back"], ensure_ascii=False),
                    templates=json.dumps(default_tmpl, ensure_ascii=False),
                    css_style=(
                        ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n"
                        "  color: #1e293b;\n  background-color: #ffffff;\n}\n\n.cloze {\n"
                        "  font-weight: bold;\n  color: #3b82f6;\n}"
                    ),
                )
                self.refresh_data()
                # Sélectionner le nouveau modèle
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    if item.data(Qt.ItemDataRole.UserRole).id == new_model.id:
                        self.list_widget.setCurrentItem(item)
                        break
                show_toast(self, f"Modèle '{name.strip()}' créé avec succès.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le modèle : {str(e)}")

    @Slot()
    def _on_duplicate_model(self) -> None:
        if not self._current_model:
            return

        dup_name = f"{self._current_model.name} (Copie)"
        idx = 2
        while NoteTypeModel.get_or_none(NoteTypeModel.name == dup_name):
            dup_name = f"{self._current_model.name} (Copie {idx})"
            idx += 1

        try:
            created = NoteTypeModel.create(
                name=dup_name,
                fields_schema=self._current_model.fields_schema,
                templates=self._current_model.templates,
                css_style=self._current_model.css_style,
            )
            self.refresh_data()
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole).id == created.id:
                    self.list_widget.setCurrentItem(item)
                    break
            show_toast(self, f"Modèle dupliqué sous '{dup_name}'.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de dupliquer le modèle : {str(e)}")

    @Slot()
    def _on_export_json(self) -> None:
        if not self._current_model:
            show_toast(self, "Aucun modèle sélectionné à exporter.", is_error=True)
            return

        self._sync_current_template_from_editors()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le modèle de carte",
            f"{self._current_model.name.replace(' ', '_').lower()}_model.json",
            "Fichier Modèle AnkiForge (*.json)",
        )
        if file_path:
            try:
                json_str = CardModelIO.export_to_json(self._current_model)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json_str)
                show_toast(self, f"Modèle exporté dans '{file_path}'.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur d'exportation", f"Impossible d'exporter le fichier : {str(e)}")

    @Slot()
    def _on_import_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer un modèle de carte",
            "",
            "Fichier Modèle AnkiForge (*.json)",
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                is_valid, parsed_data, err_msg = CardModelIO.validate_and_parse_json(content)
                if not is_valid or not parsed_data:
                    QMessageBox.critical(self, "Fichier Invalide", f"Le fichier JSON est invalide :\n{err_msg}")
                    return

                dialog = ModelImportDialog(model_data=parsed_data, parent=self)
                if dialog.exec() == ModelImportDialog.DialogCode.Accepted and dialog.imported_model:
                    self.refresh_data()
                    for i in range(self.list_widget.count()):
                        item = self.list_widget.item(i)
                        if item.data(Qt.ItemDataRole.UserRole).id == dialog.imported_model.id:
                            self.list_widget.setCurrentItem(item)
                            break
                    show_toast(self, f"Modèle '{dialog.imported_model.name}' importé avec succès.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur d'importation", f"Échec de l'import : {str(e)}")

    @Slot()
    def _on_delete_model(self) -> None:
        if not self._current_model:
            return

        res = QMessageBox.question(
            self,
            "Supprimer le modèle",
            f"Voulez-vous vraiment supprimer le modèle '{self._current_model.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                self._current_model.delete_instance()
                self._current_model = None
                self.refresh_data()
                show_toast(self, "Modèle supprimé.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le modèle : {str(e)}")

    @Slot()
    def _on_save_model(self) -> None:
        if not self._current_model:
            show_toast(self, "Aucun modèle sélectionné à sauvegarder.", is_error=True)
            return

        try:
            fields_list = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
            if not fields_list:
                fields_list = ["Front", "Back"]

            self._sync_current_template_from_editors()
            css = self.css_editor_wrapper.toPlainText()

            self._current_model.fields_schema = json.dumps(fields_list, ensure_ascii=False)
            self._current_model.templates = json.dumps(self._templates_list, ensure_ascii=False)
            self._current_model.css_style = css
            self._current_model.save()

            show_toast(self, f"Modèle '{self._current_model.name}' sauvegardé avec succès.")
            self._update_preview()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible de sauvegarder le modèle : {str(e)}")

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit les styles à chaud pour garantir une affordance et un relief parfaits dans tous les thèmes."""
        if hasattr(self, "card_preview_widget") and hasattr(self.card_preview_widget, "refresh_theme"):
            self.card_preview_widget.refresh_theme(profile)
        if hasattr(self, "snippet_drawer") and hasattr(self.snippet_drawer, "refresh_theme"):
            self.snippet_drawer.refresh_theme(profile)
        self._update_tags_toolbar()
        self._switch_subtab(self.editor_stack.currentIndex())


CardModelsTab = CardModelsView

"""Widget d'arborescence et de navigation structurelle Markdown (Outline) pour AnkiForge."""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.markdown.models import HeadingNode
from ankiforge.services.markdown.structurer import MarkdownStructurer
from ankiforge.ui.components import GlowLineEdit, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DocumentOutlineWidget(QWidget):
    """Panneau interactif d'arborescence Markdown avec saut direct à la ligne."""

    heading_selected = Signal(int)  # Émet le numéro de ligne (1-indexé)
    repair_requested = Signal()
    toc_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_content: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Champ de recherche / filtrage en direct
        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("🔍 Filtrer les titres...")
        self.search_input.setFixedHeight(28)
        self.search_input.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.search_input)

        # Arbre des titres
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Titre", "Ligne"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                font-size: 11px;
                padding: 4px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 2px;
            }}
            QTreeWidget::item {{
                padding: 4px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree, 1)

        # Message informatif document sans titres
        self.lbl_empty = QLabel("Aucun titre Markdown (# Titre) détecté.")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; padding: 20px;")
        self.lbl_empty.hide()
        layout.addWidget(self.lbl_empty)

        # Barre d'actions d'optimisation structurelle
        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)

        self.btn_repair = SecondaryButton("Réparer Titres")
        self.btn_repair.setIcon(load_phosphor_icon("ph.wrench", color=DesignTokens.COLOR_YELLOW))
        self.btn_repair.setToolTip("Harmonise la hiérarchie des titres (corrige les sauts anormaux H1->H3)")
        self.btn_repair.setFixedHeight(26)
        self.btn_repair.setStyleSheet(f"font-size: 11px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_repair.clicked.connect(self.repair_requested.emit)
        action_layout.addWidget(self.btn_repair)

        self.btn_toc = SecondaryButton("Sommaire (TOC)")
        self.btn_toc.setIcon(load_phosphor_icon("ph.list-numbers", color=DesignTokens.COLOR_BLUE))
        self.btn_toc.setToolTip("Génère et insère une Table des Matières Markdown standardisée")
        self.btn_toc.setFixedHeight(26)
        self.btn_toc.setStyleSheet(f"font-size: 11px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_toc.clicked.connect(self.toc_requested.emit)
        action_layout.addWidget(self.btn_toc)

        layout.addLayout(action_layout)

    def set_document_content(self, content: str) -> None:
        """Met à jour l'arborescence à partir du contenu Markdown brut."""
        self._current_content = content
        self.tree.clear()

        if not content or not content.strip():
            self.lbl_empty.show()
            self.tree.hide()
            return

        tree_nodes = MarkdownStructurer.get_outline_tree(content)
        if not tree_nodes:
            self.lbl_empty.show()
            self.tree.hide()
            return

        self.lbl_empty.hide()
        self.tree.show()

        for node in tree_nodes:
            self._add_node_to_tree(node, parent_item=None)

        self.tree.expandAll()

        # Ré-applique le filtre si une recherche était active
        query = self.search_input.text().strip()
        if query:
            self._on_filter_changed(query)

    def _add_node_to_tree(self, node: HeadingNode, parent_item: QTreeWidgetItem | None) -> None:
        """Ajoute récursivement un nœud et ses sous-titres dans le QTreeWidget."""
        display_title = f"{'  ' * (node.level - 1)}H{node.level}  {node.title}"
        item = QTreeWidgetItem(parent_item if parent_item is not None else self.tree)
        item.setText(0, display_title)
        item.setText(1, f"L{node.line_number}")
        item.setData(0, Qt.ItemDataRole.UserRole, node.line_number)
        item.setToolTip(0, f"Niveau {node.level} • {node.word_count} mots • Ligne {node.line_number}")

        for child in node.children:
            self._add_node_to_tree(child, parent_item=item)

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Déclenche le saut vers la ligne correspondante."""
        line_num = item.data(0, Qt.ItemDataRole.UserRole)
        if line_num and isinstance(line_num, int):
            self.heading_selected.emit(line_num)

    def _on_filter_changed(self, text: str) -> None:
        """Filtre les éléments affichés selon la saisie utilisateur."""
        query = text.strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            title = item.text(0).lower()
            matched = not query or query in title

            child_matched = False
            for i in range(item.childCount()):
                child = item.child(i)
                if child and filter_item(child):
                    child_matched = True

            visible = matched or child_matched
            item.setHidden(not visible)
            if visible and query:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            top_item = self.tree.topLevelItem(i)
            if top_item:
                filter_item(top_item)

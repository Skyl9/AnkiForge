"""Widget d'arborescence et de navigation structurelle Markdown (Outline) pour AnkiForge."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QGuiApplication,
    QPainter,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.markdown.models import HeadingNode
from ankiforge.services.markdown.structurer import MarkdownStructurer
from ankiforge.ui.components import GlowLineEdit, IconButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

# Rôles de données personnalisés pour l'arborescence
ROLE_LINE_NUMBER = Qt.ItemDataRole.UserRole  # int (1-indexé, compatibilité historique)
ROLE_LEVEL = Qt.ItemDataRole.UserRole + 1  # int (1 à 6)
ROLE_WORD_COUNT = Qt.ItemDataRole.UserRole + 2  # int
ROLE_END_LINE = Qt.ItemDataRole.UserRole + 3  # int
ROLE_SLUG = Qt.ItemDataRole.UserRole + 4  # str
ROLE_RAW_TITLE = Qt.ItemDataRole.UserRole + 5  # str
ROLE_COVERAGE_COUNT = Qt.ItemDataRole.UserRole + 6  # int | None
ROLE_IS_ACTIVE = Qt.ItemDataRole.UserRole + 7  # bool (ligne active dans l'éditeur)


class OutlineItemDelegate(QStyledItemDelegate):
    """Délégué graphique vectoriel haute performance pour les éléments du plan.

    Gère le rendu des badges sémantiques H1-H6, la mise en surbrillance Scroll Spy,
    et l'alignement précis des métadonnées de section (mots, ligne, couverture SRS).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        return QSize(0, 28)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = option.rect
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_active = bool(index.data(ROLE_IS_ACTIVE))

        # Fond de sélection / survol / actif
        if is_selected:
            painter.fillRect(rect, QColor(DesignTokens.ACCENT_PRIMARY))
        elif is_active:
            painter.fillRect(rect, QColor(DesignTokens.ACCENT_BG))
        elif is_hover:
            painter.fillRect(rect, QColor(DesignTokens.BG_HOVER))

        # Marqueur visuel gauche si la section est active dans l'éditeur (Scroll Spy)
        if is_active and not is_selected:
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), QColor(DesignTokens.ACCENT_PRIMARY))

        col = index.column()
        if col == 0:
            level = index.data(ROLE_LEVEL) or 1
            raw_title = index.data(ROLE_RAW_TITLE) or index.data(Qt.ItemDataRole.DisplayRole) or ""

            # Nettoyage du préfixe textuel si présent
            title_str = str(raw_title)
            if title_str.startswith(f"H{level}  "):
                title_str = title_str[len(f"H{level}  ") :]

            # Couleurs sémantiques de badge par niveau de titre
            if level == 1:
                badge_bg = QColor(DesignTokens.ACCENT_BG)
                badge_fg = QColor(DesignTokens.ACCENT_PRIMARY)
            elif level == 2:
                badge_bg = QColor(DesignTokens.COLOR_BLUE_BG)
                badge_fg = QColor(DesignTokens.COLOR_BLUE_TEXT)
            elif level == 3:
                badge_bg = QColor(DesignTokens.COLOR_PURPLE_BG)
                badge_fg = QColor(DesignTokens.COLOR_PURPLE_TEXT)
            else:
                badge_bg = QColor(DesignTokens.BG_HOVER)
                badge_fg = QColor(DesignTokens.TEXT_MUTED)

            # Dimensions et dessin du badge H1-H6
            badge_w = 26
            badge_h = 16
            badge_y = rect.top() + (rect.height() - badge_h) // 2
            badge_x = rect.left() + 4

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(QRectF(badge_x, badge_y, badge_w, badge_h), 3, 3)

            # Texte dans le badge
            badge_font = QFont(option.font)
            badge_font.setPointSize(9)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.setPen(badge_fg)
            painter.drawText(QRect(badge_x, badge_y, badge_w, badge_h), Qt.AlignmentFlag.AlignCenter, f"H{level}")

            # Texte du titre
            title_font = QFont(option.font)
            title_font.setPointSize(11)
            if level == 1:
                title_font.setBold(True)
            painter.setFont(title_font)

            if is_selected:
                title_color = QColor("#ffffff")
            elif is_active:
                title_color = QColor(DesignTokens.ACCENT_PRIMARY)
            else:
                title_color = QColor(DesignTokens.TEXT_PRIMARY)
            painter.setPen(title_color)

            title_x = badge_x + badge_w + 8
            title_w = rect.right() - title_x - 4
            title_rect = QRect(title_x, rect.top(), max(0, title_w), rect.height())
            elided = option.fontMetrics.elidedText(title_str, Qt.TextElideMode.ElideRight, title_rect.width())
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        elif col == 1:
            line_num = index.data(ROLE_LINE_NUMBER)
            words = index.data(ROLE_WORD_COUNT)
            cov_count = index.data(ROLE_COVERAGE_COUNT)

            parts: list[str] = []
            if cov_count is not None:
                parts.append("🟢" if cov_count > 0 else "⚠️")

            if words is not None:
                parts.append(f"{words} m.")
            if line_num is not None:
                parts.append(f"L.{line_num}")

            meta_text = " • ".join(parts) if parts else (index.data(Qt.ItemDataRole.DisplayRole) or "")

            meta_font = QFont(option.font)
            meta_font.setPointSize(10)
            painter.setFont(meta_font)
            painter.setPen(QColor(DesignTokens.TEXT_MUTED) if not is_selected else QColor("#ffffff"))

            painter.drawText(
                QRect(rect.left(), rect.top(), max(0, rect.width() - 8), rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                meta_text,
            )

        painter.restore()


class DocumentOutlineWidget(QWidget):
    """Panneau interactif d'arborescence Markdown avec navigation bidirectionnelle (Scroll Spy)

    et intégration directe de la couverture SRS et de la création de cartes.
    """

    heading_selected = Signal(int)  # Émet le numéro de ligne (1-indexé)
    forge_section_requested = Signal(str, str, int, int)  # (titre, contenu, start_line, end_line)
    repair_requested = Signal()
    toc_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_content: str = ""
        self._max_depth: int = 6
        self._active_item: QTreeWidgetItem | None = None
        self._coverage_data: dict[str, int] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Rangée 1 : Recherche & Bouton d'effacement ---
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Filtrer les titres...")
        self.search_input.setFixedHeight(28)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_input, 1)

        self.btn_clear_search = IconButton("ph.x", tooltip="Effacer la recherche (Échap)", size=26)
        self.btn_clear_search.clicked.connect(self._on_clear_search_clicked)
        search_layout.addWidget(self.btn_clear_search)

        layout.addLayout(search_layout)

        # --- Rangée 2 : Filtres de profondeur & Contrôles déplier/replier ---
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)

        self.depth_group = QButtonGroup(self)
        self.depth_group.setExclusive(True)

        depth_btn_style = f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """

        self.btn_depth_all = QPushButton("Tous")
        self.btn_depth_all.setCheckable(True)
        self.btn_depth_all.setChecked(True)
        self.btn_depth_all.setFixedHeight(24)
        self.btn_depth_all.setStyleSheet(depth_btn_style)
        self.depth_group.addButton(self.btn_depth_all, 6)
        controls_layout.addWidget(self.btn_depth_all)

        self.btn_depth_h1 = QPushButton("H1")
        self.btn_depth_h1.setCheckable(True)
        self.btn_depth_h1.setFixedHeight(24)
        self.btn_depth_h1.setStyleSheet(depth_btn_style)
        self.depth_group.addButton(self.btn_depth_h1, 1)
        controls_layout.addWidget(self.btn_depth_h1)

        self.btn_depth_h2 = QPushButton("H1-H2")
        self.btn_depth_h2.setCheckable(True)
        self.btn_depth_h2.setFixedHeight(24)
        self.btn_depth_h2.setStyleSheet(depth_btn_style)
        self.depth_group.addButton(self.btn_depth_h2, 2)
        controls_layout.addWidget(self.btn_depth_h2)

        self.btn_depth_h3 = QPushButton("H1-H3")
        self.btn_depth_h3.setCheckable(True)
        self.btn_depth_h3.setFixedHeight(24)
        self.btn_depth_h3.setStyleSheet(depth_btn_style)
        self.depth_group.addButton(self.btn_depth_h3, 3)
        controls_layout.addWidget(self.btn_depth_h3)

        self.depth_group.idClicked.connect(self._on_depth_filter_clicked)

        controls_layout.addStretch(1)

        self.btn_expand_all = IconButton("ph.arrows-out", tooltip="Déplier tout le plan", size=24)
        self.btn_expand_all.clicked.connect(self.tree_expand_all)
        controls_layout.addWidget(self.btn_expand_all)

        self.btn_collapse_all = IconButton("ph.arrows-in", tooltip="Replier tout le plan", size=24)
        self.btn_collapse_all.clicked.connect(self.tree_collapse_all)
        controls_layout.addWidget(self.btn_collapse_all)

        layout.addLayout(controls_layout)

        # --- Rangée 3 : Métadonnées / Synthèse documentaire ---
        self.lbl_stats = QLabel("📑 0 section • 0 mot")
        self.lbl_stats.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; padding: 1px 2px;")
        layout.addWidget(self.lbl_stats)

        # --- Arbre des titres ---
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        self.delegate = OutlineItemDelegate(self.tree)
        self.tree.setItemDelegate(self.delegate)

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
                padding: 2px;
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
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        layout.addWidget(self.tree, 1)

        # Message informatif si aucun titre Markdown détecté
        self.lbl_empty = QLabel("Aucun titre Markdown (# Titre) détecté.")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; padding: 20px;")
        self.lbl_empty.hide()
        layout.addWidget(self.lbl_empty)

        # --- Barre d'actions structurelles en bas ---
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

    def tree_expand_all(self) -> None:
        """Déplie tous les nœuds de l'arbre."""
        self.tree.expandAll()

    def tree_collapse_all(self) -> None:
        """Replie tous les nœuds de l'arbre."""
        self.tree.collapseAll()

    def set_document_content(self, content: str) -> None:
        """Met à jour l'arborescence à partir du contenu Markdown brut."""
        self._current_content = content
        self.tree.clear()
        self._active_item = None

        if not content or not content.strip():
            self.lbl_empty.show()
            self.tree.hide()
            self.lbl_stats.setText("📑 0 section • 0 mot")
            return

        tree_nodes = MarkdownStructurer.get_outline_tree(content)
        if not tree_nodes:
            self.lbl_empty.show()
            self.tree.hide()
            self.lbl_stats.setText("📑 0 section • 0 mot")
            return

        self.lbl_empty.hide()
        self.tree.show()

        total_nodes = 0
        total_words = 0
        max_level = 1

        for node in tree_nodes:
            count, words, level = self._add_node_to_tree(node, parent_item=None)
            total_nodes += count
            total_words += words
            max_level = max(max_level, level)

        self.tree.expandAll()
        self.lbl_stats.setText(f"📑 {total_nodes} sections • {total_words:,} mots • Profondeur max H{max_level}")

        # Ré-applique la couverture si des données étaient enregistrées
        if self._coverage_data:
            self.set_coverage_data(self._coverage_data)

        # Ré-applique les filtres
        self._apply_filters()

    def _add_node_to_tree(self, node: HeadingNode, parent_item: QTreeWidgetItem | None) -> tuple[int, int, int]:
        """Ajoute récursivement un nœud et ses sous-titres dans le QTreeWidget."""
        display_title = f"H{node.level}  {node.title}"
        item = QTreeWidgetItem(parent_item if parent_item is not None else self.tree)
        item.setText(0, display_title)
        item.setText(1, f"{node.word_count} m. • L{node.line_number}")

        item.setData(0, ROLE_LINE_NUMBER, node.line_number)
        item.setData(0, ROLE_LEVEL, node.level)
        item.setData(0, ROLE_WORD_COUNT, node.word_count)
        item.setData(0, ROLE_END_LINE, node.end_line or node.line_number)
        item.setData(0, ROLE_SLUG, node.slug)
        item.setData(0, ROLE_RAW_TITLE, node.title)
        item.setData(0, ROLE_IS_ACTIVE, False)

        item.setData(1, ROLE_LINE_NUMBER, node.line_number)
        item.setData(1, ROLE_WORD_COUNT, node.word_count)
        item.setData(1, ROLE_COVERAGE_COUNT, None)

        item.setToolTip(0, f"Niveau {node.level} • {node.word_count} mots • Lignes {node.line_number}-{node.end_line or node.line_number}")

        total_nodes = 1
        total_words = node.word_count
        max_level = node.level

        for child in node.children:
            c_nodes, c_words, c_level = self._add_node_to_tree(child, parent_item=item)
            total_nodes += c_nodes
            total_words += c_words
            max_level = max(max_level, c_level)

        return total_nodes, total_words, max_level

    def set_active_line(self, line_number: int) -> None:
        """Met à jour l'élément actif du plan correspondant à la ligne courante du curseur (Scroll Spy)."""
        if line_number <= 0 or self.tree.topLevelItemCount() == 0:
            return

        target_item: QTreeWidgetItem | None = None
        min_span = float("inf")

        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            start = item.data(0, ROLE_LINE_NUMBER)
            end = item.data(0, ROLE_END_LINE) or start

            if start is not None and start <= line_number <= end:
                span = end - start
                if span < min_span:
                    min_span = span
                    target_item = item

            it += 1

        if target_item and target_item != self._active_item:
            if self._active_item:
                self._active_item.setData(0, ROLE_IS_ACTIVE, False)
                self._active_item.setData(1, ROLE_IS_ACTIVE, False)

            target_item.setData(0, ROLE_IS_ACTIVE, True)
            target_item.setData(1, ROLE_IS_ACTIVE, True)
            self._active_item = target_item
            self.tree.viewport().update()
            self.tree.scrollToItem(target_item, QAbstractItemView.ScrollHint.EnsureVisible)

    def set_coverage_data(self, coverage_by_heading: dict[str, int]) -> None:
        """Associe les statistiques de fiches Anki créées (couverture SRS) aux sections du plan."""
        self._coverage_data = dict(coverage_by_heading)

        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value()
            raw_title = str(item.data(0, ROLE_RAW_TITLE) or "")
            slug = str(item.data(0, ROLE_SLUG) or "")

            count: int | None = None
            if raw_title in self._coverage_data:
                count = self._coverage_data[raw_title]
            elif slug in self._coverage_data:
                count = self._coverage_data[slug]

            item.setData(1, ROLE_COVERAGE_COUNT, count)
            if count is not None:
                badge_str = "🟢 Couvert" if count > 0 else "⚠️ Non couvert"
                tooltip = item.toolTip(0)
                item.setToolTip(0, f"{tooltip} • {badge_str} ({count} carte{'s' if count > 1 else ''})")

            it += 1

        self.tree.viewport().update()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Déclenche le saut vers la ligne correspondante et active visuellement la section."""
        line_num = item.data(0, ROLE_LINE_NUMBER)
        if line_num and isinstance(line_num, int):
            if self._active_item and self._active_item != item:
                self._active_item.setData(0, ROLE_IS_ACTIVE, False)
                self._active_item.setData(1, ROLE_IS_ACTIVE, False)

            item.setData(0, ROLE_IS_ACTIVE, True)
            item.setData(1, ROLE_IS_ACTIVE, True)
            self._active_item = item
            self.tree.viewport().update()
            self.heading_selected.emit(line_num)

    def _on_depth_filter_clicked(self, depth: int) -> None:
        """Applique le filtre de niveau de titre maximal sélectionné."""
        self._max_depth = depth
        self._apply_filters()

    def _on_search_text_changed(self, text: str) -> None:
        """Met à jour le filtrage textuel des titres."""
        self._apply_filters()

    def _on_clear_search_clicked(self) -> None:
        """Efface le champ de recherche et réinitialise les filtres."""
        self.search_input.clear()
        self.search_input.setFocus()

    def _apply_filters(self) -> None:
        """Filtre les éléments selon la requête textuelle et la profondeur active."""
        query = self.search_input.text().strip().lower()

        def filter_item(item: QTreeWidgetItem) -> bool:
            level = item.data(0, ROLE_LEVEL) or 1
            raw_title = str(item.data(0, ROLE_RAW_TITLE) or item.text(0)).lower()

            level_ok = level <= self._max_depth
            text_ok = not query or query in raw_title
            matched = level_ok and text_ok

            child_matched = False
            for i in range(item.childCount()):
                child = item.child(i)
                if child and filter_item(child):
                    child_matched = True

            visible = matched or child_matched
            item.setHidden(not visible)

            if visible and (query or self._max_depth < 6):
                item.setExpanded(True)

            return visible

        for i in range(self.tree.topLevelItemCount()):
            top_item = self.tree.topLevelItem(i)
            if top_item:
                filter_item(top_item)

    def _on_tree_context_menu(self, pos: Any) -> None:
        """Affiche le menu contextuel riche sur l'élément sous le pointeur."""
        item = self.tree.itemAt(pos)
        if not item:
            return

        line_start = item.data(0, ROLE_LINE_NUMBER)
        line_end = item.data(0, ROLE_END_LINE) or line_start
        title = str(item.data(0, ROLE_RAW_TITLE) or item.text(0))
        slug = str(item.data(0, ROLE_SLUG) or "")

        menu = StyledMenu(self)

        # ⚡ Forger cette section
        short_title = title if len(title) <= 24 else f"{title[:22]}…"
        act_forge = QAction(load_phosphor_icon("ph.lightning", color=DesignTokens.COLOR_YELLOW), f"⚡ Forger la section « {short_title} »", menu)
        act_forge.triggered.connect(lambda: self._trigger_forge_section(item))
        menu.addAction(act_forge)

        menu.addSeparator()

        # 📋 Copier l'ancre Markdown
        act_copy_anchor = QAction(load_phosphor_icon("ph.link", color=DesignTokens.COLOR_BLUE), f"📋 Copier l'ancre (#{slug})", menu)
        act_copy_anchor.triggered.connect(lambda: QGuiApplication.clipboard().setText(f"#{slug}"))
        menu.addAction(act_copy_anchor)

        # 📋 Copier le contenu de la section
        act_copy_content = QAction(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY), "📋 Copier le texte de la section", menu)
        act_copy_content.triggered.connect(lambda: self._copy_section_content(line_start, line_end))
        menu.addAction(act_copy_content)

        menu.addSeparator()

        # 🎯 Naviguer vers la section
        act_jump = QAction(load_phosphor_icon("ph.arrow-right", color=DesignTokens.ACCENT_PRIMARY), f"🎯 Aller à la ligne {line_start}", menu)
        act_jump.triggered.connect(lambda: self._on_item_clicked(item, 0))
        menu.addAction(act_jump)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _trigger_forge_section(self, item: QTreeWidgetItem) -> None:
        """Extrait le contenu de la section sélectionnée et émet le signal de forge."""
        start = item.data(0, ROLE_LINE_NUMBER)
        end = item.data(0, ROLE_END_LINE) or start
        title = str(item.data(0, ROLE_RAW_TITLE) or item.text(0))

        if not self._current_content:
            return

        lines = self._current_content.splitlines()
        if start <= len(lines):
            section_content = "\n".join(lines[start - 1 : min(end, len(lines))])
            self.forge_section_requested.emit(title, section_content, start, end)

    def _copy_section_content(self, start_line: int, end_line: int) -> None:
        """Copie dans le presse-papier le texte brut de la section délimitée."""
        if not self._current_content:
            return
        lines = self._current_content.splitlines()
        if start_line <= len(lines):
            text = "\n".join(lines[start_line - 1 : min(end_line, len(lines))])
            QGuiApplication.clipboard().setText(text)

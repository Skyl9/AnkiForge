import logging
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, IconButton
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DuplicateMatrixTable(QFrame):
    """Matrice des doublons détectés (Upper section)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. Title Row
        h_title = QHBoxLayout()
        h_title.setContentsMargins(0, 0, 0, 8)
        lbl_title = QLabel(" Matrice de Doublons Détectés")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.COLOR_PURPLE};")

        badge_count = QLabel("14 paires à examiner")
        badge_count.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        badge_count.setStyleSheet(f"background: rgba(168,85,247,0.2); color: {DesignTokens.COLOR_PURPLE}; padding: 3px 9px; border-radius: 5px;")

        h_title.addWidget(lbl_title)
        h_title.addStretch()
        h_title.addWidget(badge_count)
        layout.addLayout(h_title)

        # 2. Action Bar
        h_actions = QHBoxLayout()
        h_actions.setContentsMargins(0, 0, 0, 0)
        h_actions.setSpacing(12)

        # Group 1: Target deck & Analyze
        lbl_target = QLabel("PAQUET CIBLE :")
        lbl_target.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_target.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")

        self.btn_deck = SecondaryButton("Informatique::C++")
        self.btn_deck.setIcon(load_phosphor_icon("folder", color=DesignTokens.ACCENT_PRIMARY))

        self.btn_reanalyze = PrimaryButton("Relancer l'analyse")
        self.btn_reanalyze.setIcon(load_phosphor_icon("arrows-clockwise", color="#ffffff"))

        h_actions.addWidget(lbl_target)
        h_actions.addWidget(self.btn_deck)
        h_actions.addWidget(self.btn_reanalyze)

        # Group 2: Filters & Threshold
        lbl_filters = QLabel("FILTRES :")
        lbl_filters.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_filters.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; margin-left: 10px;")

        self.btn_filter_all = SecondaryButton("Toutes (14)")
        self.btn_filter_all.setStyleSheet(f"background: rgba(99, 102, 241, 0.25); border: 1px solid {DesignTokens.ACCENT_PRIMARY}; color: #ffffff;")
        self.btn_filter_95 = SecondaryButton(">95% Identiques (4)")

        h_actions.addWidget(lbl_filters)
        h_actions.addWidget(self.btn_filter_all)
        h_actions.addWidget(self.btn_filter_95)

        lbl_threshold = QLabel("Seuil :")
        lbl_threshold.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_threshold.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; margin-left: 10px;")

        self.combo_threshold = QComboBox()
        self.combo_threshold.addItems(["Seuil > 80%", "Seuil > 90%", "Seuil > 95%"])
        self.combo_threshold.setCurrentIndex(1)

        h_actions.addWidget(lbl_threshold)
        h_actions.addWidget(self.combo_threshold)

        h_actions.addStretch()

        # Group 3: Auto-merge
        self.btn_auto_merge = PrimaryButton("Auto-fusionner >95%")
        self.btn_auto_merge.setIcon(load_phosphor_icon("lightning", color="#ffffff"))
        self.btn_auto_merge.setStyleSheet(f"background: rgba(99,102,241,0.2); border: 1px solid {DesignTokens.ACCENT_PRIMARY};")

        h_actions.addWidget(self.btn_auto_merge)
        layout.addLayout(h_actions)

        # 3. Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Similitude", "Carte A (Originale)", "Carte B (Duplicata)", "Niveau de Maîtrise", "Statut"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(4, 180)
        self.table.setColumnWidth(5, 100)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"QTableWidget {{ background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")

        layout.addWidget(self.table)

    def add_row(self, note_a, content_a, note_b, content_b, similarity, row_data):
        row = self.table.rowCount()
        self.table.insertRow(row)

        cb = QCheckBox()
        cb.setChecked(True)
        cb_widget = QWidget()
        cb_layout = QHBoxLayout(cb_widget)
        cb_layout.addWidget(cb)
        cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.table.setCellWidget(row, 0, cb_widget)

        sim_str = f"{similarity*100:.1f} % C"
        if similarity > 0.95:
            rgba_bg = "rgba(239,68,68,0.25)"
            color = "#f87171"
        else:
            rgba_bg = "rgba(245,158,11,0.25)"
            color = DesignTokens.COLOR_YELLOW

        lbl_sim = QLabel(sim_str)
        lbl_sim.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_sim.setStyleSheet(f"background: {rgba_bg}; color: {color}; padding: 3px 9px; border-radius: 5px;")
        sim_widget = QWidget()
        sim_layout = QHBoxLayout(sim_widget)
        sim_layout.addWidget(lbl_sim)
        sim_layout.setContentsMargins(5, 5, 5, 5)
        self.table.setCellWidget(row, 1, sim_widget)

        cardA = content_a.get("Recto", content_a.get("Text", str(note_a.id)))
        item_a = QTableWidgetItem(cardA[:100] + "..." if len(cardA) > 100 else cardA)
        item_a.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        item_a.setData(Qt.ItemDataRole.UserRole, row_data)
        self.table.setItem(row, 2, item_a)

        cardB = content_b.get("Recto", content_b.get("Text", str(note_b.id)))
        item_b = QTableWidgetItem(cardB[:100] + "..." if len(cardB) > 100 else cardB)
        item_b.setForeground(QColor(DesignTokens.TEXT_SECONDARY))
        self.table.setItem(row, 3, item_b)

        srs = "🟡 À examiner"
        item_srs = QTableWidgetItem(srs)
        self.table.setItem(row, 4, item_srs)

        status = "En attente"
        item_status = QTableWidgetItem(status)
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setItem(row, 5, item_status)


class DuplicateMergeInspector(QFrame):
    """Inspecteur de fusion à 3 colonnes (Bottom section)."""

    merge_requested = Signal(object, object, dict)  # note_keep, note_delete, merged_content
    ignore_requested = Signal(object, object)  # note_a, note_b

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from typing import Dict, Any

        self.current_conflict: Optional[Dict[str, Any]] = None
        self.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. Header with navigation and swap
        h_header = QHBoxLayout()
        h_header.setContentsMargins(0, 0, 0, 8)

        lbl_title = QLabel(" Inspection & Fusion de Paire")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        h_header.addWidget(lbl_title)

        nav_widget = QFrame()
        nav_widget.setStyleSheet(f"background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 2px;")
        nav_layout = QHBoxLayout(nav_widget)
        nav_layout.setContentsMargins(4, 2, 4, 2)
        nav_layout.setSpacing(4)

        btn_prev = IconButton("caret-left", "", 12)
        btn_prev.setFixedSize(24, 24)
        lbl_nav = QLabel("Paire #1 / 14")
        lbl_nav.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        btn_next = IconButton("caret-right", "", 12)
        btn_next.setFixedSize(24, 24)

        nav_layout.addWidget(btn_prev)
        nav_layout.addWidget(lbl_nav)
        nav_layout.addWidget(btn_next)
        h_header.addWidget(nav_widget)

        self.btn_swap = SecondaryButton("Permuter A ↔ B")
        self.btn_swap.setIcon(load_phosphor_icon("arrows-left-right", color=DesignTokens.COLOR_PURPLE))
        self.btn_swap.setStyleSheet(f"background: rgba(168,85,247,0.15); border-color: {DesignTokens.COLOR_PURPLE}; color: {DesignTokens.COLOR_PURPLE};")
        h_header.addWidget(self.btn_swap)

        h_header.addStretch()

        self.lbl_sim = QLabel("Indice de similitude C : --%")
        self.lbl_sim.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        self.lbl_sim.setStyleSheet("background: rgba(239,68,68,0.2); color: #f87171; padding: 3px 9px; border-radius: 5px;")
        h_header.addWidget(self.lbl_sim)

        layout.addLayout(h_header)

        # 2. 3 Columns layout
        h_cols = QHBoxLayout()
        h_cols.setSpacing(14)

        # Col 1: Card A
        self.col_a, self.lbl_title_a, self.lbl_content_a, self.btn_keep_a = self._create_card_col("CARTE #1", DesignTokens.COLOR_BLUE, "...", "➔ Injecter", "Conserver Carte #1 (Originale)")
        h_cols.addWidget(self.col_a)

        # Col 2: Fusion
        self.col_fusion = QFrame()
        self.col_fusion.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; border: 2px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 6px;")
        f_layout = QVBoxLayout(self.col_fusion)
        f_layout.setContentsMargins(12, 12, 12, 12)

        f_header = QHBoxLayout()
        f_title = QLabel("CARTE FUSIONNÉE")
        f_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        f_title.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY};")
        f_header.addWidget(f_title)
        f_header.addStretch()

        btn_source = SecondaryButton("📝 Source")
        btn_source.setFixedHeight(20)
        btn_source.setStyleSheet(f"background: rgba(99, 102, 241, 0.25); border: 1px solid {DesignTokens.ACCENT_PRIMARY}; color: #ffffff; font-size: 9px;")
        f_header.addWidget(btn_source)
        f_layout.addLayout(f_header)

        self.f_body = QFrame()
        self.f_body.setStyleSheet(f"background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        f_layout.addWidget(self.f_body, 1)

        self.merged_content_layout = QVBoxLayout(self.f_body)
        self.lbl_merged = QLabel("...")
        self.lbl_merged.setWordWrap(True)
        self.lbl_merged.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        self.merged_content_layout.addWidget(self.lbl_merged)

        # Actions
        f_actions = QHBoxLayout()
        self.btn_valid = PrimaryButton("Valider la fusion")
        self.btn_valid.setIcon(load_phosphor_icon("check", color="#ffffff"))
        self.btn_ignore = SecondaryButton("Ignorer")
        self.btn_false = SecondaryButton("Faux Doublon")
        self.btn_false.setStyleSheet("border-color: rgba(239,68,68,0.5); color: #f87171;")
        f_actions.addWidget(self.btn_valid, 1)
        f_actions.addWidget(self.btn_ignore)
        f_actions.addWidget(self.btn_false)
        f_layout.addLayout(f_actions)

        h_cols.addWidget(self.col_fusion, 1)

        # Col 3: Card B
        self.col_b, self.lbl_title_b, self.lbl_content_b, self.btn_keep_b = self._create_card_col("CARTE #2", DesignTokens.COLOR_PURPLE, "...", "⬅ Injecter", "Conserver Carte #2 (Duplicata)")
        h_cols.addWidget(self.col_b)

        layout.addLayout(h_cols)

        self.btn_keep_a.clicked.connect(lambda: self.set_merged_content("A"))
        self.btn_keep_b.clicked.connect(lambda: self.set_merged_content("B"))
        self.btn_valid.clicked.connect(self.on_validate)
        self.btn_ignore.clicked.connect(self.on_ignore)
        self.btn_false.clicked.connect(self.on_ignore)

    def _create_card_col(self, title: str, color: str, content: str, btn_text: str, action_text: str):
        col = QFrame()
        col.setStyleSheet(f"background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px;")
        layout_col = QVBoxLayout(col)
        layout_col.setContentsMargins(12, 12, 12, 12)

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {color}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 6px;")
        layout_col.addWidget(lbl_title)

        body = QFrame()
        body.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        b_layout = QVBoxLayout(body)

        field_header = QHBoxLayout()
        field_lbl = QLabel("1. RECTO :")
        field_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        field_lbl.setStyleSheet(f"color: {color};")
        btn_inject = SecondaryButton(btn_text)
        btn_inject.setFixedHeight(18)
        btn_inject.setFont(QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold))
        field_header.addWidget(field_lbl)
        field_header.addStretch()
        field_header.addWidget(btn_inject)
        b_layout.addLayout(field_header)

        lbl_content = QLabel(content)
        lbl_content.setFont(QFont(DesignTokens.FONT_CODE, 10))
        lbl_content.setWordWrap(True)
        lbl_content.setAlignment(Qt.AlignmentFlag.AlignTop)
        b_layout.addWidget(lbl_content, 1)

        btn_action = SecondaryButton(action_text)
        btn_action.setCursor(Qt.CursorShape.PointingHandCursor)

        layout_col.addWidget(body, 1)
        layout_col.addWidget(btn_action)
        return col, lbl_title, lbl_content, btn_action

    def load_conflict(self, row_data: dict) -> None:
        self.current_conflict = row_data
        sim = row_data.get("sim", 0.0)
        self.lbl_sim.setText(f"Indice de similitude C : {sim*100:.1f}%")

        note_a = row_data["note_a"]
        content_a = row_data["content_a"]
        note_b = row_data["note_b"]
        content_b = row_data["content_b"]

        self.lbl_title_a.setText(f"CARTE #1 (Originale #{note_a.id})")
        self.lbl_content_a.setText(content_a.get("Recto", content_a.get("Text", "")))

        self.lbl_title_b.setText(f"CARTE #2 (Duplicata #{note_b.id})")
        self.lbl_content_b.setText(content_b.get("Recto", content_b.get("Text", "")))

        self.set_merged_content("A")

    def set_merged_content(self, source: str) -> None:
        if not self.current_conflict:
            return
        content = self.current_conflict["content_a"] if source == "A" else self.current_conflict["content_b"]
        self.lbl_merged.setText(content.get("Recto", content.get("Text", "")))
        self.current_conflict["merged_content"] = content

    def on_validate(self) -> None:
        if not self.current_conflict:
            return
        note_keep = self.current_conflict["note_a"]
        note_del = self.current_conflict["note_b"]
        merged = self.current_conflict.get("merged_content", self.current_conflict["content_a"])
        self.merge_requested.emit(note_keep, note_del, merged)

    def on_ignore(self) -> None:
        if not self.current_conflict:
            return
        self.ignore_requested.emit(self.current_conflict["note_a"], self.current_conflict["note_b"])

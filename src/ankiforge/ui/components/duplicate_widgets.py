import logging
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt
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

        # Mock Data
        self.add_mock_row(
            "94.2 % C",
            "std::unique_ptr vs std::shared_ptr en C++20...",
            "Quelles différences entre unique_ptr et shared_ptr ?",
            "🟢 Maîtrisée vs 🟡 En apprentissage",
            "En révision ▼",
            "#f87171",
            rgba_bg="rgba(239,68,68,0.25)",
        )
        self.add_mock_row(
            "98.0 % C", "Enoncer la formule de Bayes...", "Calculer P(A|B) avec le théorème de Bayes.", "🟢 Maîtrisée vs 🟡 En apprentissage", "En attente", "#f87171", rgba_bg="rgba(239,68,68,0.25)"
        )
        self.add_mock_row(
            "91.5 % C",
            "Complexité temporelle pire cas du tri Quicksort.",
            "Pire cas Quicksort O(N^2) et choix du pivot.",
            "🟡 12 révisions vs 🟡 15 révisions",
            "En attente",
            DesignTokens.COLOR_YELLOW,
            rgba_bg="rgba(245,158,11,0.25)",
        )

    def add_mock_row(self, sim: str, cardA: str, cardB: str, srs: str, status: str, color: str, rgba_bg: str):
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

        lbl_sim = QLabel(sim)
        lbl_sim.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_sim.setStyleSheet(f"background: {rgba_bg}; color: {color}; padding: 3px 9px; border-radius: 5px;")
        sim_widget = QWidget()
        sim_layout = QHBoxLayout(sim_widget)
        sim_layout.addWidget(lbl_sim)
        sim_layout.setContentsMargins(5, 5, 5, 5)
        self.table.setCellWidget(row, 1, sim_widget)

        item_a = QTableWidgetItem(cardA)
        item_a.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.table.setItem(row, 2, item_a)

        item_b = QTableWidgetItem(cardB)
        item_b.setForeground(QColor(DesignTokens.TEXT_SECONDARY))
        self.table.setItem(row, 3, item_b)

        item_srs = QTableWidgetItem(srs)
        self.table.setItem(row, 4, item_srs)

        item_status = QTableWidgetItem(status)
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if "révision" in status:
            item_status.setForeground(QColor(DesignTokens.ACCENT_PRIMARY))
        self.table.setItem(row, 5, item_status)


class DuplicateMergeInspector(QFrame):
    """Inspecteur de fusion à 3 colonnes (Bottom section)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
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

        btn_swap = SecondaryButton("Permuter A ↔ B")
        btn_swap.setIcon(load_phosphor_icon("arrows-left-right", color=DesignTokens.COLOR_PURPLE))
        btn_swap.setStyleSheet(f"background: rgba(168,85,247,0.15); border-color: {DesignTokens.COLOR_PURPLE}; color: {DesignTokens.COLOR_PURPLE};")
        h_header.addWidget(btn_swap)

        h_header.addStretch()

        lbl_sim = QLabel("Indice de similitude C : 94.2%")
        lbl_sim.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_sim.setStyleSheet("background: rgba(239,68,68,0.2); color: #f87171; padding: 3px 9px; border-radius: 5px;")
        h_header.addWidget(lbl_sim)

        layout.addLayout(h_header)

        # 2. 3 Columns layout
        h_cols = QHBoxLayout()
        h_cols.setSpacing(14)

        # Col 1: Card A
        col_a = self._create_card_col("CARTE #1 (Originale #4012)", DesignTokens.COLOR_BLUE, "std::unique_ptr vs std::shared_ptr en C++20...", "➔ Injecter", "Conserver Carte #1 (Originale)")
        h_cols.addWidget(col_a)

        # Col 2: Fusion
        col_fusion = QFrame()
        col_fusion.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; border: 2px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 6px;")
        f_layout = QVBoxLayout(col_fusion)
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

        f_body = QFrame()
        f_body.setStyleSheet(f"background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px;")
        f_layout.addWidget(f_body, 1)

        # Actions
        f_actions = QHBoxLayout()
        btn_valid = PrimaryButton("Valider la fusion")
        btn_valid.setIcon(load_phosphor_icon("check", color="#ffffff"))
        btn_ignore = SecondaryButton("Ignorer")
        btn_false = SecondaryButton("Faux Doublon")
        btn_false.setStyleSheet("border-color: rgba(239,68,68,0.5); color: #f87171;")
        f_actions.addWidget(btn_valid, 1)
        f_actions.addWidget(btn_ignore)
        f_actions.addWidget(btn_false)
        f_layout.addLayout(f_actions)

        h_cols.addWidget(col_fusion, 1)

        # Col 3: Card B
        col_b = self._create_card_col("CARTE #2 (Duplicata #4088)", DesignTokens.COLOR_PURPLE, "Quelles différences entre unique_ptr et shared_ptr ?", "⬅ Injecter", "Conserver Carte #2 (Duplicata)")
        h_cols.addWidget(col_b)

        layout.addLayout(h_cols)

    def _create_card_col(self, title: str, color: str, content: str, btn_text: str, action_text: str) -> QFrame:
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
        return col

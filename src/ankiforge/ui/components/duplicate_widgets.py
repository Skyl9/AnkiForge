import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.utils.anki_renderer import get_mathjax_script
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DuplicateMatrixTable(QFrame):
    """Matrice des doublons détectés (Upper section)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DuplicateMatrixTable")
        self.setStyleSheet(f"""
            QFrame#DuplicateMatrixTable {{ 
                background: {DesignTokens.BG_PANEL}; 
                border: 1px solid {DesignTokens.BORDER_COLOR}; 
                border-radius: 8px; 
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.COLOR_BLUE};
                border: 1px solid {DesignTokens.COLOR_BLUE};
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAyNCAyNCcgZmlsbD0nbm9uZScgc3Ryb2tlPSd3aGl0ZScgc3Ryb2tlLXdpZHRoPSc0JyBzdHJva2UtbGluZWNhcD0ncm91bmQnIHN0cm9rZS1saW5lam9pbj0ncm91bmQnPjxwb2x5bGluZSBwb2ludHM9JzIwIDYgOSAxNyA0IDEyJz48L3BvbHlsaW5lPjwvc3ZnPg==);
            }}
        """)  # noqa: E501

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # 1. Title Row
        h_title = QHBoxLayout()
        h_title.setContentsMargins(0, 0, 0, 8)

        icon_title = QLabel()
        icon_title.setPixmap(load_phosphor_icon("git-diff", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))

        lbl_title = QLabel("Matrice de Doublons Détectés")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY};")

        badge_count = QLabel("14 paires à examiner")
        badge_count.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        badge_count.setStyleSheet(
            f"background: {DesignTokens.BG_ACTIVE}; color: {DesignTokens.ACCENT_PRIMARY}; padding: 3px 10px; border-radius: 9999px; border: 1px solid {DesignTokens.BORDER_COLOR};"
        )

        h_title.addWidget(icon_title)
        h_title.addWidget(lbl_title)
        h_title.addStretch()
        h_title.addWidget(badge_count)
        layout.addLayout(h_title)

        # 1.5 Divider
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BORDER_COLOR}; border: none; }}")
        layout.addWidget(divider)

        # 2. Action Bar - Ligne 1
        h_line1 = QHBoxLayout()
        h_line1.setContentsMargins(0, 0, 0, 4)
        h_line1.setSpacing(12)

        lbl_target = QLabel("PAQUET CIBLE :")
        lbl_target.setFont(QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold))
        lbl_target.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")

        self.btn_deck = SecondaryButton("L'ensemble des paquets")
        self.btn_deck.setIcon(load_phosphor_icon("folder", color=DesignTokens.ACCENT_PRIMARY))

        h_line1.addWidget(lbl_target)
        h_line1.addWidget(self.btn_deck)
        h_line1.addStretch()

        self.btn_reanalyze = PrimaryButton("Relancer l'analyse")
        self.btn_reanalyze.setIcon(load_phosphor_icon("arrows-clockwise", color="#ffffff"))
        h_line1.addWidget(self.btn_reanalyze)

        layout.addLayout(h_line1)

        # 3. Action Bar - Ligne 2
        h_line2 = QHBoxLayout()
        h_line2.setContentsMargins(0, 0, 0, 8)
        h_line2.setSpacing(12)

        lbl_filters = QLabel("FILTRES :")
        lbl_filters.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_filters.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; margin-left: 10px;")

        def create_filter_btn(text: str, is_active: bool = False) -> SecondaryButton:
            btn = SecondaryButton(text)
            if is_active:
                btn.setStyleSheet(
                    f"background: {DesignTokens.BG_ACTIVE}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; color: {DesignTokens.ACCENT_PRIMARY}; padding: 4px 10px; border-radius: 5px;"
                )
            else:
                btn.setStyleSheet(f"background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_SECONDARY}; padding: 4px 10px; border-radius: 5px;")
            return btn

        self.btn_filter_all = create_filter_btn("Toutes (14)", is_active=True)
        self.btn_filter_95 = create_filter_btn(">95% Identiques (4)")
        self.btn_filter_katex = create_filter_btn("KaTeX (5)")
        self.btn_filter_srs = create_filter_btn("Écarts de Maîtrise (3)")

        h_line2.addWidget(lbl_filters)
        h_line2.addWidget(self.btn_filter_all)
        h_line2.addWidget(self.btn_filter_95)
        h_line2.addWidget(self.btn_filter_katex)
        h_line2.addWidget(self.btn_filter_srs)

        lbl_threshold = QLabel("Seuil :")
        lbl_threshold.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_threshold.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; margin-left: 10px;")

        self.combo_threshold = QComboBox()
        self.combo_threshold.addItems(["Seuil > 80%", "Seuil > 90%", "Seuil > 95%"])
        self.combo_threshold.setCurrentIndex(1)

        h_line2.addWidget(lbl_threshold)
        h_line2.addWidget(self.combo_threshold)
        h_line2.addStretch()

        self.btn_auto_merge = PrimaryButton("Auto-fusionner >95%")
        self.btn_auto_merge.setIcon(load_phosphor_icon("lightning", color="#ffffff"))
        self.btn_auto_merge.setStyleSheet(f"background: {DesignTokens.BG_ACTIVE}; border: 1px solid {DesignTokens.ACCENT_PRIMARY};")

        h_line2.addWidget(self.btn_auto_merge)
        layout.addLayout(h_line2)

        # 3. Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Similitude", "Carte A (Originale)", "Carte B (Duplicata)", "Niveau de Maîtrise", "Statut"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(4, 180)
        self.table.setColumnWidth(5, 100)

        self.table.verticalHeader().setDefaultSectionSize(40)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)

        # Style the header and table to match the maquette
        self.table.horizontalHeader().setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
                font-size: 10px;
                text-transform: uppercase;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 9px 12px;
            }}
        """)
        self.table.setStyleSheet(f"""
            QTableWidget {{ 
                background: {DesignTokens.BG_MAIN}; 
                border: 1px solid {DesignTokens.BORDER_COLOR}; 
                border-radius: 6px; 
            }}
            QTableWidget::item {{
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout.addWidget(self.table)

        # 4. Global "Check All" CheckBox in the Header
        self.check_all = QCheckBox(self.table.horizontalHeader())
        self.check_all.setFixedSize(16, 16)
        self.check_all.move(12, 7)  # Centers in the 40px col (40/2 - 16/2 = 12), and in 30px height header (30/2 - 16/2 = 7)
        self.check_all.setChecked(True)
        self.check_all.stateChanged.connect(self._toggle_all_rows)

    def _toggle_all_rows(self, state: int):
        is_checked = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, 0)
            if widget:
                cb = widget.findChild(QCheckBox)
                if cb:
                    cb.setChecked(is_checked)

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

        sim_str = f"{similarity * 100:.1f} % C"
        if similarity > 0.95:
            rgba_bg = "rgba(239,68,68,0.25)"
            color = DesignTokens.COLOR_RED
        else:
            rgba_bg = "rgba(245,158,11,0.25)"
            color = DesignTokens.COLOR_YELLOW

        lbl_sim = QLabel(sim_str)
        lbl_sim.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_sim.setStyleSheet(f"background: {rgba_bg}; color: {color}; padding: 3px 10px; border-radius: 9999px; border: 1px solid {color};")
        sim_widget = QWidget()
        sim_layout = QHBoxLayout(sim_widget)
        sim_layout.addWidget(lbl_sim)
        sim_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        sim_layout.setContentsMargins(10, 5, 5, 5)
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

        def _get_srs_str_color(note):
            has_srs = hasattr(note, "srs_ivl") or (hasattr(note, "cards") and len(note.cards) > 0 and hasattr(note.cards[0], "srs_ivl"))
            if has_srs:
                reps = getattr(note, "srs_reps", 0)
                if reps > 21:
                    return "🟢 Maîtrisée", DesignTokens.COLOR_GREEN
                elif reps > 5:
                    return "🟡 En apprentissage", DesignTokens.COLOR_YELLOW
                else:
                    return "🔴 Nouvelle", DesignTokens.COLOR_RED
            else:
                return "⚪ Non étudiée", DesignTokens.TEXT_MUTED

        str_a, color_a = _get_srs_str_color(note_a)
        str_b, color_b = _get_srs_str_color(note_b)

        lbl_srs = QLabel(
            f"<span style='color: {color_a}; font-weight: bold;'>{str_a}</span> \
            <span style='color: {DesignTokens.TEXT_MUTED}; font-weight: normal;'> vs </span> \
            <span style='color: {color_b}; font-weight: bold;'>{str_b}</span>"
        )
        lbl_srs.setFont(QFont(DesignTokens.FONT_MAIN, 9))

        srs_cell_widget = QWidget()
        srs_cell_layout = QHBoxLayout(srs_cell_widget)
        srs_cell_layout.addWidget(lbl_srs)
        srs_cell_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        srs_cell_layout.setContentsMargins(10, 0, 0, 0)
        self.table.setCellWidget(row, 4, srs_cell_widget)

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
        from typing import Any, Dict

        self.current_conflict: Optional[Dict[str, Any]] = None
        self.view_modes = {"A": "source", "B": "source", "Fusion": "source"}
        self.setObjectName("DuplicateMergeInspector")
        self.setStyleSheet(f"QFrame#DuplicateMergeInspector {{ background: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 8px; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # 1. Header with navigation and swap
        h_header = QHBoxLayout()
        h_header.setContentsMargins(0, 0, 0, 8)

        icon_merge = QLabel()
        icon_merge.setPixmap(load_phosphor_icon("git-merge", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))

        lbl_title = QLabel("Inspection & Fusion de Paire")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        h_header.addWidget(icon_merge)
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

        self.btn_swap = QPushButton(" Permuter A ↔ B")
        self.btn_swap.setIcon(load_phosphor_icon("arrows-left-right", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_swap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swap.setStyleSheet(f"""
            QPushButton {{
                background: {DesignTokens.BG_ACTIVE}; 
                border: 1px solid {DesignTokens.ACCENT_PRIMARY}; 
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px 10px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_swap.clicked.connect(self.on_swap)
        h_header.addWidget(self.btn_swap)

        h_header.addStretch()

        self.lbl_sim = QLabel("Indice de similitude C : --%")
        self.lbl_sim.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        self.lbl_sim.setStyleSheet(f"background: rgba(239,68,68,0.2); color: {DesignTokens.COLOR_RED}; padding: 3px 10px; border-radius: 9999px; border: 1px solid rgba(239,68,68,0.4);")
        h_header.addWidget(self.lbl_sim)

        layout.addLayout(h_header)

        # 2. 3 Columns layout
        h_cols = QHBoxLayout()
        h_cols.setSpacing(14)

        # Col 1: Card A
        self.col_a, self.lbl_title_a, self.layout_a, self.btn_keep_a, self.srs_a = self._create_card_col("CARTE #1", DesignTokens.COLOR_BLUE, "➔ Injecter", "Conserver Carte #1 (Originale)")
        h_cols.addWidget(self.col_a)

        # Col 2: Fusion
        self.col_fusion = QFrame()
        self.col_fusion.setObjectName("MergeColFusion")
        self.col_fusion.setStyleSheet(f"QFrame#MergeColFusion {{ background: {DesignTokens.BG_PANEL}; border: 2px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 6px; }}")
        f_layout = QVBoxLayout(self.col_fusion)
        f_layout.setContentsMargins(12, 12, 12, 12)

        f_header = QHBoxLayout()
        icon_sparkle = QLabel()
        icon_sparkle.setPixmap(load_phosphor_icon("sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        f_title = QLabel("CARTE FUSIONNÉE")
        f_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        f_title.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY};")
        f_header.addWidget(icon_sparkle)
        f_header.addWidget(f_title)
        f_header.addStretch()

        b_src, b_ktx = self._create_view_toggles("Fusion", DesignTokens.ACCENT_PRIMARY)
        f_header.addWidget(b_src)
        f_header.addWidget(b_ktx)
        f_layout.addLayout(f_header)

        self.f_body = QFrame()
        self.f_body.setObjectName("FusionBodyFrame")
        self.f_body.setStyleSheet(f"QFrame#FusionBodyFrame {{ background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; }}")
        f_layout.addWidget(self.f_body, 1)

        self.merged_content_layout = QVBoxLayout(self.f_body)
        self.merged_content_layout.setContentsMargins(12, 12, 12, 12)

        # Actions
        f_actions = QHBoxLayout()
        self.btn_valid = PrimaryButton("Valider la fusion")
        self.btn_valid.setIcon(load_phosphor_icon("check", color="#ffffff"))
        self.btn_ignore = SecondaryButton("Ignorer")

        self.btn_false = SecondaryButton("Faux Doublon")
        self.btn_false.setIcon(load_phosphor_icon("prohibit", color=DesignTokens.COLOR_RED))
        self.btn_false.setStyleSheet(f"border-color: rgba(239,68,68,0.5); color: {DesignTokens.COLOR_RED};")

        f_actions.addWidget(self.btn_valid, 1)
        f_actions.addWidget(self.btn_ignore)
        f_actions.addWidget(self.btn_false)
        f_layout.addLayout(f_actions)

        h_cols.addWidget(self.col_fusion, 1)

        # Col 3: Card B
        self.col_b, self.lbl_title_b, self.layout_b, self.btn_keep_b, self.srs_b = self._create_card_col("CARTE #2", DesignTokens.ACCENT_PRIMARY, "⬅ Injecter", "Conserver Carte #2 (Duplicata)")
        h_cols.addWidget(self.col_b)

        layout.addLayout(h_cols)

        self.btn_keep_a.clicked.connect(lambda: self.set_merged_content("A"))
        self.btn_keep_b.clicked.connect(lambda: self.set_merged_content("B"))
        self.btn_valid.clicked.connect(self.on_validate)
        self.btn_ignore.clicked.connect(self.on_ignore)
        self.btn_false.clicked.connect(self.on_ignore)

    def _create_card_col(self, title: str, color: str, btn_text: str, action_text: str):
        col = QFrame()
        col.setObjectName("CardCol" + title.replace(" ", "").replace("#", ""))
        col.setStyleSheet(f"QFrame#{col.objectName()} {{ background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        layout_col = QVBoxLayout(col)
        layout_col.setContentsMargins(12, 12, 12, 12)

        title_layout = QHBoxLayout()
        icon = "cards" if "CARTE #1" in title else "copy"
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(icon, color=color).pixmap(14, 14))

        lbl_title = QLabel(title)
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {color};")
        title_layout.addWidget(icon_lbl)
        title_layout.addWidget(lbl_title)
        title_layout.addStretch()

        source_key = "A" if "CARTE #1" in title else "B"
        b_src, b_ktx = self._create_view_toggles(source_key, color)
        title_layout.addWidget(b_src)
        title_layout.addWidget(b_ktx)

        header_container = QWidget()
        header_container.setLayout(title_layout)
        header_container.setStyleSheet(f"border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; margin-bottom: 6px;")
        layout_col.addWidget(header_container)

        # SRS Badges
        srs_layout = QHBoxLayout()
        srs_layout.setContentsMargins(0, 0, 0, 6)
        srs_layout.setSpacing(6)

        lbl_srs_state = QLabel("🟢 Carte Maîtrisée (42 révisions)")
        lbl_srs_state.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        lbl_srs_state.setStyleSheet(f"background: rgba(16,185,129,0.2); color: {DesignTokens.COLOR_GREEN}; padding: 2px 6px; border-radius: 4px;")

        lbl_srs_ivl = QLabel("Revoir dans : 35 jours")
        lbl_srs_ivl.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        lbl_srs_ivl.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_SECONDARY}; padding: 2px 6px; border-radius: 4px;")

        lbl_srs_ease = QLabel("Facilité : 250%")
        lbl_srs_ease.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        lbl_srs_ease.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_MUTED}; padding: 2px 6px; border-radius: 4px;")

        srs_layout.addWidget(lbl_srs_state)
        srs_layout.addWidget(lbl_srs_ivl)
        srs_layout.addWidget(lbl_srs_ease)
        srs_layout.addStretch()

        layout_col.addLayout(srs_layout)

        body = QFrame()
        body.setObjectName("CardColBody")
        body.setStyleSheet(f"QFrame#CardColBody {{ background: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; }}")
        b_layout = QVBoxLayout(body)

        btn_action = SecondaryButton(action_text)
        btn_action.setCursor(Qt.CursorShape.PointingHandCursor)

        layout_col.addWidget(body, 1)
        layout_col.addWidget(btn_action)
        return col, lbl_title, b_layout, btn_action, {"state": lbl_srs_state, "ivl": lbl_srs_ivl, "ease": lbl_srs_ease}

    def _create_view_toggles(self, source: str, active_color: str):
        btn_source = SecondaryButton("📝 Source")
        btn_source.setFixedHeight(20)
        btn_source.setFont(QFont(DesignTokens.FONT_MAIN, 9))

        btn_katex = SecondaryButton("👁️ KaTeX")
        btn_katex.setFixedHeight(20)
        btn_katex.setFont(QFont(DesignTokens.FONT_MAIN, 9))

        def _update_styles():
            mode = self.view_modes.get(source, "source")
            rgba_bg = active_color.replace("rgb", "rgba").replace(")", ", 0.25)") if "rgb" in active_color else f"{active_color}40"  # rough alpha
            if active_color.startswith("#"):
                rgba_bg = f"rgba({int(active_color[1:3], 16)}, {int(active_color[3:5], 16)}, {int(active_color[5:7], 16)}, 0.25)"

            if mode == "source":
                btn_source.setStyleSheet(f"background: {rgba_bg}; color: {active_color}; border: 1px solid {active_color}; padding: 0 4px; font-weight: bold;")
                btn_katex.setStyleSheet(f"background: transparent; color: {DesignTokens.TEXT_SECONDARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 0 4px;")
            else:
                btn_source.setStyleSheet(f"background: transparent; color: {DesignTokens.TEXT_SECONDARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 0 4px;")
                btn_katex.setStyleSheet(f"background: {rgba_bg}; color: {active_color}; border: 1px solid {active_color}; padding: 0 4px; font-weight: bold;")

        _update_styles()

        def _on_source():
            self.view_modes[source] = "source"
            _update_styles()
            self._refresh_col(source)

        def _on_katex():
            self.view_modes[source] = "katex"
            _update_styles()
            self._refresh_col(source)

        btn_source.clicked.connect(_on_source)
        btn_katex.clicked.connect(_on_katex)

        return btn_source, btn_katex

    def _refresh_col(self, source: str) -> None:
        if not self.current_conflict:
            return
        if source == "A":
            self._populate_fields(self.layout_a, self.current_conflict["content_a"], DesignTokens.COLOR_BLUE, "➔ Injecter", "A")
        elif source == "B":
            self._populate_fields(self.layout_b, self.current_conflict["content_b"], DesignTokens.ACCENT_PRIMARY, "⬅ Injecter", "B")
        elif source == "Fusion":
            self._populate_fields(self.merged_content_layout, self.current_conflict.get("merged_content", {}), DesignTokens.ACCENT_PRIMARY, "", "Fusion")

    def _clear_layout(self, layout) -> None:
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                elif item.layout() is not None:
                    self._clear_layout(item.layout())

    def _populate_fields(self, layout: QVBoxLayout, content_dict: dict, color: str, btn_text: str, source: str) -> None:
        self._clear_layout(layout)
        idx = 1
        for field_name, field_val in content_dict.items():
            # Skip empty or internal fields if needed. For now, display everything.
            field_header = QHBoxLayout()
            field_lbl = QLabel(f"{idx}. {field_name.upper()} :")
            field_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
            field_lbl.setStyleSheet(f"color: {color};")
            field_header.addWidget(field_lbl)

            field_header.addStretch()
            if btn_text:
                btn_inject = SecondaryButton(btn_text)
                btn_inject.setFixedHeight(18)
                btn_inject.setFont(QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold))
                btn_inject.clicked.connect(lambda _, f=field_name, s=source: self._inject_field(f, s))
                field_header.addWidget(btn_inject)

            layout.addLayout(field_header)

            mode = self.view_modes.get(source, "source")
            if mode == "katex":
                web_val = SafeWebEngineView()
                web_val.setMinimumHeight(100)

                text_color = DesignTokens.TEXT_PRIMARY
                html_text = str(field_val)
                final_html = f"""<!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <style>
                        body {{ 
                            background-color: transparent; 
                            margin: 0; 
                            padding: 2px; 
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            font-size: 14px;
                            color: {text_color};
                            line-height: 1.5;
                            word-wrap: break-word;
                        }}
                        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
                        ::-webkit-scrollbar-track {{ background: transparent; }}
                        ::-webkit-scrollbar-thumb {{ background: {DesignTokens.BORDER_COLOR}; border-radius: 3px; }}
                        ::-webkit-scrollbar-thumb:hover {{ background: {DesignTokens.TEXT_MUTED}; }}
                    </style>
                </head>
                <body> 
                    {html_text}
                    {get_mathjax_script()}
                </body>
                </html>
                """
                web_val.setHtmlSafe(final_html)
                layout.addWidget(web_val)
            else:
                lbl_val = QLabel()
                lbl_val.setWordWrap(True)
                lbl_val.setAlignment(Qt.AlignmentFlag.AlignTop)
                lbl_val.setFont(QFont(DesignTokens.FONT_CODE, 10))
                lbl_val.setText(str(field_val))
                lbl_val.setTextFormat(Qt.TextFormat.PlainText)
                layout.addWidget(lbl_val)

            if idx < len(content_dict):
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet(f"border: none; border-top: 1px dashed {DesignTokens.BORDER_COLOR}; margin: 6px 0;")
                layout.addWidget(sep)

            idx += 1
        layout.addStretch()

    def _inject_field(self, field_name: str, source: str) -> None:
        if not self.current_conflict:
            return
        if "merged_content" not in self.current_conflict:
            self.current_conflict["merged_content"] = self.current_conflict["content_a"].copy()

        src_dict = self.current_conflict["content_a"] if source == "A" else self.current_conflict["content_b"]
        self.current_conflict["merged_content"][field_name] = src_dict.get(field_name, "")

        # Refresh the merged column
        self._populate_fields(self.merged_content_layout, self.current_conflict["merged_content"], DesignTokens.ACCENT_PRIMARY, "", "Fusion")

    def load_conflict(self, row_data: dict) -> None:
        self.current_conflict = row_data
        sim = row_data.get("sim", 0.0)
        self.lbl_sim.setText(f"Indice de similitude C : {sim * 100:.1f}%")

        note_a = row_data["note_a"]
        content_a = row_data["content_a"]
        note_b = row_data["note_b"]
        content_b = row_data["content_b"]

        self.lbl_title_a.setText(f"CARTE #1 (Originale #{note_a.id})")
        self._populate_fields(self.layout_a, content_a, DesignTokens.COLOR_BLUE, "➔ Injecter", "A")

        self.lbl_title_b.setText(f"CARTE #2 (Duplicata #{note_b.id})")
        self._populate_fields(self.layout_b, content_b, DesignTokens.ACCENT_PRIMARY, "⬅ Injecter", "B")

        def _update_srs(note, srs_dict):
            has_srs = hasattr(note, "srs_ivl") or (hasattr(note, "cards") and len(note.cards) > 0 and hasattr(note.cards[0], "srs_ivl"))
            if has_srs:
                # Fill with real data if it becomes available in NoteModel
                srs_dict["state"].setText(f"🟢 Carte Maîtrisée ({getattr(note, 'srs_reps', 0)} révisions)")
                srs_dict["ivl"].setText(f"Revoir dans : {getattr(note, 'srs_ivl', 0)} jours")
                srs_dict["ease"].setText(f"Facilité : {getattr(note, 'srs_ease', 250)}%")
            else:
                srs_dict["state"].setText("⚪ Données d'apprentissage non synchronisées")
                srs_dict["state"].setStyleSheet(
                    f"background: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_MUTED}; padding: 2px 6px; border-radius: 4px; border: 1px dashed {DesignTokens.BORDER_COLOR};"
                )
                srs_dict["ivl"].setText("Non étudiée")
                srs_dict["ease"].setText("N/A")

        _update_srs(note_a, self.srs_a)
        _update_srs(note_b, self.srs_b)

        self.set_merged_content("A")

    def set_merged_content(self, source: str) -> None:
        if not self.current_conflict:
            return
        content = self.current_conflict["content_a"].copy() if source == "A" else self.current_conflict["content_b"].copy()
        self.current_conflict["merged_content"] = content
        self._populate_fields(self.merged_content_layout, content, DesignTokens.ACCENT_PRIMARY, "", "Fusion")

    def on_validate(self) -> None:
        if not self.current_conflict:
            return
        note_keep = self.current_conflict["note_a"]
        note_del = self.current_conflict["note_b"]
        merged = self.current_conflict.get("merged_content", self.current_conflict["content_a"])
        self.merge_requested.emit(note_keep, note_del, merged)

    def on_swap(self) -> None:
        if not self.current_conflict:
            return

        note_a = self.current_conflict["note_a"]
        content_a = self.current_conflict["content_a"]

        self.current_conflict["note_a"] = self.current_conflict["note_b"]
        self.current_conflict["content_a"] = self.current_conflict["content_b"]

        self.current_conflict["note_b"] = note_a
        self.current_conflict["content_b"] = content_a

        self.load_conflict(self.current_conflict)

    def on_ignore(self) -> None:
        if not self.current_conflict:
            return
        self.ignore_requested.emit(self.current_conflict["note_a"], self.current_conflict["note_b"])

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QTableWidget, QWidget

from ankiforge.ui.theme import DesignTokens


class VirtualTableView(QTableView):
    """
    Vue tabulaire virtualisée haute performance (60 FPS).
    Conçue pour se connecter à des QAbstractTableModel paginés (NoteVirtualTableModel).
    Active par défaut : uniformRowHeights, ScrollPerPixel, masquage des headers verticaux,
    absence de gridlines lourdes et réactivité complète aux thèmes DesignTokens.
    """

    row_selected = Signal(int)  # (row_index)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # 1. Optimisations critiques de virtualisation
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setCornerButtonEnabled(False)

        # 2. Configuration des en-têtes
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setDefaultSectionSize(34)

        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setStretchLastSection(False)

        self._apply_style()

    def _apply_style(self, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        bg_sidebar = profile.bg_sidebar if profile else DesignTokens.BG_SIDEBAR
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        radius_md = profile.radius_md if profile else DesignTokens.RADIUS_MD
        text_primary = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
        text_muted = profile.text_muted if profile else DesignTokens.TEXT_MUTED
        bg_active = profile.bg_active if profile else DesignTokens.BG_ACTIVE
        bg_hover = profile.bg_hover if profile else DesignTokens.BG_HOVER

        self.setStyleSheet(f"""
            QTableView {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {radius_md}px;
                color: {text_primary};
                outline: none;
                gridline-color: transparent;
            }}
            QHeaderView::section {{
                background-color: {bg_sidebar};
                color: {text_muted};
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid {border_col};
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
            }}
            QTableView::item {{
                padding: 0px 4px;
                border-bottom: 1px solid {border_col};
            }}
            QTableView::item:selected {{
                background-color: {bg_active};
                color: {text_primary};
            }}
            QTableView::item:hover {{
                background-color: {bg_hover};
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)

    def select_row(self, row: int) -> None:
        """Sélectionne et fait défiler jusqu'à la ligne spécifiée."""
        model = self.model()
        if model is None or row < 0 or row >= model.rowCount():
            return
        idx = model.index(row, 0)
        self.selectionModel().setCurrentIndex(
            idx,
            QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
        )
        self.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)

    def get_selected_rows(self) -> List[int]:
        """Retourne la liste des indices de lignes sélectionnées."""
        selection_model = self.selectionModel()
        if not selection_model:
            return []
        selected_indexes = selection_model.selectedRows()
        return [idx.row() for idx in selected_indexes]


class StyledTableWidget(QTableWidget):
    """Table avec style design system: sticky headers, hover rows, active row."""

    def __init__(self, columns: list[str], parent: QWidget | None = None) -> None:
        super().__init__(0, len(columns), parent)
        self.setHorizontalHeaderLabels(columns)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._apply_style()

    def _apply_style(self, profile: Any = None) -> None:
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        radius_md = profile.radius_md if profile else DesignTokens.RADIUS_MD
        text_primary = profile.text_primary if profile else DesignTokens.TEXT_PRIMARY
        text_secondary = profile.text_secondary if profile else DesignTokens.TEXT_SECONDARY
        bg_active = profile.bg_active if profile else DesignTokens.BG_ACTIVE
        bg_hover = profile.bg_hover if profile else DesignTokens.BG_HOVER

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {radius_md}px;
                color: {text_primary};
            }}
            QHeaderView::section {{
                background-color: {bg_panel};
                color: {text_secondary};
                padding: 8px 16px;
                border: none;
                border-bottom: 1px solid {border_col};
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 8px 16px;
                border-bottom: 1px solid {border_col};
            }}
            QTableWidget::item:selected {{
                background-color: {bg_active};
                color: {text_primary};
            }}
            QTableWidget::item:hover {{
                background-color: {bg_hover};
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)

    def set_active_row(self, row: int) -> None:
        self.selectRow(row)


class CicdTable(StyledTableWidget):
    """Variante CI/CD : headers uppercase, wider padding."""

    def __init__(self, columns: list[str], parent: QWidget | None = None) -> None:
        cols = [c.upper() for c in columns]
        super().__init__(cols, parent)

    def _apply_style(self, profile: Any = None) -> None:
        super()._apply_style(profile)
        self.setStyleSheet(
            self.styleSheet()
            + """
            QHeaderView::section {
                font-size: 11px;
                letter-spacing: 1px;
                padding: 12px 16px;
            }
            QTableWidget::item {
                padding: 12px 16px;
            }
        """
        )

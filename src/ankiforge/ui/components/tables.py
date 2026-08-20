from typing import Any
from PySide6.QtWidgets import QTableWidget, QWidget, QAbstractItemView, QHeaderView
from PySide6.QtCore import Qt
from ankiforge.ui.theme import DesignTokens


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

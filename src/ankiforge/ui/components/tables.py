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

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 8px 16px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 8px 16px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QTableWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTableWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

    def set_active_row(self, row: int) -> None:
        self.selectRow(row)


class CicdTable(StyledTableWidget):
    """Variante CI/CD : headers uppercase, wider padding."""

    def __init__(self, columns: list[str], parent: QWidget | None = None) -> None:
        cols = [c.upper() for c in columns]
        super().__init__(cols, parent)

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

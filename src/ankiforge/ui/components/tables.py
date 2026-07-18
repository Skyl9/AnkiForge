from PySide6.QtWidgets import QTableWidget, QWidget
from ..theme import DesignTokens


class StyledTableWidget(QTableWidget):
    """Table avec style design system: sticky headers, hover rows, active row."""

    def __init__(self, columns: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        self.horizontalHeader().setStretchLastSection(True)
        self.setAlternatingRowColors(True)
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            QTableWidget {{
                alternate-background-color: {DesignTokens.BG_INPUT};
            }}
        """
        )

    def set_active_row(self, row: int) -> None:
        self.selectRow(row)


class CicdTable(StyledTableWidget):
    """Variante CI/CD : headers uppercase, wider padding."""

    def __init__(self, columns: list[str], parent: QWidget | None = None):
        super().__init__(columns, parent)
        self.horizontalHeader().setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_MUTED};
                text-transform: uppercase;
                font-size: 10px;
                font-weight: bold;
                padding: 12px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)

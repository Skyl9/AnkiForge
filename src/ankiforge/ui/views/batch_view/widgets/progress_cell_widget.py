from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ankiforge.ui.theme import DesignTokens


class ProgressTableCellWidget(QWidget):
    """Widget de cellule affichant la barre de progression et l'état textuel (%) sous la barre."""

    def __init__(self, progress_pct: int = 0, status_text: str = "En attente...", color: str = "#6366f1", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(3)

        self.progress_pct = progress_pct
        self.status_text = status_text
        self.color = color
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setValue(progress_pct)
        self.progress_bar.setTextVisible(False)
        self._apply_style()
        layout.addWidget(self.progress_bar)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 0, 0, 0)
        sub_row.setSpacing(4)

        self.lbl_status = QLabel(status_text)
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: '{DesignTokens.FONT_CODE}';")

        self.lbl_pct = QLabel(f"{progress_pct}%")
        self.lbl_pct.setStyleSheet(f"color: {self.color}; font-size: 10px; font-family: '{DesignTokens.FONT_CODE}'; font-weight: bold;")

        sub_row.addWidget(self.lbl_status, 1)
        sub_row.addWidget(self.lbl_pct, 0, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(sub_row)

    def _apply_style(self, profile: Any = None) -> None:
        bg_input = profile.bg_input if profile else DesignTokens.BG_INPUT
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {bg_input};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background-color: {self.color};
                border-radius: 3px;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style(profile)
        if hasattr(self, "lbl_status"):
            self.lbl_status.setStyleSheet(f"color: {profile.text_muted}; font-size: 10px; font-family: '{profile.font_code}';")
        if hasattr(self, "lbl_pct"):
            self.lbl_pct.setStyleSheet(f"color: {profile.text_muted}; font-size: 10px; font-family: '{profile.font_code}'; font-weight: bold;")

    def update_progress(self, progress_pct: int, status_text: str, color: str = "#10b981") -> None:
        self.progress_pct = progress_pct
        self.status_text = status_text
        self.color = color
        self.progress_bar.setValue(progress_pct)
        self._apply_style()
        self.lbl_status.setText(status_text)
        self.lbl_pct.setText(f"{progress_pct}%")

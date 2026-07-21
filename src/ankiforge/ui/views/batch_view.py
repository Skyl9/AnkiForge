from typing import Optional, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout, QComboBox, QLineEdit, QTableWidget, QTextEdit, QSplitter, QFrame, QHeaderView
from PySide6.QtCore import Qt


class GlassCard(QFrame):
    def __init__(self, title: str, value: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        layout = QVBoxLayout(self)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        layout.addWidget(title_lbl)
        layout.addWidget(self.value_lbl)


class BatchView(QWidget):
    """
    Batch Factory view for AnkiForge.
    CI/CD & Queue style layout.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top: Metrics row
        metrics_layout = QHBoxLayout()
        self.card_status = GlassCard("Status", "🟢 Idle")
        self.card_remaining = GlassCard("Remaining Time", "--:--")
        self.card_cards = GlassCard("Cards Generated", "0")
        self.card_cost = GlassCard("Estimated Cost", "$0.00")

        metrics_layout.addWidget(self.card_status)
        metrics_layout.addWidget(self.card_remaining)
        metrics_layout.addWidget(self.card_cards)
        metrics_layout.addWidget(self.card_cost)
        layout.addLayout(metrics_layout)

        # Middle: Build parameters & Queue table
        splitter = QSplitter(Qt.Orientation.Horizontal)

        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        self.source_edit = QLineEdit()
        self.deck_combo = QComboBox()
        self.model_combo = QComboBox()
        self.engine_combo = QComboBox()

        form_layout.addRow("Source:", self.source_edit)
        form_layout.addRow("Target Deck:", self.deck_combo)
        form_layout.addRow("Note Type:", self.model_combo)
        form_layout.addRow("LLM Engine:", self.engine_combo)

        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(3)
        self.queue_table.setHorizontalHeaderLabels(["Job ID", "Status", "Progress"])
        self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.queue_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #333;
                border-radius: 4px;
                background-color: #1e1e1e;
                gridline-color: #333;
            }
            QHeaderView::section {
                background-color: #252526;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #333;
                border-right: 1px solid #333;
            }
        """)

        splitter.addWidget(form_widget)
        splitter.addWidget(self.queue_table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, stretch=2)

        # Bottom: Console log
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet("""
            QTextEdit {
                background-color: #090a0f;
                color: #d4d4d4;
                font-family: 'Fira Code', 'JetBrains Mono', monospace;
                font-size: 12px;
                border: 1px solid #1a1b26;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self.log_message("INFO", "System initialized and ready.", "#3b82f6")
        layout.addWidget(self.console_output, stretch=1)

    def log_message(self, level: str, msg: str, color: str) -> None:
        self.console_output.append(f'<span style="color: {color}; font-weight: bold;">[{level}]</span> {msg}')

    def refresh_data(self) -> None:
        """Refresh data from models (DeckModel, NoteTypeModel, LLMConfigModel, JobModel)."""
        pass

    def is_dirty(self) -> bool:
        """Check if there are unsaved changes."""
        return False


BatchTab = BatchView

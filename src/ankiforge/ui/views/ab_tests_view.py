from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox, QPushButton, QSplitter, QLabel
from PySide6.QtCore import Qt


class ABTestsView(QWidget):
    """
    Tests A/B view for AnkiForge.
    Side-by-side comparison view testing two LLM engines or prompts.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Top: Source text and Run Control
        top_layout = QHBoxLayout()
        self.source_text = QTextEdit()
        self.source_text.setPlaceholderText("Source content...")
        self.source_text.setStyleSheet("""
            QTextEdit { border: 1px solid #333; border-radius: 4px; background-color: #1e1e1e; padding: 8px; }
        """)

        controls_layout = QVBoxLayout()
        self.run_btn = QPushButton("▶ Run A/B Test")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #8b5cf6; color: white; font-weight: bold;
                border-radius: 4px; padding: 12px 24px; font-size: 14px;
            }
            QPushButton:hover { background-color: #7c3aed; }
        """)
        controls_layout.addStretch()
        controls_layout.addWidget(self.run_btn)
        controls_layout.addStretch()

        top_layout.addWidget(self.source_text, stretch=3)
        top_layout.addLayout(controls_layout, stretch=1)
        layout.addLayout(top_layout, stretch=1)

        # Bottom: Symmetric side-by-side comparison
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Engine A Container
        container_a = QWidget()
        layout_a = QVBoxLayout(container_a)
        layout_a.setContentsMargins(0, 0, 0, 0)

        header_a = QHBoxLayout()
        header_a.addWidget(QLabel("Engine A:"))
        self.engine_a_combo = QComboBox()
        self.engine_a_combo.addItems(["GPT-4o", "Claude 3.5 Sonnet", "Gemini 1.5 Pro"])
        header_a.addWidget(self.engine_a_combo, stretch=1)

        self.preview_a = QTextEdit()
        self.preview_a.setReadOnly(True)
        self.preview_a.setPlaceholderText("Result A (Generated Card Preview)...")
        self.preview_a.setStyleSheet("QTextEdit { border: 1px solid #333; border-radius: 4px; background-color: #1a1a1a; padding: 8px; }")

        layout_a.addLayout(header_a)
        layout_a.addWidget(self.preview_a)

        # Engine B Container
        container_b = QWidget()
        layout_b = QVBoxLayout(container_b)
        layout_b.setContentsMargins(0, 0, 0, 0)

        header_b = QHBoxLayout()
        header_b.addWidget(QLabel("Engine B:"))
        self.engine_b_combo = QComboBox()
        self.engine_b_combo.addItems(["Claude 3.5 Sonnet", "GPT-4o", "Gemini 1.5 Pro"])
        header_b.addWidget(self.engine_b_combo, stretch=1)

        self.preview_b = QTextEdit()
        self.preview_b.setReadOnly(True)
        self.preview_b.setPlaceholderText("Result B (Generated Card Preview)...")
        self.preview_b.setStyleSheet("QTextEdit { border: 1px solid #333; border-radius: 4px; background-color: #1a1a1a; padding: 8px; }")

        layout_b.addLayout(header_b)
        layout_b.addWidget(self.preview_b)

        splitter.addWidget(container_a)
        splitter.addWidget(container_b)

        layout.addWidget(splitter, stretch=2)

    def refresh_data(self) -> None:
        """Refresh engines from LLMConfigModel."""
        pass

    def is_dirty(self) -> bool:
        """Check if test configuration has unsaved changes."""
        return False

from typing import Optional
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QLineEdit, QTextEdit, QComboBox, QPushButton, QFormLayout, QSplitter, QListWidgetItem
from PySide6.QtCore import Qt


class AgentsView(QWidget):
    """
    Éditeur d'Agents view for AnkiForge.
    2-column layout: Agent list and Agent editor.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Agent list
        self.agent_list = QListWidget()
        self.agent_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #333;
                border-radius: 4px;
                background-color: #1e1e1e;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2d2d2d;
            }
            QListWidget::item:selected {
                background-color: #264f78;
                border-left: 3px solid #3b82f6; /* Active indicator */
            }
        """)

        # Add mock agents
        for agent in ["Archiviste", "Generator", "Linter"]:
            item = QListWidgetItem(f"🤖 {agent}")
            self.agent_list.addItem(item)

        splitter.addWidget(self.agent_list)

        # Right: Agent editor
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)

        form_layout = QFormLayout()
        self.name_edit = QLineEdit()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JSON", "Cloze"])

        form_layout.addRow("Name:", self.name_edit)
        form_layout.addRow("Output Format:", self.format_combo)

        editor_layout.addLayout(form_layout)

        # StyledTextEdit placeholder for Jinja2 System Prompt
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Jinja2 System Prompt...")
        self.prompt_edit.setStyleSheet("""
            QTextEdit {
                font-family: 'Fira Code', 'JetBrains Mono', monospace;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        editor_layout.addWidget(self.prompt_edit)

        self.save_btn = QPushButton("Save Agent")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
        """)
        editor_layout.addWidget(self.save_btn)

        splitter.addWidget(editor_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

    def refresh_data(self) -> None:
        """Refresh agent list from AgentModel."""
        pass

    def is_dirty(self) -> bool:
        """Check if the current agent being edited has unsaved changes."""
        return False

from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QLabel, QPushButton, QSplitter, QListWidgetItem
from PySide6.QtCore import Qt


class PipelineStepWidget(QWidget):
    def __init__(self, order: int, name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        drag_handle = QLabel("::")
        drag_handle.setStyleSheet("color: #666; font-weight: bold; padding-right: 8px;")

        order_lbl = QLabel(f"{order}.")
        order_lbl.setStyleSheet("font-weight: bold; color: #aaa;")

        badge = QLabel(name)
        badge.setStyleSheet("""
            background-color: #3b82f6; 
            color: white; 
            padding: 4px 8px; 
            border-radius: 10px; 
            font-weight: bold;
        """)

        layout.addWidget(drag_handle)
        layout.addWidget(order_lbl)
        layout.addWidget(badge)
        layout.addStretch()


class PipelinesView(QWidget):
    """
    Pipelines view for AnkiForge.
    Visual pipeline editor with drag-and-drop steps.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Pipelines list
        self.pipeline_list = QListWidget()
        self.pipeline_list.addItems(["Default Pipeline", "Advanced Pipeline"])
        self.pipeline_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #333;
                border-radius: 4px;
                background-color: #1e1e1e;
            }
            QListWidget::item { padding: 8px; border-bottom: 1px solid #2d2d2d; }
            QListWidget::item:selected { background-color: #264f78; }
        """)
        splitter.addWidget(self.pipeline_list)

        # Right: Pipeline editor (steps)
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Pipeline Steps:"))
        self.add_step_btn = QPushButton("Add Step")
        self.add_step_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981; color: white;
                font-weight: bold; border-radius: 4px; padding: 4px 12px;
            }
        """)
        header_layout.addWidget(self.add_step_btn)
        editor_layout.addLayout(header_layout)

        self.steps_list = QListWidget()
        self.steps_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.steps_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #333;
                border-radius: 4px;
                background-color: #1e1e1e;
            }
            QListWidget::item { border-bottom: 1px solid #2d2d2d; }
        """)

        agents = ["Archiviste", "Generator", "Linter"]
        for i, agent in enumerate(agents, start=1):
            item = QListWidgetItem(self.steps_list)
            widget = PipelineStepWidget(i, agent)
            item.setSizeHint(widget.sizeHint())
            self.steps_list.addItem(item)
            self.steps_list.setItemWidget(item, widget)

        editor_layout.addWidget(self.steps_list)

        splitter.addWidget(editor_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def refresh_data(self) -> None:
        """Refresh data from PipelineModel and PipelineStepModel."""
        pass

    def is_dirty(self) -> bool:
        """Check if pipeline configuration has unsaved changes."""
        return False

import json
import difflib
from typing import Optional

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter, QTextBrowser
from PySide6.QtCore import Qt, Signal

from ankiforge.database.models import NoteModel, NoteVersionModel
from ankiforge.ui.theme import apply_shadow


class DiffViewer(QTextBrowser):
    """A custom text browser to display diffs with highlighting."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setOpenExternalLinks(False)
        self.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333333;
                border-radius: 4px;
                font-family: Menlo;
                font-size: 13px;
                padding: 8px;
            }
        """)

    def set_diff(self, old_text: str, new_text: str) -> None:
        """Generate and set HTML diff."""
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        diff = list(difflib.ndiff(old_lines, new_lines))

        html = ["<table style='width: 100%; border-collapse: collapse; white-space: pre-wrap;'>"]

        old_line_num = 1
        new_line_num = 1

        for line in diff:
            code = line[:2]
            text = line[2:]

            # Escape HTML
            text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            if code == "  ":
                html.append(f"<tr><td style='color: #666; width: 30px;'>{old_line_num}</td><td style='color: #666; width: 30px;'>{new_line_num}</td><td>{text}</td></tr>")
                old_line_num += 1
                new_line_num += 1
            elif code == "- ":
                del_style = "background-color: rgba(239, 68, 68, 0.2);"
                html.append(f"<tr style='{del_style}'><td style='color: #ef4444; width: 30px;'>{old_line_num}</td><td style='width: 30px;'></td><td style='color: #ef4444;'>- {text}</td></tr>")
                old_line_num += 1
            elif code == "+ ":
                add_style = "background-color: rgba(16, 185, 129, 0.2);"
                html.append(f"<tr style='{add_style}'><td style='width: 30px;'></td><td style='color: #10b981; width: 30px;'>{new_line_num}</td><td style='color: #10b981;'>+ {text}</td></tr>")
                new_line_num += 1

        html.append("</table>")
        self.setHtml("".join(html))


class VersionItemWidget(QWidget):
    """Custom widget for version list items."""

    def __init__(self, version: NoteVersionModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.version = version

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        header_layout = QHBoxLayout()

        title_text = f"v{version.version_number}"
        if version.is_active:
            title_text += " (Actuelle)"

        self.title_label = QLabel(title_text)
        self.title_label.setStyleSheet("font-weight: bold; color: #ffffff;")

        self.badge_label = QLabel()
        self.badge_label.setStyleSheet(self._get_badge_style(version.source))
        self.badge_label.setText(self._get_badge_text(version.source))

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.badge_label)

        date_str = version.created_at.strftime("%Y-%m-%d %H:%M:%S")
        self.date_label = QLabel(date_str)
        self.date_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")

        layout.addLayout(header_layout)
        layout.addWidget(self.date_label)

    def _get_badge_text(self, source: str) -> str:
        if source == "manual":
            return "En ligne"
        elif source == "ai":
            return "Généré par IA"
        elif source == "import":
            return "Import"
        return source

    def _get_badge_style(self, source: str) -> str:
        base_style = "padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;"
        if source == "manual":
            return base_style + " background-color: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981;"
        elif source == "ai":
            return base_style + " background-color: rgba(168, 85, 247, 0.2); color: #a855f7; border: 1px solid #a855f7;"
        elif source == "import":
            return base_style + " background-color: rgba(59, 130, 246, 0.2); color: #3b82f6; border: 1px solid #3b82f6;"
        return base_style + " background-color: #333333; color: #ffffff;"


class HistoryModal(QDialog):
    """Dialog to view and restore note history versions."""

    version_restored = Signal(NoteVersionModel)

    def __init__(self, note: NoteModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.note = note
        self.active_version: Optional[NoteVersionModel] = None
        self.selected_version: Optional[NoteVersionModel] = None

        self.setWindowTitle("Machine à remonter le temps — Historique de version")
        self.setMinimumSize(900, 600)
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
            }
            QLabel {
                color: #e0e0e0;
            }
            QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #2a2a2a;
            }
            QSplitter::handle {
                background-color: #333333;
                width: 2px;
            }
        """)

        self._setup_ui()
        self._load_versions()
        apply_shadow(self)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Panel (Timeline)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("Historique")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 8px;")

        self.version_list = QListWidget()
        self.version_list.currentItemChanged.connect(self._on_version_selected)

        left_layout.addWidget(title_label)
        left_layout.addWidget(self.version_list)

        # Right Panel (Diff View)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        diff_header_layout = QHBoxLayout()
        diff_title = QLabel("Comparaison")
        diff_title.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.restore_btn = QPushButton("Restaurer cette version")
        self.restore_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:disabled {
                background-color: #3f3f46;
                color: #a1a1aa;
            }
        """)
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._on_restore_clicked)

        diff_header_layout.addWidget(diff_title)
        diff_header_layout.addStretch()
        diff_header_layout.addWidget(self.restore_btn)

        self.recto_diff = DiffViewer()
        self.verso_diff = DiffViewer()

        recto_label = QLabel("Recto")
        recto_label.setStyleSheet("font-weight: bold; color: #a0a0a0;")
        verso_label = QLabel("Verso")
        verso_label.setStyleSheet("font-weight: bold; color: #a0a0a0; margin-top: 8px;")

        right_layout.addLayout(diff_header_layout)
        right_layout.addWidget(recto_label)
        right_layout.addWidget(self.recto_diff, 1)
        right_layout.addWidget(verso_label)
        right_layout.addWidget(self.verso_diff, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([300, 600])

        main_layout.addWidget(splitter)

    def _load_versions(self) -> None:
        self.version_list.clear()

        versions = list(self.note.versions.order_by(NoteVersionModel.version_number.desc()))

        for version in versions:
            if version.is_active:
                self.active_version = version

            item = QListWidgetItem(self.version_list)
            widget = VersionItemWidget(version)

            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, version)

            self.version_list.addItem(item)
            self.version_list.setItemWidget(item, widget)

    def _on_version_selected(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        if not current:
            return

        self.selected_version = current.data(Qt.ItemDataRole.UserRole)

        if self.selected_version and self.active_version:
            self.restore_btn.setEnabled(not self.selected_version.is_active)
            self._update_diff_view()

    def _update_diff_view(self) -> None:
        if not self.active_version or not self.selected_version:
            return

        try:
            active_content = json.loads(self.active_version.content)
            selected_content = json.loads(self.selected_version.content)

            active_recto = active_content.get("Recto", "")
            active_verso = active_content.get("Verso", "")

            selected_recto = selected_content.get("Recto", "")
            selected_verso = selected_content.get("Verso", "")

            # Show diff between active (old) and selected (new)
            self.recto_diff.set_diff(active_recto, selected_recto)
            self.verso_diff.set_diff(active_verso, selected_verso)

        except json.JSONDecodeError:
            pass

    def _on_restore_clicked(self) -> None:
        if not self.selected_version:
            return

        try:
            content_dict = json.loads(self.selected_version.content)
            new_version = self.note.add_version(content_dict, source="manual")
            self.version_restored.emit(new_version)
            self.accept()
        except json.JSONDecodeError:
            pass

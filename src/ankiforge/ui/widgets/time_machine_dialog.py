import difflib
import json
import datetime
from typing import Any, cast
from dataclasses import dataclass

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QListWidget, QListWidgetItem, QWidget, QTextEdit, QFrame, QMessageBox
from PySide6.QtCore import Signal, Qt

from ankiforge.database.models import NoteModel, NoteVersionModel, db
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.panels import GlassPanel


@dataclass
class DiffLine:
    type: str  # 'add', 'remove', 'keep'
    content: str
    line_number_a: int | None
    line_number_b: int | None


class TimeMachineDialog(QDialog):
    version_restored = Signal(int)  # version_number

    def __init__(
        self,
        note: NoteModel | int | None = None,
        note_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if isinstance(note, int):
            try:
                note_obj = NoteModel.get_by_id(note)
            except Exception:
                note_obj = NoteModel.select().first() or NoteModel()
        elif note_id is not None:
            try:
                note_obj = NoteModel.get_by_id(note_id)
            except Exception:
                note_obj = NoteModel.select().first() or NoteModel()
        elif isinstance(note, NoteModel):
            note_obj = note
        else:
            note_obj = NoteModel.select().first() or NoteModel()

        self.note = note_obj
        note_id_str = getattr(self.note, "id", "1")
        self.setWindowTitle(f"Time Machine — Note {note_id_str}")
        self.resize(900, 600)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        self.layout_main = QVBoxLayout(self)
        self.layout_main.setContentsMargins(10, 10, 10, 10)

        self.glass_panel = GlassPanel()
        self.glass_layout = QVBoxLayout(self.glass_panel)

        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.glass_layout.addWidget(self.splitter)

        # Timeline
        self.timeline_panel = QFrame()
        self.timeline_panel.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border-radius: {DesignTokens.RADIUS_MD}px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.timeline_layout = QVBoxLayout(self.timeline_panel)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)

        self.timeline_header = QLabel("Historique des versions")
        self.timeline_header.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; padding: 10px; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        self.timeline_layout.addWidget(self.timeline_header)

        self.timeline_list = QListWidget()
        self.timeline_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.timeline_list.itemSelectionChanged.connect(self._on_version_selected)
        self.timeline_layout.addWidget(self.timeline_list)

        # Diff View
        self.diff_panel = QFrame()
        self.diff_layout = QVBoxLayout(self.diff_panel)

        self.diff_header = QLabel("Sélectionnez une version pour voir les changements")
        self.diff_header.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 14px;")
        self.diff_layout.addWidget(self.diff_header)

        self.diff_text = QTextEdit()
        self.diff_text.setReadOnly(True)
        self.diff_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: {DesignTokens.FONT_SIZE_CODE}px;
            }}
        """)
        self.diff_layout.addWidget(self.diff_text)

        self.restore_btn = PrimaryButton("Restaurer cette version")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._on_restore_clicked)
        self.diff_layout.addWidget(self.restore_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.splitter.addWidget(self.timeline_panel)
        self.splitter.addWidget(self.diff_panel)
        self.splitter.setSizes([250, 650])

        self.layout_main.addWidget(self.glass_panel)

        # Footer
        self.footer_layout = QHBoxLayout()
        self.close_btn = SecondaryButton("Fermer")
        self.close_btn.clicked.connect(self.close)
        self.footer_layout.addStretch()
        self.footer_layout.addWidget(self.close_btn)
        self.layout_main.addLayout(self.footer_layout)

        self.versions: list[NoteVersionModel] = []
        self.active_version: NoteVersionModel | None = None
        self.refresh_data()

    def refresh_data(self) -> None:
        self.timeline_list.clear()

        # Load versions from DB
        with db.atomic():
            versions = cast(Any, self.note).versions
            self.versions = list(versions.order_by(NoteVersionModel.version_number.desc()))

        self.active_version = next((v for v in self.versions if v.is_active), None)

        for version in self.versions:
            date_str = cast(datetime.datetime, version.created_at).strftime("%Y-%m-%d %H:%M")
            is_active_text = " (Active)" if version.is_active else ""
            item_text = f"v{version.version_number} - {date_str}{is_active_text}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, version)

            if version.is_active:
                item.setForeground(Qt.GlobalColor.white)

            self.timeline_list.addItem(item)

        if self.versions:
            self.timeline_list.setCurrentRow(0)

    def _on_version_selected(self) -> None:
        items = self.timeline_list.selectedItems()
        if not items:
            self.restore_btn.setEnabled(False)
            self.diff_text.clear()
            self.diff_header.setText("Sélectionnez une version pour voir les changements")
            return

        selected_version: NoteVersionModel = items[0].data(Qt.ItemDataRole.UserRole)

        if selected_version.is_active:
            self.restore_btn.setEnabled(False)
            self.diff_header.setText(f"Version {selected_version.version_number} (Active)")
            self.diff_text.setHtml(f"<p style='color: {DesignTokens.TEXT_MUTED}; padding: 10px;'>C'est la version actuellement active. Aucun changement à afficher.</p>")
            return

        self.restore_btn.setEnabled(True)
        active_ver_num = self.active_version.version_number if self.active_version else "?"
        self.diff_header.setText(f"Comparaison : Version {selected_version.version_number} → Version Active (v{active_ver_num})")

        if self.active_version:
            diff_lines = self._compute_diff(selected_version, self.active_version)
            self._render_diff(diff_lines)
        else:
            self.diff_text.setHtml(f"<p style='color: {DesignTokens.TEXT_MUTED}; padding: 10px;'>Aucune version active pour la comparaison.</p>")

    def _compute_diff(self, version_a: NoteVersionModel, version_b: NoteVersionModel) -> list[DiffLine]:
        # Parse content as pretty JSON to make it readable
        try:
            content_a_str = str(version_a.content)
            content_b_str = str(version_b.content)
            content_a_dict = json.loads(content_a_str)
            content_b_dict = json.loads(content_b_str)
            text_a = json.dumps(content_a_dict, indent=2, ensure_ascii=False).splitlines()
            text_b = json.dumps(content_b_dict, indent=2, ensure_ascii=False).splitlines()
        except json.JSONDecodeError:
            text_a = str(version_a.content).splitlines()
            text_b = str(version_b.content).splitlines()

        # Compute unified diff
        diff = list(difflib.unified_diff(text_a, text_b, n=3))

        lines = []
        line_a = 0
        line_b = 0

        for line in diff:
            if line.startswith("---") or line.startswith("+++"):
                continue
            elif line.startswith("@@"):
                parts = line.split(" ")
                if len(parts) >= 3:
                    try:
                        line_a = int(parts[1].split(",")[0].strip("-")) - 1
                        line_b = int(parts[2].split(",")[0].strip("+")) - 1
                    except ValueError:
                        pass
                continue
            elif line.startswith("+"):
                line_b += 1
                lines.append(DiffLine(type="add", content=line[1:], line_number_a=None, line_number_b=line_b))
            elif line.startswith("-"):
                line_a += 1
                lines.append(DiffLine(type="remove", content=line[1:], line_number_a=line_a, line_number_b=None))
            else:
                line_a += 1
                line_b += 1
                lines.append(DiffLine(type="keep", content=line[1:], line_number_a=line_a, line_number_b=line_b))

        return lines

    def _render_diff(self, diff_lines: list[DiffLine]) -> None:
        html = ["<table style='width: 100%; border-collapse: collapse; font-family: Menlo;'>"]

        for d in diff_lines:
            bg_color = "transparent"
            text_color = DesignTokens.TEXT_PRIMARY
            prefix = " "

            if d.type == "add":
                bg_color = "rgba(16, 185, 129, 0.2)"  # Greenish
                text_color = DesignTokens.COLOR_GREEN
                prefix = "+"
            elif d.type == "remove":
                bg_color = "rgba(239, 68, 68, 0.2)"  # Redish
                text_color = DesignTokens.COLOR_RED
                prefix = "-"

            num_a = str(d.line_number_a) if d.line_number_a is not None else ""
            num_b = str(d.line_number_b) if d.line_number_b is not None else ""

            # Escape HTML characters in content
            content = d.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # Preserve spaces
            content = content.replace(" ", "&nbsp;")

            html.append(f"<tr style='background-color: {bg_color}; color: {text_color};'>")
            html.append(f"<td style='width: 30px; text-align: right; color: {DesignTokens.TEXT_MUTED}; border-right: 1px solid {DesignTokens.BORDER_COLOR}; padding-right: 5px;'>{num_a}</td>")
            html.append(f"<td style='width: 30px; text-align: right; color: {DesignTokens.TEXT_MUTED}; border-right: 1px solid {DesignTokens.BORDER_COLOR}; padding-right: 5px;'>{num_b}</td>")
            html.append(f"<td style='padding-left: 10px; white-space: pre-wrap;'>{prefix} {content}</td>")
            html.append("</tr>")

        html.append("</table>")
        self.diff_text.setHtml("".join(html))

    def _on_restore_clicked(self) -> None:
        items = self.timeline_list.selectedItems()
        if not items:
            return

        selected_version: NoteVersionModel = items[0].data(Qt.ItemDataRole.UserRole)
        self._restore_version(selected_version)

    def _restore_version(self, version: NoteVersionModel) -> None:
        try:
            content_dict = json.loads(str(version.content))

            with db.atomic():
                new_version = self.note.add_version(content_dict, source="manual")

            self.refresh_data()
            self.version_restored.emit(new_version.version_number)

            QMessageBox.information(self, "Succès", f"Version {version.version_number} restaurée avec succès.\nNouvelle version créée : v{new_version.version_number}.")

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la restauration : {str(e)}")

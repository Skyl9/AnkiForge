# ruff: noqa: E501

import difflib
import json

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QWidget,
)

from ankiforge.database.models import db, NoteModel, NoteVersionModel
from ankiforge.ui.components.components import PrimaryButton, HeaderLabel
from ankiforge.ui.widgets.toast import show_toast


class VersionHistoryDialog(QDialog):
    def __init__(self, note: NoteModel, parent=None):
        super().__init__(parent)
        self.note = note
        self.versions: list[NoteVersionModel] = []
        self.active_version: NoteVersionModel | None = None

        self.setWindowTitle("🕒 Machine à Remonter le Temps (Historique)")
        self.setMinimumSize(850, 500)

        layout = QVBoxLayout(self)

        # En-tête
        header = HeaderLabel(f"Historique des modifications de la carte (ID: {self.note.id})")
        layout.addWidget(header)

        # Zone principale (Splitter)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PANNEAU GAUCHE : Liste des versions ---
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("<b>Versions sauvegardées</b>"))

        self.list_versions = QListWidget()
        self.list_versions.itemSelectionChanged.connect(self.on_version_selected)
        left_panel.addWidget(self.list_versions)

        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        splitter.addWidget(left_widget)

        # --- PANNEAU DROIT : Comparaison ---
        right_panel = QVBoxLayout()
        right_panel.addWidget(
            QLabel(
                "<b>Comparaison avec la version Actuelle :</b><br><span style='color:#ffcccc; font-size:12px;'>Rouge = Sera supprimé</span> | <span style='color:#ccffcc; font-size:12px;'>Vert = Sera restauré</span>"
            )
        )

        self.text_diff = QTextEdit()
        self.text_diff.setReadOnly(True)
        right_panel.addWidget(self.text_diff)

        self.btn_restore = PrimaryButton(qta.icon("fa5s.history", color="white"), " Restaurer cette version")
        self.btn_restore.clicked.connect(self.restore_selected_version)
        self.btn_restore.setEnabled(False)
        right_panel.addWidget(self.btn_restore)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        splitter.addWidget(right_widget)

        splitter.setSizes([250, 600])
        layout.addWidget(splitter)

        self.load_versions()

    def load_versions(self):
        """Charge toutes les versions de la note depuis la base de données."""
        self.list_versions.clear()

        # On récupère toutes les versions, de la plus récente à la plus ancienne
        query = NoteVersionModel.select().where(NoteVersionModel.note == self.note).order_by(NoteVersionModel.version_number.desc())
        self.versions = list(query)

        for v in self.versions:
            if v.is_active:
                self.active_version = v
                label = f"v{v.version_number} (Actuelle) - {v.source}"
            else:
                label = f"v{v.version_number} - {v.source}"

            date_str = v.created_at.strftime("%d/%m/%Y %H:%M")

            item = QListWidgetItem(f"{label}\n{date_str}")
            item.setData(Qt.ItemDataRole.UserRole, v)

            # Mettre l'icône selon la source
            if v.source == "ai":
                item.setIcon(qta.icon("fa5s.robot", color="#4CAF50"))
            elif v.source == "manual":
                item.setIcon(qta.icon("fa5s.user-edit", color="#2196F3"))
            else:
                item.setIcon(qta.icon("fa5s.save", color="#9E9E9E"))

            self.list_versions.addItem(item)

        if self.list_versions.count() > 0:
            self.list_versions.setCurrentRow(0)

    @staticmethod
    def generate_diff_html(old_text: str, new_text: str) -> str:
        """Génère le diff HTML. old_text = Active Version, new_text = Selected Version."""
        matcher = difflib.SequenceMatcher(None, old_text, new_text)
        html_result = ""

        for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
            part_a = old_text[a0:a1].replace("\n", "<br>")
            part_b = new_text[b0:b1].replace("\n", "<br>")

            if opcode == "equal":
                html_result += part_a
            elif opcode == "replace":
                html_result += f"<span style='background-color: #5c1b1b; color: #ffcccc; text-decoration: line-through;'>{part_a}</span>"
                html_result += f"<span style='background-color: #1b5c20; color: #ccffcc;'>{part_b}</span>"
            elif opcode == "delete":
                html_result += f"<span style='background-color: #5c1b1b; color: #ffcccc; text-decoration: line-through;'>{part_a}</span>"
            elif opcode == "insert":
                html_result += f"<span style='background-color: #1b5c20; color: #ccffcc;'>{part_b}</span>"

        return html_result

    @Slot()
    def on_version_selected(self):
        items = self.list_versions.selectedItems()
        if not items:
            return

        selected_version = items[0].data(Qt.ItemDataRole.UserRole)

        # On désactive le bouton de restauration si c'est déjà la version active
        self.btn_restore.setEnabled(not selected_version.is_active)

        if not self.active_version:
            return

        try:
            # On parse les JSON
            active_content = json.loads(self.active_version.content)
            selected_content = json.loads(selected_version.content)

            # On construit une vue champ par champ
            full_html = ""
            for field_name in active_content.keys():
                active_text = active_content.get(field_name, "")
                selected_text = selected_content.get(field_name, "")

                full_html += f"<h4 style='color:#90CAF9; margin-bottom:5px;'>■ Champ : {field_name}</h4>"

                if active_text == selected_text:
                    full_html += f"<div style='color:#AAA; margin-bottom:15px;'><i>(Identique)</i><br>{active_text.replace(chr(10), '<br>')}</div>"
                else:
                    diff_html = self.generate_diff_html(active_text, selected_text)
                    full_html += f"<div style='margin-bottom:15px;'>{diff_html}</div>"

            self.text_diff.setHtml(full_html)

        except Exception as e:
            self.text_diff.setPlainText(f"Erreur de lecture du JSON : {e}")

    @Slot()
    def restore_selected_version(self):
        items = self.list_versions.selectedItems()
        if not items:
            return
        selected_version = items[0].data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self,
            "Restaurer",
            "Voulez-vous restaurer cette ancienne version ?\nCela créera une nouvelle sauvegarde (v_next) avec ce contenu.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    # On utilise la méthode add_version que tu as déjà codée dans NoteModel !
                    content_dict = json.loads(selected_version.content)
                    self.note.add_version(content_dict, source="manual")

                show_toast(self, f"Version {selected_version.version_number} restaurée avec succès !")
                self.accept()  # Ferme la fenêtre avec un code de succès
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de restaurer la version : {e}")

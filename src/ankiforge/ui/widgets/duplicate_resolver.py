import difflib
import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTextEdit, QProgressBar, QMessageBox)

from ankiforge.database.models import db, NoteModel, IgnoredDuplicateModel
from ankiforge.ui.components.components import PrimaryButton, ActionButton


class DuplicateResolverDialog(QDialog):
    def __init__(self, conflicts, parent=None):
        super().__init__(parent)
        self.conflicts = conflicts  # Liste de tuples: (note_A, text_A, note_B, text_B)
        self.current_index = 0
        self.resolved_count = 0

        self.setWindowTitle("Résolution des Doublons (Git Merge)")
        self.setMinimumSize(900, 500)

        layout = QVBoxLayout(self)

        # 1. En-tête avec barre de progression
        header_layout = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(len(self.conflicts))
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)

        header_layout.addWidget(self.lbl_status)
        header_layout.addWidget(self.progress_bar, stretch=1)
        layout.addLayout(header_layout)

        # 2. Zone de comparaison (Splitter horizontal)
        compare_layout = QHBoxLayout()

        # Panneau Gauche (Original)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("<b>📄 Carte A (Ancienne/Originale)</b>"))
        self.text_left = QTextEdit()
        self.text_left.setReadOnly(True)
        self.text_left.setStyleSheet("font-size: 15px; padding: 10px;")
        left_layout.addWidget(self.text_left)

        self.btn_keep_a = PrimaryButton(qta.icon('fa5s.arrow-left', color='white'), " Garder l'Originale (Supprime B)")
        self.btn_keep_a.clicked.connect(self.keep_a)
        left_layout.addWidget(self.btn_keep_a)

        compare_layout.addLayout(left_layout)

        # Panneau Droit (Nouvelle)
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("<b>✨ Carte B (Nouvelle)</b>"))
        self.text_right = QTextEdit()
        self.text_right.setReadOnly(True)
        self.text_right.setStyleSheet("font-size: 15px; padding: 10px;")
        right_layout.addWidget(self.text_right)

        self.btn_keep_b = PrimaryButton(qta.icon('fa5s.arrow-right', color='white'), " Garder la Nouvelle (Supprime A)")
        self.btn_keep_b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_keep_b.clicked.connect(self.keep_b)
        right_layout.addWidget(self.btn_keep_b)

        compare_layout.addLayout(right_layout)
        layout.addLayout(compare_layout)

        # 3. Bouton Ignorer
        self.btn_ignore = ActionButton("Ignorer le conflit (Garder les deux)")
        self.btn_ignore.clicked.connect(self.ignore_conflict)
        layout.addWidget(self.btn_ignore)

        self.load_current_conflict()

    def generate_diff_html(self, text_a: str, text_b: str):
        """Génère un HTML coloré (Rouge/Vert) pour mettre en évidence les différences."""
        matcher = difflib.SequenceMatcher(None, text_a, text_b)
        html_a, html_b = "", ""

        for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
            part_a = text_a[a0:a1].replace('\n', '<br>')
            part_b = text_b[b0:b1].replace('\n', '<br>')

            if opcode == 'equal':
                html_a += part_a
                html_b += part_b
            elif opcode == 'replace':
                html_a += f"<span style='background-color: #5c1b1b; color: #ffcccc;'>{part_a}</span>"
                html_b += f"<span style='background-color: #1b5c20; color: #ccffcc;'>{part_b}</span>"
            elif opcode == 'delete':
                html_a += f"<span style='background-color: #5c1b1b; color: #ffcccc;'>{part_a}</span>"
            elif opcode == 'insert':
                html_b += f"<span style='background-color: #1b5c20; color: #ccffcc;'>{part_b}</span>"

        return html_a, html_b

    def load_current_conflict(self):
        if self.current_index >= len(self.conflicts):
            QMessageBox.information(self, "Terminé",
                                    f"Tous les conflits ont été traités ({self.resolved_count} résolus).")
            self.accept()
            return

        self.lbl_status.setText(f"Conflit {self.current_index + 1} sur {len(self.conflicts)}")
        self.progress_bar.setValue(self.current_index)

        note_a, text_a, note_b, text_b = self.conflicts[self.current_index]

        # On génère le surlignage Diff
        html_a, html_b = self.generate_diff_html(text_a, text_b)

        self.text_left.setHtml(f"<div style='font-family: sans-serif;'>{html_a}</div>")
        self.text_right.setHtml(f"<div style='font-family: sans-serif;'>{html_b}</div>")

    def _resolve(self, note_to_delete: NoteModel):
        try:
            with db.atomic():
                NoteModel.delete_by_id(note_to_delete.id)
            self.resolved_count += 1
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de supprimer la note : {e}")

        self.current_index += 1
        self.load_current_conflict()

    @Slot()
    def keep_a(self):
        _, _, note_b, _ = self.conflicts[self.current_index]
        self._resolve(note_b)  # Supprime B

    @Slot()
    def keep_b(self):
        note_a, _, _, _ = self.conflicts[self.current_index]
        self._resolve(note_a)  # Supprime A

    @Slot()
    def ignore_conflict(self):
        """Enregistre le conflit dans la base pour l'ignorer à l'avenir."""
        note_a, _, note_b, _ = self.conflicts[self.current_index]

        try:
            with db.atomic():
                # On ordonne toujours (plus petit ID d'abord) pour que (A, B) soit pareil que (B, A)
                id_1, id_2 = min(note_a.id, note_b.id), max(note_a.id, note_b.id)
                IgnoredDuplicateModel.get_or_create(note_a_id=id_1, note_b_id=id_2)
        except Exception as e:
            pass  # Si ça rate (ex: déjà ignoré), on continue sans planter

        self.current_index += 1
        self.load_current_conflict()
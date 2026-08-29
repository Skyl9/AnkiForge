import difflib

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QTextEdit, QVBoxLayout

from ankiforge.database.models import IgnoredDuplicateModel, NoteModel, db
from ankiforge.ui.components.components import ActionButton, PrimaryButton, RoundedPanel
from ankiforge.ui.theme import is_dark_mode


class DuplicateResolverDialog(QDialog):
    def __init__(self, conflicts, parent=None):
        super().__init__(parent)
        self.conflicts = conflicts  # Liste de tuples: (note_A, text_A, note_B, text_B)
        self.current_index = 0
        self.resolved_count = 0

        self.setWindowTitle("Résolution des Doublons (Git Merge)")
        self.setMinimumSize(1000, 600)
        self.setStyleSheet("QDialog { background-color: palette(window); }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 1. En-tête avec barre de progression
        header_layout = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("font-size: 16px; font-weight: bold; color: palette(text);")

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(len(self.conflicts))
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: palette(base); border-radius: 4px; }
            QProgressBar::chunk { background-color: palette(highlight); border-radius: 4px; }
        """)

        header_layout.addWidget(self.lbl_status)
        header_layout.addSpacing(20)
        header_layout.addWidget(self.progress_bar, stretch=1)
        layout.addLayout(header_layout)

        # 2. Zone de comparaison (Splitter horizontal)
        compare_layout = QHBoxLayout()
        compare_layout.setSpacing(20)

        # --- Panneau Gauche (Original) ---
        left_panel = RoundedPanel()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)

        lbl_left = QLabel("📄 CARTE A (ANCIENNE / ORIGINALE)")
        lbl_left.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        left_layout.addWidget(lbl_left)

        self.text_left = QTextEdit()
        self.text_left.setReadOnly(True)
        # Transparent pour fusionner avec la carte
        self.text_left.setStyleSheet("QTextEdit { border: none; background-color: transparent; font-size: 14px; }")
        left_layout.addWidget(self.text_left)

        self.btn_keep_a = PrimaryButton(qta.icon("fa5s.arrow-left", color="white"), " Garder l'Originale (Supprime B)")
        self.btn_keep_a.clicked.connect(self.keep_a)
        left_layout.addWidget(self.btn_keep_a)

        compare_layout.addWidget(left_panel)

        # --- Panneau Droit (Nouvelle) ---
        right_panel = RoundedPanel()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)

        lbl_right = QLabel("✨ CARTE B (NOUVELLE)")
        lbl_right.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        right_layout.addWidget(lbl_right)

        self.text_right = QTextEdit()
        self.text_right.setReadOnly(True)
        self.text_right.setStyleSheet("QTextEdit { border: none; background-color: transparent; font-size: 14px; }")
        right_layout.addWidget(self.text_right)

        self.btn_keep_b = PrimaryButton(qta.icon("fa5s.arrow-right", color="white"), " Garder la Nouvelle (Supprime A)")
        self.btn_keep_b.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.btn_keep_b.clicked.connect(self.keep_b)
        right_layout.addWidget(self.btn_keep_b)

        compare_layout.addWidget(right_panel)
        layout.addLayout(compare_layout)

        # 3. Bouton Ignorer
        btn_bottom_layout = QHBoxLayout()
        btn_bottom_layout.addStretch()
        self.btn_ignore = ActionButton("fa5s.forward", " Ignorer le conflit (Garder les deux)")
        self.btn_ignore.clicked.connect(self.ignore_conflict)
        btn_bottom_layout.addWidget(self.btn_ignore)
        btn_bottom_layout.addStretch()

        layout.addLayout(btn_bottom_layout)

        self.load_current_conflict()

    @staticmethod
    def generate_diff_html(text_a: str, text_b: str):
        """Génère un HTML coloré adapté au thème pour mettre en évidence les différences."""
        matcher = difflib.SequenceMatcher(None, text_a, text_b)
        html_a, html_b = "", ""

        # Couleurs dynamiques selon le thème (Clair/Sombre)
        dark = is_dark_mode()
        del_bg = "rgba(244, 67, 54, 0.2)" if dark else "rgba(244, 67, 54, 0.15)"
        del_color = "#ff8a80" if dark else "#d32f2f"
        ins_bg = "rgba(76, 175, 80, 0.2)" if dark else "rgba(76, 175, 80, 0.15)"
        ins_color = "#b9f6ca" if dark else "#2e7d32"

        for opcode, a0, a1, b0, b1 in matcher.get_opcodes():
            part_a = text_a[a0:a1].replace("\n", "<br>")
            part_b = text_b[b0:b1].replace("\n", "<br>")

            if opcode == "equal":
                html_a += part_a
                html_b += part_b
            elif opcode == "replace":
                html_a += f"<span style='background-color: {del_bg}; color: {del_color}; text-decoration: line-through;'>{part_a}</span>"
                html_b += f"<span style='background-color: {ins_bg}; color: {ins_color}; font-weight: bold;'>{part_b}</span>"
            elif opcode == "delete":
                html_a += f"<span style='background-color: {del_bg}; color: {del_color}; text-decoration: line-through;'>{part_a}</span>"
            elif opcode == "insert":
                html_b += f"<span style='background-color: {ins_bg}; color: {ins_color}; font-weight: bold;'>{part_b}</span>"

        return html_a, html_b

    def load_current_conflict(self):
        if self.current_index >= len(self.conflicts):
            QMessageBox.information(self, "Terminé", f"Tous les conflits ont été traités ({self.resolved_count} résolus).")
            self.accept()
            return

        self.lbl_status.setText(f"Conflit {self.current_index + 1} sur {len(self.conflicts)}")
        self.progress_bar.setValue(self.current_index)

        # On récupère maintenant les dictionnaires complets
        note_a, content_a, note_b, content_b = self.conflicts[self.current_index]

        full_html_a = ""
        full_html_b = ""

        dark = is_dark_mode()
        header_color_a = "#64B5F6" if dark else "#1976D2"
        header_color_b = "#81C784" if dark else "#388E3C"
        text_color = "#E0E0E0" if dark else "#333333"

        for field_name in content_a:
            text_a = str(content_a.get(field_name, ""))
            text_b = str(content_b.get(field_name, ""))

            # En-tête visuel du champ
            full_html_a += f"<h4 style='color: {header_color_a}; margin-bottom: 5px; margin-top: 15px;'>■ Champ : {field_name}</h4>"
            full_html_b += f"<h4 style='color: {header_color_b}; margin-bottom: 5px; margin-top: 15px;'>■ Champ : {field_name}</h4>"

            if text_a == text_b:
                identical_html = f"<div style='color: gray;'><i>(Identique)</i><br>{text_a.replace(chr(10), '<br>')}</div>"
                full_html_a += identical_html
                full_html_b += identical_html
            else:
                html_a, html_b = self.generate_diff_html(text_a, text_b)
                full_html_a += f"<div style='color: {text_color};'>{html_a}</div>"
                full_html_b += f"<div style='color: {text_color};'>{html_b}</div>"

        # Injection dans les zones de texte (Police native lisible)
        font_family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
        self.text_left.setHtml(f"<div style='font-family: {font_family}; line-height: 1.5;'>{full_html_a}</div>")
        self.text_right.setHtml(f"<div style='font-family: {font_family}; line-height: 1.5;'>{full_html_b}</div>")

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
                # On ordonne toujours (plus petit ID d'abord)
                id_1, id_2 = min(note_a.id, note_b.id), max(note_a.id, note_b.id)
                IgnoredDuplicateModel.get_or_create(note_a_id=id_1, note_b_id=id_2)
        except (ValueError, TypeError, AttributeError):
            pass

        self.current_index += 1
        self.load_current_conflict()

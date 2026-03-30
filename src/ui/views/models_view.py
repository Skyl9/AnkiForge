# src/ui/views/models_view.py
import json
import os
from typing import Dict, List

import qtawesome as qta
from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                               QTextEdit, QLabel, QSplitter, QGroupBox, QPushButton,
                               QComboBox, QListWidgetItem, QInputDialog, QMessageBox)

from src.database.models import db, NoteTypeModel
from src.utils.anki_renderer import render_anki_card


class ModelsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.current_model_id = None
        self.current_templates: List[Dict[str, str]] = []
        self.mock_dict: Dict[str, str] = {}
        self.current_css: str = ""

        layout = QVBoxLayout(self)

        # En-tête
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<h2>Édition des Modèles (Note Types)</h2>"))

        # Boutons avec icônes
        self.btn_new_model = QPushButton(qta.icon('fa5s.plus'), " Nouveau Modèle")
        self.btn_new_model.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_new_model.clicked.connect(self.create_new_model)

        self.btn_del_model = QPushButton(qta.icon('fa5s.trash'), " Supprimer")
        self.btn_del_model.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        self.btn_del_model.clicked.connect(self.delete_current_model)
        self.btn_del_model.setEnabled(False)

        self.btn_save_model = QPushButton(qta.icon('fa5s.save'), " Sauvegarder")
        self.btn_save_model.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_save_model.clicked.connect(self.save_current_model)
        self.btn_save_model.setEnabled(False)

        self.btn_refresh = QPushButton(qta.icon('fa5s.sync'), " Rafraîchir")
        self.btn_refresh.clicked.connect(self.refresh_models_list)

        header_layout.addWidget(self.btn_new_model)
        header_layout.addWidget(self.btn_del_model)
        header_layout.addWidget(self.btn_save_model)
        header_layout.addWidget(self.btn_refresh)

        layout.addLayout(header_layout)

        # Standard PySide6 : Qt.Orientation.Horizontal
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.models_list = QListWidget()
        self.models_list.itemClicked.connect(self.on_model_selected)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        top_splitter = QSplitter(Qt.Orientation.Vertical)

        # 1. Structure du Note Type (Métadonnées)
        meta_widget = QWidget()
        meta_layout = QVBoxLayout(meta_widget)

        self.fields_view = QTextEdit()
        self.fields_view.setMaximumHeight(60)
        self.fields_view.textChanged.connect(self._enable_save)

        self.css_editor = QTextEdit()
        self.css_editor.setStyleSheet("font-family: monospace;")
        self.css_editor.textChanged.connect(self.update_preview)
        self.css_editor.textChanged.connect(self._enable_save)

        self._add_group(meta_layout, "1. Champs de données (Séparés par des virgules ou JSON)", self.fields_view)
        self._add_group(meta_layout, "2. Style global (CSS partagé)", self.css_editor)

        # 2. Les Modèles de Cartes & Preview
        cards_widget = QWidget()
        cards_layout = QVBoxLayout(cards_widget)

        cards_toolbar = QHBoxLayout()
        self.card_selector = QComboBox()
        self.card_selector.currentIndexChanged.connect(self.on_card_template_selected)

        self.side_selector = QComboBox()
        self.side_selector.addItems(["Voir Recto", "Voir Verso"])
        self.side_selector.currentIndexChanged.connect(self.update_preview)

        self.btn_add_card = QPushButton(qta.icon('fa5s.plus'), "")
        self.btn_add_card.setToolTip("Ajouter une carte")
        self.btn_add_card.clicked.connect(self.add_new_card_template)

        self.btn_ren_card = QPushButton(qta.icon('fa5s.pen'), "")
        self.btn_ren_card.setToolTip("Renommer cette carte")
        self.btn_ren_card.clicked.connect(self.rename_card_template)

        self.btn_del_card = QPushButton(qta.icon('fa5s.trash'), "")
        self.btn_del_card.setStyleSheet("color: #F44336;")
        self.btn_del_card.setToolTip("Supprimer cette carte")
        self.btn_del_card.clicked.connect(self.delete_card_template)

        cards_toolbar.addWidget(QLabel("<b>Carte du modèle :</b>"))
        cards_toolbar.addWidget(self.card_selector)
        cards_toolbar.addWidget(self.side_selector)
        cards_toolbar.addWidget(self.btn_add_card)
        cards_toolbar.addWidget(self.btn_ren_card)
        cards_toolbar.addWidget(self.btn_del_card)

        cards_toolbar.addStretch()
        cards_layout.addLayout(cards_toolbar)

        html_preview_splitter = QSplitter(Qt.Orientation.Horizontal)

        editors_widget = QWidget()
        editors_layout = QVBoxLayout(editors_widget)
        editors_layout.setContentsMargins(0, 0, 0, 0)

        self.qfmt_editor = QTextEdit()
        self.qfmt_editor.setStyleSheet("font-family: monospace;")
        self.afmt_editor = QTextEdit()
        self.afmt_editor.setStyleSheet("font-family: monospace;")

        self.qfmt_editor.textChanged.connect(self.update_preview)
        self.qfmt_editor.textChanged.connect(self._enable_save)
        self.afmt_editor.textChanged.connect(self.update_preview)
        self.afmt_editor.textChanged.connect(self._enable_save)

        editors_layout.addWidget(QLabel("<b>HTML du Recto :</b>"))
        editors_layout.addWidget(self.qfmt_editor)
        editors_layout.addWidget(QLabel("<b>HTML du Verso :</b>"))
        editors_layout.addWidget(self.afmt_editor)

        self.web_view = QWebEngineView()

        html_preview_splitter.addWidget(editors_widget)
        html_preview_splitter.addWidget(self.web_view)
        html_preview_splitter.setSizes([350, 350])

        cards_layout.addWidget(html_preview_splitter)

        top_splitter.addWidget(meta_widget)
        top_splitter.addWidget(cards_widget)
        top_splitter.setSizes([200, 600])

        right_layout.addWidget(top_splitter)

        main_splitter.addWidget(self.models_list)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([200, 800])

        layout.addWidget(main_splitter)
        self.refresh_models_list()

    def _add_group(self, parent_layout: QVBoxLayout, title: str, widget: QWidget) -> None:
        group = QGroupBox(title)
        lyt = QVBoxLayout(group)
        lyt.addWidget(widget)
        parent_layout.addWidget(group)

    @Slot()
    def _enable_save(self) -> None:
        if self.current_model_id:
            self.btn_save_model.setEnabled(True)

    # ==========================================
    # ACTIONS BDD (Créer, Sauvegarder, Charger, Supprimer)
    # ==========================================

    @Slot()
    def delete_current_model(self) -> None:
        """Supprime le modèle actuellement sélectionné et toutes ses notes associées."""
        if not self.current_model_id:
            return

        model = NoteTypeModel.get_by_id(self.current_model_id)

        reply = QMessageBox.question(
            self,
            "Suppression Critique",
            f"Voulez-vous vraiment supprimer le modèle '{model.name}' ?\n"
            "ATTENTION : Cela supprimera ÉGALEMENT toutes les notes et cartes utilisant ce modèle !",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    model.delete_instance(recursive=True)  # Supprime en cascade
                self.refresh_models_list()

                # Réinitialisation de l'UI
                self.qfmt_editor.clear()
                self.afmt_editor.clear()
                self.css_editor.clear()
                self.fields_view.clear()
                self.web_view.setHtml("")
                self.current_model_id = None
                self.btn_del_model.setEnabled(False)

            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le modèle :\n{e}")

    @Slot()
    def create_new_model(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Modèle", "Nom du modèle :")
        if not ok or not name.strip(): return

        if NoteTypeModel.get_or_none(NoteTypeModel.name == name.strip()):
            QMessageBox.warning(self, "Erreur", "Un modèle porte déjà ce nom.")
            return

        fields_str, ok2 = QInputDialog.getText(self, "Champs de données", "Noms séparés par des virgules :")
        if not ok2 or not fields_str.strip(): return

        fields_list = [f.strip() for f in fields_str.split(",") if f.strip()]
        if not fields_list: fields_list = ["Front", "Back"]

        default_templates = [{
            "name": "Carte 1",
            "qfmt": f"{{{{{fields_list[0]}}}}}",
            "afmt": f"{{{{FrontSide}}}}\n\n<hr id=answer>\n\n{{{{{fields_list[1] if len(fields_list) > 1 else fields_list[0]}}}}}"
        }]
        default_css = ".card { font-family: arial; font-size: 20px; text-align: center; color: white; background-color: #1e1e1e; }"

        try:
            with db.atomic():
                NoteTypeModel.create(
                    name=name.strip(),
                    fields_schema=json.dumps(fields_list, ensure_ascii=False),
                    templates=json.dumps(default_templates, ensure_ascii=False),
                    css_style=default_css
                )
            self.refresh_models_list()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le modèle : {e}")

    @Slot()
    def save_current_model(self) -> None:
        if not self.current_model_id: return

        try:
            note_type = NoteTypeModel.get_by_id(self.current_model_id)
            note_type.css_style = self.css_editor.toPlainText()

            raw_fields = self.fields_view.toPlainText().strip()
            if raw_fields.startswith("["):
                note_type.fields_schema = raw_fields
            else:
                fields_list = [f.strip() for f in raw_fields.split(",") if f.strip()]
                note_type.fields_schema = json.dumps(fields_list, ensure_ascii=False)

            idx = self.card_selector.currentIndex()
            if 0 <= idx < len(self.current_templates):
                self.current_templates[idx]["qfmt"] = self.qfmt_editor.toPlainText()
                self.current_templates[idx]["afmt"] = self.afmt_editor.toPlainText()

            note_type.templates = json.dumps(self.current_templates, ensure_ascii=False)

            with db.atomic():
                note_type.save()

            self.btn_save_model.setEnabled(False)
            self.btn_save_model.setText(" Sauvegardé !")
            self.btn_save_model.setIcon(qta.icon('fa5s.check'))

            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, self._reset_save_btn)

        except Exception as e:
            QMessageBox.critical(self, "Erreur BDD", f"Impossible de sauvegarder : {e}")

    @Slot()
    def _reset_save_btn(self):
        self.btn_save_model.setText(" Sauvegarder")
        self.btn_save_model.setIcon(qta.icon('fa5s.save'))

    @Slot()
    def refresh_models_list(self) -> None:
        self.models_list.clear()
        for note_type in NoteTypeModel.select().order_by(NoteTypeModel.name):
            item = QListWidgetItem(note_type.name)
            # Standard Qt6 : ItemDataRole
            item.setData(Qt.ItemDataRole.UserRole, note_type.id)
            self.models_list.addItem(item)

        self.current_model_id = None
        self.btn_save_model.setEnabled(False)
        self.btn_del_model.setEnabled(False)

    @Slot(QListWidgetItem)
    def on_model_selected(self, item: QListWidgetItem) -> None:
        model_id = item.data(Qt.ItemDataRole.UserRole)
        self.current_model_id = model_id
        self.btn_save_model.setEnabled(False)
        self.btn_del_model.setEnabled(True)

        try:
            note_type = NoteTypeModel.get_by_id(model_id)

            fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []
            self.fields_view.blockSignals(True)
            self.fields_view.setPlainText(", ".join(fields))
            self.fields_view.blockSignals(False)

            self.mock_dict = {f: f"<span style='color:#888;'><i>[Simulation de {f}]</i></span>" for f in fields}

            self.current_css = note_type.css_style if note_type.css_style else ""
            self.css_editor.blockSignals(True)
            self.css_editor.setPlainText(self.current_css)
            self.css_editor.blockSignals(False)

            self.card_selector.blockSignals(True)
            self.card_selector.clear()
            self.current_templates = json.loads(note_type.templates) if note_type.templates else []

            for tmpl in self.current_templates:
                self.card_selector.addItem(tmpl.get("name", "Carte Inconnue"))
            self.card_selector.blockSignals(False)

            if self.current_templates:
                self.on_card_template_selected(0)

        except Exception as e:
            self.qfmt_editor.setPlainText(f"Erreur : {e}")

    @Slot(int)
    def on_card_template_selected(self, index: int) -> None:
        if 0 <= index < len(self.current_templates):
            tmpl = self.current_templates[index]
            self.qfmt_editor.blockSignals(True)
            self.afmt_editor.blockSignals(True)

            self.qfmt_editor.setPlainText(tmpl.get("qfmt", ""))
            self.afmt_editor.setPlainText(tmpl.get("afmt", ""))

            self.qfmt_editor.blockSignals(False)
            self.afmt_editor.blockSignals(False)
            self.update_preview()

    @Slot()
    def update_preview(self) -> None:
        if not self.current_templates:
            return

        is_recto = self.side_selector.currentIndex() == 0
        raw_html = self.qfmt_editor.toPlainText() if is_recto else self.afmt_editor.toPlainText()
        css = self.css_editor.toPlainText()

        final_html = render_anki_card(
            raw_html=raw_html, css=css, fields_dict=self.mock_dict,
            is_recto=is_recto, front_html=self.qfmt_editor.toPlainText()
        )

        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        media_dir = os.path.join(BASE_DIR, 'data', 'media')
        if not media_dir.endswith(os.sep): media_dir += os.sep
        base_url = QUrl.fromLocalFile(media_dir)

        self.web_view.setHtml(final_html, base_url)

    @Slot()
    def add_new_card_template(self) -> None:
        if not self.current_model_id: return
        name, ok = QInputDialog.getText(self, "Nouvelle Carte", "Nom de la carte :")
        if not ok or not name.strip(): return

        new_template = {
            "name": name.strip(),
            "qfmt": "Écrivez le HTML du Recto ici...",
            "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\nÉcrivez le HTML du Verso ici..."
        }
        self.current_templates.append(new_template)

        self.card_selector.blockSignals(True)
        self.card_selector.addItem(name.strip())
        new_index = len(self.current_templates) - 1
        self.card_selector.setCurrentIndex(new_index)
        self.card_selector.blockSignals(False)

        self.on_card_template_selected(new_index)
        self._enable_save()

    @Slot()
    def delete_card_template(self) -> None:
        if not self.current_model_id or not self.current_templates: return
        if len(self.current_templates) <= 1:
            QMessageBox.warning(self, "Erreur", "Un modèle doit contenir au moins une carte !")
            return

        idx = self.card_selector.currentIndex()
        card_name = self.current_templates[idx].get("name", "Cette carte")
        reply = QMessageBox.question(self, "Confirmation", f"Supprimer '{card_name}' ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.current_templates.pop(idx)
            self.card_selector.blockSignals(True)
            self.card_selector.removeItem(idx)
            self.card_selector.blockSignals(False)
            self.card_selector.setCurrentIndex(0)
            self.on_card_template_selected(0)
            self._enable_save()

    @Slot()
    def rename_card_template(self) -> None:
        if not self.current_model_id or not self.current_templates: return
        idx = self.card_selector.currentIndex()
        if idx < 0: return

        current_name = self.current_templates[idx].get("name", f"Carte {idx + 1}")
        new_name, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom :", text=current_name)

        if ok and new_name.strip() and new_name.strip() != current_name:
            self.current_templates[idx]["name"] = new_name.strip()
            self.card_selector.setItemText(idx, new_name.strip())
            self._enable_save()
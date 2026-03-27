import json
import os
from typing import Dict, List

from PySide6.QtCore import Qt, QUrl
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
        header_layout.addWidget(QLabel("<h2>🎨 Édition des Modèles (Note Types)</h2>"))

        self.btn_new_model = QPushButton("➕ Nouveau Modèle")
        self.btn_new_model.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_new_model.clicked.connect(self.create_new_model)
        header_layout.addWidget(self.btn_new_model)

        self.btn_save_model = QPushButton("💾 Sauvegarder les modifications")
        self.btn_save_model.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_save_model.clicked.connect(self.save_current_model)
        self.btn_save_model.setEnabled(False)
        header_layout.addWidget(self.btn_save_model)

        self.btn_refresh = QPushButton("🔄 Rafraîchir")
        self.btn_refresh.clicked.connect(self.refresh_models_list)
        header_layout.addWidget(self.btn_refresh)

        layout.addLayout(header_layout)

        main_splitter = QSplitter(Qt.Horizontal)

        # Liste des modèles
        self.models_list = QListWidget()
        self.models_list.itemClicked.connect(self.on_model_selected)

        # Panneau de droite
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        top_splitter = QSplitter(Qt.Vertical)

        # 1. Structure du Note Type (Métadonnées)
        meta_widget = QWidget()
        meta_layout = QVBoxLayout(meta_widget)

        self.fields_view = QTextEdit()
        self.fields_view.setMaximumHeight(60)
        self.fields_view.setToolTip("Pour modifier les champs, modifiez le JSON directement (Avancé).")
        self.fields_view.textChanged.connect(self._enable_save)

        self.css_editor = QTextEdit()
        self.css_editor.setStyleSheet("font-family: monospace; background-color: #1e1e1e; color: #d4d4d4;")
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

        self.btn_add_card = QPushButton("➕ Ajouter Carte")
        self.btn_add_card.clicked.connect(self.add_new_card_template)

        self.btn_ren_card = QPushButton("✏️")
        self.btn_ren_card.setToolTip("Renommer cette carte")
        self.btn_ren_card.clicked.connect(self.rename_card_template)

        self.btn_del_card = QPushButton("🗑️")
        self.btn_del_card.setStyleSheet("color: red;")
        self.btn_del_card.clicked.connect(self.delete_card_template)

        cards_toolbar.addWidget(QLabel("<b>Carte du modèle :</b>"))
        cards_toolbar.addWidget(self.card_selector)
        cards_toolbar.addWidget(self.side_selector)
        cards_toolbar.addWidget(self.btn_add_card)
        cards_toolbar.addWidget(self.btn_del_card)
        cards_toolbar.addWidget(self.btn_ren_card)

        cards_toolbar.addStretch()
        cards_layout.addLayout(cards_toolbar)

        html_preview_splitter = QSplitter(Qt.Horizontal)

        # Éditeurs HTML
        editors_widget = QWidget()
        editors_layout = QVBoxLayout(editors_widget)
        editors_layout.setContentsMargins(0, 0, 0, 0)

        self.qfmt_editor = QTextEdit()
        self.qfmt_editor.setStyleSheet("font-family: monospace; background-color: #1e1e1e; color: #d4d4d4;")
        self.afmt_editor = QTextEdit()
        self.afmt_editor.setStyleSheet("font-family: monospace; background-color: #1e1e1e; color: #d4d4d4;")

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

    def _enable_save(self) -> None:
        if self.current_model_id:
            self.btn_save_model.setEnabled(True)

    # ==========================================
    # ACTIONS BDD (Créer, Sauvegarder, Charger)
    # ==========================================

    def create_new_model(self) -> None:
        """Création assistée d'un nouveau NoteType."""
        name, ok = QInputDialog.getText(self, "Nouveau Modèle", "Nom du modèle (ex: Flashcard Code) :")
        if not ok or not name.strip(): return

        if NoteTypeModel.get_or_none(NoteTypeModel.name == name.strip()):
            QMessageBox.warning(self, "Erreur", "Un modèle porte déjà ce nom.")
            return

        fields_str, ok2 = QInputDialog.getText(self, "Champs de données",
                                               "Nom des champs séparés par des virgules :\n(Ex: Question, Réponse, Indice)")
        if not ok2 or not fields_str.strip(): return

        # Nettoyage des champs
        fields_list = [f.strip() for f in fields_str.split(",") if f.strip()]
        if not fields_list: fields_list = ["Front", "Back"]

        # Template de base par défaut
        default_templates = [{
            "name": "Carte 1",
            "qfmt": f"{{{{{fields_list[0]}}}}}",
            "afmt": f"{{{{FrontSide}}}}\n\n<hr id=answer>\n\n{{{{{fields_list[1] if len(fields_list) > 1 else fields_list[0]}}}}}"
        }]

        default_css = ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n  color: black;\n  background-color: white;\n}"

        try:
            with db.atomic():
                NoteTypeModel.create(
                    name=name.strip(),
                    fields_schema=json.dumps(fields_list, ensure_ascii=False),
                    templates=json.dumps(default_templates, ensure_ascii=False),
                    css_style=default_css
                )
            self.refresh_models_list()
            QMessageBox.information(self, "Succès", f"Le modèle '{name.strip()}' a été créé !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le modèle : {e}")

    def save_current_model(self) -> None:
        """Enregistre le HTML, le CSS et le schéma JSON actuel."""
        if not self.current_model_id: return

        try:
            note_type = NoteTypeModel.get_by_id(self.current_model_id)

            # Sauvegarde du CSS
            note_type.css_style = self.css_editor.toPlainText()

            # Sauvegarde des champs (On essaie de voir si c'est du JSON valide ou une liste à virgules)
            raw_fields = self.fields_view.toPlainText().strip()
            if raw_fields.startswith("["):
                note_type.fields_schema = raw_fields  # L'utilisateur a tapé du JSON
            else:
                fields_list = [f.strip() for f in raw_fields.split(",") if f.strip()]
                note_type.fields_schema = json.dumps(fields_list, ensure_ascii=False)

            # Sauvegarde du HTML de la carte en cours
            idx = self.card_selector.currentIndex()
            if 0 <= idx < len(self.current_templates):
                self.current_templates[idx]["qfmt"] = self.qfmt_editor.toPlainText()
                self.current_templates[idx]["afmt"] = self.afmt_editor.toPlainText()

            note_type.templates = json.dumps(self.current_templates, ensure_ascii=False)

            with db.atomic():
                note_type.save()

            self.btn_save_model.setEnabled(False)
            self.btn_save_model.setText("✅ Sauvegardé !")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, lambda: self.btn_save_model.setText("💾 Sauvegarder les modifications"))

        except Exception as e:
            QMessageBox.critical(self, "Erreur BDD", f"Impossible de sauvegarder : {e}")

    def refresh_models_list(self) -> None:
        self.models_list.clear()
        for note_type in NoteTypeModel.select().order_by(NoteTypeModel.name):
            item = QListWidgetItem(note_type.name)
            item.setData(Qt.UserRole, note_type.id)
            self.models_list.addItem(item)
        self.current_model_id = None
        self.btn_save_model.setEnabled(False)

    def on_model_selected(self, item: QListWidgetItem) -> None:
        model_id = item.data(Qt.UserRole)
        self.current_model_id = model_id
        self.btn_save_model.setEnabled(False)

        try:
            note_type = NoteTypeModel.get_by_id(model_id)

            fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []
            self.fields_view.blockSignals(True)
            self.fields_view.setPlainText(", ".join(fields))
            self.fields_view.blockSignals(False)

            self.mock_dict = {f: f"<span style='color:#888;'><i>[Simulation du champ {f}]</i></span>" for f in fields}

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
            self.qfmt_editor.setPlainText(f"Erreur de chargement : {e}")

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

    def update_preview(self) -> None:
        """Génère le rendu HTML et l'envoie à QWebEngineView (avec support des images locales)."""
        if not self.current_templates:
            return

        is_recto = self.side_selector.currentIndex() == 0
        raw_html = self.qfmt_editor.toPlainText() if is_recto else self.afmt_editor.toPlainText()
        css = self.css_editor.toPlainText()

        final_html = render_anki_card(
            raw_html=raw_html,
            css=css,
            fields_dict=self.mock_dict,
            is_recto=is_recto,
            front_html=self.qfmt_editor.toPlainText()
        )

        # Configuration du Base URL pour lire les images hachées par le MediaManager
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        media_dir = os.path.join(BASE_DIR, 'data', 'media')
        if not media_dir.endswith(os.sep):
            media_dir += os.sep
        base_url = QUrl.fromLocalFile(media_dir)

        self.web_view.setHtml(final_html, base_url)

    # ==========================================
    # GESTION DES CARTES (TEMPLATES)
    # ==========================================

    def add_new_card_template(self) -> None:
        """Ajoute un nouveau Recto/Verso au modèle actuel (ex: Carte inversée)."""
        if not self.current_model_id:
            QMessageBox.warning(self, "Erreur", "Veuillez d'abord sélectionner un modèle à gauche.")
            return

        name, ok = QInputDialog.getText(self, "Nouvelle Carte", "Nom de la carte (ex: Sens Inverse) :")
        if not ok or not name.strip():
            return

        # On crée un template vide de base
        new_template = {
            "name": name.strip(),
            "qfmt": "Écrivez le HTML du Recto ici...",
            "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\nÉcrivez le HTML du Verso ici..."
        }

        self.current_templates.append(new_template)

        # On met à jour la liste déroulante
        self.card_selector.blockSignals(True)
        self.card_selector.addItem(name.strip())
        new_index = len(self.current_templates) - 1
        self.card_selector.setCurrentIndex(new_index)
        self.card_selector.blockSignals(False)

        # On charge ce nouveau template à l'écran et on active la sauvegarde
        self.on_card_template_selected(new_index)
        self._enable_save()

    def delete_card_template(self) -> None:
        """Supprime la carte actuellement sélectionnée."""
        if not self.current_model_id or not self.current_templates:
            return

        if len(self.current_templates) <= 1:
            QMessageBox.warning(self, "Erreur",
                                "Un modèle doit contenir au moins une carte ! Vous ne pouvez pas supprimer la dernière.")
            return

        idx = self.card_selector.currentIndex()
        card_name = self.current_templates[idx].get("name", "Cette carte")

        reply = QMessageBox.question(self, "Confirmation",
                                     f"Voulez-vous vraiment supprimer '{card_name}' ?\nN'oubliez pas de sauvegarder après.",
                                     QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            # On retire le template de la liste
            self.current_templates.pop(idx)

            # On met à jour l'interface
            self.card_selector.blockSignals(True)
            self.card_selector.removeItem(idx)
            self.card_selector.blockSignals(False)

            # On bascule sur la première carte restante
            self.card_selector.setCurrentIndex(0)
            self.on_card_template_selected(0)
            self._enable_save()

    def rename_card_template(self) -> None:
        """Renomme la carte actuellement sélectionnée."""
        if not self.current_model_id or not self.current_templates:
            return

        idx = self.card_selector.currentIndex()
        if idx < 0:
            return

        # On récupère le nom actuel pour pré-remplir la boîte de dialogue
        current_name = self.current_templates[idx].get("name", f"Carte {idx + 1}")

        # On demande le nouveau nom
        new_name, ok = QInputDialog.getText(
            self,
            "Renommer la Carte",
            "Nouveau nom de la carte :",
            text=current_name
        )

        # Si l'utilisateur a cliqué sur OK, que le texte n'est pas vide et qu'il est différent de l'ancien
        if ok and new_name.strip() and new_name.strip() != current_name:
            clean_name = new_name.strip()

            # 1. Mise à jour de la mémoire (RAM)
            self.current_templates[idx]["name"] = clean_name

            # 2. Mise à jour de l'interface (Le texte de la liste déroulante)
            self.card_selector.setItemText(idx, clean_name)

            # 3. On allume le bouton "Sauvegarder"
            self._enable_save()
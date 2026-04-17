import json
import logging
from typing import cast

import qtawesome as qta
from PySide6.QtCore import Qt, QUrl, Slot, QTimer
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QTextEdit,
    QLabel,
    QSplitter,
    QComboBox,
    QListWidgetItem,
    QInputDialog,
    QMessageBox,
    QFrame,
    QPushButton,
)

from ankiforge.database.models import db, NoteTypeModel, CardModel, NoteModel
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, DangerButton, RoundedPanel
from ankiforge.ui.theme import is_dark_mode
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.ui.widgets.highlighters import AnkiHtmlHighlighter, CssHighlighter
from ankiforge.utils.anki_renderer import render_anki_card
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


class ModelsTab(QWidget):
    """
    Vue de gestion des Modèles de notes (Note Types).
    Permet de créer, configurer (champs, CSS) et éditer les templates HTML
    des cartes Anki (Recto/Verso) avec un rendu en direct.
    """

    def __init__(self) -> None:
        """Initialise l'onglet d'édition des modèles Anki."""
        super().__init__()

        # État interne
        self.current_model_id = None
        self.current_templates: list[dict[str, str]] = []
        self.mock_dict: dict[str, str | list[str]] = {}
        self.current_css: str = ""

        self._setup_ui()
        self._connect_signals()

        self.refresh_models_list()

    def _setup_ui(self) -> None:
        """Initialise et organise les layouts et widgets principaux."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self._build_header()

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)

        self._build_left_panel()
        self._build_right_panel()

        self.main_splitter.setSizes([200, 800])
        self.main_layout.addWidget(self.main_splitter)

    def _build_header(self) -> None:
        """Construit l'en-tête contenant le titre et les actions globales."""
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel("Édition des Modèles (Note Types)"))
        header_layout.addStretch()

        self.btn_new_model = ActionButton("fa5s.plus", " Nouveau Modèle")
        self.btn_refresh = ActionButton("fa5s.sync", " Rafraîchir")

        header_layout.addWidget(self.btn_new_model)
        header_layout.addWidget(self.btn_refresh)

        self.main_layout.addLayout(header_layout)

    def _build_left_panel(self) -> None:
        """Construit le panneau listant les modèles disponibles."""
        self.left_panel_widget = RoundedPanel()
        list_layout = QVBoxLayout(self.left_panel_widget)
        list_layout.setContentsMargins(15, 15, 15, 15)

        lbl_list = QLabel("MODÈLES DISPONIBLES")
        lbl_list.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        list_layout.addWidget(lbl_list)

        self.models_list = QListWidget()
        self.models_list.setFrameShape(QFrame.Shape.NoFrame)
        self.models_list.setStyleSheet("background: transparent;")

        list_layout.addWidget(self.models_list)
        self.main_splitter.addWidget(self.left_panel_widget)

    def _build_right_panel(self) -> None:
        """Construit le panneau principal d'édition scindé verticalement."""
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(10)

        self._build_global_config_panel()
        self._build_card_editor_panel()

        self.right_splitter.setSizes([300, 500])
        right_layout.addWidget(self.right_splitter)

        self.main_splitter.addWidget(right_panel)

    def _build_global_config_panel(self) -> None:
        """Construit la zone d'édition des champs de données et du CSS global."""
        self.meta_panel_widget = RoundedPanel()
        meta_layout = QVBoxLayout(self.meta_panel_widget)
        meta_layout.setContentsMargins(15, 15, 15, 15)

        lbl_meta = QLabel("CONFIGURATION GLOBALE")
        lbl_meta.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        meta_layout.addWidget(lbl_meta)

        lbl_fields = QLabel("CHAMPS DE DONNÉES (SÉPARÉS PAR DES VIRGULES) :")
        lbl_fields.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px; margin-top: 10px; margin-bottom: 5px;")
        meta_layout.addWidget(lbl_fields)

        self.fields_view = QTextEdit()
        self.fields_view.setMaximumHeight(60)
        meta_layout.addWidget(self.fields_view)

        lbl_css = QLabel("STYLE GLOBAL (CSS) :")
        lbl_css.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px; margin-top: 10px; margin-bottom: 5px;")
        meta_layout.addWidget(lbl_css)

        self.css_editor = QTextEdit()
        self.css_editor.setStyleSheet("font-family: monospace;")
        self.css_highlighter = CssHighlighter(self.css_editor.document())
        meta_layout.addWidget(self.css_editor)

        meta_actions = QHBoxLayout()
        meta_actions.addStretch()

        self.btn_del_model = DangerButton(qta.icon("fa5s.trash", color="white"), " Supprimer le modèle")
        self.btn_del_model.setEnabled(False)

        self.btn_save_model = PrimaryButton(qta.icon("fa5s.save", color="white"), " Sauvegarder le modèle")
        self.btn_save_model.setEnabled(False)

        meta_actions.addWidget(self.btn_del_model)
        meta_actions.addWidget(self.btn_save_model)
        meta_layout.addLayout(meta_actions)

        self.right_splitter.addWidget(self.meta_panel_widget)

    def _build_card_editor_panel(self) -> None:
        """Construit la zone de modification des templates HTML et l'aperçu WebEngine."""
        cards_panel = RoundedPanel()
        cards_layout = QVBoxLayout(cards_panel)
        cards_layout.setContentsMargins(15, 15, 15, 15)

        # Toolbar
        cards_toolbar = QHBoxLayout()
        lbl_card = QLabel("SÉLECTION DE LA CARTE :")
        lbl_card.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px;")
        cards_toolbar.addWidget(lbl_card)

        self.card_selector = QComboBox()
        self.card_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.card_selector.setMinimumWidth(130)
        cards_toolbar.addWidget(self.card_selector)

        self.btn_add_card = ActionButton("fa5s.plus", "")
        self.btn_add_card.setToolTip("Ajouter une carte")
        self.btn_ren_card = ActionButton("fa5s.pen", "")
        self.btn_ren_card.setToolTip("Renommer cette carte")
        self.btn_del_card = ActionButton("fa5s.trash", "")
        self.btn_del_card.setToolTip("Supprimer cette carte")

        cards_toolbar.addWidget(self.btn_add_card)
        cards_toolbar.addWidget(self.btn_ren_card)
        cards_toolbar.addWidget(self.btn_del_card)
        cards_toolbar.addStretch()

        self.btn_focus_mode = ActionButton("fa5s.expand", " Mode Focus")
        self.btn_focus_mode.setToolTip("Basculer vers l'éditeur plein écran")
        self.btn_focus_mode.clicked.connect(self.toggle_focus_mode)
        cards_toolbar.addWidget(self.btn_focus_mode)

        lbl_side = QLabel("PRÉVISUALISATION :")
        lbl_side.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px;")
        cards_toolbar.addWidget(lbl_side)

        self.side_selector = QComboBox()
        self.side_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.side_selector.setMinimumWidth(130)
        self.side_selector.addItems(["Voir Recto", "Voir Verso"])
        cards_toolbar.addWidget(self.side_selector)

        cards_layout.addLayout(cards_toolbar)

        # Barre de snippets
        snippets_layout = QHBoxLayout()
        snippets_layout.setSpacing(5)

        snippets = [
            ("{{Champ}}", "{{Champ}}"),
            ("{{FrontSide}}", "{{FrontSide}}"),
            ("{{cloze:Champ}}", "{{cloze:Champ}}"),
            ("<hr id=answer>", "<hr id=answer>"),
        ]

        for label, text in snippets:
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setStyleSheet("font-size: 10px; padding: 2px 5px; border: 1px solid palette(alternate-base); border-radius: 3px;")
            btn.clicked.connect(lambda _, t=text: self.insert_snippet(t))
            snippets_layout.addWidget(btn)

        snippets_layout.addStretch()
        cards_layout.addLayout(snippets_layout)

        # Splitter HTML vs Preview
        html_preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        html_preview_splitter.setHandleWidth(10)

        editors_widget = QWidget()
        editors_layout = QVBoxLayout(editors_widget)
        editors_layout.setContentsMargins(0, 10, 10, 0)

        lbl_qfmt = QLabel("HTML DU RECTO :")
        lbl_qfmt.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px; margin-bottom: 5px;")
        editors_layout.addWidget(lbl_qfmt)

        self.qfmt_editor = QTextEdit()
        self.qfmt_editor.setStyleSheet("font-family: monospace;")
        self.qfmt_highlighter = AnkiHtmlHighlighter(self.qfmt_editor.document())
        editors_layout.addWidget(self.qfmt_editor)

        lbl_afmt = QLabel("HTML DU VERSO :")
        lbl_afmt.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px; margin-top: 15px; margin-bottom: 5px;")
        editors_layout.addWidget(lbl_afmt)

        self.afmt_editor = QTextEdit()
        self.afmt_editor.setStyleSheet("font-family: monospace;")
        self.afmt_highlighter = AnkiHtmlHighlighter(self.afmt_editor.document())
        editors_layout.addWidget(self.afmt_editor)

        self.web_view = QWebEngineView()
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        html_preview_splitter.addWidget(editors_widget)
        html_preview_splitter.addWidget(self.web_view)
        html_preview_splitter.setSizes([350, 350])

        cards_layout.addWidget(html_preview_splitter)
        self.right_splitter.addWidget(cards_panel)

    def _connect_signals(self) -> None:
        """Centralise le branchement des signaux de l'interface."""
        # En-tête
        self.btn_new_model.clicked.connect(self.create_new_model)
        self.btn_refresh.clicked.connect(self.refresh_models_list)

        # Liste des modèles
        self.models_list.itemClicked.connect(self.on_model_selected)

        # Boutons d'action (Modèle)
        self.btn_del_model.clicked.connect(self.delete_current_model)
        self.btn_save_model.clicked.connect(self.save_current_model)

        # Éditeurs textuels
        self.fields_view.textChanged.connect(self._enable_save)
        self.css_editor.textChanged.connect(self.update_preview)
        self.css_editor.textChanged.connect(self._enable_save)
        self.qfmt_editor.textChanged.connect(self.sync_editor_to_template)
        self.afmt_editor.textChanged.connect(self.sync_editor_to_template)

        # Toolbar (Cartes)
        self.card_selector.currentIndexChanged.connect(self.on_card_template_selected)
        self.side_selector.currentIndexChanged.connect(self.update_preview)
        self.btn_add_card.clicked.connect(self.add_new_card_template)
        self.btn_ren_card.clicked.connect(self.rename_card_template)
        self.btn_del_card.clicked.connect(self.delete_card_template)

    @Slot()
    def refresh_data(self) -> None:
        """Méthode standardisée appelée par la MainWindow au changement d'onglet."""
        self.refresh_models_list()

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
            f"Voulez-vous vraiment supprimer le modèle '{model.name}' ?\nATTENTION : Cela supprimera ÉGALEMENT toutes les notes et cartes utilisant ce modèle !",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    model.delete_instance(recursive=True)  # Supprime en cascade
                logger.info(f"Modèle '{model.name}' supprimé avec succès.")
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
                logger.exception(f"Impossible de supprimer le modèle '{model.name}' :")
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le modèle :\n{e}")

    @Slot()
    def create_new_model(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Modèle", "Nom du modèle :")
        if not ok or not name.strip():
            return

        if NoteTypeModel.get_or_none(NoteTypeModel.name == name.strip()):
            QMessageBox.warning(self, "Erreur", "Un modèle porte déjà ce nom.")
            return

        fields_str, ok2 = QInputDialog.getText(self, "Champs de données", "Noms séparés par des virgules :")
        if not ok2 or not fields_str.strip():
            return

        fields_list = [f.strip() for f in fields_str.split(",") if f.strip()]
        if not fields_list:
            fields_list = ["Front", "Back"]

        default_templates = [
            {
                "name": "Carte 1",
                "qfmt": f"{{{{{fields_list[0]}}}}}",
                "afmt": f"{{{{FrontSide}}}}\n\n<hr id=answer>\n\n{{{{{fields_list[1] if len(fields_list) > 1 else fields_list[0]}}}}}",
            }
        ]
        default_css = ".card { font-family: arial; font-size: 20px; text-align: center; color: white; background-color: #1e1e1e; }"

        try:
            with db.atomic():
                NoteTypeModel.create(
                    name=name.strip(),
                    fields_schema=json.dumps(fields_list, ensure_ascii=False),
                    templates=json.dumps(default_templates, ensure_ascii=False),
                    css_style=default_css,
                )
            logger.info(f"Nouveau modèle créé : {name.strip()}")
            self.refresh_models_list()
        except Exception as e:
            logger.exception(f"Impossible de créer le modèle '{name.strip()}' :")
            QMessageBox.critical(self, "Erreur", f"Impossible de créer le modèle : {e}")

    @Slot()
    def save_current_model(self) -> None:
        if not self.current_model_id:
            return

        try:
            note_type = NoteTypeModel.get_by_id(self.current_model_id)
            note_type.css_style = self.css_editor.toPlainText()

            raw_fields = self.fields_view.toPlainText().strip()

            if raw_fields.startswith("["):
                try:
                    # On teste si c'est du vrai JSON
                    parsed_json = json.loads(raw_fields)
                    note_type.fields_schema = json.dumps(parsed_json, ensure_ascii=False)
                except json.JSONDecodeError:
                    QMessageBox.warning(
                        self,
                        "Erreur de syntaxe",
                        "Le JSON des champs est invalide. Vérifiez vos crochets et guillemets.",
                    )
                    return
            else:
                fields_list = [f.strip() for f in raw_fields.split(",") if f.strip()]
                note_type.fields_schema = json.dumps(fields_list, ensure_ascii=False)

            note_type.templates = json.dumps(self.current_templates, ensure_ascii=False)

            with db.atomic():
                note_type.save()

            logger.info(f"Modèle '{note_type.name}' sauvegardé.")
            self.btn_save_model.setEnabled(False)
            self.btn_save_model.setText(" Sauvegardé !")
            self.btn_save_model.setIcon(qta.icon("fa5s.check"))

            QTimer.singleShot(1500, self._reset_save_btn)

        except Exception as e:
            logger.exception("Impossible de sauvegarder le modèle :")
            QMessageBox.critical(self, "Erreur BDD", f"Impossible de sauvegarder : {e}")

    @Slot()
    def _reset_save_btn(self):
        self.btn_save_model.setText(" Sauvegarder")
        self.btn_save_model.setIcon(qta.icon("fa5s.save"))

    @Slot()
    def delete_card_template(self) -> None:
        if not self.current_model_id or not self.current_templates:
            return
        if len(self.current_templates) <= 1:
            QMessageBox.warning(self, "Erreur", "Un modèle doit contenir au moins une carte !")
            return

        idx = self.card_selector.currentIndex()
        card_name = self.current_templates[idx].get("name", "Cette carte")

        # 1. On compte combien de vraies cartes physiques vont être affectées
        cards_affected = CardModel.select().join(NoteModel).where((NoteModel.note_type_id == self.current_model_id) & (CardModel.template_index == idx)).count()

        # 2. On prépare le message d'avertissement adaptatif
        warn_text = f"Voulez-vous vraiment supprimer le modèle de carte '{card_name}' ?"
        if cards_affected > 0:
            warn_text += f"\n\n⚠️ ATTENTION : Cela supprimera DÉFINITIVEMENT {cards_affected} carte(s) existante(s) dans vos paquets !"

        reply = QMessageBox.question(
            self,
            "Confirmation de suppression",
            warn_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    # 3. On fait le ménage dans la base de données physique
                    if cards_affected > 0:
                        # Sous-requête pour trouver les notes concernées
                        notes_ids = NoteModel.select(NoteModel.id).where(NoteModel.note_type_id == self.current_model_id)

                        # A. On supprime les cartes utilisant ce template
                        CardModel.delete().where((CardModel.note_id.in_(notes_ids)) & (CardModel.template_index == idx)).execute()

                        # B. On décale l'index des cartes suivantes (ex: la carte 3 devient la carte 2)
                        CardModel.update(template_index=CardModel.template_index - 1).where((CardModel.note_id.in_(notes_ids)) & (CardModel.template_index > idx)).execute()

                    # 4. On supprime le template du JSON et on sauvegarde
                    self.current_templates.pop(idx)
                    note_type = NoteTypeModel.get_by_id(self.current_model_id)
                    note_type.templates = json.dumps(self.current_templates, ensure_ascii=False)
                    note_type.save()

                # 5. On rafraîchit l'interface UI
                self.card_selector.blockSignals(True)
                self.card_selector.removeItem(idx)
                self.card_selector.blockSignals(False)
                self.card_selector.setCurrentIndex(0)
                self.on_card_template_selected(0)

                logger.info(f"Modèle de carte '{card_name}' supprimé avec succès.")
                show_toast(self, f"Modèle '{card_name}' supprimé !")

            except Exception as e:
                logger.exception(f"Impossible de supprimer le modèle de carte '{card_name}' :")
                QMessageBox.critical(self, "Erreur Base de donnée", f"Impossible de supprimer le modèle :\n{e}")

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
            logger.exception(f"Erreur lors de la sélection du modèle {model_id} :")
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
            raw_html=raw_html,
            css=css,
            fields_dict=self.mock_dict,
            is_recto=is_recto,
            front_html=self.qfmt_editor.toPlainText(),
            is_dark_mode=is_dark_mode(),
        )

        media_dir = get_app_data_dir() / "media"
        media_dir.mkdir(exist_ok=True)  # S'assure que le dossier existe

        base_url = QUrl.fromLocalFile(str(media_dir) + "/")

        self.web_view.setHtml(final_html, base_url)

    @Slot()
    def add_new_card_template(self) -> None:
        if not self.current_model_id:
            return
        name, ok = QInputDialog.getText(self, "Nouvelle Carte", "Nom de la carte :")
        if not ok or not name.strip():
            return

        new_template = {
            "name": name.strip(),
            "qfmt": "Écrivez le HTML du Recto ici...",
            "afmt": "{{FrontSide}}\n\n<hr id=answer>\n\nÉcrivez le HTML du Verso ici...",
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
    def rename_card_template(self) -> None:
        if not self.current_model_id or not self.current_templates:
            return
        idx = self.card_selector.currentIndex()
        if idx < 0:
            return

        current_name = self.current_templates[idx].get("name", f"Carte {idx + 1}")
        new_name, ok = QInputDialog.getText(self, "Renommer", "Nouveau nom :", text=current_name)

        if ok and new_name.strip() and new_name.strip() != current_name:
            self.current_templates[idx]["name"] = new_name.strip()
            self.card_selector.setItemText(idx, new_name.strip())
            self._enable_save()

    @Slot()
    def toggle_focus_mode(self) -> None:
        """Bascule entre le mode normal et le mode focus (plein écran)."""
        is_focused = not self.left_panel_widget.isVisible()

        if is_focused:
            # Revenir au mode normal
            self.left_panel_widget.setVisible(True)
            self.meta_panel_widget.setVisible(True)
            self.btn_focus_mode.setText(" Mode Focus")
            self.btn_focus_mode.setIcon(qta.icon("fa5s.expand"))
        else:
            # Passer en mode focus
            self.left_panel_widget.setVisible(False)
            self.meta_panel_widget.setVisible(False)
            self.btn_focus_mode.setText(" Quitter Focus")
            self.btn_focus_mode.setIcon(qta.icon("fa5s.compress"))

    def insert_snippet(self, text: str) -> None:
        """Insère un snippet de code dans l'éditeur qui a le focus."""
        focused_widget = self.focusWidget()
        # On vérifie si c'est un de nos éditeurs HTML
        if focused_widget in [self.qfmt_editor, self.afmt_editor]:
            cast(QTextEdit, focused_widget).textCursor().insertText(text)
        else:
            # Par défaut, on insère dans celui qui est probablement en cours d'usage si aucun n'a le focus direct
            is_recto = self.side_selector.currentIndex() == 0
            editor = self.qfmt_editor if is_recto else self.afmt_editor
            editor.textCursor().insertText(text)
            editor.setFocus()

    @Slot()
    def sync_editor_to_template(self) -> None:
        """Met à jour le modèle en mémoire en temps réel quand on tape dans l'éditeur."""
        if not self.current_templates or self.current_model_id is None:
            return

        idx = self.card_selector.currentIndex()
        if 0 <= idx < len(self.current_templates):
            qfmt_text = self.qfmt_editor.toPlainText()
            afmt_text = self.afmt_editor.toPlainText()

            # On vérifie si ça a vraiment changé pour ne déclencher l'aperçu que si nécessaire
            changed = False
            if self.current_templates[idx].get("qfmt") != qfmt_text:
                self.current_templates[idx]["qfmt"] = qfmt_text
                changed = True
            if self.current_templates[idx].get("afmt") != afmt_text:
                self.current_templates[idx]["afmt"] = afmt_text
                changed = True

            if changed:
                self._enable_save()
                self.update_preview()

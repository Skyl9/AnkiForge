"""
Vue Card Models (Éditeur de Modèles de Cartes) — 100% Conforme à la Maquette concept_ide.
- Panneau gauche (250px) : Liste des modèles de cartes disponibles (Peewee NoteTypeModel).
- Panneau central : Éditeur de champs (virgules), onglets Style CSS, HTML Recto, HTML Verso, et toolbar d'insertion de tags ({{Texte}}, {{Extra}}, {{cloze:...}}).
- Panneau droit (400px) : Live Preview de carte Anki via CardPreviewWidget (MathJax, CSS, Cloze).
"""

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.components import (
    DangerButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class CardModelsView(QWidget):
    """
    Vue Card Models — 100% Conforme à la Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_model: Optional[NoteTypeModel] = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- PANNEAU GAUCHE : Modèles Disponibles (250px) ---
        self.list_panel = IdePanel(detachable=True)
        self.list_panel.setMinimumWidth(240)

        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        lbl_list_title = QLabel("MODÈLES EN BASE")
        lbl_list_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        list_layout.addWidget(lbl_list_title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 10px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                font-weight: 500;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        list_layout.addWidget(self.list_widget, 1)

        # Toolbar inférieure (Nouveau & Supprimer)
        list_toolbar = QHBoxLayout()
        list_toolbar.setSpacing(6)

        self.btn_new = SecondaryButton("Nouveau")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))

        self.btn_del = DangerButton("Supprimer", ghost=True)
        self.btn_del.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))

        list_toolbar.addWidget(self.btn_new, 1)
        list_toolbar.addWidget(self.btn_del, 1)
        list_layout.addLayout(list_toolbar)

        self.list_panel.add_tab("Modèles de Cartes", list_content, "ph.swatches", closable=False)
        self.main_splitter.addWidget(self.list_panel)

        # --- PANNEAU CENTRAL : Éditeur de Modèle ---
        self.editor_panel = IdePanel(detachable=True)

        # Header Widgets du panneau d'édition (Rafraîchir & Sauvegarder)
        self.btn_refresh = SecondaryButton("Rafraîchir")
        self.btn_refresh.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #047857);
            }
        """)

        self.editor_panel.add_header_widget(self.btn_refresh)
        self.editor_panel.add_header_widget(self.btn_save)
        self.editor_panel.add_header_separator()

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(14, 14, 14, 14)
        editor_layout.setSpacing(10)

        # Form Group : Champs de données
        lbl_fields = QLabel("CHAMPS DE DONNÉES (SÉPARÉS PAR DES VIRGULES) :")
        lbl_fields.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_fields)

        self.fields_input = StyledLineEdit()
        self.fields_input.setPlaceholderText("Texte, Extra")
        editor_layout.addWidget(self.fields_input)

        # Selection de carte / Template Toolbar
        card_sel_row = QHBoxLayout()
        card_sel_row.setSpacing(8)

        lbl_card_sel = QLabel("SÉLECTION DE LA CARTE :")
        lbl_card_sel.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        card_sel_row.addWidget(lbl_card_sel)

        self.card_selector_combo = StyledComboBox()
        self.card_selector_combo.setMinimumWidth(140)
        self.card_selector_combo.addItem("Carte 1", userData=0)
        card_sel_row.addWidget(self.card_selector_combo)

        card_sel_row.addStretch()
        editor_layout.addLayout(card_sel_row)

        # Sub-tabs Selector (CSS, HTML Recto, HTML Verso)
        subtabs_row = QHBoxLayout()
        subtabs_row.setSpacing(4)

        self.btn_subtab_css = SecondaryButton("Style CSS")
        self.btn_subtab_css.setIcon(load_phosphor_icon("ph.file-css", color=DesignTokens.COLOR_PURPLE))

        self.btn_subtab_front = SecondaryButton("HTML Recto")
        self.btn_subtab_front.setIcon(load_phosphor_icon("ph.file-html", color=DesignTokens.COLOR_BLUE))

        self.btn_subtab_back = SecondaryButton("HTML Verso")
        self.btn_subtab_back.setIcon(load_phosphor_icon("ph.file-html", color="#eab308"))

        subtabs_row.addWidget(self.btn_subtab_css)
        subtabs_row.addWidget(self.btn_subtab_front)
        subtabs_row.addWidget(self.btn_subtab_back)
        subtabs_row.addStretch()

        editor_layout.addLayout(subtabs_row)

        # Toolbar dynamique d'insertion de tags ({{Texte}}, {{Extra}}, {{cloze:...}})
        self.tags_toolbar_layout = QHBoxLayout()
        self.tags_toolbar_layout.setContentsMargins(0, 4, 0, 4)
        self.tags_toolbar_layout.setSpacing(6)
        editor_layout.addLayout(self.tags_toolbar_layout)

        # Stacked Editors Container (CSS, Front HTML, Back HTML)
        self.editor_stack = QStackedWidget()

        # Editor 0: CSS
        self.css_editor = StyledTextEdit()
        self.css_editor.setPlaceholderText(".card { font-family: arial; text-align: center; }")
        self.css_editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #090a0f;
                color: #a5b4fc;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 13px;
                border: 1px solid #2d313a;
                border-radius: 6px;
            }
        """)
        self.editor_stack.addWidget(self.css_editor)

        # Editor 1: Front HTML
        self.front_html_editor = StyledTextEdit()
        self.front_html_editor.setPlaceholderText("{{cloze:Texte}}")
        self.front_html_editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #090a0f;
                color: #a5b4fc;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 13px;
                border: 1px solid #2d313a;
                border-radius: 6px;
            }
        """)
        self.editor_stack.addWidget(self.front_html_editor)

        # Editor 2: Back HTML
        self.back_html_editor = StyledTextEdit()
        self.back_html_editor.setPlaceholderText('{{cloze:Texte}}<br><hr id="answer"><br>{{Extra}}')
        self.back_html_editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #090a0f;
                color: #a5b4fc;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 13px;
                border: 1px solid #2d313a;
                border-radius: 6px;
            }
        """)
        self.editor_stack.addWidget(self.back_html_editor)

        editor_layout.addWidget(self.editor_stack, 1)

        self.editor_panel.add_tab("Éditeur de Modèle", editor_content, "ph.pencil-simple", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        # --- PANNEAU DROIT : Live Preview (400px) ---
        self.preview_panel = IdePanel(detachable=True)
        self.preview_panel.setMinimumWidth(340)

        preview_content = QWidget()
        preview_layout = QVBoxLayout(preview_content)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        # Preview Controls Header
        prev_controls_widget = QWidget()
        prev_controls_widget.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        prev_controls = QHBoxLayout(prev_controls_widget)
        prev_controls.setContentsMargins(12, 8, 12, 8)
        prev_controls.setSpacing(8)

        lbl_prev = QLabel("LIVE PREVIEW")
        lbl_prev.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        prev_controls.addWidget(lbl_prev)

        prev_controls.addStretch()

        self.view_side_combo = StyledComboBox()
        self.view_side_combo.addItems(["Voir Recto", "Voir Verso"])
        prev_controls.addWidget(self.view_side_combo)

        preview_layout.addWidget(prev_controls_widget)

        # WebEngine Anki Preview Container
        self.card_preview_widget = CardPreviewWidget()
        preview_layout.addWidget(self.card_preview_widget, 1)

        self.preview_panel.add_tab("Live Preview Modèle", preview_content, "ph.monitor", closable=False)
        self.main_splitter.addWidget(self.preview_panel)

        self.main_splitter.setSizes([240, 500, 380])

    def _connect_signals(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.btn_new.clicked.connect(self._on_new_model)
        self.btn_del.clicked.connect(self._on_delete_model)

        self.btn_refresh.clicked.connect(self._update_preview)
        self.btn_save.clicked.connect(self._on_save_model)

        self.fields_input.textChanged.connect(self._on_fields_changed)

        self.btn_subtab_css.clicked.connect(lambda: self.editor_stack.setCurrentIndex(0))
        self.btn_subtab_front.clicked.connect(lambda: self.editor_stack.setCurrentIndex(1))
        self.btn_subtab_back.clicked.connect(lambda: self.editor_stack.setCurrentIndex(2))

        self.css_editor.textChanged.connect(self._update_preview)
        self.front_html_editor.textChanged.connect(self._update_preview)
        self.back_html_editor.textChanged.connect(self._update_preview)
        self.view_side_combo.currentIndexChanged.connect(self._update_preview)

    def refresh_data(self) -> None:
        """Recharge la liste des modèles depuis la base Peewee."""
        try:
            self.list_widget.blockSignals(True)
            self.list_widget.clear()

            models = list(NoteTypeModel.select())
            for m in models:
                item = QListWidgetItem(m.name)
                item.setData(Qt.ItemDataRole.UserRole, m)
                self.list_widget.addItem(item)

            self.list_widget.blockSignals(False)

            if models and not self._current_model:
                self.list_widget.setCurrentRow(0)

        except Exception as e:
            logger.warning("Erreur refresh_data card_models_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot()
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_model = None
            return

        model: Optional[NoteTypeModel] = current.data(Qt.ItemDataRole.UserRole)
        if not model:
            return

        self._current_model = model

        # Décompilation des champs schema JSON -> Texte séparé par virgules
        if model.fields_schema:
            try:
                parsed_fields = json.loads(model.fields_schema)
                if isinstance(parsed_fields, list):
                    self.fields_input.setText(", ".join(parsed_fields))
                else:
                    self.fields_input.setText("Texte, Extra")
            except Exception:
                self.fields_input.setText("Texte, Extra")
        else:
            self.fields_input.setText("Front, Back")

        self.css_editor.setPlainText(model.css_style or ".card { font-family: arial; text-align: center; }")

        # Décompilation des templates JSON -> Front & Back HTML
        if model.templates:
            try:
                parsed_tmpl = json.loads(model.templates)
                if isinstance(parsed_tmpl, list) and parsed_tmpl:
                    first_tmpl = parsed_tmpl[0]
                    self.front_html_editor.setPlainText(first_tmpl.get("qfmt", "{{Front}}"))
                    self.back_html_editor.setPlainText(first_tmpl.get("afmt", "{{Front}}<hr id=answer>{{Back}}"))
                else:
                    self.front_html_editor.setPlainText("{{Front}}")
                    self.back_html_editor.setPlainText("{{Front}}<hr id=answer>{{Back}}")
            except Exception:
                self.front_html_editor.setPlainText("{{Front}}")
                self.back_html_editor.setPlainText("{{Front}}<hr id=answer>{{Back}}")
        else:
            self.front_html_editor.setPlainText("{{Front}}")
            self.back_html_editor.setPlainText("{{Front}}<hr id=answer>{{Back}}")

        self._update_tags_toolbar()
        self._update_preview()

    @Slot()
    def _on_fields_changed(self) -> None:
        self._update_tags_toolbar()

    def _update_tags_toolbar(self) -> None:
        """Génère dynamiquement les boutons d'insertion de tags selon les champs spécifiés."""
        while self.tags_toolbar_layout.count():
            child = self.tags_toolbar_layout.takeAt(0)
            if child and child.widget():
                child.widget().deleteLater()

        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Texte", "Extra"]

        for f in raw_fields:
            tag_str = f"{{{{{f}}}}}"
            btn = SecondaryButton(tag_str)
            btn.setStyleSheet("padding: 2px 8px; font-size: 11px; font-family: monospace;")
            btn.clicked.connect(lambda _, t=tag_str: self._insert_tag_to_active_editor(t))
            self.tags_toolbar_layout.addWidget(btn)

            cloze_str = f"{{{{cloze:{f}}}}}"
            btn_c = SecondaryButton(cloze_str)
            btn_c.setStyleSheet("padding: 2px 8px; font-size: 11px; font-family: monospace; color: #a78bfa;")
            btn_c.clicked.connect(lambda _, t=cloze_str: self._insert_tag_to_active_editor(t))
            self.tags_toolbar_layout.addWidget(btn_c)

        btn_fs = SecondaryButton("{{FrontSide}}")
        btn_fs.setStyleSheet("padding: 2px 8px; font-size: 11px; font-family: monospace;")
        btn_fs.clicked.connect(lambda: self._insert_tag_to_active_editor("{{FrontSide}}"))
        self.tags_toolbar_layout.addWidget(btn_fs)

        btn_hr = SecondaryButton('<hr id="answer">')
        btn_hr.setStyleSheet("padding: 2px 8px; font-size: 11px; font-family: monospace;")
        btn_hr.clicked.connect(lambda: self._insert_tag_to_active_editor('<hr id="answer">'))
        self.tags_toolbar_layout.addWidget(btn_hr)

        self.tags_toolbar_layout.addStretch()

    def _insert_tag_to_active_editor(self, tag_str: str) -> None:
        active_idx = self.editor_stack.currentIndex()
        if active_idx == 1:
            self.front_html_editor.insertPlainText(tag_str)
        elif active_idx == 2:
            self.back_html_editor.insertPlainText(tag_str)
        else:
            self.css_editor.insertPlainText(tag_str)

    @Slot()
    def _update_preview(self) -> None:
        """Met à jour l'aperçu WebEngine temps réel (CardPreviewWidget)."""
        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Front", "Back"]

        # Mock data dictionary
        mock_fields: dict[str, str] = {}
        for f in raw_fields:
            if "cloze" in f.lower() or "texte" in f.lower() or "front" in f.lower():
                mock_fields[f] = "La capitale de la France est {{c1::Paris::Ville}}."
            elif "extra" in f.lower() or "back" in f.lower() or "answer" in f.lower():
                mock_fields[f] = "Paris est la ville la plus peuplée de France."
            else:
                mock_fields[f] = f"Exemple de contenu pour {f}"

        qfmt = self.front_html_editor.toPlainText()
        afmt = self.back_html_editor.toPlainText()
        css = self.css_editor.toPlainText()

        tmpl = {"name": "Carte 1", "qfmt": qfmt}
        is_verso = self.view_side_combo.currentIndex() == 1
        if is_verso:
            tmpl["afmt"] = afmt

        self.card_preview_widget.update_preview(
            note_type=self._current_model,
            fields_dict=mock_fields,
            override_templates=[tmpl],
            override_css=css,
        )

    @Slot()
    def _on_new_model(self) -> None:
        model_name, ok = QInputDialog.getText(self, "Nouveau modèle de carte", "Nom du modèle :")
        if ok and model_name.strip():
            try:
                name = model_name.strip()
                default_schema = json.dumps(["Front", "Back"], ensure_ascii=False)
                default_css = ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n  color: #f8fafc;\n  background-color: #1e2128;\n}"
                default_tmpl = json.dumps(
                    [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}],
                    ensure_ascii=False,
                )

                NoteTypeModel.create(
                    name=name,
                    fields_schema=default_schema,
                    css_style=default_css,
                    templates=default_tmpl,
                )
                self.refresh_data()

                # Sélectionner le nouveau modèle
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    if item.text() == name:
                        self.list_widget.setCurrentItem(item)
                        break

                show_toast(self, f"Modèle '{name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le modèle : {str(e)}")

    @Slot()
    def _on_delete_model(self) -> None:
        if not self._current_model:
            show_toast(self, "Aucun modèle sélectionné.", is_error=True)
            return

        confirm = QMessageBox.question(
            self,
            "Supprimer le modèle",
            f"Voulez-vous vraiment supprimer le modèle '{self._current_model.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                self._current_model.delete_instance()
                self._current_model = None
                self.refresh_data()
                show_toast(self, "Modèle supprimé de la base de données.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le modèle : {str(e)}")

    @Slot()
    def _on_save_model(self) -> None:
        if not self._current_model:
            show_toast(self, "Aucun modèle sélectionné à sauvegarder.", is_error=True)
            return

        try:
            raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
            schema_json = json.dumps(raw_fields, ensure_ascii=False)

            qfmt = self.front_html_editor.toPlainText()
            afmt = self.back_html_editor.toPlainText()

            templates_obj = [{"name": "Carte 1", "qfmt": qfmt, "afmt": afmt}]
            templates_json = json.dumps(templates_obj, ensure_ascii=False)

            css = self.css_editor.toPlainText()

            self._current_model.fields_schema = schema_json
            self._current_model.css_style = css
            self._current_model.templates = templates_json
            self._current_model.save()

            show_toast(self, f"Modèle '{self._current_model.name}' enregistré avec succès !")
            self._update_preview()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement : {str(e)}")


CardModelsTab = CardModelsView

import json
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QTextEdit, QLabel, QLineEdit
from PySide6.QtCore import Qt

from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.theme import DesignTokens


class CardModelsView(QWidget):
    """
    Card Models View:
    - 3-column split layout with IdePanel
    - Left: List of NoteTypeModel from database with "Nouveau" / "Supprimer" buttons.
    - Center: Model Editor (fields schema configuration, CSS style editor, Front HTML template, Back HTML template).
    - Right: Live Preview rendering simulated card with current CSS & HTML templates.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_model: Optional[NoteTypeModel] = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # --- Left Panel: List ---
        self.list_panel = IdePanel(title="Modèles")
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_SM}px;")

        list_btn_layout = QHBoxLayout()
        self.btn_new = PrimaryButton("Nouveau")
        self.btn_del = SecondaryButton("Supprimer")
        list_btn_layout.addWidget(self.btn_new)
        list_btn_layout.addWidget(self.btn_del)

        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.addWidget(self.list_widget)
        list_layout.addLayout(list_btn_layout)

        self.list_panel.add_tab("Liste", list_container, "ph.list")
        self.splitter.addWidget(self.list_panel)

        # --- Center Panel: Editor ---
        self.editor_panel = IdePanel(title="Éditeur")
        editor_container = QWidget()
        editor_layout = QVBoxLayout(editor_container)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nom du modèle")
        editor_layout.addWidget(QLabel("Nom du modèle:"))
        editor_layout.addWidget(self.name_input)

        self.schema_input = QTextEdit()
        self.schema_input.setPlaceholderText('["Front", "Back"]')
        self.schema_input.setStyleSheet("background-color: #090a0f; color: #a5b4fc; font-family: monospace; border: 1px solid #2d313a; border-radius: 4px;")
        editor_layout.addWidget(QLabel("Champs (JSON):"))
        editor_layout.addWidget(self.schema_input)

        self.css_input = QTextEdit()
        self.css_input.setPlaceholderText(".card { font-family: arial; }")
        self.css_input.setStyleSheet("background-color: #090a0f; color: #a5b4fc; font-family: monospace; border: 1px solid #2d313a; border-radius: 4px;")
        editor_layout.addWidget(QLabel("Style CSS:"))
        editor_layout.addWidget(self.css_input)

        self.html_input = QTextEdit()
        self.html_input.setPlaceholderText('[{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Front}}<hr id=answer>{{Back}}"}]')
        self.html_input.setStyleSheet("background-color: #090a0f; color: #a5b4fc; font-family: monospace; border: 1px solid #2d313a; border-radius: 4px;")
        editor_layout.addWidget(QLabel("Templates (JSON):"))
        editor_layout.addWidget(self.html_input)

        tag_btn_layout = QHBoxLayout()
        btn_text = SecondaryButton("{{Texte}}")
        btn_extra = SecondaryButton("{{Extra}}")
        btn_cloze = SecondaryButton("{{cloze:Texte}}")

        btn_text.clicked.connect(lambda: self.html_input.insertPlainText("{{Texte}}"))
        btn_extra.clicked.connect(lambda: self.html_input.insertPlainText("{{Extra}}"))
        btn_cloze.clicked.connect(lambda: self.html_input.insertPlainText("{{cloze:Texte}}"))

        tag_btn_layout.addWidget(btn_text)
        tag_btn_layout.addWidget(btn_extra)
        tag_btn_layout.addWidget(btn_cloze)
        editor_layout.addLayout(tag_btn_layout)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.clicked.connect(self._save_model)
        editor_layout.addWidget(self.btn_save)

        self.editor_panel.add_tab("Configuration", editor_container, "ph.code")
        self.splitter.addWidget(self.editor_panel)

        # --- Right Panel: Preview ---
        self.preview_panel = IdePanel(title="Aperçu")
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        self.preview_label = QLabel("Aperçu HTML simulé ici")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setWordWrap(True)
        preview_layout.addWidget(self.preview_label)
        self.preview_panel.add_tab("Live Preview", preview_container, "ph.eye")
        self.splitter.addWidget(self.preview_panel)

        # Configure Splitter
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 2)

        # Connections
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.btn_new.clicked.connect(self._on_new_clicked)
        self.btn_del.clicked.connect(self._on_del_clicked)
        self.css_input.textChanged.connect(self._update_preview)
        self.html_input.textChanged.connect(self._update_preview)

        self.refresh_data()

    def refresh_data(self) -> None:
        """Rafraîchit la liste des modèles depuis la base de données."""
        self.list_widget.clear()
        models = NoteTypeModel.select()
        for m in models:
            self.list_widget.addItem(m.name)

    def is_dirty(self) -> bool:
        """Vérifie s'il y a des changements non sauvegardés."""
        # Pour le moment, renvoie toujours False (peut être amélioré)
        return False

    def _on_item_selected(self, current, previous) -> None:
        if not current:
            self._current_model = None
            return

        name = current.text()
        self._current_model = NoteTypeModel.get_or_none(NoteTypeModel.name == name)

        if self._current_model:
            self.name_input.setText(self._current_model.name)
            self.schema_input.setPlainText(self._current_model.fields_schema)
            self.css_input.setPlainText(self._current_model.css_style)
            self.html_input.setPlainText(self._current_model.templates)
            self._update_preview()

    def _on_new_clicked(self) -> None:
        self.list_widget.clearSelection()
        self._current_model = None
        self.name_input.clear()
        self.schema_input.setPlainText('["Front", "Back"]')
        self.css_input.setPlainText(".card {\n    font-family: arial;\n    font-size: 20px;\n    text-align: center;\n    color: black;\n    background-color: white;\n}")
        self.html_input.setPlainText('[\n    {\n        "name": "Card 1",\n        "qfmt": "{{Front}}",\n        "afmt": "{{Front}}<hr id=answer>{{Back}}"\n    }\n]')
        self._update_preview()

    def _on_del_clicked(self) -> None:
        if self._current_model:
            self._current_model.delete_instance()
            self._current_model = None
            self.name_input.clear()
            self.schema_input.clear()
            self.css_input.clear()
            self.html_input.clear()
            self.refresh_data()

    def _save_model(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            return

        schema = self.schema_input.toPlainText()
        css = self.css_input.toPlainText()
        html = self.html_input.toPlainText()

        if self._current_model:
            self._current_model.name = name
            self._current_model.fields_schema = schema
            self._current_model.css_style = css
            self._current_model.templates = html
            self._current_model.save()
        else:
            self._current_model = NoteTypeModel.create(name=name, fields_schema=schema, css_style=css, templates=html)
        self.refresh_data()

        # Select the newly saved model
        items = self.list_widget.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.list_widget.setCurrentItem(items[0])

    def _update_preview(self) -> None:
        # Simple text preview to represent the card
        try:
            templates = json.loads(self.html_input.toPlainText())
            if templates and isinstance(templates, list):
                qfmt = templates[0].get("qfmt", "Aucun format de question")
                self.preview_label.setText(f"Aperçu :\n\n{qfmt}")
            else:
                self.preview_label.setText("Format JSON invalide")
        except json.JSONDecodeError:
            self.preview_label.setText("Format JSON invalide")

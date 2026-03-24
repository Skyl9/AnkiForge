import json
from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                               QTextEdit, QLabel, QSplitter, QGroupBox, QPushButton,
                               QComboBox, QListWidgetItem)

from src.database.models import NoteTypeModel
from src.utils.anki_renderer import render_anki_card


class ModelsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.current_templates: List[Dict[str, str]] = []
        self.mock_dict: Dict[str, str] = {}
        self.current_css: str = ""

        layout = QVBoxLayout(self)

        # En-tête
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<h2>🎨 Édition des Modèles (Note Types)</h2>"))
        self.btn_refresh = QPushButton("🔄 Rafraîchir la liste")
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
        self.css_editor = QTextEdit()
        self.css_editor.textChanged.connect(self.update_preview)

        self._add_group(meta_layout, "1. Champs de données (Schéma)", self.fields_view)
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

        cards_toolbar.addWidget(QLabel("<b>Modèle :</b>"))
        cards_toolbar.addWidget(self.card_selector)
        cards_toolbar.addWidget(self.side_selector)
        cards_toolbar.addStretch()
        cards_layout.addLayout(cards_toolbar)

        html_preview_splitter = QSplitter(Qt.Horizontal)

        # Éditeurs HTML
        editors_widget = QWidget()
        editors_layout = QVBoxLayout(editors_widget)
        editors_layout.setContentsMargins(0, 0, 0, 0)

        self.qfmt_editor = QTextEdit()
        self.afmt_editor = QTextEdit()
        self.qfmt_editor.textChanged.connect(self.update_preview)
        self.afmt_editor.textChanged.connect(self.update_preview)

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
        """Utilitaire pour créer une boîte de groupe autour d'un widget."""
        group = QGroupBox(title)
        lyt = QVBoxLayout(group)
        lyt.addWidget(widget)
        parent_layout.addWidget(group)

    def refresh_models_list(self) -> None:
        self.models_list.clear()
        for note_type in NoteTypeModel.select():
            self.models_list.addItem(note_type.name)

    def on_model_selected(self, item: QListWidgetItem) -> None:
        model_name = item.text()
        try:
            note_type = NoteTypeModel.get(NoteTypeModel.name == model_name)

            # Génération du Mock
            fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []
            self.fields_view.setPlainText(", ".join(fields))
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
        self.web_view.setHtml(final_html)

import json
import re
from typing import Optional, Dict

from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QLabel, QPushButton, QWidget, QVBoxLayout, QHBoxLayout,
                               QFileDialog, QMessageBox, QSplitter, QTreeWidget,
                               QTreeWidgetItem, QTableWidget, QTableWidgetItem,
                               QAbstractItemView, QComboBox, QScrollArea, QTextEdit)

from src.database.models import DeckModel, CardModel, NoteModel, NoteTypeModel, NoteVersionModel
from src.services.cards.export_manager import ExportManager
from src.services.cards.store_manager import StoreManager
from src.utils.anki_renderer import render_anki_card


def strip_html(text: Optional[str]) -> str:
    """Retire toutes les balises HTML d'une chaîne pour l'affichage brut."""
    if not text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).replace('&nbsp;', ' ').replace('\n', ' ').strip()


class EditionTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.store = StoreManager()
        self.current_deck_id: Optional[int] = None
        self.current_note: Optional[NoteModel] = None
        self.field_editors: Dict[str, QTextEdit] = {}

        layout = QVBoxLayout(self)

        # --- 1. EN-TÊTE ---
        header_layout = QHBoxLayout()
        titre = QLabel("Navigateur de Cartes & Notes")
        titre.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.btn_load_col = QPushButton("📂 Importer un paquet")
        self.btn_load_col.clicked.connect(self.load_cards)

        self.btn_export = QPushButton("📦 Exporter le paquet vers Anki")
        self.btn_export.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_selected_deck)
        self.btn_export.setEnabled(False)

        header_layout.addWidget(titre)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_load_col)
        header_layout.addWidget(self.btn_export)
        layout.addLayout(header_layout)

        # --- 2. LAYOUT PRINCIPAL ---
        main_splitter = QSplitter(Qt.Horizontal)
        self.deck_tree = QTreeWidget()
        self.deck_tree.setHeaderHidden(True)
        self.deck_tree.itemClicked.connect(self.on_deck_selected)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(QLabel("Mode d'affichage :"))
        self.view_mode_cb = QComboBox()
        self.view_mode_cb.addItems(["Vue : Cartes (Métadonnées)", "Vue : Notes (Texte)"])
        self.view_mode_cb.currentIndexChanged.connect(self.refresh_table)
        toolbar_layout.addWidget(self.view_mode_cb)
        toolbar_layout.addStretch()
        right_layout.addLayout(toolbar_layout)

        right_splitter = QSplitter(Qt.Vertical)

        # Le Tableau
        self.data_table = QTableWidget()
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.itemSelectionChanged.connect(self.on_row_selected)

        bottom_splitter = QSplitter(Qt.Horizontal)

        # A. L'Éditeur de champs
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_save_edits = QPushButton("💾 Sauvegarder les modifications")
        self.btn_save_edits.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 6px;")
        self.btn_save_edits.clicked.connect(self.save_note_edits)
        self.btn_save_edits.setEnabled(False)
        left_layout.addWidget(self.btn_save_edits)

        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setAlignment(Qt.AlignTop)
        self.details_scroll.setWidget(self.details_widget)

        left_layout.addWidget(self.details_scroll)

        # B. L'Aperçu WebEngine
        self.preview_panel = QWidget()
        preview_layout = QVBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_card_selector = QComboBox()
        self.preview_card_selector.currentIndexChanged.connect(self.update_preview)

        self.preview_side_selector = QComboBox()
        self.preview_side_selector.addItems(["Afficher le Recto (Question)", "Afficher le Verso (Réponse)"])
        self.preview_side_selector.currentIndexChanged.connect(self.update_preview)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.preview_card_selector)
        controls_layout.addWidget(self.preview_side_selector)

        self.web_view = QWebEngineView()

        preview_layout.addLayout(controls_layout)
        preview_layout.addWidget(self.web_view)

        bottom_splitter.addWidget(left_panel)
        bottom_splitter.addWidget(self.preview_panel)
        bottom_splitter.setSizes([350, 450])

        right_splitter.addWidget(self.data_table)
        right_splitter.addWidget(bottom_splitter)
        right_splitter.setSizes([300, 300])

        right_layout.addWidget(right_splitter)
        main_splitter.addWidget(self.deck_tree)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([200, 800])

        layout.addWidget(main_splitter)
        self.refresh_deck_tree()

    def load_cards(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir document", "", "Documents Anki (*.colpkg *.txt *.apkg)")
        if path:
            self.btn_load_col.setEnabled(False)
            try:
                self.store.store_collection(path)
                QMessageBox.information(self, "Succès", "Fichier chargé !")
                self.refresh_deck_tree()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur : {str(e)}")
            finally:
                self.btn_load_col.setEnabled(True)

    def export_selected_deck(self) -> None:
        if not self.current_deck_id:
            return

        deck = DeckModel.get_by_id(self.current_deck_id)
        default_name = f"{deck.name.replace('::', '_')}.apkg"

        path, _ = QFileDialog.getSaveFileName(self, "Exporter vers Anki", default_name, "Anki Deck (*.apkg)")
        if path:
            try:
                exporter = ExportManager()
                exporter.export_deck(self.current_deck_id, path)
                QMessageBox.information(self, "Succès 🎉", f"Le paquet '{deck.name}' a été exporté avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'exportation :\n{e}")

    def refresh_deck_tree(self) -> None:
        self.deck_tree.clear()
        try:
            decks = DeckModel.select().order_by(DeckModel.name)
            tree_nodes = {}
            for deck in decks:
                parts = deck.name.split("::")
                display_name = parts[-1]
                if len(parts) == 1:
                    item = QTreeWidgetItem(self.deck_tree, [f"📁 {display_name}"])
                else:
                    parent_name = "::".join(parts[:-1])
                    parent_item = tree_nodes.get(parent_name, self.deck_tree)
                    item = QTreeWidgetItem(parent_item, [f"📂 {display_name}"])

                item.setData(0, Qt.UserRole, deck.id)
                tree_nodes[deck.name] = item
            self.deck_tree.expandAll()
        except Exception:
            pass

    def on_deck_selected(self, item: QTreeWidgetItem, column: int) -> None:
        self.current_deck_id = item.data(0, Qt.UserRole)
        self.btn_export.setEnabled(True)
        self.refresh_table()

    def refresh_table(self) -> None:
        if not self.current_deck_id:
            return

        self.data_table.setRowCount(0)
        self.btn_save_edits.setEnabled(False)
        self.current_note = None

        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 🛡️ Ajout d'un bouclier Try/Except pour attraper les crashs silencieux
        try:
            mode = self.view_mode_cb.currentText()
            selected_deck = DeckModel.get_by_id(self.current_deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

            if mode == "Vue : Cartes (Métadonnées)":
                # La vue Cartes n'a besoin que de 4 colonnes, on les définit proprement
                self.data_table.setColumnCount(4)
                self.data_table.setHorizontalHeaderLabels(["ID Carte", "Modèle", "Paquet", "Template"])

                cards = (
                    CardModel.select(CardModel, NoteModel, DeckModel, NoteTypeModel)
                    .join(NoteModel)
                    .join(NoteTypeModel)
                    .switch(CardModel)
                    .join(DeckModel)
                    .where(CardModel.deck.in_(matching_decks))
                )

                for row_index, card in enumerate(cards):
                    self.data_table.insertRow(row_index)
                    cid = str(card.anki_id) if card.anki_id else f"Local-{card.id}"
                    note_type = card.note.note_type.name if card.note.note_type else "Inconnu"
                    deck_name = card.deck.name if card.deck else "Inconnu"
                    template = f"Carte n°{card.template_index + 1}"

                    self.data_table.setItem(row_index, 0, QTableWidgetItem(cid))
                    self.data_table.setItem(row_index, 1, QTableWidgetItem(note_type))
                    self.data_table.setItem(row_index, 2, QTableWidgetItem(deck_name))
                    self.data_table.setItem(row_index, 3, QTableWidgetItem(template))
                    self.data_table.item(row_index, 0).setData(Qt.UserRole, card.note.id)

            else:
                # La vue Notes a bien nos 5 colonnes avec la Version !
                self.data_table.setColumnCount(5)
                self.data_table.setHorizontalHeaderLabels(
                    ["Question (Aperçu)", "Réponse (Aperçu)", "Modèle", "Tags", "Version"])

                notes = (
                    NoteModel.select(NoteModel, NoteTypeModel)
                    .join(NoteTypeModel)
                    .switch(NoteModel)  # 🆕 Répare le bug de jointure SQL
                    .join(CardModel, on=(CardModel.note_id == NoteModel.id))
                    .join(DeckModel, on=(CardModel.deck_id == DeckModel.id))
                    .where(DeckModel.id.in_(matching_decks))
                    .distinct()
                )

                for row_index, note in enumerate(notes):
                    self.data_table.insertRow(row_index)

                    active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                    content_dict = json.loads(active_version.content) if active_version else {}

                    values = list(content_dict.values())
                    recto = strip_html(values[0]) if len(values) > 0 else ""
                    verso = strip_html(values[1]) if len(values) > 1 else ""

                    nt_name = note.note_type.name if note.note_type else "Inconnu"
                    tags_list = json.loads(note.tags) if note.tags else []

                    self.data_table.setItem(row_index, 0, QTableWidgetItem(recto))
                    self.data_table.setItem(row_index, 1, QTableWidgetItem(verso))
                    self.data_table.setItem(row_index, 2, QTableWidgetItem(nt_name))
                    self.data_table.setItem(row_index, 3, QTableWidgetItem(", ".join(tags_list)))

                    v_num = active_version.version_number if active_version else 1
                    item_version = QTableWidgetItem(f"v{v_num}")
                    item_version.setTextAlignment(Qt.AlignCenter)
                    self.data_table.setItem(row_index, 4, item_version)

                    self.data_table.item(row_index, 0).setData(Qt.UserRole, note.id)

        except Exception as e:
            # S'il y a un plantage, on aura enfin une alerte claire !
            QMessageBox.critical(self, "Erreur d'affichage", f"Impossible de charger le tableau :\n{e}")
            import traceback
            print(traceback.format_exc())

    def on_row_selected(self) -> None:
        selected_items = self.data_table.selectedItems()
        if not selected_items:
            return

        note_id = selected_items[0].data(Qt.UserRole)

        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.field_editors.clear()
        self.preview_card_selector.blockSignals(True)
        self.preview_card_selector.clear()

        try:
            self.current_note = NoteModel.get_by_id(note_id)
            self.btn_save_edits.setEnabled(True)

            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}

            lbl_title = QLabel(f"<h3 style='margin:0;'>Édition (Modèle : {self.current_note.note_type.name})</h3>")
            self.details_layout.addWidget(lbl_title)

            for field_name, field_value in content_dict.items():
                lbl = QLabel(f"<b>{field_name}</b>")
                text_edit = QTextEdit()
                text_edit.setPlainText(field_value)
                text_edit.setMinimumHeight(60)
                text_edit.textChanged.connect(self.update_preview)

                self.field_editors[field_name] = text_edit
                self.details_layout.addWidget(lbl)
                self.details_layout.addWidget(text_edit)

            templates = json.loads(
                self.current_note.note_type.templates) if self.current_note.note_type.templates else []
            for tmpl in templates:
                self.preview_card_selector.addItem(tmpl.get("name", "Carte"))

            self.preview_card_selector.blockSignals(False)
            self.update_preview()

        except Exception as e:
            self.details_layout.addWidget(QLabel(f"Erreur : {e}"))

    def save_note_edits(self) -> None:
        """Met à jour le JSON de la note dans la base de données Peewee"""
        if not self.current_note:
            return

        try:
            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}
            for field_name, editor in self.field_editors.items():
                content_dict[field_name] = editor.toPlainText()

                # ✅ ON CRÉE LA NOUVELLE VERSION (Commit) :
            from src.database.models import db  # Assure-toi que db est bien importé en haut
            with db.atomic():
                new_version = self.current_note.add_version(content_dict, source="manual")

            mode = self.view_mode_cb.currentText()
            if mode == "Vue : Notes (Texte)":
                selected_items = self.data_table.selectedItems()
                if selected_items:
                    row = selected_items[0].row()
                    values = list(content_dict.values())
                    recto = strip_html(values[0]) if len(values) > 0 else ""
                    verso = strip_html(values[1]) if len(values) > 1 else ""
                    self.data_table.setItem(row, 0, QTableWidgetItem(recto))
                    self.data_table.setItem(row, 1, QTableWidgetItem(verso))

                    item_version = QTableWidgetItem(f"v{new_version.version_number}")
                    item_version.setTextAlignment(Qt.AlignCenter)
                    self.data_table.setItem(row, 4, item_version)
            QMessageBox.information(self, "Succès", "La note a été mise à jour en base de données !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder : {e}")

    def update_preview(self) -> None:
        if not self.current_note or self.preview_card_selector.count() == 0:
            return

        templates = json.loads(self.current_note.note_type.templates)
        selected_tmpl_idx = self.preview_card_selector.currentIndex()
        if selected_tmpl_idx < 0:
            return

        tmpl = templates[selected_tmpl_idx]
        is_recto = self.preview_side_selector.currentIndex() == 0

        current_fields = {name: editor.toPlainText() for name, editor in self.field_editors.items()}

        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")
        css = self.current_note.note_type.css_style

        final_html = render_anki_card(
            raw_html=raw_html,
            css=css,
            fields_dict=current_fields,
            is_recto=is_recto,
            front_html=tmpl.get("qfmt", "")
        )

        self.web_view.setHtml(final_html)

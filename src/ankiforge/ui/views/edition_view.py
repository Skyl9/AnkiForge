import difflib
import json
import re
from typing import Optional, Dict

import qtawesome
from PySide6.QtCore import Qt, QUrl, Slot, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QLabel, QPushButton, QWidget, QVBoxLayout, QHBoxLayout,
                               QFileDialog, QMessageBox, QSplitter, QTreeWidget,
                               QTreeWidgetItem, QTableWidget, QTableWidgetItem,
                               QAbstractItemView, QComboBox, QScrollArea, QTextEdit, QListWidget, QListWidgetItem,
                               QMenu, QInputDialog)

from ankiforge.database.models import DeckModel, CardModel, NoteModel, NoteTypeModel, NoteVersionModel, db, \
    IgnoredDuplicateModel
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, DangerButton
from ankiforge.ui.widgets.drop_image_text_edit import DropImageTextEdit
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog
from ankiforge.utils.anki_renderer import render_anki_card
from ankiforge.utils.paths import get_app_data_dir


def strip_html(text: Optional[str]) -> str:
    """Retire toutes les balises HTML d'une chaîne pour l'affichage brut."""
    if not text:
        return ""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text).replace('&nbsp;', ' ').replace('\n', ' ').strip()


class SortableTableItem(QTableWidgetItem):
    """Un élément de tableau qui sait trier les nombres (et les 'vX') intelligemment."""

    def __lt__(self, other) -> bool:
        # On nettoie le texte (ex: on transforme "v10" en "10")
        text_self = self.text().lower().replace('v', '').strip()
        text_other = other.text().lower().replace('v', '').strip()

        try:
            # On essaie de comparer mathématiquement (10 > 2)
            return float(text_self) < float(text_other)
        except ValueError:
            # Si c'est du vrai texte (ex: "Maths" vs "Physique"), on fait un tri alphabétique
            return self.text().lower() < other.text().lower()


class EditionTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.store = StoreManager()
        self.current_deck_id: Optional[int] = None
        self.current_note: Optional[NoteModel] = None
        self.current_tag_filter: Optional[str] = None
        self.field_editors: Dict[str, QTextEdit] = {}

        layout = QVBoxLayout(self)

        # --- 1. EN-TÊTE ---
        header_layout = QHBoxLayout()
        titre = HeaderLabel("Navigateur de Cartes & Notes")

        self.btn_load_col = ActionButton(qtawesome.icon('fa5s.folder-open', color='white'), " Importer un paquet")
        self.btn_load_col.clicked.connect(self.load_cards)

        self.btn_export = PrimaryButton(qtawesome.icon('fa5s.box', color='white'), " Exporter le paquet vers Anki")
        self.btn_export.clicked.connect(self.export_selected_deck)
        self.btn_export.setEnabled(False)

        header_layout.addWidget(titre)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_load_col)
        header_layout.addWidget(self.btn_export)
        layout.addLayout(header_layout)

        # --- 2. LAYOUT PRINCIPAL ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
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
        self.view_mode_cb.addItems(
            ["Vue : Cartes (Métadonnées)", "Vue : Notes (Texte)", "Vue : Quarantaine (À valider)"])
        self.view_mode_cb.currentIndexChanged.connect(self.refresh_table)
        toolbar_layout.addWidget(self.view_mode_cb)
        toolbar_layout.addStretch()

        self.btn_approve = PrimaryButton(qtawesome.icon('fa5s.check', color='white'), " Approuver la sélection")
        self.btn_approve.clicked.connect(self.approve_selected_notes)
        self.btn_approve.setVisible(False)

        self.btn_reject = DangerButton(qtawesome.icon('fa5s.trash', color='white'), " Rejeter la sélection")
        self.btn_reject.clicked.connect(self.reject_selected_notes)
        self.btn_reject.setVisible(False)

        self.btn_scan_dupes = ActionButton(qtawesome.icon('fa5s.search', color='white'), " Traquer les doublons")
        self.btn_scan_dupes.clicked.connect(self.scan_for_duplicates)

        toolbar_layout.addWidget(self.btn_scan_dupes)
        toolbar_layout.addWidget(self.btn_approve)
        toolbar_layout.addWidget(self.btn_reject)

        right_layout.addLayout(toolbar_layout)

        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Le Tableau
        self.data_table = QTableWidget()
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.data_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.itemSelectionChanged.connect(self.on_row_selected)

        self.data_table.setSortingEnabled(True)

        bottom_splitter = QSplitter(Qt.Horizontal)

        # A. L'Éditeur de champs
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        buttons_layout = QHBoxLayout()

        self.btn_save_edits = PrimaryButton(qtawesome.icon('fa5s.save', color='white'),
                                            " Sauvegarder les modifications")
        self.btn_save_edits.clicked.connect(self.save_note_edits)
        self.btn_save_edits.setEnabled(False)

        self.btn_history = ActionButton(qtawesome.icon('fa5s.history', color='white'), " Historique")
        self.btn_history.clicked.connect(self.show_version_history)
        self.btn_history.setEnabled(False)

        buttons_layout.addWidget(self.btn_save_edits)
        buttons_layout.addWidget(self.btn_history)
        left_layout.addLayout(buttons_layout)

        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
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

        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(500)  # Attend 500ms après la dernière frappe
        self.preview_timer.timeout.connect(self.update_preview)

        preview_layout.addLayout(controls_layout)
        preview_layout.addWidget(self.web_view)

        bottom_splitter.addWidget(left_panel)
        bottom_splitter.addWidget(self.preview_panel)
        bottom_splitter.setSizes([350, 450])

        right_splitter.addWidget(self.data_table)
        right_splitter.addWidget(bottom_splitter)
        right_splitter.setSizes([300, 300])

        right_layout.addWidget(right_splitter)

        # --- PANNEAU LATÉRAL GAUCHE (Paquets + Tags) ---

        left_sidebar = QSplitter(Qt.Orientation.Vertical)
        left_sidebar.addWidget(self.deck_tree)

        tag_container = QWidget()
        tag_layout = QVBoxLayout(tag_container)
        tag_layout.setContentsMargins(0, 10, 0, 0)
        tag_layout.addWidget(QLabel("<b>🏷️ Tags</b>"))

        self.tag_list = QListWidget()
        self.tag_list.itemClicked.connect(self.on_tag_selected)

        # Activer le clic droit sur la liste de tags
        self.tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tag_list.customContextMenuRequested.connect(self.show_tag_context_menu)

        tag_layout.addWidget(self.tag_list)
        left_sidebar.addWidget(tag_container)

        main_splitter.addWidget(left_sidebar)  # 👈 On ajoute la sidebar complète au lieu du simple deck_tree

        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([200, 800])

        layout.addWidget(main_splitter)
        self.refresh_deck_tree()

    @Slot()
    def refresh_data(self) -> None:
        """Méthode standardisée appelée par la MainWindow au changement d'onglet."""
        self.refresh_deck_tree()
        self.refresh_tags_list()
        # On rafraîchit la table si un paquet est déjà sélectionné
        if self.current_deck_id:
            self.refresh_table()

    @Slot()
    def load_cards(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir document", "", "Documents Anki (*.colpkg *.txt *.apkg)")
        if path:
            self.btn_load_col.setEnabled(False)
            try:
                self.store.store_collection(path)
                show_toast(self, "Paquet importé !")
                self.refresh_deck_tree()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur : {str(e)}")
            finally:
                self.btn_load_col.setEnabled(True)

    @Slot()
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
                show_toast(self, "Exportation terminée !")
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

                item.setData(0, Qt.ItemDataRole.UserRole, deck.id)
                tree_nodes[deck.name] = item
            self.deck_tree.expandAll()
        except Exception:
            pass

    @Slot(QTreeWidgetItem, int)
    def on_deck_selected(self, item: QTreeWidgetItem, column: int) -> None:
        self.current_deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        self.btn_export.setEnabled(True)
        self.refresh_table()

    def refresh_table(self) -> None:
        if not self.current_deck_id:
            return

        self.data_table.setSortingEnabled(False)
        self.data_table.setRowCount(0)
        self.btn_save_edits.setEnabled(False)
        self.current_note = None

        mode = self.view_mode_cb.currentText()
        is_quarantine = (mode == "Vue : Quarantaine (À valider)")

        self.btn_approve.setVisible(is_quarantine)
        self.btn_reject.setVisible(is_quarantine)

        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        try:
            selected_deck = DeckModel.get_by_id(self.current_deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

            # 👇 LA SÉCURITÉ ABSOLUE : Le filtre s'adapte dynamiquement 👇
            if is_quarantine:
                # En quarantaine, on NE veut QUE les brouillons IA ('pending')
                status_condition = (NoteModel.status == "pending")
            else:
                # Dans les autres vues, on veut TOUT LE RESTE ('new', 'imported', 'review'...)
                status_condition = (NoteModel.status != "pending")

            if self.current_tag_filter:
                status_condition = status_condition & (NoteModel.tags.contains(f'"{self.current_tag_filter}"'))

            if mode == "Vue : Cartes (Métadonnées)":
                self.data_table.setColumnCount(4)
                self.data_table.setHorizontalHeaderLabels(["ID Carte", "Modèle", "Paquet", "Template"])

                cards = (
                    CardModel.select(CardModel, NoteModel, DeckModel, NoteTypeModel)
                    .join(NoteModel).where(status_condition)
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

                    self.data_table.setItem(row_index, 0, SortableTableItem(cid))
                    self.data_table.setItem(row_index, 1, SortableTableItem(note_type))
                    self.data_table.setItem(row_index, 2, SortableTableItem(deck_name))
                    self.data_table.setItem(row_index, 3, SortableTableItem(template))
                    self.data_table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, card.note.id)

            else:
                self.data_table.setColumnCount(5)
                self.data_table.setHorizontalHeaderLabels(
                    ["Question (Aperçu)", "Réponse (Aperçu)", "Modèle", "Tags", "Version"])

                notes = (
                    NoteModel.select(NoteModel, NoteTypeModel)
                    .join(NoteTypeModel)
                    .switch(NoteModel)
                    .join(CardModel, on=(CardModel.note_id == NoteModel.id))
                    .join(DeckModel, on=(CardModel.deck_id == DeckModel.id))
                    .where(DeckModel.id.in_(matching_decks) & status_condition)
                    .distinct()
                )

                for row_index, note in enumerate(notes):
                    self.data_table.insertRow(row_index)

                    active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                    content_dict = json.loads(active_version.content) if active_version else {}

                    values = list(content_dict.values())
                    recto = strip_html(values[0]) if len(values) > 0 else ""
                    verso = strip_html(values[1]) if len(values) > 1 else ""

                    if not recto.strip():
                        item_recto = SortableTableItem("⚠️ CARTE INVALIDE (Recto vide)")
                        item_recto.setForeground(QColor("red"))
                    else:
                        item_recto = SortableTableItem(recto)

                    nt_name = note.note_type.name if note.note_type else "Inconnu"
                    tags_list = json.loads(note.tags) if note.tags else []

                    self.data_table.setItem(row_index, 0, item_recto)
                    self.data_table.setItem(row_index, 1, SortableTableItem(verso))
                    self.data_table.setItem(row_index, 2, SortableTableItem(nt_name))
                    self.data_table.setItem(row_index, 3, SortableTableItem(", ".join(tags_list)))

                    v_num = active_version.version_number if active_version else 1
                    item_version = SortableTableItem(f"v{v_num}")
                    item_version.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.data_table.setItem(row_index, 4, item_version)

                    self.data_table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, note.id)

            self.data_table.setSortingEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'affichage", f"Impossible de charger le tableau :\n{e}")
            import traceback
            print(traceback.format_exc())

    def on_row_selected(self) -> None:
        selected_items = self.data_table.selectedItems()
        if not selected_items:
            return

        if self.view_mode_cb.currentText() == "Vue : Quarantaine (À valider)":
            self.btn_approve.setEnabled(True)
            self.btn_reject.setEnabled(True)

        note_id = selected_items[0].data(Qt.ItemDataRole.UserRole)

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
            self.btn_history.setEnabled(True)

            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}

            lbl_title = QLabel(f"<b>Édition (Modèle : {self.current_note.note_type.name})</b>")
            lbl_title.setStyleSheet("font-size: 16px; margin-bottom: 5px;")
            self.details_layout.addWidget(lbl_title)

            for field_name, field_value in content_dict.items():
                lbl = QLabel(f"<b>{field_name}</b>")
                text_edit = DropImageTextEdit()

                clean_value = field_value.replace('<br>', '\n') if field_value else ""
                text_edit.setPlainText(clean_value)
                text_edit.setMinimumHeight(60)

                text_edit.textChanged.connect(self._on_text_changed)

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

    @Slot()
    def _on_text_changed(self) -> None:
        """Relance le délai de 500ms à chaque frappe pour laisser MathJax respirer."""
        self.preview_timer.start()

    def save_note_edits(self) -> None:
        """Met à jour le JSON de la note dans la base de données Peewee"""
        if not self.current_note:
            return

        try:
            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}
            for field_name, editor in self.field_editors.items():
                content_dict[field_name] = editor.toPlainText().replace('\n', '<br>')

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
                    item_version.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.data_table.setItem(row, 4, item_version)
            show_toast(self, "Note mise à jour !")
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

        current_fields = {
            name: editor.toPlainText().replace('\n', '<br>')
            for name, editor in self.field_editors.items()
        }

        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")
        css = self.current_note.note_type.css_style

        final_html = render_anki_card(
            raw_html=raw_html,
            css=css,
            fields_dict=current_fields,
            is_recto=is_recto,
            front_html=tmpl.get("qfmt", "")
        )

        media_dir = get_app_data_dir() / "media"
        media_dir.mkdir(exist_ok=True)

        base_url = QUrl.fromLocalFile(str(media_dir) + "/")

        # On injecte le HTML en lui donnant le droit de lire dans le dossier media
        self.web_view.setHtml(final_html, base_url)

    def approve_selected_notes(self) -> None:
        selected_rows = set(item.row() for item in self.data_table.selectedItems())
        if not selected_rows: return

        try:
            with db.atomic():
                for row in selected_rows:
                    note_id = self.data_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                    note = NoteModel.get_by_id(note_id)
                    note.status = "new"
                    note.save()

            self.refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'approuver :\n{e}")

    def reject_selected_notes(self) -> None:
        selected_rows = set(item.row() for item in self.data_table.selectedItems())
        if not selected_rows: return

        reply = QMessageBox.question(self, "Rejeter",
                                     f"Voulez-vous vraiment supprimer définitivement ces {len(selected_rows)} cartes ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    for row in selected_rows:
                        note_id = self.data_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                        NoteModel.delete_by_id(note_id)  # CASCADE supprimera les cartes et versions

                self.refresh_table()
                self.web_view.setHtml("")
                self.btn_save_edits.setEnabled(False)
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de rejeter :\n{e}")

    # ==========================================
    # GESTIONNAIRE DE TAGS
    # ==========================================

    def refresh_tags_list(self) -> None:
        """Récupère tous les tags uniques de la base de données et peuple la liste."""
        self.tag_list.clear()

        # Option pour annuler le filtre
        all_item = QListWidgetItem("🏷️ Tous les tags")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.tag_list.addItem(all_item)

        unique_tags = set()

        # On lit toutes les notes qui ont des tags
        notes_with_tags = NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False))
        for note in notes_with_tags:
            try:
                tags = json.loads(note.tags)
                unique_tags.update(tags)
            except:
                pass

        # On les ajoute par ordre alphabétique
        for tag in sorted(unique_tags):
            item = QListWidgetItem(f"# {tag}")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self.tag_list.addItem(item)

    @Slot(QListWidgetItem)
    def on_tag_selected(self, item: QListWidgetItem) -> None:
        """Applique le filtre et rafraîchit le tableau."""
        self.current_tag_filter = item.data(Qt.ItemDataRole.UserRole)
        self.refresh_table()

    @Slot(int)
    def show_tag_context_menu(self, pos) -> None:
        """Affiche le menu contextuel (clic droit) pour renommer/supprimer un tag."""
        item = self.tag_list.itemAt(pos)
        if not item: return

        tag_name = item.data(Qt.ItemDataRole.UserRole)
        if not tag_name: return  # On ne peut pas modifier "Tous les tags"

        menu = QMenu(self)
        rename_action = menu.addAction("✏️ Renommer le tag")
        delete_action = menu.addAction("🗑️ Supprimer le tag (Retirer de toutes les cartes)")

        action = menu.exec(self.tag_list.mapToGlobal(pos))

        if action == rename_action:
            self.rename_tag(tag_name)
        elif action == delete_action:
            self.delete_tag(tag_name)

    def rename_tag(self, old_tag: str) -> None:
        new_tag, ok = QInputDialog.getText(self, "Renommer un Tag", f"Nouveau nom pour #{old_tag} :", text=old_tag)
        if ok and new_tag.strip() and new_tag.strip() != old_tag:
            new_tag = new_tag.strip()
            try:
                with db.atomic():
                    # On trouve toutes les notes qui contiennent l'ancien tag
                    notes_to_update = NoteModel.select().where(NoteModel.tags.contains(f'"{old_tag}"'))
                    for note in notes_to_update:
                        tags = json.loads(note.tags) if note.tags else []
                        if old_tag in tags:
                            # On remplace l'ancien par le nouveau
                            tags = [new_tag if t == old_tag else t for t in tags]
                            note.tags = json.dumps(tags, ensure_ascii=False)
                            note.save()

                show_toast(self, f"Tag #{old_tag} renommé en #{new_tag} !")

                # Mise à jour de l'UI
                if self.current_tag_filter == old_tag:
                    self.current_tag_filter = new_tag
                self.refresh_tags_list()
                self.refresh_table()

            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de renommer le tag : {e}")

    def delete_tag(self, tag_to_delete: str) -> None:
        reply = QMessageBox.question(self, "Confirmation",
                                     f"Voulez-vous retirer le tag #{tag_to_delete} de toutes vos notes ?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    notes_to_update = NoteModel.select().where(NoteModel.tags.contains(f'"{tag_to_delete}"'))
                    for note in notes_to_update:
                        tags = json.loads(note.tags) if note.tags else []
                        if tag_to_delete in tags:
                            tags.remove(tag_to_delete)
                            note.tags = json.dumps(tags, ensure_ascii=False)
                            note.save()

                show_toast(self, f"Tag #{tag_to_delete} supprimé !")
                if self.current_tag_filter == tag_to_delete:
                    self.current_tag_filter = None
                self.refresh_tags_list()
                self.refresh_table()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le tag : {e}")

    @Slot(int, int)
    def jump_to_note(self, note_id: int, deck_id: int) -> None:
        """Sélectionne le paquet, puis trouve et sélectionne la carte dans le tableau."""
        if not deck_id: return

        # 1. Sélectionner le paquet dans l'arbre de gauche
        from PySide6.QtWidgets import QTreeWidgetItemIterator
        iterator = QTreeWidgetItemIterator(self.deck_tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == deck_id:
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.deck_tree.setCurrentItem(item)
                self.on_deck_selected(item, 0)
                break
            iterator += 1

        # 2. Sélectionner la note dans le tableau central
        for row in range(self.data_table.rowCount()):
            row_note_id = self.data_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if row_note_id == note_id:
                self.data_table.selectRow(row)
                self.data_table.scrollToItem(self.data_table.item(row, 0))
                break

    @Slot()
    def scan_for_duplicates(self) -> None:
        if not self.current_deck_id:
            QMessageBox.warning(self, "Attention", "Veuillez d'abord sélectionner un paquet.")
            return

        self.btn_scan_dupes.setEnabled(False)
        self.btn_scan_dupes.setText("⏳ Analyse en cours...")

        try:
            selected_deck = DeckModel.get_by_id(self.current_deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

            # Récupère toutes les notes du paquet
            all_notes = (
                NoteModel.select(NoteModel, NoteTypeModel)
                .join(NoteTypeModel)
                .switch(NoteModel)
                .join(CardModel, on=(CardModel.note_id == NoteModel.id))
                .join(DeckModel, on=(CardModel.deck_id == DeckModel.id))
                .where(DeckModel.id.in_(matching_decks))
                .distinct()
            )

            # 1. Grouper par Modèle
            notes_by_model = {}
            for note in all_notes:
                model_id = note.note_type.id if note.note_type else 0
                if model_id not in notes_by_model:
                    notes_by_model[model_id] = []
                notes_by_model[model_id].append(note)

            conflicts = []

            # 2. Analyser chaque groupe
            for model_id, notes in notes_by_model.items():
                note_texts = []
                for note in notes:
                    active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                    if active_version:
                        content = json.loads(active_version.content)
                        values = list(content.values())
                        if values:
                            # On nettoie le texte pour la comparaison interne
                            clean_text = strip_html(values[0]).lower()
                            # Mais on garde la version brute pour l'affichage visuel
                            raw_text = values[0]
                            note_texts.append((note, clean_text, raw_text))

                ignored_records = IgnoredDuplicateModel.select()
                ignored_pairs = {(record.note_a_id, record.note_b_id) for record in ignored_records}

                # 3. Comparaison croisée O(N^2)
                matched_ids = set()  # Pour ne pas proposer 15 fois la même carte en conflit
                for i, (note_a, clean_a, raw_a) in enumerate(note_texts):
                    if note_a.id in matched_ids: continue

                    for j in range(i + 1, len(note_texts)):
                        note_b, clean_b, raw_b = note_texts[j]
                        if note_b.id in matched_ids: continue

                        id_1, id_2 = min(note_a.id, note_b.id), max(note_a.id, note_b.id)
                        if (id_1, id_2) in ignored_pairs:
                            continue

                        if difflib.SequenceMatcher(None, clean_a, clean_b).ratio() > 0.85:
                            # On met la carte la plus ancienne à gauche (Originale), la plus récente à droite
                            if note_a.id < note_b.id:
                                conflicts.append((note_a, raw_a, note_b, raw_b))
                            else:
                                conflicts.append((note_b, raw_b, note_a, raw_a))

                            matched_ids.add(note_b.id)
                            break  # On a trouvé son jumeau, on passe au note_a suivant

            # 4. Lancer l'interface utilisateur si on a trouvé des conflits
            if not conflicts:
                show_toast(self, "Aucun doublon détecté dans ce paquet !")
            else:
                dialog = DuplicateResolverDialog(conflicts, self)
                dialog.exec()
                # On rafraîchit le tableau car des cartes ont potentiellement été supprimées
                self.refresh_table()

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'analyse : {e}")
        finally:
            self.btn_scan_dupes.setEnabled(True)
            self.btn_scan_dupes.setText(" Traquer les doublons")
            self.btn_scan_dupes.setIcon(qtawesome.icon('fa5s.search'))

    @Slot()
    def show_version_history(self) -> None:
        if not self.current_note:
            return

        dialog = VersionHistoryDialog(self.current_note, self)
        # Si la boîte de dialogue renvoie "accept" (l'utilisateur a restauré une version)
        if dialog.exec():
            # On recharge l'éditeur avec la nouvelle version restaurée
            self.on_row_selected()
            # On rafraîchit le numéro de version dans le tableau !
            self.refresh_table()

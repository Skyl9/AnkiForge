import logging
from typing import Optional

import qtawesome
from PySide6.QtCore import QSettings, Qt, Slot
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QProgressDialog, QSplitter, QVBoxLayout, QWidget

from ankiforge.database.models import DeckModel, LLMConfigModel, NoteModel, db
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.cards.duplicate_manager import DuplicateManager
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.services.workers.batch_edit_worker import BatchEditWorker
from ankiforge.services.workers.import_cards_worker import ImportCardsWorker
from ankiforge.ui.components.components import ActionButton, HeaderLabel, PrimaryButton
from ankiforge.ui.widgets.auto_tag_dialog import AutoTagDialog
from ankiforge.ui.widgets.batch_edit_dialog import BatchEditDialog
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog

# Nouveaux composants extraits
from ankiforge.ui.widgets.filter_sidebar import FilterSidebar
from ankiforge.ui.widgets.note_editor_widget import NoteEditorWidget
from ankiforge.ui.widgets.note_table_widget import NoteTableWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog

logger = logging.getLogger(__name__)


class EditionTab(QWidget):
    """
    Navigateur principal de l'application permettant de visualiser, éditer,
    filtrer, taguer et exporter les notes et cartes Anki.
    Orchestre les widgets FilterSidebar, NoteTableWidget et NoteEditorWidget.
    """

    def __init__(self) -> None:
        super().__init__()

        # État interne et asynchrone
        self.batch_thread: BatchEditWorker | None = None
        self.import_thread: ImportCardsWorker | None = None
        self.progress_dialog: QProgressDialog | None = None
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self.store = StoreManager()

        self.current_deck_id: int | None = None
        self.current_tag_filter: str | None = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        """Construit et organise les layouts et widgets de la vue d'édition."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self._build_header()

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)

        # 1. Barre latérale de filtrage
        self.filter_sidebar = FilterSidebar()
        self.main_splitter.addWidget(self.filter_sidebar)

        # Zone de droite (Tableau + Éditeur)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(10)

        # 2. Tableau des notes
        self.note_table = NoteTableWidget()
        self.right_splitter.addWidget(self.note_table)

        # 3. Éditeur de note
        self.note_editor = NoteEditorWidget()
        self.right_splitter.addWidget(self.note_editor)

        self.right_splitter.setSizes([300, 300])
        self.main_splitter.addWidget(self.right_splitter)

        self.main_splitter.setSizes([200, 800])
        self.main_layout.addWidget(self.main_splitter)

    def _build_header(self) -> None:
        """Construit l'en-tête de la vue."""
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel("Navigateur de Cartes & Notes"))
        header_layout.addStretch()

        self.btn_load_col = ActionButton("fa5s.folder-open", " Importer un paquet")
        self.btn_export = PrimaryButton(qtawesome.icon("fa5s.box", color="white"), " Exporter vers Anki")
        self.btn_export.setEnabled(False)

        header_layout.addWidget(self.btn_load_col)
        header_layout.addWidget(self.btn_export)
        self.main_layout.addLayout(header_layout)

    def _connect_signals(self) -> None:
        """Centralise le branchement des signaux des composants."""
        # En-tête
        self.btn_load_col.clicked.connect(self.load_cards)
        self.btn_export.clicked.connect(self.export_selected_deck)

        # Sidebar
        self.filter_sidebar.deck_selected.connect(self.on_deck_selected)
        self.filter_sidebar.tag_selected.connect(self.on_tag_selected)

        # Table
        self.note_table.note_selected.connect(self.on_note_selected)
        self.note_table.view_mode_changed.connect(self.on_view_mode_changed)
        self.note_table.new_note_requested.connect(self.enter_creation_mode)
        self.note_table.scan_dupes_requested.connect(self.scan_for_duplicates)
        self.note_table.batch_ai_requested.connect(self.open_batch_edit_dialog)
        self.note_table.auto_tag_requested.connect(self.open_auto_tag_dialog)
        self.note_table.approve_requested.connect(self.approve_selected_notes)
        self.note_table.reject_requested.connect(self.reject_selected_notes)

        # Editor
        self.note_editor.note_updated.connect(self.note_table.update_row_after_save)
        self.note_editor.history_requested.connect(self.show_version_history)
        self.note_editor.creation_mode_exited.connect(self.on_creation_mode_exited)

    @Slot()
    def refresh_data(self) -> None:
        """Rafraîchit l'intégralité des données de la vue."""
        self.filter_sidebar.refresh_decks()
        self.refresh_tags()
        if self.current_deck_id:
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    def refresh_tags(self) -> None:
        mode = self.note_table.view_mode_cb.currentText()
        is_quarantine = mode == "Vue : Quarantaine (À valider)"
        self.filter_sidebar.refresh_tags(self.current_deck_id, is_quarantine)

    @Slot(int)
    def on_deck_selected(self, deck_id: int) -> None:
        if self.note_editor.is_creating:
            reply = QMessageBox.question(
                self,
                "Création en cours",
                "Changer de paquet annulera la création en cours. Continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            self.note_editor._exit_creation_mode(refresh=False)

        self.current_deck_id = deck_id
        self.current_tag_filter = None
        self.btn_export.setEnabled(True)
        self.note_editor.set_current_deck(deck_id)

        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
        self.refresh_tags()

    @Slot(object)
    def on_tag_selected(self, tag: Optional[str]) -> None:
        self.current_tag_filter = tag
        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    @Slot(str)
    def on_view_mode_changed(self, mode_text: str) -> None:
        self.refresh_tags()
        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    @Slot(int)
    def on_note_selected(self, note_id: int) -> None:
        if self.note_editor.is_creating:
            # Si on sélectionne une ligne pendant la création, on demande confirmation
            # (Logique simplifiée ici, NoteEditorWidget pourrait aussi gérer son propre état bloquant)
            pass
        self.note_editor.load_note(note_id)

    @Slot()
    def enter_creation_mode(self) -> None:
        if not self.current_deck_id:
            return
        self.note_editor.enter_creation_mode()

    @Slot(bool, object)
    def on_creation_mode_exited(self, refresh: bool, select_note_id: int | None) -> None:
        if refresh:
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
            if select_note_id is not None and self.current_deck_id is not None:
                deck_id_local = self.current_deck_id
                self.jump_to_note(select_note_id, deck_id_local)

    def jump_to_note(self, note_id: int, deck_id: int) -> None:
        """Sélectionne le paquet, puis trouve et sélectionne la carte dans le tableau."""
        # On délègue la partie sélection de deck à la sidebar
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(self.filter_sidebar.deck_tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == deck_id:
                self.filter_sidebar.deck_tree.setCurrentItem(item)
                self.on_deck_selected(deck_id)
                break
            iterator += 1

        # Puis on cherche dans la table
        table = self.note_table.data_table
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == note_id:
                table.selectRow(row)
                table.scrollToItem(item)
                break

    @Slot()
    def load_cards(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir document", "", "Documents Anki (*.colpkg *.txt *.apkg)")
        if path:
            self.btn_load_col.setEnabled(False)
            self.progress_dialog = QProgressDialog("Importation en cours...", "Annuler", 0, 0, self)
            self.progress_dialog.show()

            self.import_thread = ImportCardsWorker(self.store, path)
            self.import_thread.progress.connect(self.progress_dialog.setLabelText)
            self.import_thread.finished_signal.connect(self._on_import_success)
            self.import_thread.error_signal.connect(self._on_import_error)
            self.import_thread.start()

    def _on_import_success(self) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        show_toast(self, "Paquet importé avec succès !")
        self.refresh_data()
        self.btn_load_col.setEnabled(True)

    def _on_import_error(self, error_msg: str) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Erreur d'importation", error_msg)
        self.btn_load_col.setEnabled(True)

    @Slot()
    def export_selected_deck(self) -> None:
        if not self.current_deck_id:
            return
        deck = DeckModel.get_by_id(self.current_deck_id)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Exportation")
        msg_box.setText(f"Exporter le paquet '{deck.name}' ?")
        btn_new = msg_box.addButton("🚀 Nouvelles cartes", QMessageBox.ButtonRole.AcceptRole)
        _ = msg_box.addButton("📦 Tout le paquet", QMessageBox.ButtonRole.RejectRole)
        msg_box.addButton("Annuler", QMessageBox.ButtonRole.DestructiveRole)
        msg_box.exec()

        if msg_box.clickedButton().text() == "Annuler":
            return
        export_only_new = msg_box.clickedButton() == btn_new

        path, _ = QFileDialog.getSaveFileName(self, "Exporter", f"{deck.name}.apkg", "Anki Deck (*.apkg)")
        if path:
            try:
                ExportManager().export_deck(self.current_deck_id, path, export_only_new=export_only_new)
                show_toast(self, "Exportation terminée !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", str(e))

    @Slot(list)
    def approve_selected_notes(self, note_ids: list[int]) -> None:
        try:
            with db.atomic():
                NoteModel.update(status="new").where(NoteModel.id.in_(note_ids)).execute()
            show_toast(self, f"{len(note_ids)} notes approuvées !")
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    @Slot(list)
    def reject_selected_notes(self, note_ids: list[int]) -> None:
        reply = QMessageBox.question(self, "Confirmation", f"Supprimer définitivement {len(note_ids)} notes ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    NoteModel.delete().where(NoteModel.id.in_(note_ids)).execute()
                show_toast(self, "Notes supprimées.")
                self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
                self.note_editor._clear_editor()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", str(e))

    @Slot()
    def scan_for_duplicates(self) -> None:
        if not self.current_deck_id:
            return
        try:
            conflicts = DuplicateManager.find_duplicates(self.current_deck_id)
            if not conflicts:
                show_toast(self, "Aucun doublon trouvé !")
            else:
                DuplicateResolverDialog(conflicts, self).exec()
                self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", str(e))

    @Slot(int)
    def show_version_history(self, note_id: int) -> None:
        note = NoteModel.get_by_id(note_id)
        if VersionHistoryDialog(note, self).exec():
            self.note_editor.load_note(note_id)
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    @Slot(list)
    def open_batch_edit_dialog(self, note_ids: list[int]) -> None:
        dialog = BatchEditDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            llm_config = LLMConfigModel.get_by_id(data["llm_id"])
            provider = AIManager.create_provider_from_config(llm_config)

            self.progress_dialog = QProgressDialog("Modification IA...", "Annuler", 0, 0, self)
            self.batch_thread = BatchEditWorker(provider, note_ids, data["prompt"], data["chunk_size"])
            self.batch_thread.progress.connect(self.progress_dialog.setLabelText)
            self.batch_thread.finished_signal.connect(self._on_batch_edit_success)
            self.batch_thread.error_signal.connect(self._on_batch_edit_error)
            self.progress_dialog.canceled.connect(self.batch_thread.cancel)
            self.batch_thread.start()
            self.progress_dialog.show()

    def _on_batch_edit_success(self, count: int):
        if self.progress_dialog:
            self.progress_dialog.close()
        show_toast(self, f"{count} notes traitées !")
        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    def _on_batch_edit_error(self, msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Erreur IA", msg)

    @Slot(list)
    def open_auto_tag_dialog(self, note_ids: list[int]) -> None:
        if AutoTagDialog(self, note_ids).exec():
            show_toast(self, "Auto-Tagging terminé !")
            self.refresh_tags()
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

import logging


from PySide6.QtCore import QSettings, Qt, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog, QSplitter, QVBoxLayout, QWidget

from ankiforge.database.models import DeckModel, LLMConfigModel, NoteModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.cards.duplicate_manager import DuplicateManager
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.services.workers.batch_edit_worker import BatchEditWorker
from ankiforge.services.workers.import_cards_worker import ImportCardsWorker
from ankiforge.ui.widgets.auto_tag_dialog import AutoTagDialog
from ankiforge.ui.widgets.batch_edit_dialog import BatchEditDialog
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog
from ankiforge.ui.widgets.linter_dialog import LinterDialog

# Nouveaux composants extraits
from ankiforge.ui.widgets.filter_sidebar import FilterSidebar
from ankiforge.ui.widgets.note_editor_widget import NoteEditorWidget
from ankiforge.ui.widgets.note_table_widget import NoteTableWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog
from ankiforge.ui.widgets.edition_header_widget import EditionHeaderWidget

logger = logging.getLogger(__name__)


class EditionTab(QWidget):
    """
    Main application navigator allowing to visualize, edit,
    filter, tag and export Anki notes and cards.
    Orchestrates the FilterSidebar, NoteTableWidget and NoteEditorWidget widgets.
    """

    def __init__(self) -> None:
        super().__init__()

        # Internal and asynchronous state
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
        """Builds and organizes layouts and widgets for the edition view."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self.header_widget = EditionHeaderWidget()
        self.main_layout.addWidget(self.header_widget)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)

        # 1. Filter sidebar
        self.filter_sidebar = FilterSidebar()
        self.main_splitter.addWidget(self.filter_sidebar)

        # Right zone (Table + Editor)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(10)

        # 2. Notes table
        self.note_table = NoteTableWidget()
        self.right_splitter.addWidget(self.note_table)

        # 3. Note editor
        self.note_editor = NoteEditorWidget()
        self.right_splitter.addWidget(self.note_editor)

        self.right_splitter.setSizes([300, 300])
        self.main_splitter.addWidget(self.right_splitter)

        self.main_splitter.setSizes([200, 800])
        self.main_layout.addWidget(self.main_splitter)

    def _connect_signals(self) -> None:
        """Centralizes component signal connections."""
        # Header
        self.header_widget.import_requested.connect(self.load_cards)
        self.header_widget.export_requested.connect(self.export_selected_deck)

        # Sidebar
        self.filter_sidebar.deck_selected.connect(self.on_deck_selected)
        self.filter_sidebar.tag_selected.connect(self.on_tag_selected)

        # Table
        self.note_table.note_selected.connect(self.on_note_selected)
        self.note_table.view_mode_changed.connect(self.on_view_mode_changed)
        self.note_table.new_note_requested.connect(self.enter_creation_mode)
        self.note_table.scan_dupes_requested.connect(self.scan_for_duplicates)
        self.note_table.batch_ai_requested.connect(self.open_batch_edit_dialog)
        self.note_table.audit_ai_requested.connect(self.open_linter_dialog)
        self.note_table.auto_tag_requested.connect(self.open_auto_tag_dialog)
        self.note_table.approve_requested.connect(self.approve_selected_notes)
        self.note_table.reject_requested.connect(self.reject_selected_notes)

        # Editor
        self.note_editor.note_updated.connect(self.note_table.update_row_after_save)
        self.note_editor.history_requested.connect(self.show_version_history)
        self.note_editor.creation_mode_exited.connect(self.on_creation_mode_exited)

    @Slot()
    def refresh_data(self) -> None:
        """Refreshes all view data."""
        self.filter_sidebar.refresh_decks()
        self.refresh_tags()
        if self.current_deck_id:
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    def refresh_tags(self) -> None:
        mode = self.note_table.get_current_view_mode()
        # Comparison with translated mode name
        is_quarantine = mode == self.tr("View: Quarantine (To validate)")
        self.filter_sidebar.refresh_tags(self.current_deck_id, is_quarantine)

    @Slot(int)
    def on_deck_selected(self, deck_id: int) -> None:
        if self.note_editor.is_creating:
            reply = QMessageBox.question(
                self,
                self.tr("Creation in progress"),
                self.tr("Changing deck will cancel the current creation. Continue?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            self.note_editor._exit_creation_mode(refresh=False)

        self.current_deck_id = deck_id
        self.current_tag_filter = None
        self.header_widget.set_export_enabled(True)
        self.note_editor.set_current_deck(deck_id)

        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
        self.refresh_tags()

    @Slot(object)
    def on_tag_selected(self, tag: str | None) -> None:
        self.current_tag_filter = tag
        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    @Slot(str)
    def on_view_mode_changed(self, mode_text: str) -> None:
        self.refresh_tags()
        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    @Slot(int)
    def on_note_selected(self, note_id: int) -> None:
        if self.note_editor.is_creating:
            # If a row is selected during creation, we should ask for confirmation
            # (Simplified logic here, NoteEditorWidget could also handle its own blocking state)
            pass
        self.note_editor.load_note(note_id)

    @Slot(list)
    def open_linter_dialog(self, note_ids: list[int]) -> None:
        if not note_ids:
            return
        dialog = LinterDialog(note_ids, self)
        dialog.exec()
        self.refresh_data()

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
        """Selects the deck, then finds and selects the card in the table."""
        # Delegate deck selection to sidebar
        if self.filter_sidebar.select_deck(deck_id):
            self.on_deck_selected(deck_id)

        # Then search in table
        self.note_table.select_and_scroll_to_note(note_id)

    @Slot()
    def load_cards(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr("Open document"), "", self.tr("Anki Documents (*.colpkg *.txt *.apkg)"))
        if path:
            self.header_widget.set_import_enabled(False)
            self.progress_dialog = QProgressDialog(self.tr("Importing..."), self.tr("Cancel"), 0, 0, self)
            self.progress_dialog.show()

            self.import_thread = ImportCardsWorker(self.store, path)
            self.import_thread.progress.connect(self.progress_dialog.setLabelText)
            self.import_thread.finished_signal.connect(self._on_import_success)
            self.import_thread.error_signal.connect(self._on_import_error)
            self.import_thread.start()

    def _on_import_success(self) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        show_toast(self, self.tr("Deck imported successfully!"))
        self.refresh_data()
        self.header_widget.set_import_enabled(True)

    def _on_import_error(self, error_msg: str) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, self.tr("Import Error"), error_msg)
        self.header_widget.set_import_enabled(True)

    def is_dirty(self) -> bool:
        """Indique si une création de note manuelle est en cours."""
        return self.note_editor.is_creating

    def reset_unsaved_state(self) -> None:
        """Réinitialise l'état de l'onglet après abandon de la création en cours."""
        if self.note_editor.is_creating:
            # On sort du mode création silencieusement, sans rafraîchir le tableau
            self.note_editor._exit_creation_mode(refresh=False)
            logger.info("Mode création annulé (changement d'onglet forcé).")

    @Slot()
    def export_selected_deck(self) -> None:
        if not self.current_deck_id:
            return
        deck = DeckModel.get_by_id(self.current_deck_id)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Export"))
        msg_box.setText(self.tr("Export deck '{0}'?").format(deck.name))
        btn_new = msg_box.addButton(self.tr("🚀 New cards"), QMessageBox.ButtonRole.AcceptRole)
        _ = msg_box.addButton(self.tr("📦 Whole deck"), QMessageBox.ButtonRole.RejectRole)
        msg_box.addButton(self.tr("Cancel"), QMessageBox.ButtonRole.DestructiveRole)
        msg_box.exec()

        if msg_box.clickedButton().text() == self.tr("Cancel"):
            return
        export_only_new = msg_box.clickedButton() == btn_new

        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export"), self.tr("{0}.apkg").format(deck.name), self.tr("Anki Deck (*.apkg)"))
        if path:
            try:
                ExportManager().export_deck(self.current_deck_id, path, export_only_new=export_only_new)
                show_toast(self, self.tr("Export finished!"))
            except Exception as e:
                logger.exception("Error during deck export")
                QMessageBox.critical(self, self.tr("Error"), str(e))

    @Slot(list)
    def approve_selected_notes(self, note_ids: list[int]) -> None:
        try:
            self.store.approve_notes(note_ids)
            show_toast(self, self.tr("{0} notes approved!").format(len(note_ids)))
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
        except Exception as e:
            logger.exception("Error while approving notes")
            QMessageBox.critical(self, self.tr("Error"), str(e))

    @Slot(list)
    def reject_selected_notes(self, note_ids: list[int]) -> None:
        reply = QMessageBox.question(self, self.tr("Confirmation"), self.tr("Permanently delete {0} notes?").format(len(note_ids)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_notes(note_ids)
                show_toast(self, self.tr("Notes deleted."))
                self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
                self.note_editor._clear_editor()
            except Exception as e:
                logger.exception("Error while deleting notes")
                QMessageBox.critical(self, self.tr("Error"), str(e))

    @Slot()
    def scan_for_duplicates(self) -> None:
        if not self.current_deck_id:
            return
        try:
            conflicts = DuplicateManager.find_duplicates(self.current_deck_id)
            if not conflicts:
                show_toast(self, self.tr("No duplicates found!"))
            else:
                DuplicateResolverDialog(conflicts, self).exec()
                self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)
        except Exception as e:
            logger.exception("Error while scanning for duplicates")
            QMessageBox.critical(self, self.tr("Error"), str(e))

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

            self.progress_dialog = QProgressDialog(self.tr("AI Modification..."), self.tr("Cancel"), 0, 0, self)
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
        show_toast(self, self.tr("{0} notes processed!").format(count))
        self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

    def _on_batch_edit_error(self, msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, self.tr("AI Error"), msg)

    @Slot(list)
    def open_auto_tag_dialog(self, note_ids: list[int]) -> None:
        if AutoTagDialog(self, note_ids).exec():
            show_toast(self, self.tr("Auto-Tagging finished!"))
            self.refresh_tags()
            self.note_table.refresh_table(self.current_deck_id, self.current_tag_filter)

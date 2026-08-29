import json
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ankiforge.database.models import IgnoredDuplicateModel, NoteVersionModel, db
from ankiforge.services.workers.duplicate_worker import DuplicateWorker
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.duplicate_widgets import DuplicateMatrixTable, DuplicateMergeInspector

logger = logging.getLogger(__name__)


class AIDuplicatesMergeTab(QWidget):
    """Onglet de gestion des fusions et faux doublons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected_deck_id: int | None = None
        self.conflicts: list = []
        self.worker: DuplicateWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # 1. Matrice des doublons
        self.matrix_table = DuplicateMatrixTable()
        layout.addWidget(self.matrix_table, stretch=1)

        # 2. Inspecteur de fusion
        self.merge_inspector = DuplicateMergeInspector()
        self.merge_inspector.hide()
        layout.addWidget(self.merge_inspector, stretch=1)

        # Connexions
        self.matrix_table.btn_deck.clicked.connect(self.open_deck_select_dialog)
        self.matrix_table.btn_reanalyze.clicked.connect(self.run_duplicate_scan)
        self.matrix_table.table.itemSelectionChanged.connect(self.on_table_selection_changed)

        self.merge_inspector.merge_requested.connect(self.on_merge_requested)
        self.merge_inspector.ignore_requested.connect(self.on_ignore_requested)

    def open_deck_select_dialog(self) -> None:
        self._deck_dialog = DeckSelectWindow(parent=self)
        self._deck_dialog.deck_selected.connect(self._on_deck_selected)
        self._deck_dialog.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        self.selected_deck_id = deck_id
        self.matrix_table.btn_deck.setText(deck_name)
        self.run_duplicate_scan()
        if hasattr(self, "_deck_dialog") and self._deck_dialog:
            self._deck_dialog.close()

    def run_duplicate_scan(self) -> None:
        if self.selected_deck_id is None:
            return

        self.matrix_table.btn_reanalyze.setEnabled(False)
        self.matrix_table.btn_reanalyze.setText("Recherche...")
        self.matrix_table.table.setRowCount(0)

        self.worker = DuplicateWorker(deck_id=self.selected_deck_id, parent=self)
        self.worker.finished_processing.connect(self.on_scan_finished)
        self.worker.error_occurred.connect(self.on_scan_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def on_scan_finished(self, conflicts: list) -> None:
        self.matrix_table.btn_reanalyze.setEnabled(True)
        self.matrix_table.btn_reanalyze.setText("Relancer l'analyse")
        self.conflicts = conflicts

        for child in self.matrix_table.findChildren(QLabel):
            if "paires à examiner" in child.text() or "0" in child.text():
                child.setText(f"{len(conflicts)} paires à examiner")

        self.matrix_table.table.setRowCount(0)
        for idx, (note_a, content_a, note_b, content_b, sim) in enumerate(conflicts):
            row_data = {
                "idx": idx,
                "note_a": note_a,
                "content_a": content_a,
                "note_b": note_b,
                "content_b": content_b,
                "sim": sim,
            }
            self.matrix_table.add_row(note_a, content_a, note_b, content_b, sim, row_data)

    def on_scan_error(self, err: str) -> None:
        self.matrix_table.btn_reanalyze.setEnabled(True)
        self.matrix_table.btn_reanalyze.setText("Relancer l'analyse")
        logger.error("Erreur lors du scan des doublons : %s", err)

    def on_table_selection_changed(self) -> None:
        selected = self.matrix_table.table.selectedItems()
        if not selected:
            self.merge_inspector.hide()
            return

        row = selected[0].row()
        item = self.matrix_table.table.item(row, 2)
        if not item:
            self.merge_inspector.hide()
            return

        row_data = item.data(Qt.ItemDataRole.UserRole)
        if not row_data:
            self.merge_inspector.hide()
            return

        self.merge_inspector.load_conflict(row_data)
        self.merge_inspector.show()

    def on_merge_requested(self, note_keep, note_del, merged_content) -> None:
        try:
            with db.atomic():
                active_ver = NoteVersionModel.get_or_none(note=note_keep, is_active=True)
                if active_ver:
                    active_ver.is_active = False
                    active_ver.save()
                    NoteVersionModel.create(
                        note=note_keep,
                        version_number=active_ver.version_number + 1,
                        content=json.dumps(merged_content),
                        is_active=True,
                        change_reason="Fusion avec doublon",
                        author_type="human",
                    )
                note_del.delete_instance(recursive=True)

            self.remove_current_conflict()
        except Exception as e:
            logger.error("Erreur lors de la fusion : %s", e, exc_info=True)

    def on_ignore_requested(self, note_a, note_b) -> None:
        try:
            id_1, id_2 = min(note_a.id, note_b.id), max(note_a.id, note_b.id)
            IgnoredDuplicateModel.get_or_create(note_a_id=id_1, note_b_id=id_2)
            self.remove_current_conflict()
        except Exception as e:
            logger.error("Erreur lors de l'ignorance du doublon : %s", e, exc_info=True)

    def remove_current_conflict(self):
        selected = self.matrix_table.table.selectedItems()
        if selected:
            row = selected[0].row()
            self.matrix_table.table.removeRow(row)
            self.merge_inspector.current_conflict = None
            self.merge_inspector.lbl_title_a.setText("CARTE #1")
            self.merge_inspector.lbl_title_b.setText("CARTE #2")
            self.merge_inspector.lbl_content_a.setText("...")
            self.merge_inspector.lbl_content_b.setText("...")
            self.merge_inspector.lbl_merged.setText("...")

            for child in self.matrix_table.findChildren(QLabel):
                if "paires à examiner" in child.text() or "0" in child.text():
                    child.setText(f"{self.matrix_table.table.rowCount()} paires à examiner")

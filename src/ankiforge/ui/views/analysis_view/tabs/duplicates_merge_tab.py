import json
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget
from shiboken6 import isValid

from ankiforge.database.models import IgnoredDuplicateModel, NoteVersionModel, db
from ankiforge.services.workers.duplicate_worker import DuplicateWorker
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.duplicate_widgets import DuplicateMatrixTable, DuplicateMergeInspector
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)

# Délai maximal (ms) d'attente du thread d'analyse lors du masquage ou de la destruction de l'onglet.
_WORKER_JOIN_TIMEOUT_MS = 5000


def _live_worker(worker_holder: list[DuplicateWorker | None]) -> DuplicateWorker | None:
    """Écarte un pointeur fantôme et renvoie le worker encore vivant.

    Après ``deleteLater()``, le conteneur peut viser un objet C++ déjà détruit :
    appeler ``isRunning()`` dessus lève alors ``RuntimeError: libshiboken:
    Internal C++ object already deleted``.
    """
    worker = worker_holder[0]
    if worker is None:
        return None
    if not isValid(worker):
        logger.debug("Worker d'analyse des doublons déjà détruit : pointeur réinitialisé.")
        worker_holder[0] = None
        return None
    return worker


def _join_worker(worker_holder: list[DuplicateWorker | None]) -> None:
    """Attend (au plus ``_WORKER_JOIN_TIMEOUT_MS``) la fin du thread d'analyse.

    Ni le masquage ni la destruction de l'onglet ne doivent détruire un
    ``QThread`` encore actif (« QThread: Destroyed while thread is still running »).
    """
    worker = _live_worker(worker_holder)
    if worker is None or not worker.isRunning():
        return
    if not worker.wait(_WORKER_JOIN_TIMEOUT_MS):
        logger.warning(
            "Le scan des doublons du paquet ID=%d n'a pas terminé dans les %d ms : il se poursuit en arrière-plan.",
            worker.deck_id,
            _WORKER_JOIN_TIMEOUT_MS,
        )


class AIDuplicatesMergeTab(QWidget):
    """Onglet de gestion des fusions et faux doublons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected_deck_id: int = -1
        self.conflicts: list = []
        # Conteneur mutable partagé avec le raccourci de `destroyed` : un slot lié à
        # `self` n'est pas appelé pendant `~QObject`, un lambda qui ne capture que ce
        # conteneur l'est, et il peut encore joindre le thread enfant avant sa destruction.
        worker_holder: list[DuplicateWorker | None] = [None]
        self._worker_holder = worker_holder
        self.destroyed.connect(self._on_destroyed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # Splitter vertical permettant d'ajuster l'espace entre la matrice et l'inspecteur
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)

        # 1. Matrice des doublons
        self.matrix_table = DuplicateMatrixTable()
        self.splitter.addWidget(self.matrix_table)

        # 2. Inspecteur de fusion
        self.merge_inspector = DuplicateMergeInspector()
        self.merge_inspector.hide()
        self.splitter.addWidget(self.merge_inspector)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)

        layout.addWidget(self.splitter)

        # Connexions
        self.matrix_table.btn_deck.clicked.connect(self.open_deck_select_dialog)
        self.matrix_table.btn_reanalyze.clicked.connect(self.run_duplicate_scan)
        self.matrix_table.table.itemSelectionChanged.connect(self.on_table_selection_changed)

        self.merge_inspector.merge_requested.connect(self.on_merge_requested)
        self.merge_inspector.ignore_requested.connect(self.on_ignore_requested)

    @property
    def worker(self) -> DuplicateWorker | None:
        """Thread du scan en cours, ou ``None`` hors analyse."""
        return self._worker_holder[0]

    @worker.setter
    def worker(self, worker: DuplicateWorker | None) -> None:
        self._worker_holder[0] = worker

    def _on_destroyed(self, *_args: object) -> None:
        """Joint le thread encore actif au moment de la destruction du widget."""
        _join_worker(self._worker_holder)

    def open_deck_select_dialog(self) -> None:
        self._deck_dialog = DeckSelectWindow(parent=self, selected_deck_id=self.selected_deck_id)
        self._deck_dialog.deck_selected.connect(self._on_deck_selected)
        self._deck_dialog.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        self.selected_deck_id = deck_id
        self.matrix_table.btn_deck.setText(deck_name)
        self.run_duplicate_scan()
        if hasattr(self, "_deck_dialog") and self._deck_dialog:
            self._deck_dialog.close()

    def refresh_data(self) -> None:
        """Relance l'analyse des doublons pour le paquet sélectionné."""
        self.run_duplicate_scan()

    def run_duplicate_scan(self) -> None:
        if self._scan_already_running():
            return

        if self.selected_deck_id is None:
            self.selected_deck_id = -1

        self.matrix_table.btn_reanalyze.setEnabled(False)
        self.matrix_table.btn_reanalyze.setText(self.tr("Recherche..."))
        self.matrix_table.table.setRowCount(0)

        worker = DuplicateWorker(deck_id=self.selected_deck_id, parent=self)
        worker.finished_processing.connect(self.on_scan_finished)
        worker.error_occurred.connect(self.on_scan_error)
        worker.finished.connect(self._release_worker_reference)
        worker.finished.connect(worker.deleteLater)
        self.worker = worker
        worker.start()

    def _scan_already_running(self) -> bool:
        """Vrai si un scan est déjà en cours (le pointeur fantôme d'un scan fini est écarté)."""
        worker = _live_worker(self._worker_holder)
        return worker is not None and worker.isRunning()

    def _release_worker_reference(self) -> None:
        """Remet ``self.worker`` à ``None`` à la fin d'un scan.

        Un signal émis par un scan déjà remplacé ne doit pas invalider le
        pointeur vers le worker en cours, d'où la garde sur l'émetteur.
        """
        sender = self.sender()
        if sender is not None and sender is not self.worker:
            return
        self.worker = None

    def on_scan_finished(self, conflicts: list) -> None:
        self._release_worker_reference()
        self.matrix_table.btn_reanalyze.setEnabled(True)
        self.matrix_table.btn_reanalyze.setText(self.tr("Relancer l'analyse"))
        self.conflicts = conflicts
        self.merge_inspector.reset_inspector()
        self.merge_inspector.hide()

        self.matrix_table.table.setRowCount(0)
        if not conflicts:
            self._update_badge(0)
            self.matrix_table.empty_state.setVisible(True)
            show_toast(self, self.tr("Aucun doublon détecté dans ce paquet."))
            return

        self.matrix_table.empty_state.setVisible(False)
        self._update_badge(len(conflicts))
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

    def _update_badge(self, count: int) -> None:
        label = "paire à examiner" if count <= 1 else "paires à examiner"
        self.matrix_table.badge_count.setText(tr("%1 %2", count, label))

    def on_scan_error(self, err: str) -> None:
        self._release_worker_reference()
        self.matrix_table.btn_reanalyze.setEnabled(True)
        self.matrix_table.btn_reanalyze.setText(self.tr("Relancer l'analyse"))
        logger.error("Erreur lors du scan des doublons : %s", err)

    def on_table_selection_changed(self) -> None:
        selected = self.matrix_table.table.selectedItems()
        if not selected:
            self.merge_inspector.reset_inspector()
            self.merge_inspector.hide()
            return

        row = selected[0].row()
        item = self.matrix_table.table.item(row, 2)
        if not item:
            self.merge_inspector.reset_inspector()
            self.merge_inspector.hide()
            return

        row_data = item.data(Qt.ItemDataRole.UserRole)
        if not row_data:
            self.merge_inspector.reset_inspector()
            self.merge_inspector.hide()
            return

        self.merge_inspector.load_conflict(row_data)
        if self.merge_inspector.isHidden():
            self.merge_inspector.show()
            sizes = self.splitter.sizes()
            total = sum(sizes)
            if total > 0 and (len(sizes) < 2 or sizes[1] == 0):
                self.splitter.setSizes([total // 2, total // 2])
        else:
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

    def remove_current_conflict(self) -> None:
        selected = self.matrix_table.table.selectedItems()
        if selected:
            row = selected[0].row()
            self.matrix_table.table.removeRow(row)
            self.merge_inspector.reset_inspector()
            self.merge_inspector.hide()

            remaining = self.matrix_table.table.rowCount()
            self._update_badge(remaining)
            self.matrix_table.empty_state.setVisible(remaining == 0)

    def hideEvent(self, event: object) -> None:
        """Attend la fin du scan puis décharge les ressources WebEngine lorsque l'onglet est masqué."""
        _join_worker(self._worker_holder)
        if hasattr(self, "merge_inspector"):
            self.merge_inspector.cleanup()
        super().hideEvent(event)

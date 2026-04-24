import json
import logging
import re
from typing import Optional, cast

import qtawesome
from PySide6.QtCore import QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.components.components import ActionButton, DangerButton, EmptyStateWidget, PrimaryButton, RoundedPanel

logger = logging.getLogger(__name__)


def strip_html(text: Optional[str]) -> str:
    """Retire toutes les balises HTML d'une chaîne pour l'affichage brut dans les tableaux."""
    if not text:
        return ""
    clean = re.compile("<.*?>")
    return re.sub(clean, "", text).replace("&nbsp;", " ").replace("\n", " ").strip()


class SortableTableItem(QTableWidgetItem):
    """Élément de tableau Qt capable de trier les valeurs numériques et textuelles intelligemment."""

    def __lt__(self, other) -> bool:
        text_self = self.text().lower().replace("v", "").strip()
        text_other = other.text().lower().replace("v", "").strip()

        try:
            return float(text_self) < float(text_other)
        except ValueError:
            return self.text().lower() < other.text().lower()


class NoteTableWidget(RoundedPanel):
    """
    Panneau central affichant le tableau des notes/cartes avec sa toolbar d'actions.
    """

    note_selected = Signal(int)  # ID de la note sélectionnée
    selection_changed = Signal(list)  # Liste des IDs de notes sélectionnées
    view_mode_changed = Signal(str)
    new_note_requested = Signal()
    scan_dupes_requested = Signal()
    batch_ai_requested = Signal(list)  # Liste des IDs
    auto_tag_requested = Signal(list)  # Liste des IDs
    approve_requested = Signal(list)  # Liste des IDs
    reject_requested = Signal(list)  # Liste des IDs

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # --- Toolbar ---
        toolbar_layout = QHBoxLayout()
        lbl_mode = QLabel("MODE D'AFFICHAGE :")
        lbl_mode.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px;")
        toolbar_layout.addWidget(lbl_mode)

        self.view_mode_cb = QComboBox()
        self.view_mode_cb.addItems(["Vue : Cartes (Métadonnées)", "Vue : Notes (Texte)", "Vue : Quarantaine (À valider)"])
        toolbar_layout.addWidget(self.view_mode_cb)
        toolbar_layout.addStretch()

        self.btn_approve = PrimaryButton(qtawesome.icon("fa5s.check", color="white"), " Approuver")
        self.btn_approve.setVisible(False)
        self.btn_reject = DangerButton(qtawesome.icon("fa5s.trash", color="white"), " Rejeter")
        self.btn_reject.setVisible(False)

        self.btn_new_note = PrimaryButton(qtawesome.icon("fa5s.plus", color="white"), " Nouvelle Note")
        self.btn_new_note.setEnabled(False)

        self.btn_scan_dupes = ActionButton("fa5s.search", " Traquer les doublons")

        self.btn_batch_ai = ActionButton("fa5s.magic", " Modification IA")
        self.btn_batch_ai.setEnabled(False)

        self.btn_auto_tag = ActionButton("fa5s.tags", " Auto-Tag IA")
        self.btn_auto_tag.setEnabled(False)

        toolbar_layout.addWidget(self.btn_new_note)
        toolbar_layout.addWidget(self.btn_batch_ai)
        toolbar_layout.addWidget(self.btn_auto_tag)
        toolbar_layout.addWidget(self.btn_scan_dupes)
        toolbar_layout.addWidget(self.btn_approve)
        toolbar_layout.addWidget(self.btn_reject)

        layout.addLayout(toolbar_layout)

        # --- Table ---
        self.container_layout = QVBoxLayout()
        self.container_layout.setContentsMargins(0, 0, 0, 0)

        self.data_table = QTableWidget()
        self.data_table.setFrameShape(QFrame.Shape.NoFrame)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.data_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.horizontalHeader().setSectionsMovable(True)
        self.data_table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_table.setSortingEnabled(True)

        self.empty_overlay = EmptyStateWidget(
            icon_name="fa5s.clone",
            title=self.tr("Aucune carte à afficher"),
            description=self.tr("Sélectionnez un paquet dans l'explorateur à gauche ou créez votre première carte pour la voir apparaître ici."),
        )

        self.container_layout.addWidget(self.data_table)
        self.container_layout.addWidget(self.empty_overlay)
        layout.addLayout(self.container_layout)

        # État initial
        self.data_table.hide()

    def _connect_signals(self):
        self.view_mode_cb.currentIndexChanged.connect(self._on_view_mode_changed)
        self.btn_new_note.clicked.connect(self.new_note_requested.emit)
        self.btn_scan_dupes.clicked.connect(self.scan_dupes_requested.emit)
        self.btn_batch_ai.clicked.connect(self._on_batch_ai_clicked)
        self.btn_auto_tag.clicked.connect(self._on_auto_tag_clicked)
        self.btn_approve.clicked.connect(self._on_approve_clicked)
        self.btn_reject.clicked.connect(self._on_reject_clicked)

        self.data_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.data_table.horizontalHeader().customContextMenuRequested.connect(self._show_header_menu)
        self.data_table.horizontalHeader().sectionResized.connect(self._save_table_state)
        self.data_table.horizontalHeader().sectionMoved.connect(self._save_table_state)

    def _on_view_mode_changed(self):
        self.view_mode_changed.emit(self.view_mode_cb.currentText())

    def _on_selection_changed(self):
        selected_ids = self.get_selected_note_ids()
        self.btn_batch_ai.setEnabled(bool(selected_ids))
        self.btn_auto_tag.setEnabled(bool(selected_ids))

        is_quarantine = self.view_mode_cb.currentText() == "Vue : Quarantaine (À valider)"
        if is_quarantine:
            self.btn_approve.setEnabled(bool(selected_ids))
            self.btn_reject.setEnabled(bool(selected_ids))

        self.selection_changed.emit(selected_ids)
        if selected_ids:
            self.note_selected.emit(selected_ids[0])

    def get_selected_note_ids(self) -> list[int]:
        selected_items = self.data_table.selectedItems()
        # On ne prend que le premier item de chaque ligne (colonne 0)
        note_ids = []
        rows = set()
        for item in selected_items:
            row = item.row()
            if row not in rows:
                rows.add(row)
                # On récupère l'ID stocké dans l'item de la colonne 0
                item_col0 = self.data_table.item(row, 0)
                if item_col0:
                    note_id = item_col0.data(Qt.ItemDataRole.UserRole)
                    if note_id is not None:
                        note_ids.append(note_id)
        return note_ids

    def _on_batch_ai_clicked(self):
        self.batch_ai_requested.emit(self.get_selected_note_ids())

    def _on_auto_tag_clicked(self):
        self.auto_tag_requested.emit(self.get_selected_note_ids())

    def _on_approve_clicked(self):
        self.approve_requested.emit(self.get_selected_note_ids())

    def _on_reject_clicked(self):
        self.reject_requested.emit(self.get_selected_note_ids())

    def refresh_table(self, deck_id: int | None, tag_filter: str | None = None) -> None:
        if not deck_id:
            self.data_table.hide()
            self.empty_overlay.show()
            return

        self.data_table.setSortingEnabled(False)
        self.data_table.setRowCount(0)

        mode = self.view_mode_cb.currentText()
        is_quarantine = mode == "Vue : Quarantaine (À valider)"

        self.btn_approve.setVisible(is_quarantine)
        self.btn_reject.setVisible(is_quarantine)
        self.btn_new_note.setEnabled(not is_quarantine)

        try:
            selected_deck = DeckModel.get_by_id(deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

            status_condition = (NoteModel.status == "pending") if is_quarantine else (NoteModel.status != "pending")
            if tag_filter:
                status_condition = status_condition & (NoteModel.tags.contains(f'"{tag_filter}"'))

            if mode == "Vue : Cartes (Métadonnées)":
                self.data_table.setColumnCount(4)
                self.data_table.setHorizontalHeaderLabels(["ID Carte", "Modèle", "Paquet", "Template"])

                cards = (
                    CardModel.select(CardModel, NoteModel, DeckModel, NoteTypeModel)
                    .join(NoteModel)
                    .where(status_condition)
                    .join(NoteTypeModel)
                    .switch(CardModel)
                    .join(DeckModel)
                    .where(CardModel.deck.in_(matching_decks))
                )

                for row_index, card in enumerate(cards):
                    self.data_table.insertRow(row_index)
                    cid = str(card.anki_id) if card.anki_id else f"Local-{card.id}"
                    note_type = card.note.note_type.name if card.note and card.note.note_type else "Inconnu"
                    deck_name = card.deck.name if card.deck else "Inconnu"
                    template = f"Carte n°{card.template_index + 1}"

                    self.data_table.setItem(row_index, 0, SortableTableItem(cid))
                    self.data_table.setItem(row_index, 1, SortableTableItem(note_type))
                    self.data_table.setItem(row_index, 2, SortableTableItem(deck_name))
                    self.data_table.setItem(row_index, 3, SortableTableItem(template))

                    item = self.data_table.item(row_index, 0)
                    if item and card.note:
                        item.setData(Qt.ItemDataRole.UserRole, card.note.id)

            else:
                self.data_table.setColumnCount(5)
                self.data_table.setHorizontalHeaderLabels(["Question (Aperçu)", "Réponse (Aperçu)", "Modèle", "Tags", "Version"])

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
                    tags_list = cast(list[str], json.loads(note.tags)) if note.tags else []

                    item_recto.setData(Qt.ItemDataRole.UserRole, note.id)
                    self.data_table.setItem(row_index, 0, item_recto)
                    self.data_table.setItem(row_index, 1, SortableTableItem(verso))
                    self.data_table.setItem(row_index, 2, SortableTableItem(nt_name))
                    self.data_table.setItem(row_index, 3, SortableTableItem(", ".join(tags_list)))

                    v_num = active_version.version_number if active_version else 1
                    item_version = SortableTableItem(f"v{v_num}")
                    item_version.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.data_table.setItem(row_index, 4, item_version)

            self.data_table.setSortingEnabled(True)
            self._restore_table_state()
        except Exception as e:
            logger.exception("Erreur lors du rafraîchissement du tableau de données :")
            QMessageBox.critical(self, "Erreur d'affichage", f"Impossible de charger le tableau :\n{e}")

        if self.data_table.rowCount() == 0:
            self.data_table.hide()
            self.empty_overlay.show()
        else:
            self.empty_overlay.hide()
            self.data_table.show()

    def _show_header_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        visible_count = sum(not self.data_table.isColumnHidden(i) for i in range(self.data_table.columnCount()))
        for i in range(self.data_table.columnCount()):
            header_item = self.data_table.horizontalHeaderItem(i)
            if header_item is None:
                continue
            action = QAction(header_item.text(), self)
            action.setCheckable(True)
            is_visible = not self.data_table.isColumnHidden(i)
            action.setChecked(is_visible)
            if is_visible and visible_count <= 1:
                action.setEnabled(False)
            action.toggled.connect(lambda checked, col=i: self._toggle_column_visibility(col, checked))
            menu.addAction(action)
        menu.exec(self.data_table.horizontalHeader().mapToGlobal(pos))

    def _toggle_column_visibility(self, col: int, visible: bool) -> None:
        self.data_table.setColumnHidden(col, not visible)
        self._save_table_state()

    def _get_table_state_key(self) -> str:
        mode = self.view_mode_cb.currentText()
        if mode == "Vue : Cartes (Métadonnées)":
            return "EditionView/TableState_Cards"
        else:
            return "EditionView/TableState_Notes"

    def _save_table_state(self, *args) -> None:
        if self.data_table.columnCount() == 0:
            return
        state = self.data_table.horizontalHeader().saveState()
        self.settings.setValue(self._get_table_state_key(), state)

    def _restore_table_state(self) -> None:
        state = self.settings.value(self._get_table_state_key())
        if state:
            self.data_table.horizontalHeader().restoreState(state)

    def update_row_after_save(self, note_id: int, content_dict: dict, version_num: int):
        # On cherche la ligne correspondant à note_id
        for row in range(self.data_table.rowCount()):
            item = self.data_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == note_id:
                values = list(content_dict.values())
                recto = strip_html(values[0]) if len(values) > 0 else ""
                verso = strip_html(values[1]) if len(values) > 1 else ""

                # Attention au mode de vue pour les index de colonnes
                if self.view_mode_cb.currentText() == "Vue : Notes (Texte)":
                    self.data_table.setItem(row, 0, SortableTableItem(recto))
                    self.data_table.setItem(row, 1, SortableTableItem(verso))
                    item_version = SortableTableItem(f"v{version_num}")
                    item_version.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.data_table.setItem(row, 4, item_version)
                    # On remet l'ID car setItem l'écrase
                    item_first = self.data_table.item(row, 0)
                    if item_first:
                        item_first.setData(Qt.ItemDataRole.UserRole, note_id)
                break

"""
Batch Staging Panel — Volet de Revue & Staging des cartes générées.

Affiché quand l'utilisateur clique sur "Examiner" ou sélectionne une tâche en statut REVIEW.
Splitter gauche/droite : table des cartes | aperçu WebEngine live (CardPreviewWidget).

Signaux émis :
  - cards_accepted(task_idx: int, accepted_cards: list[dict])
  - task_rejected(task_idx: int)

Qt equivalent: QWidget (QSplitter horizontal)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.logger import log_and_notify_error

logger = logging.getLogger(__name__)


class BatchStagingPanel(QWidget):
    """
    Volet de revue interactif pour les tâches en statut REVIEW.

    L'utilisateur peut :
      • Voir toutes les cartes générées (table multi-sélection)
      • Prévisualiser chaque carte dans le WebEngine live
      • Accepter tout, accepter la sélection, ou rejeter la tranche

    Qt equivalent: QWidget (QSplitter horizontal)
    """

    # Signaux vers BatchView
    cards_accepted = Signal(int, list)  # (task_idx, accepted_cards)
    task_rejected = Signal(int)  # (task_idx,)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchStagingPanel")

        self._current_task_idx: int = -1
        self._current_task_data: dict[str, Any] = {}
        self._prepared_notes: list[dict[str, Any]] = []
        self._save_callback: Callable[[list[dict[str, Any]], int, int, int], None] | None = None

        self._setup_ui()
        self.setVisible(False)  # masqué jusqu'à la sélection d'une tâche REVIEW

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("stagingHeader")
        header.setStyleSheet(f"QFrame#stagingHeader {{ background: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; }}")
        header.setFixedHeight(44)

        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 6, 12, 6)
        header_row.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.COLOR_PURPLE).pixmap(16, 16))
        ico.setStyleSheet("border: none; background: transparent;")

        self.lbl_title = QLabel("Revue & Staging — sélectionnez une tâche terminée")
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none; background: transparent;")

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")

        header_row.addWidget(ico)
        header_row.addWidget(self.lbl_title, 1)
        header_row.addWidget(self.lbl_count)

        # Bouton fermer
        btn_close = IconButton("ph.x", tooltip="Fermer le panneau de revue", size=20)
        btn_close.clicked.connect(lambda: self.setVisible(False))
        header_row.addWidget(btn_close)

        main_layout.addWidget(header)

        # ── Splitter principal ────────────────────────────────────────────
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # Volet gauche : table des cartes
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.cards_table = QTableWidget(0, 3)
        self.cards_table.setHorizontalHeaderLabels(["STATUT", "CONTENU (Recto)", "CHAMPS"])
        self.cards_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cards_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.cards_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.cards_table.verticalHeader().setDefaultSectionSize(38)
        self.cards_table.verticalHeader().setVisible(False)

        hdr = self.cards_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.cards_table.setColumnWidth(0, 80)
        self.cards_table.setColumnWidth(2, 70)

        self.cards_table.setStyleSheet(
            f"""
            QTableWidget {{
                background: {DesignTokens.BG_INPUT};
                border: none;
                font-size: 11px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTableWidget::item:selected {{
                background: {DesignTokens.ACCENT_PRIMARY}22;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                font-weight: bold;
                padding: 4px 8px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            """
        )
        self.cards_table.currentCellChanged.connect(lambda row, *_: self._on_card_row_changed(row))

        left_layout.addWidget(self.cards_table, 1)

        # Barre d'actions
        action_bar = QFrame()
        action_bar.setStyleSheet(f"QFrame {{ background: {DesignTokens.BG_PANEL}; border-top: 1px solid {DesignTokens.BORDER_COLOR}; }}")
        action_row = QHBoxLayout(action_bar)
        action_row.setContentsMargins(8, 6, 8, 6)
        action_row.setSpacing(6)

        self.btn_accept_all = PrimaryButton("Tout valider & Enregistrer")
        self.btn_accept_all.setIcon(load_on_accent_icon("ph.check"))
        self.btn_accept_all.clicked.connect(self._on_accept_all)

        self.btn_accept_selection = SecondaryButton("Valider la sélection")
        self.btn_accept_selection.setIcon(load_phosphor_icon("ph.check-square", color=DesignTokens.COLOR_GREEN))
        self.btn_accept_selection.clicked.connect(self._on_accept_selection)

        self.btn_reject_task = SecondaryButton("Rejeter la tranche")
        self.btn_reject_task.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_reject_task.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; border-color: {DesignTokens.COLOR_RED};")
        self.btn_reject_task.clicked.connect(self._on_reject_task)

        action_row.addWidget(self.btn_accept_all)
        action_row.addWidget(self.btn_accept_selection)
        action_row.addStretch()
        action_row.addWidget(self.btn_reject_task)

        left_layout.addWidget(action_bar)
        self._splitter.addWidget(left_widget)

        # Volet droit : aperçu WebEngine
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        preview_header = QLabel("APERÇU CARTE")
        preview_header.setStyleSheet(
            f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; padding: 8px 12px; background: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};"
        )
        right_layout.addWidget(preview_header)

        # Lazy import pour éviter le coût de SafeWebEngineView si le panneau n'est jamais ouvert
        from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget

        self.card_preview = CardPreviewWidget(parent=right_widget, show_header=False)
        self.card_preview.set_empty_state("Sélectionnez une carte pour la prévisualiser.")
        right_layout.addWidget(self.card_preview, 1)

        self._splitter.addWidget(right_widget)
        self._splitter.setSizes([380, 420])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)

        main_layout.addWidget(self._splitter, 1)

    # ── API publique ──────────────────────────────────────────────────────

    def set_save_callback(self, cb: Callable[[list[dict[str, Any]], int, int, int], None]) -> None:
        """Enregistre la fonction de sauvegarde (déléguée à BatchView._save_extracted_notes_to_db)."""
        self._save_callback = cb

    def load_task(
        self,
        task_idx: int,
        task_data: dict[str, Any],
        prepared_notes: list[dict[str, Any]],
    ) -> None:
        """
        Charge une tâche terminée pour révision.

        Args:
            task_idx: Indice de la tâche dans queue_tasks_data.
            task_data: Entrée brute de queue_tasks_data[task_idx].
            prepared_notes: Cartes générées (list of field dicts).
        """
        self._current_task_idx = task_idx
        self._current_task_data = task_data
        self._prepared_notes = [dict(note) for note in prepared_notes]

        # Ajouter un statut de staging par carte si absent
        for note in self._prepared_notes:
            note.setdefault("_staging_status", "pending")

        doc_title: str = str(task_data.get("doc_title") or task_data.get("doc", {}).get("title", "Document"))
        self.lbl_title.setText(f"Revue — {doc_title[:60]}")
        self.lbl_count.setText(f"{len(self._prepared_notes)} carte(s)")

        self._rebuild_table()
        self.setVisible(True)
        self.card_preview.set_empty_state("Cliquez sur une carte pour la prévisualiser.")

    def _rebuild_table(self) -> None:
        self.cards_table.setRowCount(0)
        self.cards_table.setRowCount(len(self._prepared_notes))

        for row_idx, note in enumerate(self._prepared_notes):
            # Col 0 : statut de staging
            staging_status = note.get("_staging_status", "pending")
            status_text, status_color = _staging_label(staging_status)
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(Qt.GlobalColor.white)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setData(Qt.ItemDataRole.UserRole, staging_status)
            self.cards_table.setItem(row_idx, 0, status_item)

            # Col 1 : premier champ non-privé (Recto)
            front_text = _get_front_text(note)
            content_item = QTableWidgetItem(front_text[:120])
            content_item.setToolTip(front_text)
            self.cards_table.setItem(row_idx, 1, content_item)

            # Col 2 : nombre de champs
            field_count = sum(1 for k in note if not k.startswith("_"))
            fields_item = QTableWidgetItem(f"{field_count} ch.")
            fields_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fields_item.setForeground(Qt.GlobalColor.gray)
            self.cards_table.setItem(row_idx, 2, fields_item)

            # Colorier la ligne selon le statut
            for col in range(3):
                item = self.cards_table.item(row_idx, col)
                if item:
                    item.setBackground(Qt.GlobalColor.transparent)

    # ── Slots privés ──────────────────────────────────────────────────────

    @Slot(int)
    def _on_card_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._prepared_notes):
            self.card_preview.set_empty_state()
            return

        note = self._prepared_notes[row]
        task_data = self._current_task_data
        note_type = task_data.get("note_type")

        # Préparer les champs pour CardPreviewWidget (exclure les clés _staging_*)
        fields_dict = {k: str(v) for k, v in note.items() if not k.startswith("_")}

        if note_type is not None:
            self.card_preview.update_preview(note_type=note_type, fields_dict=fields_dict)
        else:
            # Fallback sans note_type : afficher le champ Front brut
            front = _get_front_text(note)
            self.card_preview.set_empty_state(front[:500] if front else "Aperçu indisponible")

    @Slot()
    def _on_accept_all(self) -> None:
        for note in self._prepared_notes:
            note["_staging_status"] = "accepted"
        self._save_and_emit(self._prepared_notes)

    @Slot()
    def _on_accept_selection(self) -> None:
        selected_rows = {idx.row() for idx in self.cards_table.selectedIndexes()}
        if not selected_rows:
            return
        accepted: list[dict[str, Any]] = []
        for row_idx in sorted(selected_rows):
            if 0 <= row_idx < len(self._prepared_notes):
                note = self._prepared_notes[row_idx]
                note["_staging_status"] = "accepted"
                accepted.append(note)
        self._rebuild_table()
        self._save_and_emit(accepted)

    @Slot()
    def _on_reject_task(self) -> None:
        for note in self._prepared_notes:
            note["_staging_status"] = "rejected"
        self._rebuild_table()
        self.task_rejected.emit(self._current_task_idx)
        self.setVisible(False)

    def _save_and_emit(self, notes_to_save: list[dict[str, Any]]) -> None:
        task = self._current_task_data
        deck_id = task["deck"].id if hasattr(task.get("deck"), "id") else 1
        model_id = task["note_type"].id if hasattr(task.get("note_type"), "id") else 1
        doc = task.get("doc")
        doc_id = doc.id if hasattr(doc, "id") else 0

        # Filtrer les champs internes avant sauvegarde
        clean_notes = [{k: v for k, v in n.items() if not k.startswith("_")} for n in notes_to_save]

        if self._save_callback is not None:
            try:
                self._save_callback(clean_notes, deck_id, model_id, doc_id)
            except Exception as exc:
                log_and_notify_error(str(exc), context="Staging Panel", parent=self)
                return
        else:
            logger.warning("BatchStagingPanel: aucun callback de sauvegarde configuré.")

        self._rebuild_table()
        self.cards_accepted.emit(self._current_task_idx, clean_notes)
        self.setVisible(False)


# ── Helpers ───────────────────────────────────────────────────────────────


def _staging_label(status: str) -> tuple[str, str]:
    """Retourne (texte affiché, couleur hex) selon le statut de staging."""
    mapping: dict[str, tuple[str, str]] = {
        "pending": ("En attente", DesignTokens.COLOR_YELLOW),
        "accepted": ("Validée ✓", DesignTokens.COLOR_GREEN),
        "rejected": ("Rejetée ✗", DesignTokens.COLOR_RED),
    }
    return mapping.get(status, (status, DesignTokens.TEXT_MUTED))


def _get_front_text(note: dict[str, Any]) -> str:
    """Extrait le texte du premier champ non-privé comme représentation 'Recto'."""
    for key, val in note.items():
        if not key.startswith("_") and str(val).strip():
            return str(val)
    return "(Carte vide)"

"""
Batch Queue Table — Tableau de bord de la file d'attente de l'Atelier de Production.

Encapsule le StyledTableWidget (9 colonnes), la barre de filtres par état
(Tous / En attente / À réviser / Terminés / Erreurs) et le rendu des badges,
cellules de progression et actions par ligne (Examiner, Relancer, Supprimer).

Les actions globales (Démarrer, Pause, Reprendre, Vider) restent dans le header
de l'IdePanel de BatchView pour préserver la surface de rétrocompatibilité.

Qt equivalent: QWidget (QVBoxLayout avec toolbar de filtres + table)
"""

from __future__ import annotations

from typing import Any, cast

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import Badge, EmptyStateWidget, IconButton, StyledTableWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.batch_view.constants import apply_pill_style
from ankiforge.ui.views.batch_view.widgets.progress_cell_widget import ProgressTableCellWidget
from ankiforge.utils.icon_loader import load_phosphor_icon

_STATUS_COLORS: dict[str, str] = {
    "En attente": DesignTokens.COLOR_YELLOW,
    "En cours": DesignTokens.COLOR_BLUE,
    "Succès": DesignTokens.COLOR_GREEN,
    "À réviser": DesignTokens.COLOR_PURPLE,
    "Acceptée": DesignTokens.COLOR_GREEN,
    "Partielle": DesignTokens.COLOR_YELLOW,
    "Rejetée": DesignTokens.COLOR_RED,
    "Erreur": DesignTokens.COLOR_RED,
    "Annulé": DesignTokens.TEXT_MUTED,
    "Interrompu": DesignTokens.TEXT_MUTED,
    "Échec": DesignTokens.COLOR_RED,
}

_STATUS_PROGRESS_TEXT: dict[str, str] = {
    "Succès": "Terminé",
    "En cours": "En cours...",
    "Erreur": "Erreur",
    "Annulé": "Annulé",
    "À réviser": "à valider",
    "Acceptée": "Validé",
    "Rejetée": "Rejeté",
    "Partielle": "Partiel",
}

_FILTERS = (
    ("Tous", ()),
    ("En attente", ("En attente", "En cours")),
    ("À réviser", ("À réviser",)),
    ("Terminés", ("Succès", "Acceptée", "Partielle", "Rejetée")),
    ("Erreurs", ("Erreur", "Annulé", "Interrompu", "Échec")),
)


class BatchQueueTable(QWidget):
    """
    Tableau de bord de la file d'attente : rendu, filtres par état et actions unitaires.

    Signaux émis (re-steering vers BatchView) :
      - review_requested(row_idx)  → ouvrir la zone de staging (clic simple sur « À réviser »,
                                    double-clic sur une tranche traitée avec notes pour relire)
      - retry_requested(row_idx)   → relancer une tâche en échec
      - remove_requested(row_idx)  → retirer une tâche de la file

    Qt equivalent: QWidget (QVBoxLayout)
    """

    review_requested = Signal(int)
    retry_requested = Signal(int)
    remove_requested = Signal(int)
    filter_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchQueueTable")

        self._tasks: list[dict[str, Any]] = []
        self._filter = "Tous"
        self.cell_widgets_map: dict[int, ProgressTableCellWidget] = {}
        self.status_badges_map: dict[int, Badge] = {}
        self.cards_items_map: dict[int, QTableWidgetItem] = {}
        self._clickable_review_rows: set[int] = set()
        self._reopen_rows: set[int] = set()

        self._build_ui()

    @property
    def tasks(self) -> list[dict[str, Any]]:
        """Référence directe sur les données affichées (propriété pour BatchView)."""
        return self._tasks

    def set_tasks(self, tasks: list[dict[str, Any]]) -> None:
        """Remplace la liste des tâches affichées puis rend la table."""
        self._tasks = tasks
        self._render()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Barre de filtres d'états ─────────────────────────────────
        filter_bar = QWidget()
        filter_bar.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        filter_row = QHBoxLayout(filter_bar)
        filter_row.setContentsMargins(8, 4, 8, 4)
        filter_row.setSpacing(4)

        self.filter_buttons: dict[str, QLabel] = {}
        for label, _ in _FILTERS:
            chip = QLabel(label)
            chip.setStyleSheet(
                f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 9px; background: transparent;"
            )
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setFixedHeight(18)
            chip.mousePressEvent = self._make_filter_handler(label)
            self.filter_buttons[label] = chip
            filter_row.addWidget(chip)

        self.lbl_filter_info = QLabel("")
        self.lbl_filter_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        filter_row.addStretch(1)
        filter_row.addWidget(self.lbl_filter_info)
        layout.addWidget(filter_bar)

        # ── Table d'attente ──────────────────────────────────────────
        self.table = StyledTableWidget(["", "STATUT", "TRANCHE / SOURCE", "PAQUET", "MODÈLE", "PIPELINE", "PROGRÈS", "CARTES", "ACTIONS"])
        self.table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(46)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 32)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 150)
        self.table.setColumnWidth(7, 80)
        self.table.setColumnWidth(8, 88)

        self.table.setStyleSheet(
            self.table.styleSheet()
            + """
            QHeaderView::section {
                padding: 6px 8px;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px 6px;
            }
        """
        )

        layout.addWidget(self.table, 1)

        self.table.itemClicked.connect(self._on_item_single_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.viewport().installEventFilter(self)

        self.queue_empty = EmptyStateWidget(
            icon_name="ph.tray",
            title="File d'attente vide",
            description="Sélectionnez des documents et configurez la forge à gauche pour ajouter des tâches par lots.",
        )
        layout.addWidget(self.queue_empty, 1)

    # ── File cliquable (T3) ─────────────────────────────────────────────

    def _on_item_single_clicked(self, item: QTableWidgetItem) -> None:
        """Simple-clic sur une rangée « À réviser » : ouvre la revue."""
        if item.row() in self._clickable_review_rows and item.row() < len(self._tasks):
            self.review_requested.emit(item.row())

    def _on_item_double_clicked(self, item: QTableWidgetItem) -> None:
        """Double-clic sur une rangée traitée avec cartes : relecture."""
        if item.row() in self._reopen_rows and item.row() < len(self._tasks):
            self.review_requested.emit(item.row())

    def eventFilter(self, obj: Any, event: Any) -> bool:
        """Affordance visuelle : curseur « main » sur les rangées ouvrables."""
        if obj is self.table.viewport() and event.type() == QEvent.Type.MouseMove:
            pos = cast(QMouseEvent, event).position().toPoint()
            item = self.table.itemAt(pos)
            row = item.row() if item is not None else -1
            cursor = Qt.CursorShape.PointingHandCursor if row in self._clickable_review_rows or row in self._reopen_rows else Qt.CursorShape.ArrowCursor
            if obj.cursor().shape() != cursor:
                obj.setCursor(cursor)
        return super().eventFilter(obj, event)

    # ── Rendu ──────────────────────────────────────────────────────────

    def _render(self) -> None:
        self.table.blockSignals(True)
        self.cell_widgets_map.clear()
        self.status_badges_map.clear()
        self.cards_items_map.clear()

        if not self._tasks:
            self._clickable_review_rows.clear()
            self._reopen_rows.clear()
            self.table.setRowCount(0)
            self.table.hide()
            self.queue_empty.show()
            self.table.blockSignals(False)
            self.lbl_filter_info.setText("")
            return

        self.queue_empty.hide()
        self.table.show()
        self.table.clearSpans()
        self.table.setRowCount(len(self._tasks))

        for i, task in enumerate(self._tasks):
            doc = task.get("doc")
            status: str = str(task.get("status", "En attente"))
            progress_pct: int = int(task.get("progress_pct", 0))
            cards_count: int = int(task.get("cards_count", 0))
            has_notes = bool(task.get("_staging_notes"))
            if status == "À réviser" and has_notes:
                self._clickable_review_rows.add(i)
            elif status in ("Succès", "Acceptée", "Partielle", "Rejetée") and has_notes:
                self._reopen_rows.add(i)

            # Col 0: Checkbox
            cb_item = QTableWidgetItem()
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(i, 0, cb_item)

            # Col 1: Badge Statut
            status_badge = Badge(status, variant="status")
            apply_pill_style(status_badge, _STATUS_COLORS.get(status, DesignTokens.COLOR_YELLOW))
            self.status_badges_map[i] = status_badge
            self.table.setCellWidget(i, 1, status_badge)

            # Col 2: Source
            doc_title = getattr(doc, "title", str(doc)) if doc is not None else str(task.get("doc_title", ""))
            chunk_label = task.get("chunk_label")
            source_label = f"{doc_title} › {chunk_label}" if chunk_label else doc_title
            doc_item = QTableWidgetItem(source_label)
            doc_item.setIcon(load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))
            doc_item.setToolTip(
                f"Type: {getattr(doc, 'file_type', 'doc') if doc is not None else 'doc'} | "
                f"Mots: {len(str(task.get('doc_content') or (getattr(doc, 'content', '') if doc is not None else '') or '').split())}"
            )
            if status == "À réviser" and has_notes:
                doc_item.setToolTip(doc_item.toolTip() + "\nCliquer pour examiner et valider les cartes.")
            elif i in self._reopen_rows:
                doc_item.setToolTip(doc_item.toolTip() + "\nDouble-cliquer pour relire les cartes.")
            self.table.setItem(i, 2, doc_item)

            # Cols 3-5: cibles
            self.table.setItem(i, 3, QTableWidgetItem(str(task.get("deck_name", "Général"))))
            self.table.setItem(i, 4, QTableWidgetItem(str(task.get("model_name", "Basique"))))
            self.table.setItem(i, 5, QTableWidgetItem(str(task.get("pipeline_name", "Standard"))))

            # Col 6: Progression
            p_color = DesignTokens.ACCENT_PRIMARY
            p_text = "En attente..."
            if status == "En cours":
                p_color = DesignTokens.COLOR_BLUE
                p_text = f"{progress_pct}%"
            elif status in _STATUS_PROGRESS_TEXT:
                p_color = _STATUS_COLORS.get(status, DesignTokens.ACCENT_PRIMARY)
                p_text = _STATUS_PROGRESS_TEXT[status]
                if status == "À réviser":
                    p_text = f"{cards_count} carte(s) à valider"
            prog_widget = ProgressTableCellWidget(progress_pct=progress_pct, status_text=p_text, color=p_color)
            self.cell_widgets_map[i] = prog_widget
            self.table.setCellWidget(i, 6, prog_widget)

            # Col 7: Cartes
            cards_text = f"{cards_count} cartes" if cards_count > 0 else "-"
            if status == "À réviser":
                cards_text = f"{cards_count} ⏳"
            cards_item = QTableWidgetItem(cards_text)
            cards_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_items_map[i] = cards_item
            self.table.setItem(i, 7, cards_item)

            # Col 8: Actions
            self.table.setCellWidget(i, 8, self._build_actions(i, status))

        self.table.blockSignals(False)
        self._apply_filter()

    def _build_actions(self, row_idx: int, status: str) -> QWidget:
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(2, 0, 2, 0)
        action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_layout.setSpacing(2)

        if status == "À réviser":
            btn_review = IconButton("ph.magnifying-glass", tooltip="Examiner & valider les cartes", size=18)
            btn_review.clicked.connect(lambda _=False, row_idx=row_idx: self.review_requested.emit(row_idx))
            btn_review.setStyleSheet(f"border: 1px solid {DesignTokens.COLOR_PURPLE}; border-radius: 4px;")
            action_layout.addWidget(btn_review)

        if status in ("Erreur", "Échec", "Interrompu"):
            btn_retry = IconButton("ph.arrow-clockwise", tooltip="Relancer la tâche", size=18)
            btn_retry.clicked.connect(lambda _=False, row_idx=row_idx: self.retry_requested.emit(row_idx))
            btn_retry.setStyleSheet(f"border: 1px solid {DesignTokens.COLOR_YELLOW}; border-radius: 4px;")
            action_layout.addWidget(btn_retry)

        btn_del = IconButton("ph.x", tooltip="Retirer de la queue", size=18)
        btn_del.clicked.connect(lambda _=False, row_idx=row_idx: self.remove_requested.emit(row_idx))
        action_layout.addWidget(btn_del)

        return action_widget

    # ── Mises à jour ciblées (évitent un re-rendu complet à chaque progrès) ──

    def sync_started(self, row_idx: int) -> None:
        self._set_badge(row_idx, "En cours", DesignTokens.COLOR_BLUE)
        self._set_progress(row_idx, 0, "Démarrage...", DesignTokens.COLOR_BLUE)

    def sync_progress(self, row_idx: int, progress_pct: int, step_detail: str) -> None:
        self._set_progress(row_idx, progress_pct, step_detail, DesignTokens.COLOR_BLUE)

    def sync_completed(self, row_idx: int, status: str, cards_count: int) -> None:
        color = _STATUS_COLORS.get(status, DesignTokens.COLOR_GREEN)
        self._set_badge(row_idx, status, color)
        if status == "À réviser":
            self._set_progress(row_idx, 100, f"{cards_count} cartes à valider", DesignTokens.COLOR_PURPLE)
            self._set_cards(row_idx, f"{cards_count} ⏳")
        else:
            self._set_progress(row_idx, 100, _STATUS_PROGRESS_TEXT.get(status, "Terminé"), color)
            self._set_cards(row_idx, f"{cards_count} cartes" if cards_count > 0 else "-")

    def sync_failed(self, row_idx: int) -> None:
        self._set_badge(row_idx, "Erreur", DesignTokens.COLOR_RED)
        self._set_progress(row_idx, 100, "Échec", DesignTokens.COLOR_RED)

    def _set_badge(self, row_idx: int, text: str, color: str) -> None:
        if row_idx in self.status_badges_map:
            badge = self.status_badges_map[row_idx]
            badge.setText(text)
            apply_pill_style(badge, color)

    def _set_progress(self, row_idx: int, pct: int, text: str, color: str) -> None:
        if row_idx in self.cell_widgets_map:
            self.cell_widgets_map[row_idx].update_progress(pct, text, color=color)

    def _set_cards(self, row_idx: int, text: str) -> None:
        if row_idx in self.cards_items_map:
            self.cards_items_map[row_idx].setText(text)

    # ── Filtres ─────────────────────────────────────────────────────────

    def _make_filter_handler(self, label: str) -> Any:
        def _handler(_event: Any) -> None:
            self.set_filter(label)

        return _handler

    def set_filter(self, label: str) -> None:
        """Applique un filtre d'état puis met à jour les chips visuellement."""
        self._filter = label
        for name, chip in self.filter_buttons.items():
            if name == label:
                chip.setStyleSheet(
                    f"color: {DesignTokens.TEXT_ON_ACCENT}; font-size: 10px; font-weight: bold; padding: 2px 8px; "
                    f"border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 9px; background: {DesignTokens.ACCENT_PRIMARY};"
                )
            else:
                chip.setStyleSheet(
                    f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; padding: 2px 8px; "
                    f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 9px; background: transparent;"
                )
        self._apply_filter()
        self.filter_changed.emit(label)

    @property
    def filter(self) -> str:
        return self._filter

    def _apply_filter(self) -> None:
        for row_idx in range(self.table.rowCount()):
            status = "En attente"
            if row_idx < len(self._tasks):
                status = str(self._tasks[row_idx].get("status", "En attente"))
            visible = self._status_matches(status)
            self.table.setRowHidden(row_idx, not visible)
        visible_rows = sum(1 for row_idx in range(self.table.rowCount()) if not self.table.isRowHidden(row_idx))
        self.lbl_filter_info.setText(f"{visible_rows}/{len(self._tasks)} tâche(s)")

    def _status_matches(self, status: str) -> bool:
        for label, statuses in _FILTERS:
            if label == self._filter:
                return not statuses or status in statuses
        return True

    # ── Thème ───────────────────────────────────────────────────────────

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self.table, "refresh_theme"):
            self.table.refresh_theme(profile)
        for cell in self.cell_widgets_map.values():
            if hasattr(cell, "refresh_theme"):
                cell.refresh_theme(profile)

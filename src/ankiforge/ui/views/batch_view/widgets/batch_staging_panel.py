"""
Batch Staging Panel — Volet de Revue & Staging des cartes générées.

Affiché quand l'utilisateur clique sur "Examiner" ou sélectionne une tâche en statut REVIEW.
Harmonisé sur les principes ergonomiques de CreationView :
  - Volet gauche : table des cartes avec multi-sélection, statuts unitaires en direct.
  - Volet droit : aperçu WebEngine live avec navigation (<, X/Y, >) et badge de statut in-situ.
  - Barre d'actions inférieure :
      • Gauche : Enregistrer dans la Forge (X/Y) + Tout valider (1-clic)
      • Droite : Rejeter (R / Suppr), Éditer (E / CardEditDialog), Valider la carte (V / Espace), Rejeter tranche.
  - Raccourcis clavier (V, R, E) et menu contextuel complet.

Signaux émis (identifiés par la clé de rangée « _queue_uid », jamais par l'index) :
  - cards_accepted(task_uid: str, accepted_cards: list[dict])
  - task_rejected(task_uid: str)

Qt equivalent: QWidget (QSplitter horizontal + barre d'actions)
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, cast

from PySide6.QtCore import QEvent, Qt, Signal, Slot
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import Badge, DangerButton, IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.creation_view.dialogs import CardEditDialog
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import ToastManager, show_toast
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.logger import log_and_notify_error

logger = logging.getLogger(__name__)


class BatchStagingPanel(QWidget):
    """
    Volet de revue interactif pour les tâches en statut REVIEW.

    L'utilisateur peut :
      • Examiner les cartes une par une avec l'aperçu WebEngine en direct
      • Naviguer entre les cartes (<, X/Y, >) ou via la table
      • Valider (V), Rejeter (R) ou Éditer (E via CardEditDialog) carte par carte ou par sélection
      • Tout valider en 1-clic pour basculer les cartes restantes
      • Enregistrer les cartes validées dans AnkiForge avec dialogue de validation globale
    """

    # Signaux vers BatchView (portent la clé de rangée, stable même après suppression en amont)
    cards_accepted = Signal(str, list)  # (task_uid, accepted_cards)
    task_rejected = Signal(str)  # (task_uid,)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchStagingPanel")

        self._current_task_idx: int = -1
        self._current_task_uid: str = ""
        # Une revue est « actives » dès qu'une tâche est chargée ; la garde anti-écrasement
        # du flux auto (task_review_ready) repose sur cet état, plus sur la visibilité.
        self._review_active: bool = False
        self._current_task_data: dict[str, Any] = {}
        self._prepared_notes: list[dict[str, Any]] = []
        self._current_card_idx: int = 0
        self._save_callback: Callable[[list[dict[str, Any]], int, int, int], None] | None = None
        self._review_tasks_provider: Callable[[], list[tuple[int, dict[str, Any], list[dict[str, Any]]]]] | None = None

        self._setup_ui()
        self.show_empty_state()

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

        # Navigation entre les tâches 'À réviser' (revue agrégée du lot)
        self.btn_prev_task = IconButton("ph.caret-left", tooltip="Tranche précédente à valider", size=18)
        self.btn_next_task = IconButton("ph.caret-right", tooltip="Tranche suivante à valider", size=18)
        self.btn_prev_task.clicked.connect(lambda: self._nav_to_task(-1))
        self.btn_next_task.clicked.connect(lambda: self._nav_to_task(1))
        header_row.addWidget(self.btn_prev_task)
        header_row.addWidget(self.btn_next_task)

        # Bouton fermer (ferme la revue, pas l'onglet : la tâche reste consultable dans la file)
        btn_close = IconButton("ph.x", tooltip="Fermer la revue (la tâche reste dans la file)", size=20)
        btn_close.clicked.connect(lambda: self.show_empty_state("Revue fermée — la tâche reste 'À réviser' dans la file."))
        header_row.addWidget(btn_close)

        main_layout.addWidget(header)

        # ── Splitter principal (Table à gauche | Aperçu à droite) ─────────
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
        self.cards_table.verticalHeader().setDefaultSectionSize(36)
        self.cards_table.verticalHeader().setVisible(False)

        hdr = self.cards_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.cards_table.setColumnWidth(0, 95)
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
        self.cards_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.cards_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.cards_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cards_table.customContextMenuRequested.connect(self._on_context_menu)
        self.cards_table.installEventFilter(self)

        left_layout.addWidget(self.cards_table, 1)
        self._splitter.addWidget(left_widget)

        # Volet droit : navigation in-situ + aperçu WebEngine
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        preview_nav = QFrame()
        preview_nav.setObjectName("stagingPreviewNav")
        preview_nav.setStyleSheet(f"QFrame#stagingPreviewNav {{ background: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; }}")
        preview_nav.setFixedHeight(38)
        preview_nav_layout = QHBoxLayout(preview_nav)
        preview_nav_layout.setContentsMargins(10, 4, 10, 4)
        preview_nav_layout.setSpacing(8)

        self.btn_prev_card = IconButton("ph.caret-left", "Carte précédente", 20)
        self.btn_next_card = IconButton("ph.caret-right", "Carte suivante", 20)
        self.btn_prev_card.clicked.connect(self._on_prev_card)
        self.btn_next_card.clicked.connect(self._on_next_card)

        self.lbl_card_counter = QLabel("0 / 0")
        self.lbl_card_counter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-weight: bold; font-size: 11px;")

        self.status_badge = Badge("En attente", variant="warning")

        preview_nav_layout.addWidget(self.btn_prev_card)
        preview_nav_layout.addWidget(self.lbl_card_counter)
        preview_nav_layout.addWidget(self.btn_next_card)
        preview_nav_layout.addSpacing(6)
        preview_nav_layout.addWidget(self.status_badge)
        preview_nav_layout.addStretch()

        right_layout.addWidget(preview_nav)

        self.card_preview = CardPreviewWidget(parent=right_widget, show_header=False)
        self.card_preview.set_empty_state("Sélectionnez une carte pour la prévisualiser.")
        right_layout.addWidget(self.card_preview, 1)

        self._splitter.addWidget(right_widget)
        self._splitter.setSizes([400, 440])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)

        main_layout.addWidget(self._splitter, 1)

        # ── Barre d'actions inférieure (Pôle Persistance & Pôle Granularité) ──
        action_bar = QFrame()
        action_bar.setObjectName("stagingActionBar")
        action_bar.setStyleSheet(f"QFrame#stagingActionBar {{ background: {DesignTokens.BG_PANEL}; border-top: 1px solid {DesignTokens.BORDER_COLOR}; }}")
        action_row = QHBoxLayout(action_bar)
        action_row.setContentsMargins(10, 6, 10, 6)
        action_row.setSpacing(8)

        # Pôle Gauche : Enregistrer & Tout valider
        self.btn_save_anki = PrimaryButton("Enregistrer dans la Forge (0/0)")
        self.btn_save_anki.setIcon(load_on_accent_icon("ph.floppy-disk"))
        self.btn_save_anki.setToolTip("Enregistrer les cartes validées dans votre collection AnkiForge (Ctrl+S)")
        self.btn_save_anki.clicked.connect(self._on_save_anki)

        self.btn_accept_all = SecondaryButton("Tout valider")
        self.btn_accept_all.setIcon(load_phosphor_icon("ph.checks", color=DesignTokens.COLOR_GREEN))
        self.btn_accept_all.setToolTip("Marquer toutes les cartes comme validées (1-clic)")
        self.btn_accept_all.clicked.connect(self._on_mark_all_accepted)

        action_row.addWidget(self.btn_save_anki)
        action_row.addWidget(self.btn_accept_all)

        action_row.addStretch()

        # Pôle Droit : Actions granulaires (Rejeter, Éditer, Valider, Rejeter tranche)
        self.btn_rejeter = DangerButton("Rejeter", ghost=True)
        self.btn_rejeter.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_rejeter.setToolTip("Rejeter la carte active et passer à la suivante (Raccourci: Suppr ou R)")
        self.btn_rejeter.clicked.connect(self._on_reject_card)

        self.btn_editer = SecondaryButton("Éditer")
        self.btn_editer.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_editer.setToolTip("Modifier les champs de la carte (Raccourci: E ou double-clic)")
        self.btn_editer.clicked.connect(self._on_edit_card)

        self.btn_valider = PrimaryButton("Valider la carte")
        self.btn_valider.setIcon(load_on_accent_icon("ph.check"))
        self.btn_valider.setToolTip("Valider la carte active et passer à la suivante (Raccourci: Espace ou V)")
        self.btn_valider.clicked.connect(self._on_validate_card)

        self.btn_reject_task = SecondaryButton("Rejeter la tranche")
        self.btn_reject_task.setIcon(load_phosphor_icon("ph.x-circle", color=DesignTokens.COLOR_RED))
        self.btn_reject_task.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; border-color: {DesignTokens.COLOR_RED};")
        self.btn_reject_task.setToolTip("Abandonner toute la tranche et ses cartes")
        self.btn_reject_task.clicked.connect(self._on_reject_task)

        action_row.addWidget(self.btn_rejeter)
        action_row.addWidget(self.btn_editer)
        action_row.addWidget(self.btn_valider)
        action_row.addSpacing(4)
        action_row.addWidget(self.btn_reject_task)

        # Attribut de compatibilité pour d'éventuels appels existants
        self.btn_accept_selection = SecondaryButton("Valider la sélection")
        self.btn_accept_selection.hide()
        self.btn_accept_selection.clicked.connect(self._on_accept_selection)

        main_layout.addWidget(action_bar)

    # ── Raccourcis Clavier ────────────────────────────────────────────────

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj == self.cards_table and event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)
            key = key_event.key()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_V):
                self._on_validate_card()
                return True
            elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace, Qt.Key.Key_R):
                self._on_reject_card()
                return True
            elif key == Qt.Key.Key_E:
                self._on_edit_card()
                return True
        return super().eventFilter(obj, event)

    # ── API publique ──────────────────────────────────────────────────────

    def set_save_callback(self, cb: Callable[[list[dict[str, Any]], int, int, int], None]) -> None:
        """Enregistre la fonction de sauvegarde (déléguée à BatchView._save_extracted_notes_to_db)."""
        self._save_callback = cb

    def set_review_tasks_provider(self, provider: Callable[[], list[tuple[int, dict[str, Any], list[dict[str, Any]]]]] | None) -> None:
        """Enregistre la source des tâches 'À réviser' pour la navigation '< >' entre tranches."""
        self._review_tasks_provider = provider

    def _nav_to_task(self, offset: int) -> None:
        """Bascule vers la tranche précédente/suivante de la revue agrégée du lot."""
        if self._review_tasks_provider is None:
            return
        review_tasks = self._review_tasks_provider()
        if not review_tasks:
            return
        indices = [entry[0] for entry in review_tasks]
        try:
            pos = indices.index(self._current_task_idx)
        except ValueError:
            pos = 0 if offset > 0 else len(review_tasks) - 1
        else:
            pos = (pos + offset) % len(review_tasks)
        task_idx, task_data, notes = review_tasks[pos]
        self.load_task(task_idx, task_data, notes, force=True)

    def load_task(
        self,
        task_idx: int,
        task_data: dict[str, Any],
        prepared_notes: list[dict[str, Any]],
        force: bool = False,
    ) -> None:
        """
        Charge une tâche terminée pour révision.

        Args:
            task_idx: Indice de la tâche dans queue_tasks_data.
            task_data: Entrée brute de queue_tasks_data[task_idx] (doit porter `_queue_uid`).
            prepared_notes: Cartes générées (list of field dicts).
            force: Si False (appels automatiques), ne pas écraser une revue en cours.
        """
        task_uid = str(task_data.get("_queue_uid") or "")
        if not force and self._review_active and self._current_task_uid and self._current_task_uid != task_uid:
            logger.info("Revue en cours ignorée : le volet affiche déjà une autre tâche (clé %s).", self._current_task_uid)
            return

        self._current_task_idx = task_idx
        self._current_task_uid = task_uid
        self._review_active = True
        self._current_task_data = task_data
        self._prepared_notes = [dict(note) for note in prepared_notes]
        self._current_card_idx = 0

        # Ajouter un statut de staging par carte si absent
        for note in self._prepared_notes:
            note.setdefault("_staging_status", "pending")

        doc_title: str = str(task_data.get("doc_title") or task_data.get("doc", {}).get("title", "Document"))
        self.lbl_title.setText(f"Revue — {doc_title[:60]}")
        self.lbl_count.setText(f"{len(self._prepared_notes)} carte(s)")

        self._rebuild_table()
        self._refresh_save_button()

        if self._prepared_notes:
            self._select_card(0)
        else:
            self.card_preview.set_empty_state("Cliquez sur une carte pour la prévisualiser.")
            self._update_card_preview()

    def show_empty_state(self, message: str = "Revue — sélectionnez une tâche 'À réviser' dans la file d'attente.") -> None:
        """Réinitialise le volet de revue : aucune tâche chargée, table et aperçu vides.

        L'onglet reste affiché (non fermable) ; seule la *revue en cours* est fermée.
        """
        self._review_active = False
        self._current_task_idx = -1
        self._current_task_uid = ""
        self._current_task_data = {}
        self._prepared_notes = []
        self._current_card_idx = 0
        self.lbl_title.setText(message)
        self.lbl_count.setText("")
        self.cards_table.blockSignals(True)
        self.cards_table.setRowCount(0)
        self.cards_table.blockSignals(False)
        self._refresh_save_button()
        self._update_card_preview()

    def _rebuild_table(self) -> None:
        self.cards_table.blockSignals(True)
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
            edited = bool(note.get("_user_edited"))
            content_item = QTableWidgetItem(("✎ " + front_text[:120]) if edited else front_text[:120])
            content_item.setToolTip((front_text + "\n[Carte modifiée manuellement]") if edited else front_text)
            self.cards_table.setItem(row_idx, 1, content_item)

            # Col 2 : nombre de champs
            field_count = sum(1 for k in note if not k.startswith("_"))
            fields_item = QTableWidgetItem(f"{field_count} ch.")
            fields_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            fields_item.setForeground(Qt.GlobalColor.gray)
            self.cards_table.setItem(row_idx, 2, fields_item)

            # Colorier la ligne selon le statut de staging
            bg = {
                "accepted": QColor(DesignTokens.COLOR_GREEN),
                "rejected": QColor(DesignTokens.COLOR_RED),
            }.get(staging_status, QColor(DesignTokens.BG_INPUT))
            for col in range(3):
                item = self.cards_table.item(row_idx, col)
                if item:
                    item.setBackground(bg)

        self.cards_table.blockSignals(False)

    def _select_card(self, idx: int) -> None:
        """Sélectionne une carte dans la table et synchronise l'aperçu."""
        if not self._prepared_notes:
            return
        idx = max(0, min(idx, len(self._prepared_notes) - 1))
        self._current_card_idx = idx

        self.cards_table.blockSignals(True)
        self.cards_table.selectRow(idx)
        self.cards_table.blockSignals(False)

        item = self.cards_table.item(idx, 0)
        if item:
            self.cards_table.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

        self._update_card_preview()

    def _update_card_preview(self) -> None:
        """Met à jour l'aperçu WebEngine, le compteur et le badge de statut in-situ."""
        if not self._prepared_notes or not (0 <= self._current_card_idx < len(self._prepared_notes)):
            self.card_preview.set_empty_state("Sélectionnez une carte pour la prévisualiser.")
            self.lbl_card_counter.setText("0 / 0")
            self.status_badge.setText("En attente")
            self.status_badge.set_variant("warning")
            self.btn_prev_card.setEnabled(False)
            self.btn_next_card.setEnabled(False)
            return

        note = self._prepared_notes[self._current_card_idx]
        total = len(self._prepared_notes)
        self.lbl_card_counter.setText(f"{self._current_card_idx + 1} / {total}")
        self.btn_prev_card.setEnabled(self._current_card_idx > 0)
        self.btn_next_card.setEnabled(self._current_card_idx < total - 1)

        # Statut badge in-situ
        status = note.get("_staging_status", "pending")
        status_map: dict[str, tuple[str, str]] = {
            "pending": ("En attente", "warning"),
            "accepted": ("Validée", "success"),
            "rejected": ("Refusée", "danger"),
        }
        text, variant = status_map.get(status, (status, "warning"))
        self.status_badge.setText(text)
        self.status_badge.set_variant(variant)

        # Mise à jour CardPreviewWidget
        task_data = self._current_task_data
        note_type = task_data.get("note_type")
        fields_dict = {k: str(v) for k, v in note.items() if not k.startswith("_")}

        if note_type is not None:
            self.card_preview.update_preview(note_type=note_type, fields_dict=fields_dict)
        else:
            front = _get_front_text(note)
            self.card_preview.set_empty_state(front[:500] if front else "Aperçu indisponible")

    def _refresh_save_button(self) -> None:
        """Met à jour le décompte affiché sur le bouton d'enregistrement."""
        accepted_count = sum(1 for c in self._prepared_notes if c.get("_staging_status") == "accepted")
        total_count = len(self._prepared_notes)
        if total_count > 0:
            self.btn_save_anki.setText(f"Enregistrer dans la Forge ({accepted_count}/{total_count})")
            self.btn_save_anki.setEnabled(True)
        else:
            self.btn_save_anki.setText("Enregistrer dans la Forge (0)")
            self.btn_save_anki.setEnabled(False)

    # ── Slots de Navigation Carte ─────────────────────────────────────────

    @Slot()
    def _on_prev_card(self) -> None:
        if self._current_card_idx > 0:
            self._select_card(self._current_card_idx - 1)

    @Slot()
    def _on_next_card(self) -> None:
        if self._current_card_idx < len(self._prepared_notes) - 1:
            self._select_card(self._current_card_idx + 1)

    # ── Slots de Modification de Statut Granulaire ────────────────────────

    @Slot()
    def _on_validate_card(self) -> None:
        """Valide la carte active ou toutes les cartes sélectionnées, et avance."""
        if not self._prepared_notes:
            return

        ToastManager.get_instance().clear()
        selected_rows = sorted({idx.row() for idx in self.cards_table.selectedIndexes()})

        if len(selected_rows) > 1:
            for r in selected_rows:
                if 0 <= r < len(self._prepared_notes):
                    self._prepared_notes[r]["_staging_status"] = "accepted"
            self._rebuild_table()
            self._refresh_save_button()
            next_idx = min(selected_rows[-1] + 1, len(self._prepared_notes) - 1)
            self._select_card(next_idx)
            return

        if not (0 <= self._current_card_idx < len(self._prepared_notes)):
            return

        self._prepared_notes[self._current_card_idx]["_staging_status"] = "accepted"
        next_idx = self._current_card_idx + 1
        self._rebuild_table()
        self._refresh_save_button()

        if next_idx < len(self._prepared_notes):
            self._select_card(next_idx)
        else:
            self._select_card(self._current_card_idx)
            show_toast(self, "Toutes les cartes ont été passées en revue !", is_error=False)

    @Slot()
    def _on_reject_card(self) -> None:
        """Rejette la carte active ou toutes les cartes sélectionnées, et avance."""
        if not self._prepared_notes:
            return

        ToastManager.get_instance().clear()
        selected_rows = sorted({idx.row() for idx in self.cards_table.selectedIndexes()})

        if len(selected_rows) > 1:
            for r in selected_rows:
                if 0 <= r < len(self._prepared_notes):
                    self._prepared_notes[r]["_staging_status"] = "rejected"
            self._rebuild_table()
            self._refresh_save_button()
            next_idx = min(selected_rows[-1] + 1, len(self._prepared_notes) - 1)
            self._select_card(next_idx)
            return

        if not (0 <= self._current_card_idx < len(self._prepared_notes)):
            return

        self._prepared_notes[self._current_card_idx]["_staging_status"] = "rejected"
        next_idx = self._current_card_idx + 1
        self._rebuild_table()
        self._refresh_save_button()

        if next_idx < len(self._prepared_notes):
            self._select_card(next_idx)
        else:
            self._select_card(self._current_card_idx)
            show_toast(self, "Toutes les cartes ont été passées en revue !", is_error=False)

    @Slot()
    def _on_edit_card(self) -> None:
        """Ouvre CardEditDialog pour éditer tous les champs de la carte courante."""
        if not self._prepared_notes or not (0 <= self._current_card_idx < len(self._prepared_notes)):
            return

        note = self._prepared_notes[self._current_card_idx]
        task_data = self._current_task_data
        target_nt = task_data.get("note_type")

        field_names: list[str] = []
        if target_nt and hasattr(target_nt, "fields_schema") and target_nt.fields_schema:
            try:
                raw_schema = target_nt.fields_schema
                field_names = json.loads(str(raw_schema)) if isinstance(raw_schema, str) else list(raw_schema)
            except Exception:
                field_names = []

        dlg = CardEditDialog(
            card_data=note,
            field_names=field_names,
            note_type=target_nt,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            updated_fields = dlg.get_fields()
            note.update(updated_fields)
            note["_user_edited"] = True  # pastille « modifiée » ; clé interne exclue de la sauvegarde

            # Nettoyer les clés fantômes
            if field_names:
                for k in list(note.keys()):
                    if k not in CardEditDialog.METADATA_KEYS and not str(k).startswith("_") and k not in field_names:
                        del note[k]

            self._rebuild_table()
            self._update_card_preview()
            show_toast(self, "Carte modifiée en mémoire.")

    @Slot()
    def _on_mark_all_accepted(self) -> None:
        """Marque toutes les cartes 'pending' comme 'accepted' en mémoire, sans fermer le staging."""
        changed = 0
        for note in self._prepared_notes:
            if note.get("_staging_status") not in ("rejected", "accepted"):
                note["_staging_status"] = "accepted"
                changed += 1
        if changed > 0:
            self._rebuild_table()
            self._refresh_save_button()
            self._update_card_preview()
            show_toast(self, f"{changed} carte(s) marquée(s) comme validée(s).", is_error=False)

    def _toggle_card_status(self, row_idx: int, status: str) -> None:
        """Bascule le statut de staging d'une carte (sans sauvegarde, revue en cours)."""
        if 0 <= row_idx < len(self._prepared_notes):
            note = self._prepared_notes[row_idx]
            current = note.get("_staging_status", "pending")
            note["_staging_status"] = status if current != status else "pending"
            self._rebuild_table()
            self._refresh_save_button()
            self._select_card(row_idx)

    def _set_single_status(self, row_idx: int, status: str) -> None:
        """Assigne explicitement un statut de staging à une carte."""
        if 0 <= row_idx < len(self._prepared_notes):
            self._prepared_notes[row_idx]["_staging_status"] = status
            self._rebuild_table()
            self._refresh_save_button()
            self._select_card(row_idx)

    def _on_reset_selection(self) -> None:
        """Remet les cartes sélectionnées à l'état 'pending' (En attente)."""
        selected_rows = {idx.row() for idx in self.cards_table.selectedIndexes()}
        for r in selected_rows:
            if 0 <= r < len(self._prepared_notes):
                self._prepared_notes[r]["_staging_status"] = "pending"
        self._rebuild_table()
        self._refresh_save_button()
        self._update_card_preview()

    # ── Événements de Table ───────────────────────────────────────────────

    @Slot()
    def _on_table_selection_changed(self) -> None:
        """Adapte dynamiquement les libellés des boutons selon la sélection."""
        selected_rows = {idx.row() for idx in self.cards_table.selectedIndexes()}
        count = len(selected_rows)
        if count > 1:
            self.btn_valider.setText(f"Valider la sélection ({count})")
            self.btn_valider.setToolTip(f"Marquer les {count} cartes sélectionnées comme validées")
            self.btn_rejeter.setText(f"Rejeter la sélection ({count})")
            self.btn_rejeter.setToolTip(f"Marquer les {count} cartes sélectionnées comme rejetées")
            self.btn_editer.setEnabled(False)
        else:
            self.btn_valider.setText("Valider la carte")
            self.btn_valider.setToolTip("Valider la carte active et passer à la suivante (Raccourci: Espace ou V)")
            self.btn_rejeter.setText("Rejeter")
            self.btn_rejeter.setToolTip("Rejeter la carte active et passer à la suivante (Raccourci: Suppr ou R)")
            self.btn_editer.setEnabled(True)
            if count == 1:
                row = next(iter(selected_rows))
                if 0 <= row < len(self._prepared_notes) and row != self._current_card_idx:
                    self._current_card_idx = row
                    self._update_card_preview()

    @Slot(int)
    def _on_card_row_changed(self, row: int) -> None:
        if 0 <= row < len(self._prepared_notes):
            self._current_card_idx = row
            self._update_card_preview()

    @Slot(int, int)
    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        """Double-clic sur une ligne : ouvre CardEditDialog pour éditer la carte proprement."""
        if 0 <= row < len(self._prepared_notes):
            self._current_card_idx = row
            self._on_edit_card()

    def _on_context_menu(self, pos: Any) -> None:
        """Menu contextuel granulaire : valider, rejeter, remettre en attente, éditer."""
        row = self.cards_table.rowAt(pos.y())
        selected_rows = {idx.row() for idx in self.cards_table.selectedIndexes()}
        menu = QMenu(self)

        if len(selected_rows) > 1:
            act_val_sel = menu.addAction(f"Valider la sélection ({len(selected_rows)})")
            act_val_sel.setIcon(load_phosphor_icon("ph.check", color=DesignTokens.COLOR_GREEN))
            act_val_sel.triggered.connect(self._on_validate_card)

            act_rej_sel = menu.addAction(f"Rejeter la sélection ({len(selected_rows)})")
            act_rej_sel.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
            act_rej_sel.triggered.connect(self._on_reject_card)

            act_reset_sel = menu.addAction(f"Remettre en attente ({len(selected_rows)})")
            act_reset_sel.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise", color=DesignTokens.COLOR_YELLOW))
            act_reset_sel.triggered.connect(self._on_reset_selection)
            menu.addSeparator()
        elif row >= 0:
            act_accept = menu.addAction("Valider la carte (V)")
            act_accept.setIcon(load_phosphor_icon("ph.check", color=DesignTokens.COLOR_GREEN))
            act_accept.triggered.connect(lambda _=False, r=row: self._set_single_status(r, "accepted"))

            act_reject = menu.addAction("Rejeter la carte (R)")
            act_reject.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
            act_reject.triggered.connect(lambda _=False, r=row: self._set_single_status(r, "rejected"))

            act_reset = menu.addAction("Remettre en attente")
            act_reset.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise", color=DesignTokens.COLOR_YELLOW))
            act_reset.triggered.connect(lambda _=False, r=row: self._set_single_status(r, "pending"))

            act_edit = menu.addAction("Éditer la carte... (E)")
            act_edit.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
            act_edit.triggered.connect(self._on_edit_card)
            menu.addSeparator()

        act_all = menu.addAction("Tout valider")
        act_all.setIcon(load_phosphor_icon("ph.checks", color=DesignTokens.COLOR_GREEN))
        act_all.triggered.connect(self._on_mark_all_accepted)

        menu.addSeparator()
        act_rej_task = menu.addAction("Rejeter la tranche entière")
        act_rej_task.setIcon(load_phosphor_icon("ph.x-circle", color=DesignTokens.COLOR_RED))
        act_rej_task.triggered.connect(self._on_reject_task)

        menu.exec(self.cards_table.viewport().mapToGlobal(pos))

    # ── Sauvegarde & Clôture de la Tranche ────────────────────────────────

    @Slot()
    def _on_save_anki(self) -> None:
        """Enregistre les cartes validées dans AnkiForge avec dialogue de validation si cartes en attente."""
        if not self._prepared_notes:
            show_toast(self, "Aucune carte générée à enregistrer.", is_error=True)
            return

        pending_cards = [c for c in self._prepared_notes if c.get("_staging_status") == "pending"]
        accepted_cards = [c for c in self._prepared_notes if c.get("_staging_status") == "accepted"]

        if pending_cards:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Enregistrement des Cartes")
            msg_box.setText(f"Il reste <b>{len(pending_cards)} carte(s)</b> en attente de décision.")
            msg_box.setInformativeText("Souhaitez-vous tout valider automatiquement ou enregistrer uniquement les cartes déjà marquées 'Validée' ?")

            btn_accept_all = msg_box.addButton(
                f"Tout Valider et Enregistrer ({len(accepted_cards) + len(pending_cards)})",
                QMessageBox.ButtonRole.AcceptRole,
            )
            btn_save_validated = msg_box.addButton(
                f"Enregistrer Validées Uniquement ({len(accepted_cards)})",
                QMessageBox.ButtonRole.ActionRole,
            )
            _ = msg_box.addButton("Continuer la Revue", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()
            clicked_btn = msg_box.clickedButton()

            if clicked_btn == btn_accept_all:
                for c in self._prepared_notes:
                    if c.get("_staging_status") == "pending":
                        c["_staging_status"] = "accepted"
                accepted_cards = [c for c in self._prepared_notes if c.get("_staging_status") == "accepted"]
            elif clicked_btn == btn_save_validated:
                if not accepted_cards:
                    show_toast(self, "Aucune carte n'a encore été marquée 'Validée'. Validez des cartes d'abord.", is_error=True)
                    return
            else:
                return

        if not accepted_cards:
            show_toast(self, "Aucune carte 'Validée' à enregistrer.", is_error=True)
            return

        self._save_and_emit(accepted_cards)

    @Slot()
    def _on_accept_all(self) -> None:
        """Tout valider et enregistrer immédiatement (rétrocompatibilité tests et raccourci batch)."""
        accepted = [note for note in self._prepared_notes if note.get("_staging_status") != "rejected"]
        for note in accepted:
            note["_staging_status"] = "accepted"
        if accepted:
            self._save_and_emit(accepted)
        else:
            self.task_rejected.emit(self._current_task_uid)

    @Slot()
    def _on_accept_selection(self) -> None:
        """Valide les lignes sélectionnées dans la table sans fermer le staging."""
        selected_rows = {idx.row() for idx in self.cards_table.selectedIndexes()}
        if not selected_rows:
            return
        for row_idx in selected_rows:
            if 0 <= row_idx < len(self._prepared_notes):
                self._prepared_notes[row_idx]["_staging_status"] = "accepted"
        self._rebuild_table()
        self._refresh_save_button()
        self._update_card_preview()

    @Slot()
    def _on_reject_task(self) -> None:
        """Rejette l'ensemble des cartes de la tranche."""
        for note in self._prepared_notes:
            note["_staging_status"] = "rejected"
        self._rebuild_table()
        self.task_rejected.emit(self._current_task_uid)

    def _save_and_emit(self, notes_to_save: list[dict[str, Any]]) -> None:
        """Délègue l'enregistrement en BDD et émet cards_accepted."""
        task = self._current_task_data
        deck_id = task["deck"].id if hasattr(task.get("deck"), "id") else 1
        model_id = task["note_type"].id if hasattr(task.get("note_type"), "id") else 1
        doc = task.get("doc")
        doc_id = doc.id if hasattr(doc, "id") else 0

        # Filtrer les clés internes de staging avant sauvegarde (conserver la provenance _source_*)
        clean_notes = [{k: v for k, v in n.items() if not k.startswith("_") or k.startswith("_source_")} for n in notes_to_save]

        if self._save_callback is not None:
            try:
                self._save_callback(clean_notes, deck_id, model_id, doc_id)
            except Exception as exc:
                log_and_notify_error(str(exc), context="Staging Panel", parent=self)
                return
        else:
            logger.warning("BatchStagingPanel: aucun callback de sauvegarde configuré.")

        self._rebuild_table()
        self.cards_accepted.emit(self._current_task_uid, clean_notes)


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

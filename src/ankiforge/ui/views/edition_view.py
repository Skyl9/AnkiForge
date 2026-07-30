"""
Vue Édition / Analyse — 100% Conforme à la Maquette concept_ide + Raccordement Métier Avancé.
- Barre de filtre (Dossier, Tags)
- QTableWidget multicolonnes pour liste des cartes.
- Éditeur masqué par défaut si aucune carte n'est sélectionnée.
- Redimensionnement interactif libre de la table et de l'éditeur via QSplitter vertical.
"""

import logging
import json
from typing import Optional, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QLabel,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QProgressDialog,
    QMenu,
    QPushButton,
    QAbstractItemView,
    QInputDialog,
)
from PySide6.QtCore import Qt, Slot, QSettings
from PySide6.QtGui import QFont, QAction, QColor, QBrush

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton, IconButton
from ankiforge.ui.components.inputs import StyledTextEdit
from ankiforge.utils.icon_loader import load_phosphor_icon

from ankiforge.database.models import NoteModel, NoteVersionModel, LLMConfigModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.cards.duplicate_manager import DuplicateManager
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.services.workers.batch_edit_worker import BatchEditWorker
from ankiforge.services.workers.import_cards_worker import ImportCardsWorker

from ankiforge.ui.widgets.auto_tag_dialog import AutoTagDialog
from ankiforge.ui.widgets.batch_edit_dialog import BatchEditDialog
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog
from ankiforge.ui.widgets.linter_dialog import LinterDialog
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog
from ankiforge.ui.dialogs.history_modal import HistoryModal
from ankiforge.ui.widgets.katex_editor import KaTeXHighlighter
from ankiforge.ui.components.deck_select_window import DeckSelectWindow

logger = logging.getLogger(__name__)


class EditionView(QWidget):
    """
    Vue Édition / Analyse conformité 100% avec maquette concept_ide/index.html.
    Orchestration complète des opérations métiers Anki (Linter IA, Auto-Tag, Doublons, Édition par Lot, Versionnage).
    Optimisation pour >2000 cartes via chargement virtuel dynamique et fenêtre de prévisualisation rétractable.
    """

    BATCH_SIZE = 50

    def __init__(self, ai_manager: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.store = StoreManager()
        self.settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

        self.batch_thread: Optional[BatchEditWorker] = None
        self.import_thread: Optional[ImportCardsWorker] = None
        self.progress_dialog: Optional[QProgressDialog] = None

        self._dirty = False
        self._current_note: Optional[NoteModel] = None
        self._preview_device = "desktop"
        self._active_folder_id: Optional[int] = None
        self._active_tag: Optional[str] = None
        self._deck_modal: Optional[DeckSelectWindow] = None

        # Optimization state for large collections (>2000 cards)
        self._all_notes: list[NoteModel] = []
        self._displayed_count: int = 0

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Panneau unifié (IdePanel)
        self.main_panel = IdePanel(detachable=True)

        panel_content = QWidget()
        panel_layout = QVBoxLayout(panel_content)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # --- BARRE DE SÉLECTION DE DOSSIER & BULLES DE TAGS ---
        filter_bar = QWidget()
        filter_bar.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(10, 6, 10, 6)
        filter_layout.setSpacing(8)

        self.btn_open_folder = QPushButton("Dossier : Informatique ▾")
        self.btn_open_folder.setIcon(load_phosphor_icon("folder", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: rgba(99, 102, 241, 0.1);
            }}
        """)
        self.btn_open_folder.clicked.connect(self._show_folder_modal)
        filter_layout.addWidget(self.btn_open_folder)

        separator = QFrame()
        separator.setFixedSize(1, 14)
        separator.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        filter_layout.addWidget(separator)

        tags_lbl = QLabel("TAGS SÉLECTIONNÉS :")
        tags_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; text-transform: uppercase; text-decoration: none;")
        filter_layout.addWidget(tags_lbl)

        self.btn_open_tag = QPushButton("Ajouter tag")
        self.btn_open_tag.setIcon(load_phosphor_icon("plus", color=DesignTokens.TEXT_SECONDARY))
        self.btn_open_tag.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: 12px;
                padding: 2px 10px;
                min-height: 20px;
                font-size: 11px;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_open_tag.clicked.connect(self._show_tag_modal)
        filter_layout.addWidget(self.btn_open_tag)
        filter_layout.addStretch()

        panel_layout.addWidget(filter_bar)

        # --- QSplitter Vertical (Table 45% + Éditeur 55%) ---
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {DesignTokens.BORDER_COLOR}; height: 4px; }}")

        # TABLEAU ANKI DE CARTES
        self.card_table = QTableWidget()
        self.card_table.setColumnCount(6)
        self.card_table.setHorizontalHeaderLabels(["", "Question / Recto", "Réponse / Verso", "Deck", "Tags", "Rétention"])
        self.card_table.verticalHeader().setVisible(False)
        self.card_table.setShowGrid(False)
        self.card_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.card_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.card_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.card_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.card_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.card_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.card_table.setColumnWidth(0, 36)
        self.card_table.setColumnWidth(3, 140)
        self.card_table.setColumnWidth(4, 140)
        self.card_table.setColumnWidth(5, 90)

        self.card_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_MUTED};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                padding: 6px;
            }}
            QTableWidget::item {{
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 8px 10px;
            }}
            QTableWidget::item:selected {{
                background-color: rgba(99, 102, 241, 0.12);
            }}
        """)
        self.card_table.itemClicked.connect(self._on_card_selected)
        self.card_table.verticalScrollBar().valueChanged.connect(self._on_card_list_scrolled)
        self.card_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.card_table.customContextMenuRequested.connect(self._show_card_context_menu)

        self.main_splitter.addWidget(self.card_table)

        # BLOC ÉDITION RECTO/VERSO (Éditeur)
        self.editor_container = QWidget()
        self.editor_container.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR};")
        editor_layout = QVBoxLayout(self.editor_container)
        editor_layout.setContentsMargins(6, 6, 6, 6)
        editor_layout.setSpacing(6)

        # Barre d'Outils + Sauvegarder
        toolbar_layout = QHBoxLayout()
        self.btn_bold = IconButton("text-b", tooltip="Gras", size=24)
        self.btn_bold.clicked.connect(lambda: self._insert_format("**", "**"))
        self.btn_italic = IconButton("text-italic", tooltip="Italique", size=24)
        self.btn_italic.clicked.connect(lambda: self._insert_format("*", "*"))
        self.btn_code = IconButton("code", tooltip="Code", size=24)
        self.btn_code.clicked.connect(lambda: self._insert_format("`", "`"))
        toolbar_layout.addWidget(self.btn_bold)
        toolbar_layout.addWidget(self.btn_italic)
        toolbar_layout.addWidget(self.btn_code)

        toolbar_layout.addStretch()

        self.btn_history = SecondaryButton("Historique")
        self.btn_history.setIcon(load_phosphor_icon("clock-counter-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_history.clicked.connect(self._open_history_modal)
        toolbar_layout.addWidget(self.btn_history)

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("floppy-disk", color="white"))
        self.btn_save.clicked.connect(self._save_card)
        toolbar_layout.addWidget(self.btn_save)

        editor_layout.addLayout(toolbar_layout)

        # Champs + Prévisualisation
        fields_layout = QHBoxLayout()
        fields_layout.setSpacing(6)

        # Recto
        recto_widget = QWidget()
        recto_layout = QVBoxLayout(recto_widget)
        recto_layout.setContentsMargins(6, 6, 6, 6)
        recto_lbl = QLabel("RECTO (Question)")
        recto_lbl.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px; font-weight: bold;")
        recto_layout.addWidget(recto_lbl)
        self.editor_recto = StyledTextEdit()
        self.editor_recto.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_MAIN} !important;
                border: 1px solid {DesignTokens.BORDER_COLOR} !important;
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY} !important;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                padding: 10px;
            }}
        """)
        self.editor_recto.textChanged.connect(self._on_text_changed)
        self.recto_highlighter = KaTeXHighlighter(self.editor_recto.document())
        recto_layout.addWidget(self.editor_recto)
        fields_layout.addWidget(recto_widget)

        # Verso
        verso_widget = QWidget()
        verso_layout = QVBoxLayout(verso_widget)
        verso_layout.setContentsMargins(6, 6, 6, 6)
        verso_lbl = QLabel("VERSO (Réponse)")
        verso_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: bold;")
        verso_layout.addWidget(verso_lbl)
        self.editor_verso = StyledTextEdit()
        self.editor_verso.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_MAIN} !important;
                border: 1px solid {DesignTokens.BORDER_COLOR} !important;
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY} !important;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                padding: 10px;
            }}
        """)
        self.editor_verso.textChanged.connect(self._on_text_changed)
        self.verso_highlighter = KaTeXHighlighter(self.editor_verso.document())
        verso_layout.addWidget(self.editor_verso)
        fields_layout.addWidget(verso_widget)

        # Live Preview (KaTeX)
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_lbl = QLabel("Rendu Live KaTeX")
        preview_lbl.setStyleSheet("color: #c084fc; font-size: 11px; font-weight: bold;")
        preview_layout.addWidget(preview_lbl)
        self.card_preview = CardPreviewWidget(show_header=False)
        preview_layout.addWidget(self.card_preview)
        fields_layout.addWidget(preview_widget)

        editor_layout.addLayout(fields_layout)

        self.main_splitter.addWidget(self.editor_container)
        self.main_splitter.setSizes([450, 550])

        panel_layout.addWidget(self.main_splitter)

        self.main_panel.add_tab("Éditeur & Navigateur de Cartes (Style Anki Desktop)", panel_content, icon_name="ph.cards", closable=False)
        main_layout.addWidget(self.main_panel)

        self.editor_container.setVisible(False)

    def _show_card_context_menu(self, pos) -> None:
        item = self.card_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        checkbox_item = self.card_table.item(row, 0)
        if not checkbox_item:
            return
        note = checkbox_item.data(Qt.ItemDataRole.UserRole)
        if not note:
            return

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QMenu::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        act_approve = QAction("Approuver la note", self)
        act_approve.triggered.connect(lambda: self.approve_selected_notes([note.id]))
        menu.addAction(act_approve)

        act_reject = QAction("Rejeter / Supprimer la note", self)
        act_reject.triggered.connect(lambda: self.reject_selected_notes([note.id]))
        menu.addAction(act_reject)

        menu.addSeparator()

        act_linter = QAction("Linter IA", self)
        act_linter.triggered.connect(lambda: self.open_linter_dialog([note.id]))
        menu.addAction(act_linter)

        act_autotag = QAction("Auto-Tag IA", self)
        act_autotag.triggered.connect(lambda: self.open_auto_tag_dialog([note.id]))
        menu.addAction(act_autotag)

        act_batch = QAction("Édition IA par Lot", self)
        act_batch.triggered.connect(lambda: self.open_batch_edit_dialog([note.id]))
        menu.addAction(act_batch)

        act_history = QAction("Historique des versions", self)
        act_history.triggered.connect(lambda: self.show_version_history(note.id))
        menu.addAction(act_history)

        menu.exec(self.card_table.mapToGlobal(pos))

    def _on_filter_folder(self, folder_id: Optional[int]) -> None:
        self._active_folder_id = folder_id
        self.refresh_data()

    def _on_filter_tag(self, tag_name: Optional[str]) -> None:
        self._active_tag = tag_name
        self.refresh_data()

    def _on_card_selected(self, item: QTableWidgetItem) -> None:
        row = item.row()
        checkbox_item = self.card_table.item(row, 0)
        if not checkbox_item:
            return
        note: Optional[NoteModel] = checkbox_item.data(Qt.ItemDataRole.UserRole)
        if not note:
            return
        self._current_note = note

        if not self.editor_container.isVisible():
            self.editor_container.setVisible(True)

        recto = ""
        verso = ""
        version = NoteVersionModel.get_or_none(note=note, is_active=True)
        if not version:
            version = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

        if version and version.content:
            try:
                data = json.loads(version.content)
                if isinstance(data, dict):
                    for k, v in data.items():
                        k_lower = str(k).lower()
                        if k_lower in ["front", "recto", "question", "text", "texte", "field_1"] and not recto:
                            recto = str(v)
                        elif k_lower in ["back", "verso", "answer", "réponse", "reponse", "extra", "field_2"] and not verso:
                            verso = str(v)
                    if not recto and len(data) > 0:
                        vals = list(data.values())
                        recto = str(vals[0]) if len(vals) > 0 else ""
                        verso = str(vals[1]) if len(vals) > 1 else ""
                else:
                    recto = str(data)
            except Exception:
                recto = version.content

        if not recto and not verso:
            recto = f"Carte #{note.id}"
            verso = ""

        self.editor_recto.setPlainText(recto)
        self.editor_verso.setPlainText(verso)
        self._update_preview()
        self._dirty = False

    def _on_text_changed(self) -> None:
        self._dirty = True
        self._update_preview()

    def _update_preview(self) -> None:
        recto_text = self.editor_recto.toPlainText()
        verso_text = self.editor_verso.toPlainText()

        note_type = getattr(self._current_note, "note_type", None) if self._current_note else None
        fields_dict: dict[str, str] = {
            "Front": recto_text,
            "Back": verso_text,
            "front": recto_text,
            "back": verso_text,
            "Question": recto_text,
            "Answer": verso_text,
        }

        if self._current_note:
            version = NoteVersionModel.get_or_none(note=self._current_note, is_active=True)
            if version and version.content:
                try:
                    v_data = json.loads(version.content)
                    if isinstance(v_data, dict):
                        for k, v in v_data.items():
                            fields_dict[str(k)] = str(v)
                except Exception as e:
                    logger.debug(f"Erreur de parsing JSON pour le contenu de la note: {e}")

        fields_dict["Front"] = recto_text
        fields_dict["Back"] = verso_text
        fields_dict["front"] = recto_text
        fields_dict["back"] = verso_text

        override_templates = None
        if not note_type or not getattr(note_type, "templates", None):
            override_templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]

        self.card_preview.update_preview(
            note_type=note_type,
            fields_dict=fields_dict,
            override_templates=override_templates,
        )

    def _insert_format(self, prefix: str, suffix: str) -> None:
        cursor = self.editor_recto.textCursor()
        selected = cursor.selectedText()
        cursor.insertText(f"{prefix}{selected}{suffix}")

    def _open_history_modal(self) -> None:
        if self._current_note:
            modal = HistoryModal(self._current_note, self)
            modal.exec()

    @Slot()
    def _show_folder_modal(self) -> None:
        if self._deck_modal and self._deck_modal.isVisible():
            self._deck_modal.raise_()
            self._deck_modal.activateWindow()
            return

        self._deck_modal = DeckSelectWindow(parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected_from_modal)
        self._deck_modal.show()

    @Slot(int, str)
    def _on_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
        self.btn_open_folder.setText(f"Dossier : {deck_name} ▾")
        self._active_folder_id = deck_id
        # Reload cards to apply filter
        self.refresh_data()

    @Slot()
    def _show_tag_modal(self) -> None:
        text, ok = QInputDialog.getText(self, "Ajouter un tag", "Rechercher ou ajouter un tag :")
        if ok and text:
            show_toast(self, f"Tag {text} ajouté au filtre")

    @Slot()
    def _run_linter(self) -> None:
        if self._current_note:
            self.open_linter_dialog([self._current_note.id])

    @Slot()
    def _save_card(self) -> None:
        if not self._current_note:
            return

        try:
            new_content = {"front": self.editor_recto.toPlainText(), "back": self.editor_verso.toPlainText()}
            self._current_note.add_version(new_content, source="manual")
            self._dirty = False
            self.refresh_data()
            show_toast(self, f"Carte #{self._current_note.id} sauvegardée avec succès.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible de sauvegarder la carte : {str(e)}")

    @Slot(list)
    def open_linter_dialog(self, note_ids: list[int]) -> None:
        if not note_ids:
            return
        dialog = LinterDialog(note_ids, self)
        dialog.exec()
        self.refresh_data()

    @Slot(list)
    def open_auto_tag_dialog(self, note_ids: list[int]) -> None:
        if not note_ids:
            return
        if AutoTagDialog(self, note_ids).exec():
            show_toast(self, "Auto-Tagging terminé avec succès !")
            self.refresh_data()

    @Slot(list)
    def open_batch_edit_dialog(self, note_ids: list[int]) -> None:
        if not note_ids:
            return
        dialog = BatchEditDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                llm_config = LLMConfigModel.get_by_id(data["llm_id"])
                provider = AIManager.create_provider_from_config(llm_config)
            except Exception:
                provider = None

            if not provider:
                QMessageBox.warning(self, "Configuration IA", "Aucun provider IA disponible pour l'édition par lot.")
                return

            self.progress_dialog = QProgressDialog("Modification IA en cours...", "Annuler", 0, 0, self)
            self.batch_thread = BatchEditWorker(provider, note_ids, data["prompt"], data["chunk_size"])
            self.batch_thread.progress.connect(self.progress_dialog.setLabelText)
            self.batch_thread.finished_signal.connect(self._on_batch_edit_success)
            self.batch_thread.error_signal.connect(self._on_batch_edit_error)
            self.progress_dialog.canceled.connect(self.batch_thread.cancel)
            self.batch_thread.start()
            self.progress_dialog.show()

    def _on_batch_edit_success(self, count: int) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        show_toast(self, f"{count} notes traitées par l'IA !")
        self.refresh_data()

    def _on_batch_edit_error(self, msg: str) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()
        QMessageBox.critical(self, "Erreur IA", msg)

    @Slot()
    def scan_for_duplicates(self) -> None:
        try:
            deck_id = self._active_folder_id or 1
            conflicts = DuplicateManager.find_duplicates(deck_id)
            if not conflicts:
                show_toast(self, "Aucun doublon trouvé !")
            else:
                DuplicateResolverDialog(conflicts, self).exec()
                self.refresh_data()
        except Exception as e:
            logger.exception("Erreur lors du scan des doublons")
            QMessageBox.critical(self, "Erreur", str(e))

    @Slot(int)
    def show_version_history(self, note_id: int) -> None:
        try:
            note = NoteModel.get_by_id(note_id)
            if VersionHistoryDialog(note, self).exec():
                self.refresh_data()
        except Exception:
            self._open_history_modal()

    @Slot(list)
    def approve_selected_notes(self, note_ids: list[int]) -> None:
        try:
            self.store.approve_notes(note_ids)
            show_toast(self, f"{len(note_ids)} note(s) approuvée(s) !")
            self.refresh_data()
        except Exception as e:
            logger.exception("Erreur lors de l'approbation des notes")
            QMessageBox.critical(self, "Erreur", str(e))

    @Slot(list)
    def reject_selected_notes(self, note_ids: list[int]) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Supprimer définitivement {len(note_ids)} note(s) ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_notes(note_ids)
                show_toast(self, "Notes supprimées.")
                self.refresh_data()
            except Exception as e:
                logger.exception("Erreur lors de la suppression des notes")
                QMessageBox.critical(self, "Erreur", str(e))

    def _on_card_list_scrolled(self, value: int) -> None:
        scrollbar = self.card_table.verticalScrollBar()
        if scrollbar.maximum() > 0 and value >= int(scrollbar.maximum() * 0.85):
            self._load_next_card_batch()

    def _get_note_content_fields(self, note: NoteModel) -> tuple[str, str]:
        recto = ""
        verso = ""
        version = NoteVersionModel.get_or_none(note=note, is_active=True)
        if not version:
            version = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

        if version and version.content:
            try:
                data = json.loads(version.content)
                if isinstance(data, dict):
                    for k, v in data.items():
                        k_lower = str(k).lower()
                        if k_lower in ["front", "recto", "question", "text", "texte", "field_1"] and not recto:
                            recto = str(v)
                        elif k_lower in ["back", "verso", "answer", "réponse", "reponse", "extra", "field_2"] and not verso:
                            verso = str(v)
                    if not recto and len(data) > 0:
                        vals = list(data.values())
                        recto = str(vals[0]) if len(vals) > 0 else ""
                        verso = str(vals[1]) if len(vals) > 1 else ""
                else:
                    recto = str(data)
            except Exception:
                recto = version.content
        return recto, verso

    def _load_next_card_batch(self) -> None:
        if self._displayed_count >= len(self._all_notes):
            return

        next_batch = self._all_notes[self._displayed_count : self._displayed_count + self.BATCH_SIZE]

        for note in next_batch:
            row = self.card_table.rowCount()
            self.card_table.insertRow(row)

            # Checkbox
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, note)
            self.card_table.setItem(row, 0, chk)

            recto, verso = self._get_note_content_fields(note)

            # Question / Recto
            item_recto = QTableWidgetItem(str(recto)[:100] + ("..." if len(str(recto)) > 100 else ""))
            item_recto.setFont(QFont(DesignTokens.FONT_CODE, 10))
            self.card_table.setItem(row, 1, item_recto)

            # Réponse / Verso
            item_verso = QTableWidgetItem(str(verso)[:100] + ("..." if len(str(verso)) > 100 else ""))
            item_verso.setForeground(QBrush(QColor(DesignTokens.TEXT_SECONDARY)))
            self.card_table.setItem(row, 2, item_verso)

            # Deck
            folder_name = getattr(note, "_deck_name", "Par défaut")
            if folder_name == "Par défaut" and hasattr(note, "cards"):
                try:
                    cards_list = list(note.cards)
                    if cards_list and cards_list[0].deck:
                        folder_name = cards_list[0].deck.name
                except Exception as e:
                    logger.debug(f"Impossible de récupérer le nom du dossier pour la note: {e}")
            item_deck = QTableWidgetItem(folder_name)
            item_deck.setForeground(QBrush(QColor(DesignTokens.ACCENT_PRIMARY)))
            self.card_table.setItem(row, 3, item_deck)

            # Tags
            item_tags = QTableWidgetItem(str(note.tags) if note.tags else "")
            item_tags.setForeground(QBrush(QColor("#c084fc")))
            self.card_table.setItem(row, 4, item_tags)

            # Rétention
            item_ret = QTableWidgetItem("N/A")
            item_ret.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.card_table.setItem(row, 5, item_ret)

        self._displayed_count += len(next_batch)

    def refresh_data(self) -> None:
        self.card_table.setRowCount(0)
        self._all_notes = []
        self._displayed_count = 0

        self._current_note = None
        self.editor_container.setVisible(False)

        try:
            query = NoteModel.select()
            if self._active_folder_id is not None:
                from ankiforge.database.models import CardModel

                matching_note_ids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.deck == self._active_folder_id)]
                query = query.where(NoteModel.id.in_(matching_note_ids))
            if self._active_tag is not None:
                query = query.where(NoteModel.tags.contains(self._active_tag))

            self._all_notes = list(query)
            self._load_next_card_batch()

        except Exception as e:
            logger.warning("Erreur lors du rafraîchissement d'EditionView: %s", e)

    def select_note_by_id(self, note_id: int) -> None:
        try:
            for row in range(self.card_table.rowCount()):
                item = self.card_table.item(row, 0)
                if item:
                    note = item.data(Qt.ItemDataRole.UserRole)
                    if note and note.id == note_id:
                        self.card_table.setCurrentItem(item)
                        self._on_card_selected(item)
                        return

            target_note = NoteModel.get_or_none(NoteModel.id == note_id)
            if target_note:
                self._all_notes.insert(0, target_note)
                self.card_table.setRowCount(0)
                self._displayed_count = 0
                self._load_next_card_batch()
                item = self.card_table.item(0, 0)
                if item:
                    self.card_table.setCurrentItem(item)
                    self._on_card_selected(item)
        except Exception as e:
            logger.warning("Impossible de sélectionner la note %s: %s", note_id, e)

    def is_dirty(self) -> bool:
        return self._dirty


# Alias pour la rétrocompatibilité
EditionTab = EditionView

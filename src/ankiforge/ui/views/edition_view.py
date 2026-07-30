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
    QScrollArea,
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
from ankiforge.ui.components.tag_select_window import TagSelectWindow
from ankiforge.database.models import NoteTypeModel

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
        self._active_tags: list[str] = []
        self._active_model_id: Optional[int] = None
        self._current_table_fields: Optional[list[str]] = None
        self._original_content: dict[str, str] = {}

        self.dynamic_editors: dict[str, StyledTextEdit] = {}
        self.dynamic_highlighters: dict[str, KaTeXHighlighter] = {}

        self._deck_modal: Optional[DeckSelectWindow] = None
        self._tag_modal: Optional[TagSelectWindow] = None

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

        self.btn_open_folder = QPushButton("Dossier : Tous ▾")
        self.btn_open_folder.setIcon(load_phosphor_icon("folders", color=DesignTokens.TEXT_SECONDARY))
        self.btn_open_folder.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_open_folder.clicked.connect(self._show_folder_modal)
        filter_layout.addWidget(self.btn_open_folder)

        self.btn_open_model = QPushButton("Modèle : Tous ▾")
        self.btn_open_model.setIcon(load_phosphor_icon("cards", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_open_model.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.05);
            }}
        """)
        self.btn_open_model.clicked.connect(self._show_model_menu)
        filter_layout.addWidget(self.btn_open_model)

        separator = QFrame()
        separator.setFixedSize(1, 14)
        separator.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        filter_layout.addWidget(separator)

        tags_lbl = QLabel("TAGS SÉLECTIONNÉS :")
        tags_lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; text-transform: uppercase; text-decoration: none;")
        filter_layout.addWidget(tags_lbl)

        self.tags_container = QWidget()
        self.tags_layout = QHBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)
        filter_layout.addWidget(self.tags_container)

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
        self._update_table_headers()

        self.card_table.verticalHeader().setVisible(False)
        self.card_table.setShowGrid(False)
        self.card_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.card_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.card_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

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
        self.fields_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.fields_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {DesignTokens.BORDER_COLOR}; width: 4px; }}")

        # Left side: ScrollArea for fields
        self.fields_scroll_area = QScrollArea()
        self.fields_scroll_area.setWidgetResizable(True)
        self.fields_scroll_area.setStyleSheet(f"QScrollArea {{ border: none; background-color: {DesignTokens.BG_SIDEBAR}; }}")

        self.fields_container = QWidget()
        self.fields_container.setStyleSheet(f"background-color: {DesignTokens.BG_SIDEBAR};")
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(6)
        self.fields_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.fields_scroll_area.setWidget(self.fields_container)
        self.fields_splitter.addWidget(self.fields_scroll_area)

        # Right side: Live Preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_lbl = QLabel("PRÉVISUALISATION")
        preview_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        preview_layout.addWidget(preview_lbl)
        self.card_preview = CardPreviewWidget(show_header=False)
        preview_layout.addWidget(self.card_preview)

        self.fields_splitter.addWidget(preview_widget)
        self.fields_splitter.setSizes([400, 400])

        editor_layout.addWidget(self.fields_splitter)

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
        if tag_name:
            self._active_tags = [tag_name]
        else:
            self._active_tags = []
        self._rebuild_tag_chips()
        self.refresh_data()

    def _build_dynamic_editors(self, note: NoteModel, data: dict[str, str]) -> None:
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        self.dynamic_editors.clear()
        self.dynamic_highlighters.clear()
        self._original_content.clear()

        fields = ["Front", "Back"]
        if note.note_type and note.note_type.fields_schema:
            try:
                import json

                fields = json.loads(note.note_type.fields_schema)
            except Exception as e:
                import logging

                logging.warning(f"Failed to load fields_schema: {e}")

        for i, field_name in enumerate(fields):
            val = data.get(field_name, data.get(field_name.lower(), ""))

            group = QWidget()
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(0)

            btn_toggle = QPushButton(f"▼ {field_name.upper()}")
            btn_toggle.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.ACCENT_PRIMARY if i == 0 else DesignTokens.TEXT_PRIMARY};
                    text-align: left;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 6px 10px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)

            editor = StyledTextEdit()
            editor.setPlainText(val)
            editor.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {DesignTokens.BG_MAIN} !important;
                    border: 1px solid {DesignTokens.BORDER_COLOR} !important;
                    border-top: none !important;
                    border-bottom-left-radius: 4px;
                    border-bottom-right-radius: 4px;
                    color: {DesignTokens.TEXT_PRIMARY} !important;
                    font-family: '{DesignTokens.FONT_CODE}';
                    font-size: 12px;
                    padding: 10px;
                }}
            """)
            editor.textChanged.connect(self._on_text_changed)
            highlighter = KaTeXHighlighter(editor.document())

            self.dynamic_editors[field_name] = editor
            self.dynamic_highlighters[field_name] = highlighter
            self._original_content[field_name] = val

            btn_toggle.clicked.connect(lambda checked=False, e=editor, b=btn_toggle, f=field_name: self._toggle_editor(b, e, f))

            group_layout.addWidget(btn_toggle)
            group_layout.addWidget(editor)
            self.fields_layout.addWidget(group)

    def _toggle_editor(self, btn: QPushButton, editor: StyledTextEdit, field_name: str) -> None:
        if editor.isVisible():
            editor.hide()
            btn.setText(f"▶ {field_name.upper()}")
        else:
            editor.show()
            btn.setText(f"▼ {field_name.upper()}")

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

        data = self._get_note_content_dynamic(note)
        self._build_dynamic_editors(note, data)

        self._update_preview()
        self._dirty = False

    def _on_text_changed(self) -> None:
        is_modified = False
        for field_name, editor in self.dynamic_editors.items():
            if editor.toPlainText() != self._original_content.get(field_name, ""):
                is_modified = True
                break

        self._dirty = is_modified
        self._update_preview()

    def _update_preview(self) -> None:
        fields_dict: dict[str, str] = {}
        for field_name, editor in self.dynamic_editors.items():
            fields_dict[field_name] = editor.toPlainText()

        note_type = getattr(self._current_note, "note_type", None) if self._current_note else None

        # Fallbacks for old basic templates referencing Front/Back
        if "Front" not in fields_dict and len(fields_dict) > 0:
            fields_dict["Front"] = list(fields_dict.values())[0]
        if "Back" not in fields_dict and len(fields_dict) > 1:
            fields_dict["Back"] = list(fields_dict.values())[1]

        override_templates = None
        if not note_type or not getattr(note_type, "templates", None):
            override_templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]

        self.card_preview.update_preview(
            note_type=note_type,
            fields_dict=fields_dict,
            override_templates=override_templates,
        )

    def _insert_format(self, prefix: str, suffix: str) -> None:
        for editor in self.dynamic_editors.values():
            if editor.hasFocus():
                cursor = editor.textCursor()
                selected = cursor.selectedText()
                cursor.insertText(f"{prefix}{selected}{suffix}")
                return

    def _open_history_modal(self) -> None:
        if self._current_note:
            modal = HistoryModal(self._current_note, self)
            modal.exec()

    @Slot()
    def _show_folder_modal(self) -> None:
        try:
            if self._deck_modal and self._deck_modal.isVisible():
                self._deck_modal.raise_()
                self._deck_modal.activateWindow()
                return
        except RuntimeError:
            self._deck_modal = None

        self._deck_modal = DeckSelectWindow(parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected_from_modal)
        self._deck_modal.show()

    @Slot(int, str)
    def _on_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
        if deck_id == -1:
            self.btn_open_folder.setText("Dossier : Tous ▾")
            self.btn_open_folder.setIcon(load_phosphor_icon("folders", color=DesignTokens.TEXT_SECONDARY))
            self.btn_open_folder.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.TEXT_SECONDARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
            self._active_folder_id = None
        else:
            self.btn_open_folder.setText(f"Dossier : {deck_name} ▾")
            self.btn_open_folder.setIcon(load_phosphor_icon("folder", color=DesignTokens.ACCENT_PRIMARY))
            self.btn_open_folder.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(99, 102, 241, 0.15);
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            self._active_folder_id = deck_id

        # Reload cards to apply filter
        self.refresh_data()

    @Slot()
    def _show_tag_modal(self) -> None:
        try:
            if self._tag_modal and self._tag_modal.isVisible():
                self._tag_modal.raise_()
                self._tag_modal.activateWindow()
                return
        except RuntimeError:
            self._tag_modal = None

        current_tags = set()
        import json

        for note in self._all_notes:
            if note.tags:
                try:
                    tags = json.loads(str(note.tags))
                    if isinstance(tags, list):
                        for t in tags:
                            if t.strip():
                                current_tags.add(t.strip())
                except Exception as e:
                    import logging

                    logging.warning(f"Failed to parse tags: {e}")

        self._tag_modal = TagSelectWindow(allowed_tags=current_tags, parent=self)
        self._tag_modal.tag_selected.connect(self._on_tag_selected_from_modal)
        self._tag_modal.show()

    @Slot(str)
    def _on_tag_selected_from_modal(self, tag: str) -> None:
        if tag not in self._active_tags:
            self._active_tags.append(tag)
            self._rebuild_tag_chips()
            show_toast(self, f"Tag {tag} ajouté au filtre")
            self.refresh_data()

    def _rebuild_tag_chips(self) -> None:
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        for tag in self._active_tags:
            chip = QPushButton(f"{tag}")
            chip.setIcon(load_phosphor_icon("x", color="#c084fc"))
            chip.setStyleSheet("""
                QPushButton {
                    background-color: rgba(192, 132, 252, 0.15);
                    border: 1px solid #c084fc;
                    border-radius: 12px;
                    padding: 2px 10px 2px 8px;
                    min-height: 20px;
                    font-size: 11px;
                    font-weight: bold;
                    color: #c084fc;
                }
                QPushButton:hover {
                    background-color: rgba(192, 132, 252, 0.3);
                }
            """)
            chip.clicked.connect(lambda checked=False, t=tag: self._remove_tag_filter(t))
            self.tags_layout.addWidget(chip)

    def _remove_tag_filter(self, tag: str) -> None:
        if tag in self._active_tags:
            self._active_tags.remove(tag)
            self._rebuild_tag_chips()
            self.refresh_data()

    @Slot()
    def _show_model_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; }}
            QMenu::item {{ color: {DesignTokens.TEXT_PRIMARY}; padding: 6px 24px; font-size: 12px; }}
            QMenu::item:selected {{ background-color: {DesignTokens.BG_HOVER}; }}
        """)

        all_action = menu.addAction("Tous les modèles")
        all_action.triggered.connect(lambda: self._on_model_selected(None, "Tous les modèles"))

        menu.addSeparator()

        try:
            for m in NoteTypeModel.select():
                action = menu.addAction(m.name)
                action.triggered.connect(lambda checked=False, mid=m.id, mname=m.name: self._on_model_selected(mid, mname))
        except Exception as e:
            logger.warning(f"Erreur chargement modèles: {e}")

        menu.exec(self.btn_open_model.mapToGlobal(self.btn_open_model.rect().bottomLeft()))

    def _on_model_selected(self, model_id: Optional[int], model_name: str) -> None:
        self._active_model_id = model_id
        if model_id is None:
            self.btn_open_model.setText("Modèle : Tous ▾")
            self.btn_open_model.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.TEXT_SECONDARY};
                }}
            """)
        else:
            self.btn_open_model.setText(f"Modèle : {model_name} ▾")
            self.btn_open_model.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(99, 102, 241, 0.15);
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                    color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
        self._update_table_headers()
        self.refresh_data()

    def _update_table_headers(self) -> None:
        self.card_table.clear()
        if self._active_model_id:
            try:
                model = NoteTypeModel.get_or_none(NoteTypeModel.id == self._active_model_id)
                if model and model.fields_schema:
                    import json

                    fields = json.loads(model.fields_schema)
                    current_fields = fields[:3]
                    self._current_table_fields = current_fields
                    headers = [""] + current_fields + ["Deck", "Tags", "Rétention"]
                    self.card_table.setColumnCount(len(headers))
                    self.card_table.setHorizontalHeaderLabels(headers)
                    self.card_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
                    for i in range(1, len(current_fields) + 1):
                        self.card_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

                    deck_col = len(current_fields) + 1
                    self.card_table.setColumnWidth(0, 36)
                    self.card_table.setColumnWidth(deck_col, 140)
                    self.card_table.setColumnWidth(deck_col + 1, 140)
                    self.card_table.setColumnWidth(deck_col + 2, 90)
                    return
            except Exception as e:
                import logging

                logging.warning(f"An error occurred: {e}")

        # Default (Mixed / All Models)
        self._current_table_fields = None
        headers = ["", "Champ 1 (Tri)", "Autres champs", "Modèle", "Deck", "Tags", "Rétention"]
        self.card_table.setColumnCount(7)
        self.card_table.setHorizontalHeaderLabels(headers)
        self.card_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.card_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.card_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.card_table.setColumnWidth(0, 36)
        self.card_table.setColumnWidth(3, 100)  # Modèle
        self.card_table.setColumnWidth(4, 140)
        self.card_table.setColumnWidth(5, 140)
        self.card_table.setColumnWidth(6, 90)

    @Slot()
    def _run_linter(self) -> None:
        if self._current_note:
            self.open_linter_dialog([self._current_note.id])

    @Slot()
    def _save_card(self) -> None:
        if not self._current_note:
            return

        try:
            note_id = self._current_note.id
            new_content = {field: editor.toPlainText() for field, editor in self.dynamic_editors.items()}
            self._current_note.add_version(new_content, source="manual")
            self._original_content = new_content.copy()
            self._dirty = False

            # Update the table row without closing the editor
            for row in range(self.card_table.rowCount()):
                item = self.card_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == note_id:
                    vals = list(new_content.values())
                    recto = vals[0] if vals else ""
                    verso = " | ".join(vals[1:]) if len(vals) > 1 else ""

                    if self._current_table_fields:
                        if len(self._current_table_fields) > 0:
                            item_recto = self.card_table.item(row, 1)
                            if item_recto:
                                item_recto.setText(recto[:100] + ("..." if len(recto) > 100 else ""))
                        if len(self._current_table_fields) > 1:
                            item_verso = self.card_table.item(row, 2)
                            if item_verso:
                                item_verso.setText(verso[:100] + ("..." if len(verso) > 100 else ""))
                    break

            show_toast(self, f"Carte #{note_id} sauvegardée avec succès.")
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

    def _get_note_content_dynamic(self, note: NoteModel) -> dict[str, str]:
        data = {}
        version = NoteVersionModel.get_or_none(note=note, is_active=True)
        if not version:
            version = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

        if version and version.content:
            try:
                parsed = json.loads(version.content)
                if isinstance(parsed, dict):
                    data = {str(k): str(v) for k, v in parsed.items()}
            except Exception as e:
                import logging

                logging.warning(f"An error occurred: {e}")
        return data

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

            data = self._get_note_content_dynamic(note)

            col_offset = 1
            if self._current_table_fields:
                for idx, field in enumerate(self._current_table_fields):
                    val = data.get(field, "")
                    item = QTableWidgetItem(val[:100] + ("..." if len(val) > 100 else ""))
                    if idx == 0:
                        item.setFont(QFont(DesignTokens.FONT_CODE, 10))
                    else:
                        item.setForeground(QBrush(QColor(DesignTokens.TEXT_SECONDARY)))
                    self.card_table.setItem(row, col_offset + idx, item)

                col_offset += len(self._current_table_fields)
            else:
                vals = list(data.values())
                recto = vals[0] if vals else ""
                verso = " | ".join(vals[1:]) if len(vals) > 1 else ""

                item_recto = QTableWidgetItem(recto[:100] + ("..." if len(recto) > 100 else ""))
                item_recto.setFont(QFont(DesignTokens.FONT_CODE, 10))
                self.card_table.setItem(row, 1, item_recto)

                item_verso = QTableWidgetItem(verso[:100] + ("..." if len(verso) > 100 else ""))
                item_verso.setForeground(QBrush(QColor(DesignTokens.TEXT_SECONDARY)))
                self.card_table.setItem(row, 2, item_verso)

                model_name = note.note_type.name if note.note_type else "Inconnu"
                item_model = QTableWidgetItem(model_name)
                item_model.setForeground(QBrush(QColor(DesignTokens.TEXT_MUTED)))
                self.card_table.setItem(row, 3, item_model)

                col_offset = 4

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
            self.card_table.setItem(row, col_offset, item_deck)

            # Tags
            item_tags = QTableWidgetItem(str(note.tags) if note.tags else "")
            item_tags.setForeground(QBrush(QColor("#c084fc")))
            self.card_table.setItem(row, col_offset + 1, item_tags)

            # Rétention
            item_ret = QTableWidgetItem("N/A")
            item_ret.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.card_table.setItem(row, col_offset + 2, item_ret)

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
                from ankiforge.database.models import CardModel, DeckModel

                active_deck = DeckModel.get_or_none(DeckModel.id == self._active_folder_id)
                if active_deck:
                    deck_name = active_deck.name
                    descendant_decks = DeckModel.select(DeckModel.id).where((DeckModel.id == active_deck.id) | (DeckModel.name.startswith(f"{deck_name}::")))
                    deck_ids = [d.id for d in descendant_decks]
                    matching_note_ids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.deck.in_(deck_ids))]
                    query = query.where(NoteModel.id.in_(matching_note_ids))
            for tag in self._active_tags:
                query = query.where(NoteModel.tags.contains(tag))
            if self._active_model_id is not None:
                query = query.where(NoteModel.note_type == self._active_model_id)

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

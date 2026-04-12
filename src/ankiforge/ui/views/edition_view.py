import json
import logging
import os
import re
from typing import Optional, Any, cast

import qtawesome
from PySide6.QtCore import Qt, QUrl, Slot, QTimer, QSettings, QThread, Signal, QPoint
from PySide6.QtGui import QColor, QAction
from PySide6.QtWidgets import (
    QLabel,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QComboBox,
    QScrollArea,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QInputDialog,
    QFrame,
    QProgressDialog,
)

from ankiforge.database.models import (
    DeckModel,
    CardModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
    IgnoredDuplicateModel,
    LLMConfigModel,
)
from ankiforge.services.ai.base import MockProvider, LLMProvider
from ankiforge.services.ai.flexible_service import OllamaProvider, GroqProvider, OpenAICompatibleProvider
from ankiforge.services.ai.gemini_service import GeminiService
from ankiforge.services.ai.utils import parse_ai_json_response
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.store_manager import StoreManager
from ankiforge.ui.components.components import HeaderLabel, ActionButton, PrimaryButton, DangerButton, RoundedPanel
from ankiforge.ui.theme import is_dark_mode
from ankiforge.ui.widgets.batch_edit_dialog import BatchEditDialog
from ankiforge.ui.widgets.cloze_gestion import is_template_cloze
from ankiforge.ui.widgets.drop_image_text_edit import DropImageTextEdit
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog
from ankiforge.utils.anki_renderer import render_anki_card, get_max_cloze_index
from ankiforge.utils.c_bridge import get_similarity
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)


def strip_html(text: Optional[str]) -> str:
    """Retire toutes les balises HTML d'une chaîne pour l'affichage brut."""
    if not text:
        return ""
    clean = re.compile("<.*?>")
    return re.sub(clean, "", text).replace("&nbsp;", " ").replace("\n", " ").strip()


class SortableTableItem(QTableWidgetItem):
    """Un élément de tableau qui sait trier les nombres (et les 'vX') intelligemment."""

    def __lt__(self, other) -> bool:
        # On nettoie le texte (ex: on transforme "v10" en "10")
        text_self = self.text().lower().replace("v", "").strip()
        text_other = other.text().lower().replace("v", "").strip()

        try:
            # On essaie de comparer mathématiquement (10 > 2)
            return float(text_self) < float(text_other)
        except ValueError:
            # Si c'est du vrai texte (ex: "Maths" vs "Physique"), on fait un tri alphabétique
            return self.text().lower() < other.text().lower()


class ImportThread(QThread):
    """Gère l'importation lourde d'un paquet Anki en arrière-plan."""

    progress = Signal(str)
    finished_signal = Signal()
    error_signal = Signal(str)

    def __init__(self, store_manager, path: str):
        super().__init__()
        self.store_manager = store_manager
        self.path = path

    def run(self):
        try:
            # On passe le signal .emit() comme fonction de callback !
            self.store_manager.store_collection(self.path, progress_callback=self.progress.emit)
            self.finished_signal.emit()
        except Exception as e:
            logger.exception("Erreur lors de l'importation d'un paquet Anki :")
            self.error_signal.emit(str(e))


class BatchEditThread(QThread):
    progress = Signal(str)
    finished_signal = Signal(int)  # Nombre de cartes modifiées
    error_signal = Signal(str)
    cancelled = Signal()

    def __init__(self, ai_provider: Any, note_ids: list[int], user_prompt: str, chunk_size: int):
        super().__init__()
        self.ai_provider = ai_provider
        self.note_ids = note_ids
        self.user_prompt = user_prompt
        self.chunk_size = chunk_size
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            total_processed = 0

            system_contract = (
                "Tu es un assistant de traitement de base de données.\n"
                "Voici ton instruction principale :\n"
                f"--- {self.user_prompt} ---\n\n"
                "RÈGLE ABSOLUE : Tu vas recevoir un tableau JSON d'objets.\n"
                "Tu dois renvoyer EXACTEMENT la même structure (un tableau JSON).\n"
                "Chaque objet possède une clé 'note_id' que tu DOIS impérativement conserver intacte.\n"
                "Ne rajoute AUCUN texte autour de ta réponse, uniquement du JSON valide."
            )

            for i in range(0, len(self.note_ids), self.chunk_size):
                if self._is_cancelled:
                    logger.info("Traitement par lots AI annulé par l'utilisateur.")
                    self.cancelled.emit()
                    return

                chunk_ids = self.note_ids[i : i + self.chunk_size]
                self.progress.emit(f"Traitement du lot {i // self.chunk_size + 1} (Cartes {i + 1} à {min(i + self.chunk_size, len(self.note_ids))})...")

                payload = []
                for nid in chunk_ids:
                    note = NoteModel.get_by_id(nid)
                    active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                    if active_version:
                        content = json.loads(active_version.content)
                        content["note_id"] = note.id
                        payload.append(content)

                if not payload:
                    continue

                input_json = json.dumps(payload, ensure_ascii=False, indent=2)
                raw_response = self.ai_provider.generate(system_prompt=system_contract, user_prompt=input_json)

                try:
                    modified_notes = parse_ai_json_response(raw_response)
                    if not isinstance(modified_notes, list):
                        raise ValueError("L'IA n'a pas renvoyé un tableau (list) JSON.")

                    with db.atomic():
                        for modified_note in modified_notes:
                            note_id = modified_note.pop("note_id", None)
                            if not note_id:
                                continue

                            db_note = NoteModel.get_by_id(note_id)
                            active_version = NoteVersionModel.get_or_none(note=db_note, is_active=True)

                            if active_version:
                                old_content = json.loads(active_version.content)
                                if old_content == modified_note:
                                    continue  # On ignore si l'IA n'a rien changé !

                            db_note.add_version(modified_note, source="ai_batch")
                            db_note.status = "pending"
                            db_note.save()
                            total_processed += 1

                except (ValueError, TypeError) as e:
                    logger.exception("Erreur de parsing lors du batch edit :")
                    self.error_signal.emit(f"Erreur de parsing sur un lot : {e}\nRéponse brute : {raw_response[:100]}...")
                    return

            if not self._is_cancelled:
                self.finished_signal.emit(total_processed)

        except (ValueError, TypeError, RuntimeError) as e:
            logger.exception("Erreur critique lors du batch edit :")
            self.error_signal.emit(f"Erreur critique du Batch Edit : {e}")


class EditionTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.batch_thread: BatchEditThread | None = None
        self.creation_model_cb: QComboBox | None = None
        self.import_thread: ImportThread | None = None
        self.progress_dialog: QProgressDialog | None = None
        self.settings = QSettings("AnkiForgeOrg", "AnkiForge")
        self.store = StoreManager()
        self.current_deck_id: Optional[int] = None
        self.current_note: Optional[NoteModel] = None
        self.current_tag_filter: Optional[str] = None
        self.field_editors: dict[str, QTextEdit] = {}
        self.is_creating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # --- 1. EN-TÊTE ---
        header_layout = QHBoxLayout()
        titre = HeaderLabel("Navigateur de Cartes & Notes")

        self.btn_load_col = ActionButton("fa5s.folder-open", " Importer un paquet")
        self.btn_load_col.clicked.connect(self.load_cards)

        self.btn_export = PrimaryButton(qtawesome.icon("fa5s.box", color="white"), " Exporter vers Anki")
        self.btn_export.clicked.connect(self.export_selected_deck)
        self.btn_export.setEnabled(False)

        header_layout.addWidget(titre)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_load_col)
        header_layout.addWidget(self.btn_export)
        layout.addLayout(header_layout)

        # --- 2. LAYOUT PRINCIPAL ---
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(10)

        # ==========================================
        # PANNEAU GAUCHE : Explorateur (Paquets & Tags)
        # ==========================================
        nav_panel = RoundedPanel()
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(15, 15, 15, 15)
        nav_layout.setSpacing(10)

        lbl_nav = QLabel("EXPLORATEUR")
        lbl_nav.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        nav_layout.addWidget(lbl_nav)

        self.deck_tree = QTreeWidget()
        self.deck_tree.setHeaderHidden(True)
        self.deck_tree.setFrameShape(QFrame.Shape.NoFrame)
        self.deck_tree.setStyleSheet("background: transparent;")
        self.deck_tree.itemClicked.connect(self.on_deck_selected)
        nav_layout.addWidget(self.deck_tree)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        # On utilise ta palette pour que ça s'adapte au mode sombre/clair automatiquement
        separator.setStyleSheet("""
            background-color: palette(alternate-base); 
            max-height: 1px; 
            border: none; 
            margin-top: 8px; 
            margin-bottom: 8px;
        """)
        nav_layout.addWidget(separator)

        lbl_tags = QLabel("FILTRES (TAGS)")
        lbl_tags.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-top: 10px;")
        nav_layout.addWidget(lbl_tags)

        self.tag_list = QListWidget()
        self.tag_list.setFrameShape(QFrame.Shape.NoFrame)
        self.tag_list.setStyleSheet("background: transparent;")
        self.tag_list.itemClicked.connect(self.on_tag_selected)
        self.tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tag_list.customContextMenuRequested.connect(self.show_tag_context_menu)
        nav_layout.addWidget(self.tag_list)

        main_splitter.addWidget(nav_panel)

        # ==========================================
        # PANNEAU DROIT : Contenu Principal
        # ==========================================
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(10)

        # --- 2A. Le Tableau des données ---
        table_panel = RoundedPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(15, 15, 15, 15)

        toolbar_layout = QHBoxLayout()
        lbl_mode = QLabel("MODE D'AFFICHAGE :")
        lbl_mode.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; letter-spacing: 1px;")
        toolbar_layout.addWidget(lbl_mode)
        self.view_mode_cb = QComboBox()
        self.view_mode_cb.addItems(["Vue : Cartes (Métadonnées)", "Vue : Notes (Texte)", "Vue : Quarantaine (À valider)"])
        self.view_mode_cb.currentIndexChanged.connect(self.refresh_table)
        toolbar_layout.addWidget(self.view_mode_cb)
        toolbar_layout.addStretch()

        self.btn_approve = PrimaryButton(qtawesome.icon("fa5s.check", color="white"), " Approuver")
        self.btn_approve.clicked.connect(self.approve_selected_notes)
        self.btn_approve.setVisible(False)

        self.btn_reject = DangerButton(qtawesome.icon("fa5s.trash", color="white"), " Rejeter")
        self.btn_reject.clicked.connect(self.reject_selected_notes)
        self.btn_reject.setVisible(False)

        self.btn_new_note = PrimaryButton(qtawesome.icon("fa5s.plus", color="white"), " Nouvelle Note")
        self.btn_new_note.clicked.connect(self.enter_creation_mode)
        self.btn_new_note.setEnabled(False)

        self.btn_scan_dupes = ActionButton("fa5s.search", " Traquer les doublons")
        self.btn_scan_dupes.clicked.connect(self.scan_for_duplicates)

        self.btn_batch_ai = ActionButton("fa5s.magic", " Modification IA")
        self.btn_batch_ai.clicked.connect(self.open_batch_edit_dialog)
        self.btn_batch_ai.setEnabled(False)  # On le grise tant qu'aucune ligne n'est sélectionnée

        toolbar_layout.addWidget(self.btn_new_note)
        toolbar_layout.addWidget(self.btn_batch_ai)
        toolbar_layout.addWidget(self.btn_scan_dupes)
        toolbar_layout.addWidget(self.btn_approve)
        toolbar_layout.addWidget(self.btn_reject)

        table_layout.addLayout(toolbar_layout)

        self.data_table = QTableWidget()
        self.data_table.setFrameShape(QFrame.Shape.NoFrame)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.data_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.horizontalHeader().setStretchLastSection(True)
        self.data_table.horizontalHeader().setSectionsMovable(True)
        self.data_table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.data_table.horizontalHeader().customContextMenuRequested.connect(self.show_header_menu)
        self.data_table.horizontalHeader().sectionResized.connect(self.save_table_state)
        self.data_table.horizontalHeader().sectionMoved.connect(self.save_table_state)
        self.data_table.itemSelectionChanged.connect(self.on_row_selected)
        self.data_table.setSortingEnabled(True)

        table_layout.addWidget(self.data_table)
        right_splitter.addWidget(table_panel)

        # --- 2B. Éditeur et Aperçu ---
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setHandleWidth(10)

        # L'Éditeur de champs (Gauche)
        editor_panel = RoundedPanel()
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(15, 15, 15, 15)

        self.details_scroll = QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.details_widget = QWidget()
        self.details_widget.setStyleSheet("background: transparent;")
        self.details_layout = QVBoxLayout(self.details_widget)
        self.details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.details_scroll.setWidget(self.details_widget)

        editor_layout.addWidget(self.details_scroll)

        buttons_layout = QHBoxLayout()
        self.btn_history = ActionButton("fa5s.history", " Historique")
        self.btn_history.clicked.connect(self.show_version_history)
        self.btn_history.setEnabled(False)

        self.btn_save_edits = PrimaryButton(qtawesome.icon("fa5s.save", color="white"), " Sauvegarder modifications")
        self.btn_save_edits.clicked.connect(self.save_note_edits)
        self.btn_save_edits.setEnabled(False)

        buttons_layout.addWidget(self.btn_history)
        buttons_layout.addStretch()  # Pousse le bouton sauvegarder tout à droite
        buttons_layout.addWidget(self.btn_save_edits)

        editor_layout.addLayout(buttons_layout)
        bottom_splitter.addWidget(editor_panel)

        # L'Aperçu WebEngine (Droite)
        preview_panel = RoundedPanel()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)  # Marge aérée

        controls_layout = QHBoxLayout()

        lbl_preview = QLabel("Prévisualisation :")
        lbl_preview.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; text-transform: uppercase; letter-spacing: 1px;")
        controls_layout.addWidget(lbl_preview)

        self.preview_card_selector = QComboBox()
        self.preview_card_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.preview_card_selector.setMinimumWidth(130)
        self.preview_card_selector.currentIndexChanged.connect(self.update_preview)

        self.preview_side_selector = QComboBox()
        self.preview_side_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.preview_side_selector.setMinimumWidth(130)
        self.preview_side_selector.addItems(["Voir Recto", "Voir Verso"])
        self.preview_side_selector.currentIndexChanged.connect(self.update_preview)

        controls_layout.addWidget(self.preview_card_selector)
        controls_layout.addWidget(self.preview_side_selector)
        controls_layout.addStretch()  # Pousse les menus vers la gauche

        preview_layout.addLayout(controls_layout)

        self.web_view = SafeWebEngineView()
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

        preview_layout.addWidget(self.web_view)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(500)
        self.preview_timer.timeout.connect(self.update_preview)

        bottom_splitter.addWidget(preview_panel)
        bottom_splitter.setSizes([350, 450])
        right_splitter.addWidget(bottom_splitter)
        right_splitter.setSizes([300, 300])

        main_splitter.addWidget(nav_panel)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([200, 800])

        layout.addWidget(main_splitter)
        self.refresh_deck_tree()

    @Slot()
    def refresh_data(self) -> None:
        """Méthode standardisée appelée par la MainWindow au changement d'onglet."""
        self.refresh_deck_tree()
        self.refresh_tags_list()
        # On rafraîchit la table si un paquet est déjà sélectionné
        if self.current_deck_id:
            self.refresh_table()

    @Slot()
    def load_cards(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir document", "", "Documents Anki (*.colpkg *.txt *.apkg)")
        if path:
            self.btn_load_col.setEnabled(False)
            # Création d'une boîte de dialogue pour afficher les logs en direct
            self.progress_dialog = QProgressDialog("Préparation de l'importation...", "", 0, 0, self)
            self.progress_dialog.setWindowTitle("Importation en cours")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setMinimumDuration(0)  # Affichage immédiat
            self.progress_dialog.show()

            # Lancement du travail en arrière-plan
            self.import_thread = ImportThread(self.store, path)
            self.import_thread.progress.connect(self.progress_dialog.setLabelText)
            self.import_thread.finished_signal.connect(self._on_import_success)
            self.import_thread.error_signal.connect(self._on_import_error)
            self.import_thread.start()

    @Slot()
    def _on_import_success(self) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()

        logger.info("Paquet Anki importé avec succès.")
        show_toast(self, "Paquet importé avec succès !")
        self.refresh_deck_tree()
        self.btn_load_col.setEnabled(True)

    @Slot(str)
    def _on_import_error(self, error_msg: str) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()

        logger.error(f"Erreur lors de l'importation : {error_msg}")
        QMessageBox.critical(self, "Erreur d'importation", f"Erreur : {error_msg}")
        self.btn_load_col.setEnabled(True)

    @Slot()
    def export_selected_deck(self) -> None:
        if not self.current_deck_id:
            return

        deck = DeckModel.get_by_id(self.current_deck_id)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Exportation Intelligente")
        msg_box.setText(f"Que souhaitez-vous exporter depuis le paquet '{deck.name}' ?")

        btn_new = msg_box.addButton("🚀 Nouvelles cartes uniquement", QMessageBox.ButtonRole.AcceptRole)
        _ = msg_box.addButton("📦 Tout le paquet (Écrase)", QMessageBox.ButtonRole.RejectRole)
        btn_cancel = msg_box.addButton("Annuler", QMessageBox.ButtonRole.DestructiveRole)

        msg_box.exec()

        if msg_box.clickedButton() == btn_cancel:
            return

        export_only_new = msg_box.clickedButton() == btn_new
        default_name = f"{deck.name.replace('::', '_')}.apkg"

        path, _ = QFileDialog.getSaveFileName(self, "Exporter vers Anki", default_name, "Anki Deck (*.apkg)")
        if path:
            try:
                exporter = ExportManager()
                # ✅ CORRECTION : On utilise enfin la variable `export_only_new` !
                exporter.export_deck(self.current_deck_id, path, export_only_new=export_only_new)
                logger.info(f"Paquet {self.current_deck_id} exporté vers {path}.")
                show_toast(self, "Exportation terminée !")
            except Exception as e:
                logger.exception(f"Erreur lors de l'exportation du paquet {self.current_deck_id} :")
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'exportation :\n{e}")

    def refresh_deck_tree(self) -> None:
        self.deck_tree.clear()
        try:
            decks = DeckModel.select().order_by(DeckModel.name)
            tree_nodes: dict[str, QTreeWidgetItem] = {}
            for deck in decks:
                parts = deck.name.split("::")
                display_name = parts[-1]
                if len(parts) == 1:
                    item = QTreeWidgetItem(self.deck_tree, [f"📁 {display_name}"])
                else:
                    parent_name = "::".join(parts[:-1])
                    parent_item = tree_nodes.get(parent_name, self.deck_tree)
                    item = QTreeWidgetItem(parent_item, [f"📂 {display_name}"])

                item.setData(0, Qt.ItemDataRole.UserRole, deck.id)
                tree_nodes[deck.name] = item
            self.deck_tree.expandAll()
        except (ValueError, AttributeError):
            pass

    @Slot(QTreeWidgetItem, int)
    def on_deck_selected(self, item: QTreeWidgetItem, column: int) -> None:
        if self.is_creating:
            reply = QMessageBox.question(
                self,
                "Création en cours",
                "Changer de paquet annulera la création en cours. Continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return
            self._exit_creation_mode(refresh=False)

        self.current_deck_id = item.data(0, Qt.ItemDataRole.UserRole)
        self.btn_export.setEnabled(True)
        self.refresh_table()
        self.refresh_tags_list()

    def show_header_menu(self, pos: QPoint) -> None:
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
            action.toggled.connect(lambda checked, col=i: self.toggle_column_visibility(col, checked))
            menu.addAction(action)
        menu.exec(self.data_table.horizontalHeader().mapToGlobal(pos))

    def toggle_column_visibility(self, col: int, visible: bool) -> None:
        self.data_table.setColumnHidden(col, not visible)
        self.save_table_state()

    def get_table_state_key(self) -> str:
        mode = self.view_mode_cb.currentText()
        if mode == "Vue : Cartes (Métadonnées)":
            return "EditionView/TableState_Cards"
        else:
            return "EditionView/TableState_Notes"

    def save_table_state(self, *args) -> None:
        if self.data_table.columnCount() == 0:
            return
        state = self.data_table.horizontalHeader().saveState()
        self.settings.setValue(self.get_table_state_key(), state)

    def restore_table_state(self) -> None:
        state = self.settings.value(self.get_table_state_key())
        if state:
            self.data_table.horizontalHeader().restoreState(state)

    def refresh_table(self) -> None:
        if not self.current_deck_id:
            return

        self.data_table.setSortingEnabled(False)
        self.data_table.setRowCount(0)
        self.btn_save_edits.setEnabled(False)
        self.current_note = None

        mode = self.view_mode_cb.currentText()
        is_quarantine = mode == "Vue : Quarantaine (À valider)"

        self.btn_approve.setVisible(is_quarantine)
        self.btn_reject.setVisible(is_quarantine)
        self.btn_new_note.setEnabled(not is_quarantine and self.current_deck_id is not None)

        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        try:
            selected_deck = DeckModel.get_by_id(self.current_deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

            # 👇 LA SÉCURITÉ ABSOLUE : Le filtre s'adapte dynamiquement 👇
            if is_quarantine:
                # En quarantaine, on NE veut QUE les brouillons IA ('pending')
                status_condition = NoteModel.status == "pending"
            else:
                # Dans les autres vues, on veut TOUT LE RESTE ('new', 'imported', 'review'...)
                status_condition = NoteModel.status != "pending"

            if self.current_tag_filter:
                status_condition = status_condition & (NoteModel.tags.contains(f'"{self.current_tag_filter}"'))

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
                    if item is not None and card.note is not None:
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

                    item = self.data_table.item(row_index, 0)
                    if item is not None:
                        item.setData(Qt.ItemDataRole.UserRole, note.id)
                    self.data_table.setItem(row_index, 1, SortableTableItem(verso))
                    self.data_table.setItem(row_index, 2, SortableTableItem(nt_name))
                    self.data_table.setItem(row_index, 3, SortableTableItem(", ".join(tags_list)))

                    v_num = active_version.version_number if active_version else 1
                    item_version = SortableTableItem(f"v{v_num}")
                    item_version.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.data_table.setItem(row_index, 4, item_version)
                    item = self.data_table.item(row_index, 0)
                    if item is not None:
                        item.setData(Qt.ItemDataRole.UserRole, note.id)

            self.data_table.setSortingEnabled(True)
            self.restore_table_state()
        except Exception as e:
            logger.exception("Erreur lors du rafraîchissement du tableau de données :")
            QMessageBox.critical(self, "Erreur d'affichage", f"Impossible de charger le tableau :\n{e}")

    def on_row_selected(self) -> None:
        selected_items = self.data_table.selectedItems()
        self.btn_batch_ai.setEnabled(bool(selected_items))
        if not selected_items:
            return

        if self.is_creating:
            reply = QMessageBox.question(
                self,
                "Création en cours",
                "Vous avez une création de note en cours. Voulez-vous vraiment annuler ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                self.data_table.blockSignals(True)
                self.data_table.clearSelection()
                self.data_table.blockSignals(False)
                return
            else:
                self._exit_creation_mode(refresh=False)

        if self.view_mode_cb.currentText() == "Vue : Quarantaine (À valider)":
            self.btn_approve.setEnabled(True)
            self.btn_reject.setEnabled(True)

        note_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if note_id is None:
            return

        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        self.field_editors.clear()

        try:
            self.current_note = NoteModel.get_by_id(note_id)
            if self.current_note is None or self.current_note.note_type is None:
                return
            self.btn_save_edits.setEnabled(True)
            self.btn_history.setEnabled(True)

            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}

            lbl_title = QLabel(f"<b>Édition (Modèle : {self.current_note.note_type.name})</b>")
            lbl_title.setStyleSheet("font-size: 16px; margin-bottom: 5px;")
            self.details_layout.addWidget(lbl_title)

            for field_name, field_value in content_dict.items():
                lbl = QLabel(field_name)
                lbl.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; margin-top: 15px; margin-bottom: 5px;")
                text_edit = DropImageTextEdit()

                clean_value = field_value.replace("<br>", "\n") if field_value else ""
                text_edit.setPlainText(clean_value)
                text_edit.setMinimumHeight(60)
                text_edit.textChanged.connect(self._on_text_changed)

                self.field_editors[field_name] = text_edit
                self.details_layout.addWidget(lbl)
                self.details_layout.addWidget(text_edit)

            self.update_preview()
        except Exception as e:
            logger.exception("Erreur lors de la sélection d'une ligne :")
            self.details_layout.addWidget(QLabel(f"Erreur : {e}"))

    @Slot()
    def enter_creation_mode(self) -> None:
        if not self.current_deck_id:
            return

        # Annuler la sélection du tableau sans déclencher on_row_selected immédiatement pour éviter des conflits
        self.data_table.blockSignals(True)
        self.data_table.clearSelection()
        self.data_table.blockSignals(False)

        self.is_creating = True
        self.current_note = None

        self.btn_save_edits.setText(" ✨ Créer la note")
        self.btn_save_edits.setEnabled(True)
        self.btn_history.setVisible(False)

        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        self.field_editors.clear()

        lbl_title = QLabel("<b>Création de Note</b>")
        lbl_title.setStyleSheet("font-size: 16px; margin-bottom: 5px;")
        self.details_layout.addWidget(lbl_title)

        # Sélecteur de modèle
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Modèle :"))
        self.creation_model_cb = QComboBox()
        models = NoteTypeModel.select()
        for m in models:
            self.creation_model_cb.addItem(m.name, m.id)

        if self.creation_model_cb is None:
            return None
        self.creation_model_cb.currentIndexChanged.connect(self.render_creation_fields)
        model_layout.addWidget(self.creation_model_cb)
        model_layout.addStretch()

        # On encapsule dans un widget pour l'ajouter au QVBoxLayout
        model_widget = QWidget()
        model_widget.setLayout(model_layout)
        self.details_layout.addWidget(model_widget)

        # On appelle le rendu initial
        self.render_creation_fields()

    @Slot()
    def render_creation_fields(self) -> None:
        if not self.is_creating:
            return

        if self.creation_model_cb is None:
            return
        model_id = self.creation_model_cb.currentData()
        if not model_id:
            return

        note_type = NoteTypeModel.get_by_id(model_id)
        fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []
        if note_type is None:
            return
            # On nettoie les anciens champs (tout sauf le titre et le combobox)
        while self.details_layout.count() > 2:
            child = self.details_layout.takeAt(2)
            if not child:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        self.field_editors.clear()

        for field_name in fields:
            lbl = QLabel(f"<b>{field_name}</b>")
            text_edit = DropImageTextEdit()
            text_edit.setMinimumHeight(60)
            text_edit.textChanged.connect(self._on_text_changed)

            self.field_editors[field_name] = text_edit
            self.details_layout.addWidget(lbl)
            self.details_layout.addWidget(text_edit)

        # Mise à jour de l'aperçu pour la création (brouillon)
        self.preview_card_selector.blockSignals(True)
        self.preview_card_selector.clear()
        templates = json.loads(note_type.templates) if note_type.templates else []
        for tmpl in templates:
            self.preview_card_selector.addItem(tmpl.get("name", "Carte"))
        self.preview_card_selector.blockSignals(False)
        self.update_preview()

    @Slot()
    def _on_text_changed(self) -> None:
        """Relance le délai de 500ms à chaque frappe pour laisser MathJax respirer."""
        self.preview_timer.start()

    @Slot()
    def save_note_edits(self) -> None:
        if self.is_creating:
            self._create_new_note()
            return
        if not self.current_note:
            return

        try:
            active_version = NoteVersionModel.get_or_none(note=self.current_note, is_active=True)
            content_dict = json.loads(active_version.content) if active_version else {}
            for field_name, editor in self.field_editors.items():
                content_dict[field_name] = editor.toPlainText().replace("\n", "<br>")

            with db.atomic():
                new_version = self.current_note.add_version(content_dict, source="manual")

                # ========================================================
                # SYNCHRONISATION DYNAMIQUE DES CARTES CLOZE
                # ========================================================
                note_type = self.current_note.note_type
                if note_type is None:
                    return
                templates = json.loads(note_type.templates) if note_type.templates else []
                is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

                if is_cloze:
                    max_cloze = get_max_cloze_index(content_dict)
                    target_num_cards = max(1, max_cloze)
                    existing_cards = list(self.current_note.cards.order_by(CardModel.template_index))
                    current_num_cards = len(existing_cards)

                    if target_num_cards > current_num_cards:
                        deck = existing_cards[0].deck if existing_cards else DeckModel.get_by_id(self.current_deck_id)
                        for i in range(current_num_cards, target_num_cards):
                            CardModel.create(note=self.current_note, deck=deck, template_index=i)
                    elif target_num_cards < current_num_cards:
                        for card in existing_cards[target_num_cards:]:
                            card.delete_instance()
                # ========================================================

            mode = self.view_mode_cb.currentText()
            if mode == "Vue : Notes (Texte)":
                selected_items = self.data_table.selectedItems()
                if selected_items:
                    row = selected_items[0].row()
                    values = list(content_dict.values())
                    recto = strip_html(values[0]) if len(values) > 0 else ""
                    verso = strip_html(values[1]) if len(values) > 1 else ""
                    self.data_table.setItem(row, 0, QTableWidgetItem(recto))
                    self.data_table.setItem(row, 1, QTableWidgetItem(verso))
                    item_version = QTableWidgetItem(f"v{new_version.version_number}")
                    item_version.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.data_table.setItem(row, 4, item_version)
            else:
                self.refresh_table()

            logger.info(f"Note {self.current_note.id} mise à jour manuellement.")
            show_toast(self, "Note mise à jour !")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde des modifications de la note :")
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder : {e}")

    def _create_new_note(self) -> None:
        try:
            if self.creation_model_cb is None:
                return
            model_id = self.creation_model_cb.currentData()
            note_type = NoteTypeModel.get_by_id(model_id)
            if note_type is None:
                return
            content_dict = {}
            for field_name, editor in self.field_editors.items():
                content_dict[field_name] = editor.toPlainText().replace("\n", "<br>")

            import uuid

            with db.atomic():
                # 1. Créer la Note
                new_note = NoteModel.create(
                    guid=str(uuid.uuid4())[:10],  # format basique
                    note_type=note_type,
                    tags="[]",
                    status="new",
                )

                # 2. Créer la version initiale
                new_note.add_version(content_dict, source="manual")

                # 3. Créer la/les cartes
                templates = json.loads(note_type.templates) if note_type.templates else []
                deck = DeckModel.get_by_id(self.current_deck_id)
                is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

                if is_cloze:
                    max_cloze = get_max_cloze_index(content_dict)
                    num_cards = max(1, max_cloze)  # Au moins 1 carte même si l'utilisateur a oublié de mettre un trou
                    for i in range(num_cards):
                        CardModel.create(note=new_note, deck=deck, template_index=i)
                else:
                    for i, _ in enumerate(templates):
                        CardModel.create(note=new_note, deck=deck, template_index=i)

            logger.info(f"Nouvelle note créée (ID: {new_note.id}).")
            show_toast(self, "✨ Nouvelle note créée !")
            self._exit_creation_mode(refresh=True, select_note_id=new_note.id)

        except Exception as e:
            logger.exception("Erreur lors de la création d'une nouvelle note :")
            QMessageBox.critical(self, "Erreur", f"Impossible de créer la note : {e}")

    def _exit_creation_mode(self, refresh: bool = False, select_note_id: int | None = None) -> None:
        self.is_creating = False
        self.btn_save_edits.setText(" Sauvegarder les modifications")
        self.btn_history.setVisible(True)

        if refresh:
            self.refresh_table()

        if select_note_id and self.current_deck_id is not None:
            self.jump_to_note(select_note_id, self.current_deck_id)
        else:
            # Nettoyer l'interface si on annule simplement
            while self.details_layout.count():
                child = self.details_layout.takeAt(0)
                widget = child.widget()
                if widget is not None:
                    widget.deleteLater()
            self.field_editors.clear()
            self.btn_save_edits.setEnabled(False)
            self.btn_history.setEnabled(False)

    @Slot()
    def update_preview(self) -> None:
        if not self.current_note and not self.is_creating:
            return

        note_type = None
        if self.is_creating:
            if not self.creation_model_cb:
                return
            model_id = self.creation_model_cb.currentData()
            if not model_id:
                return
            note_type = NoteTypeModel.get_by_id(model_id)
        elif self.current_note:
            note_type = self.current_note.note_type
        note_type = cast(NoteTypeModel, note_type)

        if note_type is None:
            return

        current_fields = {name: editor.toPlainText().replace("\n", "<br>") for name, editor in self.field_editors.items()}
        note_type_templates = note_type.templates
        templates = cast(list[dict[str, Any]], json.loads(note_type_templates)) if note_type_templates else []
        is_cloze = is_template_cloze(templates=templates)

        # ----------------------------------------------------
        # GESTION DYNAMIQUE DE LA LISTE DÉROULANTE DE PREVIEW
        # ----------------------------------------------------
        current_selector_count = self.preview_card_selector.count()
        if is_cloze:
            max_cloze = get_max_cloze_index(current_fields)
            num_cards = max(1, max_cloze)
            if current_selector_count != num_cards:
                self.preview_card_selector.blockSignals(True)
                self.preview_card_selector.clear()
                for i in range(num_cards):
                    self.preview_card_selector.addItem(f"Trou {i + 1} (c{i + 1})")
                self.preview_card_selector.blockSignals(False)
        else:
            if current_selector_count != len(templates):
                self.preview_card_selector.blockSignals(True)
                self.preview_card_selector.clear()
                for tmpl in templates:
                    self.preview_card_selector.addItem(tmpl.get("name", "Carte"))
                self.preview_card_selector.blockSignals(False)

        selected_tmpl_idx = self.preview_card_selector.currentIndex()
        if selected_tmpl_idx < 0:
            selected_tmpl_idx = 0

        if is_cloze:
            tmpl = templates[0] if templates else {}
            card_idx = selected_tmpl_idx  # c1, c2, etc.
        else:
            if selected_tmpl_idx >= len(templates):
                selected_tmpl_idx = 0
            tmpl = templates[selected_tmpl_idx] if templates else {}
            card_idx = selected_tmpl_idx

        is_recto = self.preview_side_selector.currentIndex() == 0
        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")
        css = getattr(note_type, "css_style", "") or ""

        final_html = render_anki_card(
            raw_html=raw_html,
            css=css,
            fields_dict=current_fields,
            is_recto=is_recto,
            front_html=tmpl.get("qfmt", ""),
            is_dark_mode=is_dark_mode(),
            template_index=int(card_idx),
        )

        media_dir = get_app_data_dir() / "media"
        media_dir.mkdir(exist_ok=True)
        base_url = QUrl.fromLocalFile(str(media_dir) + "/")
        self.web_view.setHtmlSafe(final_html, base_url)

    def approve_selected_notes(self) -> None:
        selected_rows = set(item.row() for item in self.data_table.selectedItems())
        if not selected_rows:
            return

        try:
            with db.atomic():
                for row in selected_rows:
                    row_item = self.data_table.item(row, 0)
                    if row_item is None:
                        continue
                    note_id = row_item.data(Qt.ItemDataRole.UserRole)
                    if note_id is None:
                        continue
                    note = NoteModel.get_by_id(note_id)
                    if note is None:
                        continue
                    note.status = "new"
                    note.save()

            logger.info(f"{len(selected_rows)} notes approuvées et sorties de quarantaine.")
            self.refresh_table()
        except Exception as e:
            logger.exception("Erreur lors de l'approbation des notes :")
            QMessageBox.critical(self, "Erreur", f"Impossible d'approuver :\n{e}")

    def reject_selected_notes(self) -> None:
        selected_rows = set(item.row() for item in self.data_table.selectedItems())
        if not selected_rows:
            return

        reply = QMessageBox.question(
            self,
            "Rejeter",
            f"Voulez-vous vraiment supprimer définitivement ces {len(selected_rows)} cartes ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    for row in selected_rows:
                        row_item = self.data_table.item(row, 0)
                        if row_item is None:
                            continue
                        note_id = row_item.data(Qt.ItemDataRole.UserRole)
                        if note_id is not None:
                            NoteModel.delete_by_id(note_id)  # CASCADE supprimera les cartes et versions

                logger.info(f"{len(selected_rows)} notes rejetées et supprimées.")
                self.refresh_table()
                self.web_view.setHtml("")
                self.btn_save_edits.setEnabled(False)
            except Exception as e:
                logger.exception("Erreur lors du rejet des notes :")
                QMessageBox.critical(self, "Erreur", f"Impossible de rejeter :\n{e}")

    # ==========================================
    # GESTIONNAIRE DE TAGS
    # ==========================================

    def refresh_tags_list(self) -> None:
        """Récupère les tags uniques du paquet sélectionné ET du mode de vue actuel."""
        self.tag_list.clear()

        all_item = QListWidgetItem("🏷️ Tous les tags")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self.tag_list.addItem(all_item)

        tag_counts: dict[str, int] = {}

        mode = self.view_mode_cb.currentText()
        is_quarantine = mode == "Vue : Quarantaine (À valider)"
        status_condition = (NoteModel.status == "pending") if is_quarantine else (NoteModel.status != "pending")

        if self.current_deck_id:
            try:
                selected_deck = DeckModel.get_by_id(self.current_deck_id)
                matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

                notes_with_tags = (
                    NoteModel.select(NoteModel.id, NoteModel.tags)
                    .join(NoteTypeModel)
                    .switch(NoteModel)
                    .join(CardModel, on=(CardModel.note_id == NoteModel.id))
                    .join(DeckModel, on=(CardModel.deck_id == DeckModel.id))
                    .where(DeckModel.id.in_(matching_decks) & NoteModel.tags.is_null(False) & status_condition)
                    .distinct()
                )
            except (ValueError, AttributeError, TypeError):
                notes_with_tags = []
        else:
            notes_with_tags = (
                NoteModel.select(NoteModel.id, NoteModel.tags)
                .join(NoteTypeModel)  # FIX 2 ici aussi
                .where(NoteModel.tags.is_null(False) & status_condition)
                .distinct()
            )

        for note in notes_with_tags:
            try:
                tags = cast(list[str], json.loads(note.tags))
                if isinstance(tags, list):
                    for tag in set(tags):
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
            except (ValueError, TypeError, json.JSONDecodeError):
                pass

        for tag in sorted(tag_counts.keys()):
            count = tag_counts[tag]
            item = QListWidgetItem(f"# {tag} ({count})")
            item.setData(Qt.ItemDataRole.UserRole, tag)
            self.tag_list.addItem(item)

    @Slot(QListWidgetItem)
    def on_tag_selected(self, item: QListWidgetItem) -> None:
        """Applique le filtre et rafraîchit le tableau."""
        self.current_tag_filter = item.data(Qt.ItemDataRole.UserRole)
        self.refresh_table()

    @Slot(int)
    def show_tag_context_menu(self, pos: QPoint) -> None:
        """Affiche le menu contextuel (clic droit) pour renommer/supprimer un tag."""
        item = self.tag_list.itemAt(pos)
        if not item:
            return

        tag_name = item.data(Qt.ItemDataRole.UserRole)
        if not tag_name:
            return  # On ne peut pas modifier "Tous les tags"

        menu = QMenu(self)
        rename_action = menu.addAction("✏️ Renommer le tag")
        delete_action = menu.addAction("🗑️ Supprimer le tag (Retirer de toutes les cartes)")

        action = menu.exec(self.tag_list.mapToGlobal(pos))

        if action == rename_action:
            self.rename_tag(tag_name)
        elif action == delete_action:
            self.delete_tag(tag_name)

    def rename_tag(self, old_tag: str) -> None:
        new_tag, ok = QInputDialog.getText(self, "Renommer un Tag", f"Nouveau nom pour #{old_tag} :", text=old_tag)
        if ok and new_tag.strip() and new_tag.strip() != old_tag:
            new_tag = new_tag.strip()
            try:
                with db.atomic():
                    # On trouve toutes les notes qui contiennent l'ancien tag
                    notes_to_update = NoteModel.select().where(NoteModel.tags.contains(f'"{old_tag}"'))
                    for note in notes_to_update:
                        raw_tags = note.tags
                        if isinstance(raw_tags, (str, bytes, bytearray)) and raw_tags:
                            tags = cast(list[str], json.loads(raw_tags))
                        else:
                            tags = []
                        if old_tag in tags:
                            # On remplace l'ancien par le nouveau
                            tags = [new_tag if t == old_tag else t for t in tags]
                            note.tags = json.dumps(tags, ensure_ascii=False)
                            note.save()

                show_toast(self, f"Tag #{old_tag} renommé en #{new_tag} !")

                # Mise à jour de l'UI
                if self.current_tag_filter == old_tag:
                    self.current_tag_filter = new_tag
                logger.info(f"Tag #{old_tag} renommé en #{new_tag}.")
                self.refresh_tags_list()
                self.refresh_table()

            except Exception as e:
                logger.exception(f"Erreur lors du renommage du tag #{old_tag} :")
                QMessageBox.critical(self, "Erreur", f"Impossible de renommer le tag : {e}")

    def delete_tag(self, tag_to_delete: str) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Voulez-vous retirer le tag #{tag_to_delete} de toutes vos notes ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with db.atomic():
                    notes_to_update = NoteModel.select().where(NoteModel.tags.contains(f'"{tag_to_delete}"'))
                    for note in notes_to_update:
                        raw_tags = note.tags
                        if isinstance(raw_tags, (str, bytes, bytearray)) and raw_tags:
                            tags = cast(list[str], json.loads(raw_tags))
                        else:
                            tags = []
                        if tag_to_delete in tags:
                            tags.remove(tag_to_delete)
                            note.tags = json.dumps(tags, ensure_ascii=False)
                            note.save()

                logger.info(f"Tag #{tag_to_delete} supprimé de toutes les notes.")
                show_toast(self, f"Tag #{tag_to_delete} supprimé !")
                if self.current_tag_filter == tag_to_delete:
                    self.current_tag_filter = None
                self.refresh_tags_list()
                self.refresh_table()
            except Exception as e:
                logger.exception(f"Erreur lors de la suppression du tag #{tag_to_delete} :")
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le tag : {e}")

    @Slot(int, int)
    def jump_to_note(self, note_id: int, deck_id: int) -> None:
        """Sélectionne le paquet, puis trouve et sélectionne la carte dans le tableau."""
        if not deck_id:
            return

        # 1. Sélectionner le paquet dans l'arbre de gauche
        from PySide6.QtWidgets import QTreeWidgetItemIterator

        iterator = QTreeWidgetItemIterator(self.deck_tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, Qt.ItemDataRole.UserRole) == deck_id:
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.deck_tree.setCurrentItem(item)
                self.on_deck_selected(item, 0)
                break
            iterator += 1

        # 2. Sélectionner la note dans le tableau central
        for row in range(self.data_table.rowCount()):
            row_item = self.data_table.item(row, 0)
            if row_item is None:
                continue
            row_note_id = row_item.data(Qt.ItemDataRole.UserRole)
            if row_note_id == note_id:
                self.data_table.selectRow(row)
                self.data_table.scrollToItem(row_item)
                break

    @Slot()
    def scan_for_duplicates(self) -> None:
        if self.is_creating:
            QMessageBox.warning(self, "Attention", "Veuillez terminer ou annuler la création en cours d'abord.")
            return

        if not self.current_deck_id:
            QMessageBox.warning(self, "Attention", "Veuillez d'abord sélectionner un paquet.")
            return

        self.btn_scan_dupes.setEnabled(False)
        self.btn_scan_dupes.setText("⏳ Analyse en cours...")

        try:
            selected_deck = DeckModel.get_by_id(self.current_deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

            # Récupère toutes les notes du paquet
            all_notes = (
                NoteModel.select(NoteModel, NoteTypeModel)
                .join(NoteTypeModel)
                .switch(NoteModel)
                .join(CardModel, on=(CardModel.note_id == NoteModel.id))
                .join(DeckModel, on=(CardModel.deck_id == DeckModel.id))
                .where(DeckModel.id.in_(matching_decks))
                .distinct()
            )

            # 1. Grouper par Modèle
            notes_by_model: dict[int, list[NoteModel]] = {}
            for note in all_notes:
                model_id = note.note_type.id if note.note_type else 0
                if model_id not in notes_by_model:
                    notes_by_model[model_id] = []
                notes_by_model[model_id].append(note)

            conflicts = []

            # 2. Analyser chaque groupe
            for _, notes in notes_by_model.items():
                note_data_list = []
                for note in notes:
                    active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                    if active_version:
                        content = json.loads(active_version.content)
                        values = list(content.values())
                        if values:
                            all_text_combined = " ".join(str(v) for v in values)
                            clean_text = strip_html(all_text_combined).lower()

                            # ✨ NOUVEAU : Pré-calcul des métriques pour les heuristiques
                            text_length = len(clean_text)
                            # On crée un Set des mots de plus de 2 lettres (pour ignorer le, la, de, un...)
                            word_set = set(w for w in clean_text.split() if len(w) > 2)

                            note_data_list.append((note, clean_text, content, text_length, word_set))

                ignored_records = IgnoredDuplicateModel.select()
                ignored_pairs = {(record.note_a_id, record.note_b_id) for record in ignored_records}

                # 3. Comparaison croisée O(N^2) avec Heuristiques
                matched_ids = set()
                for i, (note_a, clean_a, content_a, len_a, words_a) in enumerate(note_data_list):
                    if note_a.id in matched_ids:
                        continue

                    for j in range(i + 1, len(note_data_list)):
                        note_b, clean_b, content_b, len_b, words_b = note_data_list[j]
                        if note_b.id in matched_ids:
                            continue

                        # HEURISTIQUE 1 : Le filtre absolu de longueur O(1)
                        # Si le ratio mathématique maximal possible est sous 85%, on ignore
                        if (len_a + len_b) > 0:
                            max_possible_ratio = (2.0 * min(int(len_a), int(len_b))) / (len_a + len_b)
                            if max_possible_ratio < 0.85:
                                continue

                        # HEURISTIQUE 2 : Le filtre sémantique (Intersection de Jaccard) O(N)
                        # On vérifie si les cartes partagent un minimum de vocabulaire
                        if words_a and words_b:
                            intersection = len(words_a & words_b)
                            union = len(words_a | words_b)
                            jaccard_ratio = float(intersection) / float(union) if union > 0 else 0.0

                            # S'ils partagent moins de 35% de leur vocabulaire, ils sont trop différents
                            if jaccard_ratio < 0.35:
                                continue

                        # Si on est arrivé jusqu'ici, la comparaison est justifiée !
                        id_1, id_2 = min(note_a.id, note_b.id), max(note_a.id, note_b.id)
                        if (id_1, id_2) in ignored_pairs:
                            continue

                        # LE MOTEUR C : On fait appel à la librairie rapide pour le verdict final
                        if get_similarity(clean_a, clean_b) > 0.90:
                            if note_a.id < note_b.id:
                                conflicts.append((note_a, content_a, note_b, content_b))
                            else:
                                conflicts.append((note_b, content_b, note_a, content_a))

                            matched_ids.add(note_b.id)
                            break

            # 4. Lancer l'interface utilisateur si on a trouvé des conflits
            if not conflicts:
                logger.info("Scan des doublons terminé : aucun doublon trouvé.")
                show_toast(self, "Aucun doublon détecté dans ce paquet !")
            else:
                logger.info(f"Scan des doublons terminé : {len(conflicts)} conflits trouvés.")
                dialog = DuplicateResolverDialog(conflicts, self)
                dialog.exec()
                # On rafraîchit le tableau car des cartes ont potentiellement été supprimées
                self.refresh_table()

        except Exception as e:
            logger.exception("Erreur lors du scan des doublons :")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'analyse : {e}")
        finally:
            self.btn_scan_dupes.setEnabled(True)
            self.btn_scan_dupes.setText(" Traquer les doublons")
            self.btn_scan_dupes.setIcon(qtawesome.icon("fa5s.search"))

    @Slot()
    def show_version_history(self) -> None:
        if not self.current_note:
            return

        dialog = VersionHistoryDialog(self.current_note, self)
        # Si la boîte de dialogue renvoie "accept" (l'utilisateur a restauré une version)
        if dialog.exec():
            # On recharge l'éditeur avec la nouvelle version restaurée
            self.on_row_selected()
            # On rafraîchit le numéro de version dans le tableau !
            self.refresh_table()

    @Slot()
    def open_batch_edit_dialog(self) -> None:
        # N'oublie pas d'importer ta nouvelle boîte de dialogue en haut du fichier !

        selected_items = self.data_table.selectedItems()
        if not selected_items:
            return

        # On récupère les IDs uniques des notes sélectionnées
        selected_rows = set(item.row() for item in selected_items)
        note_ids = []
        for row in selected_rows:
            row_item = self.data_table.item(row, 0)
            if row_item is None:
                continue
            note_id = row_item.data(Qt.ItemDataRole.UserRole)
            if note_id is not None:
                note_ids.append(note_id)

        dialog = BatchEditDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            llm_id = data["llm_id"]
            prompt = data["prompt"]
            chunk_size = data["chunk_size"]

            if not prompt or not llm_id:
                show_toast(self, "Configuration IA incomplète.", is_error=True)
                return

            # Instanciation dynamique du Moteur IA

            llm_config = LLMConfigModel.get_by_id(llm_id)
            if llm_config is None:
                return
            p_name = llm_config.provider.lower()
            active_provider: LLMProvider
            if p_name == "ollama":
                active_provider = OllamaProvider(model_name=llm_config.model_id)
            elif p_name == "gemini":
                active_provider = GeminiService(model_name=llm_config.model_id)
            elif p_name == "groq":
                active_provider = GroqProvider(model_name=llm_config.model_id)
            elif p_name == "openai":
                active_provider = OpenAICompatibleProvider(
                    base_url="https://api.openai.com/v1",
                    model_name=llm_config.model_id,
                    api_key=os.environ.get("OPENAI_API_KEY", ""),
                )
            else:
                active_provider = MockProvider()

            # Préparation de l'interface de chargement (QProgressDialog gère le bouton "Annuler" nativement)

            self.progress_dialog = QProgressDialog("Préparation de l'IA...", "Annuler", 0, 0, self)
            self.progress_dialog.setWindowTitle("Modification par lot en cours")
            self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.progress_dialog.setMinimumDuration(0)

            # Lancement du Thread
            logger.info(f"Lancement du batch edit IA sur {len(note_ids)} notes.")
            self.batch_thread = BatchEditThread(active_provider, note_ids, prompt, chunk_size)
            self.batch_thread.progress.connect(self.progress_dialog.setLabelText)
            self.batch_thread.finished_signal.connect(self._on_batch_edit_success)
            self.batch_thread.error_signal.connect(self._on_batch_edit_error)
            self.batch_thread.cancelled.connect(self._on_batch_edit_cancelled)

            # Si l'utilisateur clique sur Annuler, on coupe le thread !
            self.progress_dialog.canceled.connect(self.batch_thread.cancel)

            self.batch_thread.start()
            self.progress_dialog.show()

    @Slot(int)
    def _on_batch_edit_success(self, processed_count: int):
        if self.progress_dialog:
            self.progress_dialog.close()

        if processed_count > 0:
            logger.info(f"Batch edit terminé : {processed_count} notes modifiées.")
            show_toast(self, f"{processed_count} carte(s) modifiée(s) et placée(s) en Quarantaine !")
        else:
            logger.info("Batch edit terminé : aucune note modifiée.")
            show_toast(self, "L'IA a estimé qu'aucune modification n'était nécessaire sur ces cartes.")

        self.refresh_table()  # Fera disparaître les cartes modifiées vers la vue Quarantaine !

    @Slot(str)
    def _on_batch_edit_error(self, error_msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
        logger.error(f"Erreur lors du batch edit : {error_msg}")
        QMessageBox.critical(self, "Erreur IA", f"Erreur lors de la modification : {error_msg}")

    @Slot()
    def _on_batch_edit_cancelled(self):
        if self.progress_dialog:
            self.progress_dialog.close()
        logger.info("Batch edit annulé par l'utilisateur.")
        show_toast(self, "Modification par lot annulée.", is_error=True)
        self.refresh_table()

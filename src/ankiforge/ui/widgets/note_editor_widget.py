import logging
import json
from typing import Optional

import qtawesome
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QScrollArea, QSplitter, QComboBox, QMessageBox

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel, DeckModel, CardModel, db
from ankiforge.ui.components.components import RoundedPanel, PrimaryButton, ActionButton
from ankiforge.ui.widgets.drop_image_text_edit import DropImageTextEdit
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.services.cards.note_manager import NoteManager
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


class NoteEditorWidget(QWidget):
    """
    Zone d'édition des champs d'une note et prévisualisation en temps réel.
    """

    note_updated = Signal(int, dict, int)  # note_id, content_dict, version_num
    note_created = Signal(int)  # new_note_id
    history_requested = Signal(int)  # note_id
    creation_mode_exited = Signal(bool, object)  # refresh, select_note_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_note: Optional[NoteModel] = None
        self.current_deck_id: Optional[int] = None
        self.field_editors: dict[str, QTextEdit] = {}
        self.is_creating = False
        self.creation_model_cb: Optional[QComboBox] = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(10)

        # --- Panneau Édition ---
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
        self.btn_history.setEnabled(False)

        self.btn_save_edits = PrimaryButton(qtawesome.icon("fa5s.save", color="white"), " Sauvegarder modifications")
        self.btn_save_edits.setEnabled(False)

        buttons_layout.addWidget(self.btn_history)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.btn_save_edits)

        editor_layout.addLayout(buttons_layout)
        self.splitter.addWidget(editor_panel)

        # --- Panneau Prévisualisation ---
        preview_panel = RoundedPanel()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(15, 15, 15, 15)

        self.preview_widget = CardPreviewWidget(show_header=True)
        preview_layout.addWidget(self.preview_widget)

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(500)

        self.splitter.addWidget(preview_panel)
        self.splitter.setSizes([350, 450])

        layout.addWidget(self.splitter)

    def _connect_signals(self):
        self.btn_history.clicked.connect(self._on_history_clicked)
        self.btn_save_edits.clicked.connect(self.save_note_edits)
        self.preview_timer.timeout.connect(self.update_preview)

    def set_current_deck(self, deck_id: Optional[int]):
        self.current_deck_id = deck_id

    def load_note(self, note_id: int):
        self._clear_editor()
        self.is_creating = False
        try:
            self.current_note = NoteModel.get_by_id(note_id)
            if not self.current_note or not self.current_note.note_type:
                return

            self.btn_save_edits.setText(" Sauvegarder modifications")
            self.btn_save_edits.setEnabled(True)
            self.btn_history.setEnabled(True)
            self.btn_history.setVisible(True)

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
            logger.exception("Erreur lors du chargement de la note dans l'éditeur :")
            self.details_layout.addWidget(QLabel(f"Erreur : {e}"))

    def enter_creation_mode(self):
        self._clear_editor()
        self.is_creating = True
        self.current_note = None

        self.btn_save_edits.setText(" ✨ Créer la note")
        self.btn_save_edits.setEnabled(True)
        self.btn_history.setVisible(False)

        lbl_title = QLabel("<b>Création de Note</b>")
        lbl_title.setStyleSheet("font-size: 16px; margin-bottom: 5px;")
        self.details_layout.addWidget(lbl_title)

        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("Modèle :"))
        self.creation_model_cb = QComboBox()
        models = NoteTypeModel.select()
        for m in models:
            self.creation_model_cb.addItem(m.name, m.id)

        self.creation_model_cb.currentIndexChanged.connect(self._render_creation_fields)
        model_layout.addWidget(self.creation_model_cb)
        model_layout.addStretch()

        model_widget = QWidget()
        model_widget.setLayout(model_layout)
        self.details_layout.addWidget(model_widget)

        self._render_creation_fields()

    def _render_creation_fields(self):
        if not self.is_creating or not self.creation_model_cb:
            return

        model_id = self.creation_model_cb.currentData()
        if not model_id:
            return

        note_type = NoteTypeModel.get_by_id(model_id)
        fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []

        while self.details_layout.count() > 2:
            child = self.details_layout.takeAt(2)
            if child:
                w = child.widget()
                if w:
                    w.deleteLater()

        self.field_editors.clear()
        for field_name in fields:
            lbl = QLabel(f"<b>{field_name}</b>")
            text_edit = DropImageTextEdit()
            text_edit.setMinimumHeight(60)
            text_edit.textChanged.connect(self._on_text_changed)

            self.field_editors[field_name] = text_edit
            self.details_layout.addWidget(lbl)
            self.details_layout.addWidget(text_edit)

        self.update_preview()

    def _clear_editor(self):
        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child:
                w = child.widget()
                if w:
                    w.deleteLater()
        self.field_editors.clear()
        self.current_note = None

    @Slot()
    def _on_text_changed(self):
        self.preview_timer.start()

    @Slot()
    def _on_history_clicked(self):
        if self.current_note:
            self.history_requested.emit(self.current_note.id)

    @Slot()
    def save_note_edits(self):
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

                # Sync Cloze cards logic
                note_type = self.current_note.note_type
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

            self.note_updated.emit(self.current_note.id, content_dict, new_version.version_number)
            show_toast(self, "Note mise à jour !")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde :")
            QMessageBox.critical(self, "Erreur", f"Impossible de sauvegarder : {e}")

    def _create_new_note(self):
        try:
            if not self.creation_model_cb or not self.current_deck_id:
                return

            model_id = self.creation_model_cb.currentData()
            note_type = NoteTypeModel.get_by_id(model_id)
            deck = DeckModel.get_by_id(self.current_deck_id)

            content_dict = {name: editor.toPlainText().replace("\n", "<br>") for name, editor in self.field_editors.items()}
            new_note = NoteManager.create_note(note_type=note_type, deck=deck, content_dict=content_dict, tags=[], status="new", source="manual")

            show_toast(self, "✨ Nouvelle note créée !")
            self._exit_creation_mode(refresh=True, select_note_id=new_note.id)
            self.note_created.emit(new_note.id)
        except Exception as e:
            logger.exception("Erreur lors de la création :")
            QMessageBox.critical(self, "Erreur", f"Impossible de créer la note : {e}")

    def _exit_creation_mode(self, refresh: bool = False, select_note_id: int | None = None):
        self.is_creating = False
        self.btn_save_edits.setText(" Sauvegarder les modifications")
        self.btn_history.setVisible(True)
        self.creation_mode_exited.emit(refresh, select_note_id)
        if not refresh:
            self._clear_editor()
            self.btn_save_edits.setEnabled(False)
            self.btn_history.setEnabled(False)

    @Slot()
    def update_preview(self):
        note_type = None
        if self.is_creating:
            if not self.creation_model_cb:
                return
            model_id = self.creation_model_cb.currentData()
            note_type = NoteTypeModel.get_by_id(model_id)
        elif self.current_note:
            note_type = self.current_note.note_type

        if not note_type:
            self.preview_widget.set_empty_state("Sélectionnez une note pour la prévisualiser.")
            return

        current_fields = {name: editor.toPlainText().replace("\n", "<br>") for name, editor in self.field_editors.items()}
        self.preview_widget.update_preview(note_type, current_fields)

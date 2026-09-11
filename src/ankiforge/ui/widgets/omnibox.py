import json
import re

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QGraphicsDropShadowEffect, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from ankiforge.database.models import CardModel, DocumentModel, NoteModel, NoteVersionModel
from ankiforge.services.search.fts_service import FTSService
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class Omnibox(QDialog):
    # Ce signal enverra : le type ("doc" ou "note"), l'ID de l'objet, et une info bonus (l'ID du paquet)
    result_selected = Signal(str, int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Rend la fenêtre flottante, sans bordures OS, style "Spotlight"
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup)
        self.setMinimumWidth(650)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QLineEdit {{
                padding: 12px;
                font-size: 15px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QListWidget {{
                border: none;
                background-color: transparent;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 13px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)  # Légèrement augmenté pour laisser respirer l'ombre

        # Ajout de l'ombre portée pour détacher l'Omnibox du fond
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 80))  # Ombre noire avec 80 d'opacité
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        # 1. La barre de recherche
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Rechercher dans les cours ou les flashcards...")
        self.search_bar.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_bar)

        # 2. La liste de résultats
        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self._on_item_activated)
        layout.addWidget(self.results_list)

        # 3. Timer (Debounce) pour ne pas exploser la BDD à chaque lettre
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.perform_search)

        # 4. Raccourcis clavier de navigation interne
        QShortcut(QKeySequence("Escape"), self).activated.connect(self.close)
        QShortcut(QKeySequence("Return"), self.search_bar).activated.connect(self._on_enter_pressed)
        QShortcut(QKeySequence("Down"), self.search_bar).activated.connect(self._focus_list)

    @Slot()
    def _on_text_changed(self):
        self.search_timer.start()

    @Slot()
    def _focus_list(self):
        if self.results_list.count() > 0:
            self.results_list.setFocus()
            self.results_list.setCurrentRow(0)

    @Slot()
    def _on_enter_pressed(self):
        if self.results_list.count() > 0:
            if self.results_list.currentRow() == -1:
                self.results_list.setCurrentRow(0)
            self._on_item_activated(self.results_list.currentItem())

    @Slot()
    def perform_search(self):
        query = self.search_bar.text().strip().lower()
        self.results_list.clear()
        if len(query) < 2:
            return

        # A. Chercher dans les Documents (Titres ou Contenu)
        docs = DocumentModel.select().where(DocumentModel.title.contains(query) | DocumentModel.content.contains(query)).limit(5)

        for doc in docs:
            icon = load_phosphor_icon("file-text", color=DesignTokens.COLOR_BLUE)
            item = QListWidgetItem(icon, f" [Cours] {doc.title}")
            item.setData(Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id, "deck_id": None})
            self.results_list.addItem(item)

        # B. Chercher dans les Flashcards (Plein-texte FTS5 ou repli optimisé)
        if FTSService.is_available():
            fts_results = FTSService.search(query, limit=10, as_prefix=True)
            for res in fts_results:
                clean_snippet = re.sub(r"[\r\n\t]+", " ", res.snippet).strip()
                clean_preview = re.sub(r"<[^>]+>", "", clean_snippet)[:75]
                if not clean_preview:
                    clean_preview = "..."

                icon = load_phosphor_icon("cards", color=DesignTokens.COLOR_GREEN)
                item = QListWidgetItem(icon, f" [Carte] {clean_preview}")
                item.setData(Qt.ItemDataRole.UserRole, {"type": "note", "id": res.note_id, "deck_id": res.deck_id or None})
                self.results_list.addItem(item)
        else:
            notes = (
                NoteModel.select(NoteModel.id, NoteVersionModel.content, CardModel.deck)
                .join(NoteVersionModel, on=(NoteVersionModel.note == NoteModel.id))
                .join(CardModel, on=((CardModel.note == NoteModel.id) & (CardModel.template_index == 0)), join_type="LEFT OUTER")
                .where(NoteVersionModel.is_active & NoteVersionModel.content.contains(query))
                .limit(10)
            )
            for note in notes:
                try:
                    content = json.loads(note.noteversionmodel.content) if hasattr(note, "noteversionmodel") else {}
                except Exception:
                    content = {}

                preview = " | ".join(str(v) for v in content.values() if isinstance(v, str))
                preview = re.sub(r"<[^>]+>", "", preview).replace("\n", " ")[:70] + "..."
                deck_id = getattr(note.cardmodel, "deck_id", None) if hasattr(note, "cardmodel") else None

                icon = load_phosphor_icon("cards", color=DesignTokens.COLOR_GREEN)
                item = QListWidgetItem(icon, f" [Carte] {preview}")
                item.setData(Qt.ItemDataRole.UserRole, {"type": "note", "id": note.id, "deck_id": deck_id})
                self.results_list.addItem(item)

    @Slot(QListWidgetItem)
    def _on_item_activated(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.result_selected.emit(data["type"], data["id"], data["deck_id"])
        self.close()

    def showEvent(self, event):
        """Réinitialise la boîte à chaque ouverture."""
        super().showEvent(event)
        self.search_bar.clear()
        self.results_list.clear()
        self.search_bar.setFocus()

    def exec_centered(self, parent_window):
        """Affiche la boîte proprement centrée en haut de la fenêtre principale."""
        self.adjustSize()
        geo = self.geometry()
        geo.moveCenter(parent_window.geometry().center())
        geo.moveTop(parent_window.geometry().top() + 100)  # Un peu vers le haut
        self.setGeometry(geo)
        self.exec()

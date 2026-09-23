"""
Fenêtre modale de sélection de document / cours RAG.
Miroir de `deck_select_window.py` pour les documents et la bibliothèque de cours.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel, FolderModel
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def document_meta_line(doc: DocumentModel) -> str:
    """Métadonnées compactes d'un document : type • volume • estimation de tokens.

    Partagé entre la modale de sélection et le DocumentPickerButton pour garantir
    la même lecture des documents aux deux étages du parcours.
    """
    ft = (getattr(doc, "file_type", "") or "md").lower()
    content = getattr(doc, "content", "") or ""
    tokens = ContextCompactor.estimate_tokens(content)

    if ft == "pdf":
        pages_count = getattr(doc, "total_pages", 0) or content.count("<!-- PAGE:")
        meta_str = f"PDF • {pages_count} page(s) • ~{tokens:,} tokens"
    elif ft in ("md", "markdown"):
        words = len(content.split())
        meta_str = f"Markdown • {words:,} mots • ~{tokens:,} tokens"
    elif ft == "album":
        pages_count = getattr(doc, "total_pages", 0) or 0
        meta_str = f"Album • {pages_count} planche(s) • ~{tokens:,} tokens"
    elif ft == "epub":
        meta_str = f"ePub • ~{tokens:,} tokens"
    elif ft == "pptx":
        meta_str = f"Présentation • ~{tokens:,} tokens"
    elif ft in ("audio", "mp3", "m4a", "wav"):
        meta_str = f"Audio • ~{tokens:,} tokens"
    elif ft in ("youtube", "video"):
        meta_str = f"Vidéo • ~{tokens:,} tokens"
    elif ft == "web":
        meta_str = f"Web • ~{tokens:,} tokens"
    else:
        words = len(content.split())
        meta_str = f"Texte • {words:,} mots • ~{tokens:,} tokens"
    return meta_str.replace(",", " ")


class DocumentSelectWindow(QWidget):
    """
    Fenêtre modale de sélection d'un document ou cours (RAG) avec arborescence et recherche.
    """

    document_selected = Signal(int, str)  # (doc_id, doc_title)

    def __init__(
        self,
        title: str = "Sélectionner un Cours / Document (RAG)",
        parent: QWidget | None = None,
        selected_doc_id: int | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(620, 540)
        self._selected_doc_id = selected_doc_id

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
            }}
        """)

        self.setWindowFlags(Qt.WindowType.Dialog if parent else Qt.WindowType.Window)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)

        # Barre de recherche avec icône Phosphor
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un document (ex: Anatomie, Cardiologie)...")
        search_icon = load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED)
        self.search_input.addAction(search_icon, QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.setFixedHeight(32)

        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 0 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QLineEdit:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        content_layout.addWidget(self.search_input)

        # Arborescence de documents et dossiers (colonne 0 : titre, colonne 1 : métadonnées)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setColumnWidth(0, 340)
        self.tree.header().setStretchLastSection(True)

        palette = self.tree.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(DesignTokens.ACCENT_PRIMARY))
        self.tree.setPalette(palette)

        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 13px;
                font-family: '{DesignTokens.FONT_MAIN}';
                show-decoration-selected: 1;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 6px 4px;
                border: none;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                font-weight: bold;
            }}
        """)

        content_layout.addWidget(self.tree)
        layout.addWidget(content)

        # Footer avec actions
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(8)

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.close)

        self.btn_confirm = PrimaryButton("Valider ce document")
        self.btn_confirm.clicked.connect(self._on_confirm)
        self.btn_confirm.setEnabled(False)

        footer_layout.addStretch()
        footer_layout.addWidget(btn_cancel)
        footer_layout.addWidget(self.btn_confirm)
        layout.addWidget(footer)

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._doc_items_by_id: dict[int, QTreeWidgetItem] = {}
        self._load_documents()

    def _load_documents(self) -> None:
        """Charge l'arborescence des dossiers et documents depuis DocumentModel."""
        self.tree.clear()
        self._doc_items_by_id.clear()

        # 1. Charger les dossiers
        folder_items: dict[int, QTreeWidgetItem] = {}
        folders = list(FolderModel.select())
        for folder in folders:
            item = QTreeWidgetItem(self.tree, [folder.name])
            item.setIcon(0, load_phosphor_icon("ph.folder", weight="fill", color=DesignTokens.COLOR_BLUE))
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id, "title": folder.name})
            folder_items[folder.id] = item

        # 2. Charger les documents
        documents = list(DocumentModel.select().order_by(DocumentModel.id.desc()))
        if not documents and not folders:
            empty_item = QTreeWidgetItem(self.tree, ["Aucun document disponible dans la bibliothèque"])
            empty_item.setData(0, Qt.ItemDataRole.UserRole, None)
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setForeground(0, QColor(DesignTokens.TEXT_MUTED))
            return

        for doc in documents:
            folder_id = getattr(doc, "folder_id", None)
            parent_item = folder_items.get(folder_id, self.tree) if folder_id else self.tree
            title_to_display = doc.title
            if not title_to_display:
                try:
                    if getattr(doc, "original_media", None):
                        title_to_display = doc.original_media.original_name
                except Exception as err:
                    logger.debug("Récupération du nom de média original ignorée : %s", err)
            title_to_display = title_to_display or "Document sans titre"

            item = QTreeWidgetItem(parent_item, [title_to_display, document_meta_line(doc)])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id, "title": title_to_display})
            item.setForeground(1, QColor(DesignTokens.TEXT_MUTED))
            ft = (getattr(doc, "file_type", "md") or "md").lower()
            content = getattr(doc, "content", "") or ""
            folder_item = folder_items.get(folder_id) if folder_id else None
            folder_name = folder_item.text(0) if folder_item is not None else "Aucun dossier"
            pages = int(getattr(doc, "total_pages", 0) or 0)
            words = len(content.split())
            tokens = ContextCompactor.estimate_tokens(content)
            item.setToolTip(
                0,
                f"{title_to_display}\nType : {ft.upper() or 'MD'}\nPages : {pages or '—'}\nVolume : ~{words:,} mots • ~{tokens:,} tokens\n".replace(",", " ")
                + f"Dossier : {folder_name}"
                + (f"\nSource : {doc.source_url}" if getattr(doc, "source_url", None) else ""),
            )

            # Icône selon le type de fichier
            if ft == "pdf":
                item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED))
            elif ft in ("md", "markdown"):
                item.setIcon(0, load_phosphor_icon("ph.file-code", color=DesignTokens.COLOR_YELLOW))
            elif ft == "album":
                item.setIcon(0, load_phosphor_icon("ph.images", color=DesignTokens.COLOR_PURPLE))
            elif ft == "epub":
                item.setIcon(0, load_phosphor_icon("ph.book-open", color=DesignTokens.COLOR_PURPLE))
            elif ft == "pptx":
                item.setIcon(0, load_phosphor_icon("ph.presentation", color=DesignTokens.COLOR_YELLOW))
            elif ft in ("audio", "mp3", "m4a", "wav"):
                item.setIcon(0, load_phosphor_icon("ph.headphones", color=DesignTokens.COLOR_GREEN))
            elif ft in ("youtube", "video"):
                item.setIcon(0, load_phosphor_icon("ph.youtube-logo", color=DesignTokens.COLOR_RED))
            elif ft == "web":
                item.setIcon(0, load_phosphor_icon("ph.globe", color=DesignTokens.ACCENT_PRIMARY))
            else:
                item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))

            self._doc_items_by_id[doc.id] = item

        self.tree.expandAll()

        if self._selected_doc_id is not None and self._selected_doc_id in self._doc_items_by_id:
            sel_item = self._doc_items_by_id[self._selected_doc_id]
            self.tree.setCurrentItem(sel_item)
            sel_item.setSelected(True)
            self.tree.scrollToItem(sel_item)
            self.btn_confirm.setEnabled(True)

    def _on_search_changed(self, text: str) -> None:
        """Filtre l'arborescence : affiche les correspondances et leurs dossiers parents."""
        query = text.lower().strip()

        if not query:
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item:
                    self._set_item_visibility_recursive(item, True)
            return

        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item:
                self._set_item_visibility_recursive(item, False)

        for item in self._doc_items_by_id.values():
            if query in item.text(0).lower():
                item.setHidden(False)
                parent = item.parent()
                while parent:
                    parent.setHidden(False)
                    parent.setExpanded(True)
                    parent = parent.parent()

    def _set_item_visibility_recursive(self, item: QTreeWidgetItem, visible: bool) -> None:
        item.setHidden(not visible)
        for i in range(item.childCount()):
            self._set_item_visibility_recursive(item.child(i), visible)

    def _get_selected_doc_info(self) -> tuple[int, str] | None:
        selected = self.tree.selectedItems()
        if not selected:
            return None
        data: Any = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("type") == "doc":
            return int(data["id"]), str(data.get("title", ""))
        return None

    def _on_selection_changed(self) -> None:
        info = self._get_selected_doc_info()
        self.btn_confirm.setEnabled(info is not None)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        info = self._get_selected_doc_info()
        if info is not None:
            self._on_confirm()

    def _on_confirm(self) -> None:
        info = self._get_selected_doc_info()
        if info is not None:
            doc_id, doc_title = info
            self.document_selected.emit(doc_id, doc_title)
            self.close()

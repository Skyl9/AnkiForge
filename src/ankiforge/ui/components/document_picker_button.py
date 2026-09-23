"""
Composant bouton-sélecteur de document source (DocumentPickerButton).
Miroir des sélecteurs de Paquets et Modèles d'AnkiForge, avec prévisualisation et métadonnées.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QCursor, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ankiforge.database.models import DocumentModel
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.ui.components.document_select_window import DocumentSelectWindow
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DocumentPickerButton(QFrame):
    """
    Bouton interactif élégant affichant le document source actif avec son icône,
    son titre et ses métadonnées (type, pages, estimation de tokens).
    Un clic ouvre la modale DocumentSelectWindow.
    """

    document_changed = Signal(object)  # DocumentModel | None

    def __init__(self, parent: Any = None, allow_clear: bool = True) -> None:
        super().__init__(parent)
        self.allow_clear = allow_clear
        self._current_doc: DocumentModel | None = None
        self._modal: DocumentSelectWindow | None = None

        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(54)
        self.setObjectName("documentPickerButton")

        self._build_ui()
        self._update_display()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # Icône dans un conteneur arrondi
        self.icon_badge = QFrame()
        self.icon_badge.setFixedSize(36, 36)
        self.icon_badge.setObjectName("iconBadge")
        badge_layout = QVBoxLayout(self.icon_badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        badge_layout.addWidget(self.icon_label)
        layout.addWidget(self.icon_badge)

        # Textes (Titre + Métadonnées)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.title_label = QLabel("Sélectionner un cours...")
        self.title_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; background: transparent; border: none;")
        text_layout.addWidget(self.title_label)

        self.meta_label = QLabel("Aucun document lié • Saisie libre")
        self.meta_label.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; background: transparent; border: none;")
        text_layout.addWidget(self.meta_label)
        layout.addLayout(text_layout, 1)

        # Bouton d'effacement rapide (croix)
        self.btn_clear = QPushButton()
        self.btn_clear.setFixedSize(24, 24)
        self.btn_clear.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.TEXT_MUTED))
        self.btn_clear.setToolTip("Désélectionner le document (revenir en saisie libre)")
        self.btn_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_clear.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_RED_BG};
            }}
        """)
        self.btn_clear.clicked.connect(self.clear_document)
        self.btn_clear.setVisible(False)
        layout.addWidget(self.btn_clear)

        # Indicateur de navigation (chevron droit)
        self.chevron_label = QLabel()
        self.chevron_label.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        self.chevron_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.chevron_label)

        self.setStyleSheet(f"""
            QFrame#documentPickerButton {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#documentPickerButton:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QFrame#iconBadge {{
                background-color: {DesignTokens.ACCENT_BG};
                border: 1px solid {DesignTokens.ACCENT_BORDER};
                border-radius: 6px;
            }}
        """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.btn_clear.underMouse():
            self._open_selector_modal()
        super().mousePressEvent(event)

    def _open_selector_modal(self) -> None:
        """Ouvre la fenêtre modale de sélection de document."""
        # Tente de fermer l'ancienne instance si elle existe encore côté C++.
        # L'objet Qt peut déjà avoir été détruit (GC ou fermeture par l'utilisateur),
        # d'où le try/except sur RuntimeError (libshiboken: Internal C++ object deleted).
        if self._modal is not None:
            try:
                self._modal.close()
            except RuntimeError:
                pass
            self._modal = None

        # Toujours recréer une instance fraîche pour éviter les états corrompus.
        current_id = self._current_doc.id if self._current_doc else None
        self._modal = DocumentSelectWindow(title="Sélectionner un document source", parent=self.window(), selected_doc_id=current_id)
        self._modal.document_selected.connect(self._on_modal_document_selected)
        self._modal.show()

    def _on_modal_document_selected(self, doc_id: int, doc_title: str) -> None:
        try:
            doc = DocumentModel.get_by_id(doc_id)
            self.set_document(doc)
        except Exception as e:
            logger.error("Impossible de charger le document id=%d (%s) : %s", doc_id, doc_title, e)

    def set_document(self, doc: DocumentModel | None, emit_signal: bool = True) -> None:
        """Définit le document actuellement sélectionné."""
        is_same = (self._current_doc is not None and doc is not None and getattr(self._current_doc, "id", None) is not None and getattr(self._current_doc, "id", None) == getattr(doc, "id", None)) or (
            self._current_doc is None and doc is None
        )

        if doc is not None and getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception as err:
                logger.debug("Rechargement du document ignoré : %s", err)
        self._current_doc = doc
        self._update_display()
        if emit_signal and not is_same:
            self.document_changed.emit(doc)

    def get_document(self) -> DocumentModel | None:
        """Récupère le document actuellement sélectionné."""
        if self._current_doc and getattr(self._current_doc, "id", None):
            try:
                self._current_doc = DocumentModel.get_by_id(self._current_doc.id)
            except Exception as err:
                logger.debug("Rechargement du document courant ignoré : %s", err)
        return self._current_doc

    def clear_document(self) -> None:
        """Désélectionne le document actif."""
        self.set_document(None)

    def _update_display(self) -> None:
        """Met à jour les icônes, titres et sous-titres selon le document sélectionné."""
        if not self._current_doc:
            self.title_label.setText("Sélectionner un cours...")
            self.title_label.setStyleSheet(f"font-size: 12px; font-weight: 500; color: {DesignTokens.TEXT_MUTED}; background: transparent; border: none;")
            self.meta_label.setText("Aucun document lié • Saisie libre")
            self.icon_label.setPixmap(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
            self.icon_badge.setStyleSheet(f"""
                QFrame#iconBadge {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 6px;
                }}
            """)
            self.btn_clear.setVisible(False)
            return

        doc = self._current_doc
        full_title = doc.title or "Document sans titre"
        # Troncature souple avec infobulle complète
        display_title = full_title[:62] + "..." if len(full_title) > 65 else full_title
        self.title_label.setText(display_title)
        self.title_label.setToolTip(full_title)
        self.title_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; background: transparent; border: none;")

        ft = (getattr(doc, "file_type", "") or "md").lower()
        content = getattr(doc, "content", "") or ""
        tokens = ContextCompactor.estimate_tokens(content)

        # Icône et libellé de métadonnées selon le type
        if ft == "pdf":
            icon_name = "ph.file-pdf"
            icon_color = DesignTokens.COLOR_RED
            pages_count = getattr(doc, "total_pages", 0) or content.count("<!-- PAGE:")
            meta_str = f"PDF • {pages_count} page(s) • ~{tokens:,} tokens".replace(",", " ")
        elif ft in ("md", "markdown"):
            icon_name = "ph.file-code"
            icon_color = DesignTokens.COLOR_YELLOW
            words = len(content.split())
            meta_str = f"Markdown • {words:,} mots • ~{tokens:,} tokens".replace(",", " ")
        elif ft == "album":
            icon_name = "ph.images"
            icon_color = DesignTokens.COLOR_PURPLE
            pages_count = getattr(doc, "total_pages", 0) or 0
            meta_str = f"Album • {pages_count} planche(s) • ~{tokens:,} tokens".replace(",", " ")
        elif ft == "epub":
            icon_name = "ph.book-open"
            icon_color = DesignTokens.COLOR_PURPLE
            meta_str = f"ePub • ~{tokens:,} tokens".replace(",", " ")
        elif ft == "pptx":
            icon_name = "ph.presentation"
            icon_color = DesignTokens.COLOR_YELLOW
            meta_str = f"Présentation • ~{tokens:,} tokens".replace(",", " ")
        elif ft in ("audio", "mp3", "m4a", "wav"):
            icon_name = "ph.headphones"
            icon_color = DesignTokens.COLOR_PURPLE
            meta_str = f"Audio • ~{tokens:,} tokens".replace(",", " ")
        elif ft in ("youtube", "video"):
            icon_name = "ph.youtube-logo"
            icon_color = DesignTokens.COLOR_RED
            meta_str = f"Vidéo • ~{tokens:,} tokens".replace(",", " ")
        elif ft == "web":
            icon_name = "ph.globe"
            icon_color = DesignTokens.ACCENT_PRIMARY
            meta_str = f"Web • ~{tokens:,} tokens".replace(",", " ")
        else:
            icon_name = "ph.file-text"
            icon_color = DesignTokens.COLOR_BLUE
            meta_str = f"Texte • ~{tokens:,} tokens".replace(",", " ")

        self.icon_label.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(18, 18))
        self.icon_badge.setStyleSheet(f"""
            QFrame#iconBadge {{
                background-color: rgba({int(QColor(icon_color).red())}, {int(QColor(icon_color).green())}, {int(QColor(icon_color).blue())}, 0.12);
                border: 1px solid rgba({int(QColor(icon_color).red())}, {int(QColor(icon_color).green())}, {int(QColor(icon_color).blue())}, 0.25);
                border-radius: 6px;
            }}
        """)
        self.meta_label.setText(meta_str)
        self.btn_clear.setVisible(self.allow_clear)

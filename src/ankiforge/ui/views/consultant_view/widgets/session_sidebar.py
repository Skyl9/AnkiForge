"""
Sidebar de gestion des sessions pour le Consultant IA (Style Cursor / Windsurf).

Affiche l'arborescence chronologique des sessions de discussion, permet la recherche rapide,
la création, le renommage, la suppression et l'exportation des conversations.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import ConsultantSessionModel
from ankiforge.ui.components import (
    IconButton,
    PrimaryButton,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens, StyledMenu
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class SessionItemWidget(QWidget):
    """Widget de rendu d'une ligne de session dans la sidebar."""

    renamed = Signal(int, str)
    deleted = Signal(int)
    exported = Signal(int)

    def __init__(
        self,
        session: ConsultantSessionModel,
        is_active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.session = session
        self.is_active = is_active
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if self.is_active:
            self.setStyleSheet(f"""
                SessionItemWidget {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                SessionItemWidget {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
                SessionItemWidget:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 6, 6)
        layout.setSpacing(8)

        # Icône bulle
        self.lbl_icon = QLabel()
        icon_name = "ph.chat-circle-dots" if not self.is_active else "ph.chat-teardrop-text"
        icon_color = DesignTokens.ACCENT_PRIMARY if self.is_active else DesignTokens.TEXT_MUTED
        self.lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(16, 16))
        layout.addWidget(self.lbl_icon)

        # Conteneur Titre + Date
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.lbl_title = QLabel(self.session.title)
        self.lbl_title.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                font-weight: {"600" if self.is_active else "500"};
                color: {DesignTokens.TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
        """)
        text_layout.addWidget(self.lbl_title)

        # Date relative
        date_str = self._format_date(self.session.updated_at)
        self.lbl_date = QLabel(date_str)
        self.lbl_date.setStyleSheet(f"""
            QLabel {{
                font-size: 10px;
                color: {DesignTokens.TEXT_MUTED};
                background: transparent;
                border: none;
            }}
        """)
        text_layout.addWidget(self.lbl_date)
        layout.addWidget(text_container, 1)

        # Bouton menu 3-points discret
        self.btn_menu = IconButton("ph.dots-three-vertical", tooltip="Options de la discussion", size=20)
        self.btn_menu.clicked.connect(self._show_menu)
        layout.addWidget(self.btn_menu)

    def _format_date(self, dt: datetime.datetime | None) -> str:
        if not dt:
            return ""
        now = datetime.datetime.now()
        diff = now - dt
        if diff.days == 0:
            return dt.strftime("%H:%M")
        elif diff.days == 1:
            return "Hier"
        elif diff.days < 7:
            return f"Il y a {diff.days}j"
        return dt.strftime("%d/%m")

    def _show_menu(self) -> None:
        menu = StyledMenu(self)
        act_rename = menu.addAction(
            load_phosphor_icon("ph.pencil", color=DesignTokens.TEXT_PRIMARY),
            "Renommer...",
        )
        act_export = menu.addAction(
            load_phosphor_icon("ph.share-network", color=DesignTokens.TEXT_PRIMARY),
            "Copier en Markdown",
        )
        menu.addSeparator()
        act_delete = menu.addAction(
            load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED),
            "Supprimer",
        )

        pos = self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft())
        action = menu.exec(pos)

        if action == act_rename:
            new_title, ok = QInputDialog.getText(
                self,
                "Renommer la discussion",
                "Nouveau titre :",
                text=self.session.title,
            )
            if ok and new_title.strip():
                self.renamed.emit(self.session.id, new_title.strip())

        elif action == act_export:
            self.exported.emit(self.session.id)

        elif action == act_delete:
            ret = QMessageBox.question(
                self,
                "Confirmer la suppression",
                f"Voulez-vous vraiment supprimer la discussion '{self.session.title}' ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret == QMessageBox.StandardButton.Yes:
                self.deleted.emit(self.session.id)


class ConsultantSessionSidebar(QFrame):
    """
    Panneau latéral moderne listant les discussions avec recherche instantanée,
    actions contextuelles et indicateurs de métriques.
    """

    session_selected = Signal(int)
    new_chat_requested = Signal()
    session_renamed = Signal(int, str)
    session_deleted = Signal(int)
    session_exported = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._all_sessions: list[ConsultantSessionModel] = []
        self._active_session_id: int | None = None
        self._filter_query: str = ""
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setMinimumWidth(210)
        self.setMaximumWidth(320)
        self.setStyleSheet(f"""
            ConsultantSessionSidebar {{
                background-color: {DesignTokens.BG_SIDEBAR};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # ── 1. Header avec bouton Nouveau Chat ──────────────────────────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        lbl_header = QLabel("DISCUSSIONS")
        lbl_header.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                font-weight: 700;
                color: {DesignTokens.TEXT_MUTED};
                letter-spacing: 0.5px;
            }}
        """)
        header_row.addWidget(lbl_header)
        header_row.addStretch()

        self.btn_new = PrimaryButton("Nouveau")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color="white"))
        self.btn_new.setFixedHeight(28)
        self.btn_new.setStyleSheet("""
            QPushButton {
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_new.clicked.connect(self.new_chat_requested.emit)
        header_row.addWidget(self.btn_new)
        layout.addLayout(header_row)

        # ── 2. Champ de recherche rapide ────────────────────────────────────
        self.search_input = StyledLineEdit()
        self.search_input.setPlaceholderText("Filtrer l'historique...")
        self.search_input.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.search_input)

        # ── 3. Liste des sessions ───────────────────────────────────────────
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 2px;
                padding: 0px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)

        # ── 4. Footer avec métriques de session ─────────────────────────────
        footer = QFrame()
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(6, 4, 6, 4)
        footer_layout.setSpacing(6)

        self.lbl_footer_tokens = QLabel("⚡ 0 tokens")
        self.lbl_footer_tokens.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        footer_layout.addWidget(self.lbl_footer_tokens)
        footer_layout.addStretch()

        self.lbl_footer_cards = QLabel("📦 0 mod.")
        self.lbl_footer_cards.setStyleSheet(f"font-size: 10px; color: {DesignTokens.COLOR_GREEN}; font-weight: 600;")
        footer_layout.addWidget(self.lbl_footer_cards)

        layout.addWidget(footer)

    def set_sessions(self, sessions: list[ConsultantSessionModel], active_id: int | None = None) -> None:
        """Met à jour la liste des sessions affichées."""
        self._all_sessions = list(sessions)
        if active_id is not None:
            self._active_session_id = active_id
        elif self._all_sessions and self._active_session_id is None:
            self._active_session_id = self._all_sessions[0].id

        self._render_list()

    def set_active_session_id(self, session_id: int) -> None:
        """Sélectionne visuellement la session active."""
        self._active_session_id = session_id
        self._render_list()

    def update_metrics(self, tokens: int, modified_cards: int) -> None:
        """Met à jour les compteurs du footer."""
        self.lbl_footer_tokens.setText(f"⚡ {tokens:,} tok")
        self.lbl_footer_cards.setText(f"📦 {modified_cards} mod.")

    def _on_filter_changed(self, text: str) -> None:
        self._filter_query = text.strip().lower()
        self._render_list()

    def _render_list(self) -> None:
        self.list_widget.clear()
        filtered = [s for s in self._all_sessions if not self._filter_query or self._filter_query in s.title.lower()]

        for s in filtered:
            item = QListWidgetItem(self.list_widget)
            item.setData(Qt.ItemDataRole.UserRole, s.id)

            is_active = s.id == self._active_session_id
            row_widget = SessionItemWidget(s, is_active=is_active)
            row_widget.renamed.connect(self.session_renamed.emit)
            row_widget.deleted.connect(self.session_deleted.emit)
            row_widget.exported.connect(self.session_exported.emit)

            item.setSizeHint(row_widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row_widget)

            if is_active:
                self.list_widget.setCurrentItem(item)

    @Slot(QListWidgetItem)
    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        s_id = item.data(Qt.ItemDataRole.UserRole)
        if s_id and s_id != self._active_session_id:
            self._active_session_id = s_id
            self.session_selected.emit(s_id)
            self._render_list()

    def refresh_theme(self, profile: Any) -> None:
        """Réactualise dynamiquement les couleurs et tokens lors d'un changement de thème."""
        self.setStyleSheet(f"""
            ConsultantSessionSidebar {{
                background-color: {profile.bg_sidebar};
            }}
        """)
        self._render_list()

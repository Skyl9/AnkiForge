"""
EmbeddedCardTableWidget — Tableau compact de cartes Anki intégré dans le fil de chat du Consultant IA.

Affiche une sélection de notes retournées par un outil MCP (diagnostic, FTS5, recherche) sous forme d'un
tableau tabulaire défilable avec colonnes ID, Modèle, Recto, Verso et action d'ouverture directe dans
l'Éditeur de notes. Respecte le principe d'immuabilité conversationnelle via freeze().

Qt PySide6 equivalent: QFrame > QVBoxLayout(header + QTableWidget)
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class EmbeddedCardTableWidget(QFrame):
    """
    Tableau compact et fluide de cartes Anki inséré dans une bulle de chat du Consultant IA.

    Affiche les colonnes : ID • Modèle • Recto (tronqué) • Verso (tronqué) • Action ↗.
    Supporte le tri par colonne, le mode figé (is_frozen) et refresh_theme().

    Qt PySide6 equivalent: QFrame héritant de QWidget
    DESIGN.md: EmbeddedCardTableWidget — token bg=BG_PANEL, border=BORDER_COLOR, accent=ACCENT_PRIMARY
    """

    open_editor_requested = Signal(int)  # note_id
    """Emis lorsque l'utilisateur clique sur ↗ pour ouvrir la note dans l'Éditeur."""

    def __init__(
        self,
        card_rows: list[dict[str, Any]],
        title: str = "Cartes retournées",
        parent: QWidget | None = None,
    ) -> None:
        """
        Args:
            card_rows: Liste de dicts avec clés : id, model, front, back.
            title: Titre affiché dans l'en-tête du tableau.
        """
        super().__init__(parent)
        self.is_frozen: bool = False
        self._card_rows = card_rows

        self.setObjectName("EmbeddedCardTableWidget")
        self._setup_ui(title)
        self._populate(card_rows)
        self._apply_theme()

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _setup_ui(self, title: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- En-tête ---
        header_container = QWidget()
        header_container.setObjectName("EmbeddedCardTableHeader")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(10, 8, 10, 8)
        header_layout.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.table", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        header_layout.addWidget(icon_lbl)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("EmbeddedCardTableTitle")

        header_layout.addWidget(self.lbl_title, 1)

        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("EmbeddedCardTableCount")
        header_layout.addWidget(self.lbl_count)

        self.lbl_frozen_badge = QLabel("🔒 Figé")
        self.lbl_frozen_badge.setVisible(False)
        self.lbl_frozen_badge.setObjectName("EmbeddedCardFrozenBadge")
        header_layout.addWidget(self.lbl_frozen_badge)

        layout.addWidget(header_container)

        # --- Tableau ---
        self.table = QTableWidget()
        self.table.setObjectName("EmbeddedCardTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Modèle", "Recto", "Verso", ""])
        self.table.horizontalHeader().setSortIndicatorShown(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(4, 34)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(False)
        self.table.setMaximumHeight(280)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        layout.addWidget(self.table)

    def _populate(self, card_rows: list[dict[str, Any]]) -> None:
        """Remplit le tableau avec les données de cartes."""
        self.table.setRowCount(len(card_rows))
        self.lbl_count.setText(f"{len(card_rows)} carte{'s' if len(card_rows) > 1 else ''}")

        for row_idx, row in enumerate(card_rows):
            note_id = int(row.get("id", 0))
            model_name = str(row.get("model", "—"))
            front_text = self._truncate(str(row.get("front", "")), 60)
            back_text = self._truncate(str(row.get("back", "")), 60)

            item_id = QTableWidgetItem(str(note_id))
            item_id.setData(Qt.ItemDataRole.UserRole, note_id)
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_model = QTableWidgetItem(model_name)
            item_front = QTableWidgetItem(front_text)
            item_back = QTableWidgetItem(back_text)

            self.table.setItem(row_idx, 0, item_id)
            self.table.setItem(row_idx, 1, item_model)
            self.table.setItem(row_idx, 2, item_front)
            self.table.setItem(row_idx, 3, item_back)

            # Bouton ↗ Ouvrir dans l'Éditeur
            btn_open = QPushButton()
            btn_open.setIcon(load_phosphor_icon("ph.arrow-square-out", color=DesignTokens.ACCENT_PRIMARY))
            btn_open.setFixedSize(28, 26)
            btn_open.setToolTip(f"Ouvrir la note #{note_id} dans l'Éditeur")
            btn_open.clicked.connect(lambda _, nid=note_id: self.open_editor_requested.emit(nid))

            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(3, 2, 3, 2)
            cell_layout.addWidget(btn_open)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row_idx, 4, cell_widget)

        self.table.resizeRowsToContents()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_rows(self, card_rows: list[dict[str, Any]]) -> None:
        """Met à jour les données du tableau avec une nouvelle liste de cartes."""
        if self.is_frozen:
            logger.debug("EmbeddedCardTableWidget.update_rows ignoré : widget figé.")
            return
        self._card_rows = card_rows
        self._populate(card_rows)

    def freeze(self, timestamp: str = "") -> None:
        """Fige le widget en mode immuable : désactive les boutons et affiche un badge de statut."""
        if self.is_frozen:
            return
        self.is_frozen = True
        # Désactiver les boutons d'ouverture
        for row_idx in range(self.table.rowCount()):
            cell = self.table.cellWidget(row_idx, 4)
            if cell:
                for btn in cell.findChildren(QPushButton):
                    btn.setEnabled(False)
        badge_text = f"🔒 Figé{f' · {timestamp}' if timestamp else ''}"
        self.lbl_frozen_badge.setText(badge_text)
        self.lbl_frozen_badge.setVisible(True)
        logger.debug("EmbeddedCardTableWidget figé.")

    def refresh_theme(self) -> None:
        """Réapplique les tokens DesignTokens après un changement de thème."""
        self._apply_theme()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """Tronque le texte à max_len caractères en ajoutant '…'."""
        # Supprime les balises HTML pour la prévisualisation
        import re

        clean = re.sub(r"<[^>]+>", "", text).strip()
        if len(clean) > max_len:
            return clean[:max_len] + "…"
        return clean

    def _apply_theme(self) -> None:
        """Applique le style DesignTokens au widget."""
        self.setStyleSheet(f"""
            QFrame#EmbeddedCardTableWidget {{
                background: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QWidget#EmbeddedCardTableHeader {{
                background: {DesignTokens.BG_SIDEBAR};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px {DesignTokens.RADIUS_MD}px 0 0;
            }}
            QLabel#EmbeddedCardTableTitle {{
                font-weight: bold;
                font-size: 11px;
                color: {DesignTokens.TEXT_SECONDARY};
                letter-spacing: 0.3px;
                border: none;
            }}
            QLabel#EmbeddedCardTableCount {{
                font-size: 10px;
                color: {DesignTokens.TEXT_MUTED};
                border: none;
            }}
            QLabel#EmbeddedCardFrozenBadge {{
                font-size: 10px;
                color: {DesignTokens.TEXT_MUTED};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 1px 6px;
            }}
            QTableWidget#EmbeddedCardTable {{
                background: {DesignTokens.BG_PANEL};
                alternate-background-color: {DesignTokens.BG_SIDEBAR};
                border: none;
                gridline-color: {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                selection-background-color: {DesignTokens.BG_ACTIVE};
            }}
            QHeaderView::section {{
                background: {DesignTokens.BG_SIDEBAR};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px 6px;
            }}
            QScrollBar:vertical {{
                width: 6px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {DesignTokens.BORDER_COLOR};
                border-radius: 3px;
            }}
        """)

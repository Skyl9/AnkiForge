"""Onglet « Clavier » des Paramètres AnkiForge (KeyboardTab).

Permet de visualiser l'ensemble des raccourcis déclaratifs de l'application,
de rechercher par action ou séquence, de filtrer par catégorie, de remapper par appui réel,
et de réinitialiser unitairement ou globalement les surcharges utilisateur.
Conforme à l'ADR 0013 et à l'ADR 0032 (notamment §9).
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components.buttons import SecondaryButton
from ankiforge.ui.shortcuts.catalog import (
    get_shortcut_catalog,
    get_shortcut_definition,
)
from ankiforge.ui.shortcuts.models import (
    ShortcutCategory,
    ShortcutId,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components import SettingsCard
from ankiforge.ui.widgets.settings_modal.dialogs.shortcut_capture_dialog import (
    ShortcutCaptureDialog,
)
from ankiforge.ui.widgets.settings_modal.dirty import SettingsDirtyMixin
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

DOC_SHORTCUTS_URL = "https://skyl9.github.io/AnkiForge/guides/raccourcis_clavier/"


class KeyboardTab(SettingsDirtyMixin, QWidget):
    """Onglet de configuration et personnalisation des raccourcis clavier."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial_overrides: dict[str, str] = {}
        self._pending_overrides: dict[str, str] = {}
        self._row_to_id: list[ShortcutId] = []

        self._load_initial_state()
        self._setup_ui()
        self._populate_table()

    def _load_initial_state(self) -> None:
        """Charge les surcharges existantes depuis SettingsService."""
        self._initial_overrides = SettingsService.get_all_shortcut_overrides()
        self._pending_overrides = dict(self._initial_overrides)

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── 1. CARTE DE CONTRÔLE ET RECHERCHE ────────────────────────────────
        self.card_controls = SettingsCard(self.content_widget)
        ctrl_layout = QVBoxLayout(self.card_controls)
        ctrl_layout.setContentsMargins(14, 12, 14, 12)
        ctrl_layout.setSpacing(10)

        # Ligne de titre et description
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel(self.card_controls)
        icon_lbl.setPixmap(load_phosphor_icon("ph.key", color=DesignTokens.ACCENT_PRIMARY).pixmap(22, 22))
        header_row.addWidget(icon_lbl)

        lbl_title = QLabel(self.tr("Personnalisation des Raccourcis Clavier"), self.card_controls)
        lbl_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        header_row.addWidget(lbl_title)
        header_row.addStretch()

        self.btn_doc = SecondaryButton(self.tr("Documentation"))
        self.btn_doc.setAutoDefault(False)
        self.btn_doc.setIcon(load_phosphor_icon("ph.book-open"))
        self.btn_doc.setToolTip(self.tr("Ouvrir la page de référence des raccourcis clavier"))
        self.btn_doc.clicked.connect(self._on_open_docs_clicked)
        header_row.addWidget(self.btn_doc)

        self.btn_reset_all = SecondaryButton(self.tr("Réinitialiser tout"))
        self.btn_reset_all.setAutoDefault(False)
        self.btn_reset_all.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise"))
        self.btn_reset_all.setToolTip(self.tr("Restaurer tous les raccourcis à leurs valeurs d'origine"))
        self.btn_reset_all.clicked.connect(self.reset_all)
        header_row.addWidget(self.btn_reset_all)

        ctrl_layout.addLayout(header_row)

        lbl_desc = QLabel(
            self.tr("Consultez et réassignez les actions du clavier. Les conflits sont automatiquement prévenus."),
            self.card_controls,
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        ctrl_layout.addWidget(lbl_desc)

        # Ligne de filtre et recherche
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.le_search = QLineEdit(self.card_controls)
        self.le_search.setPlaceholderText(self.tr("Rechercher une action ou un raccourci..."))
        self.le_search.setClearButtonEnabled(True)
        self.le_search.textChanged.connect(self._filter_table)
        filter_row.addWidget(self.le_search, 2)

        self.cb_category = QComboBox(self.card_controls)
        self.cb_category.addItem(self.tr("Toutes les catégories"), None)
        for cat in ShortcutCategory:
            self.cb_category.addItem(cat.value, cat.value)
        self.cb_category.currentIndexChanged.connect(self._filter_table)
        filter_row.addWidget(self.cb_category, 1)

        ctrl_layout.addLayout(filter_row)
        layout.addWidget(self.card_controls)

        # ── 2. TABLE DES RACCOURCIS ──────────────────────────────────────────
        self.table_shortcuts = QTableWidget(0, 6, self.content_widget)
        self.table_shortcuts.setHorizontalHeaderLabels(
            [
                self.tr("Action"),
                self.tr("Catégorie"),
                self.tr("Portée"),
                self.tr("Raccourci"),
                self.tr("État"),
                self.tr("Actions"),
            ]
        )
        self.table_shortcuts.horizontalHeader().setStretchLastSection(False)
        self.table_shortcuts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_shortcuts.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_shortcuts.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_shortcuts.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_shortcuts.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_shortcuts.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table_shortcuts.setColumnWidth(5, 170)
        self.table_shortcuts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_shortcuts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_shortcuts.verticalHeader().setVisible(False)
        self.table_shortcuts.verticalHeader().setDefaultSectionSize(40)
        self.table_shortcuts.setMinimumHeight(380)

        self.table_shortcuts.cellDoubleClicked.connect(self._on_cell_double_clicked)

        self._apply_table_styles()
        layout.addWidget(self.table_shortcuts)

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

    def _apply_table_styles(self) -> None:
        self.table_shortcuts.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 6px 8px;
            }}
            QTableWidget::item {{
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
        """)

    def _populate_table(self) -> None:
        """Remplit la table avec toutes les actions du catalogue déclaratif."""
        catalog = get_shortcut_catalog()
        self.table_shortcuts.setRowCount(len(catalog))
        self._row_to_id = []

        for row, (sc_id, defn) in enumerate(catalog.items()):
            self._row_to_id.append(sc_id)

            # Col 0 : Titre de l'action
            item_title = QTableWidgetItem(defn.title)
            tooltip_parts = [defn.title, f"ID: {sc_id.value}"]
            if defn.description:
                tooltip_parts.append(defn.description)
            item_title.setToolTip("\n".join(tooltip_parts))
            item_title.setData(Qt.ItemDataRole.UserRole, sc_id.value)
            self.table_shortcuts.setItem(row, 0, item_title)

            # Col 1 : Catégorie
            item_cat = QTableWidgetItem(defn.category.value)
            item_cat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_shortcuts.setItem(row, 1, item_cat)

            # Col 2 : Portée
            item_scope = QTableWidgetItem(defn.scope.name)
            item_scope.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_shortcuts.setItem(row, 2, item_scope)

            # Séquence effective (override en attente ou défaut)
            is_overridden = sc_id.value in self._pending_overrides
            current_seq = self._pending_overrides[sc_id.value] if is_overridden else defn.default_sequence

            # Col 3 : Raccourci
            item_seq = QTableWidgetItem(current_seq)
            item_seq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_shortcuts.setItem(row, 3, item_seq)

            # Col 4 : État (Défaut / Modifié)
            state_text = self.tr("Personnalisé") if is_overridden else self.tr("Défaut")
            item_state = QTableWidgetItem(state_text)
            item_state.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_overridden:
                item_state.setForeground(Qt.GlobalColor.darkGreen)
            else:
                item_state.setForeground(Qt.GlobalColor.gray)
            self.table_shortcuts.setItem(row, 4, item_state)

            # Col 5 : Actions ("Modifier" + "Réinitialiser")
            actions_widget = QWidget(self.table_shortcuts)
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)

            btn_edit = SecondaryButton(self.tr("Modifier"))
            btn_edit.setAutoDefault(False)
            btn_edit.setFixedHeight(24)
            btn_edit.clicked.connect(lambda _, s=sc_id: self.open_capture_dialog(s))
            actions_layout.addWidget(btn_edit)

            btn_reset = SecondaryButton(self.tr("Défaut"))
            btn_reset.setAutoDefault(False)
            btn_reset.setFixedHeight(24)
            btn_reset.setEnabled(is_overridden)
            btn_reset.clicked.connect(lambda _, s=sc_id: self.reset_single(s))
            actions_layout.addWidget(btn_reset)

            self.table_shortcuts.setCellWidget(row, 5, actions_widget)

        self._filter_table()

    def _filter_table(self) -> None:
        """Applique les filtres de recherche et de catégorie sur les lignes."""
        query = self.le_search.text().lower().strip()
        selected_cat = self.cb_category.currentData()

        for row in range(self.table_shortcuts.rowCount()):
            item_title = self.table_shortcuts.item(row, 0)
            item_cat = self.table_shortcuts.item(row, 1)
            item_seq = self.table_shortcuts.item(row, 3)

            title_text = item_title.text().lower() if item_title else ""
            cat_text = item_cat.text() if item_cat else ""
            seq_text = item_seq.text().lower() if item_seq else ""
            id_text = str(item_title.data(Qt.ItemDataRole.UserRole) or "").lower() if item_title else ""

            match_text = not query or (query in title_text or query in seq_text or query in id_text)
            match_cat = not selected_cat or cat_text == selected_cat

            self.table_shortcuts.setRowHidden(row, not (match_text and match_cat))

    def _on_cell_double_clicked(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._row_to_id):
            sc_id = self._row_to_id[row]
            self.open_capture_dialog(sc_id)

    def find_row_by_id(self, shortcut_id_val: str) -> int | None:
        """Trouve l'indice de ligne correspondant à un identifiant d'action."""
        for r in range(self.table_shortcuts.rowCount()):
            item = self.table_shortcuts.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == shortcut_id_val:
                return r
        return None

    def open_capture_dialog(self, shortcut_id: ShortcutId) -> None:
        """Ouvre le dialogue modal de capture interactif."""
        defn = get_shortcut_definition(shortcut_id)
        current_seq = self._pending_overrides.get(shortcut_id.value, defn.default_sequence)

        dialog = ShortcutCaptureDialog(
            shortcut_id=shortcut_id,
            current_sequence=current_seq,
            current_overrides=self._pending_overrides,
            parent=self.window() if self.window() is not None else self,
        )

        if dialog.exec():
            new_seq = dialog.captured_sequence
            if new_seq:
                self.apply_override(shortcut_id, new_seq)

    def apply_override(self, shortcut_id: ShortcutId, new_sequence: str) -> None:
        """Applique une nouvelle séquence en mémoire pour l'action donnée."""
        defn = get_shortcut_definition(shortcut_id)
        clean = new_sequence.strip()
        if clean.upper() == defn.default_sequence.strip().upper():
            self._pending_overrides.pop(shortcut_id.value, None)
        else:
            self._pending_overrides[shortcut_id.value] = clean

        self._populate_table()

    def reset_single(self, shortcut_id: ShortcutId) -> None:
        """Restaure une action à sa valeur par défaut."""
        if shortcut_id.value in self._pending_overrides:
            self._pending_overrides.pop(shortcut_id.value, None)
            self._populate_table()

    def reset_all(self) -> None:
        """Restaure l'intégralité des raccourcis à leurs valeurs d'origine."""
        if self._pending_overrides:
            self._pending_overrides.clear()
            self._populate_table()

    def _on_open_docs_clicked(self) -> None:
        """Ouvre la page de référence de la documentation."""
        QDesktopServices.openUrl(QUrl(DOC_SHORTCUTS_URL))

    # ── Cycle de vie SettingsDirtyMixin ───────────────────────────────────────

    def has_pending_changes(self) -> bool:
        """Indique si des surcharges de raccourcis sont en attente d'enregistrement."""
        return self._pending_overrides != self._initial_overrides

    def save_tab(self) -> tuple[bool, None, None]:
        """Persiste les surcharges dans SettingsService si modifiées."""
        has_change = self.has_pending_changes()
        if not has_change:
            return (False, None, None)

        catalog = get_shortcut_catalog()

        # Enregistrer les surcharges actuelles
        for sc_id_val, seq in list(self._pending_overrides.items()):
            default_seq = catalog[ShortcutId(sc_id_val)].default_sequence if ShortcutId(sc_id_val) in catalog else None
            SettingsService.set_shortcut_override(sc_id_val, seq, default_sequence=default_seq)

        # Supprimer les surcharges qui ont été réinitialisées
        for sc_id_val in list(self._initial_overrides.keys()):
            if sc_id_val not in self._pending_overrides:
                SettingsService.remove_shortcut_override(sc_id_val)

        # Si toutes les surcharges ont été vidées
        if not self._pending_overrides and self._initial_overrides:
            SettingsService.clear_all_shortcut_overrides()

        self._initial_overrides = dict(self._pending_overrides)
        self._populate_table()
        logger.info("Surcharges de raccourcis enregistrées avec succès")
        return (True, None, None)

    def save_settings(self) -> tuple[bool, None, None]:
        """Alias pour compatibilité avec SettingsModal._save_all."""
        return self.save_tab()

    def refresh_theme(self, profile: Any) -> None:
        """Met à jour les styles dynamiques de l'onglet lors d'un changement de thème."""
        if hasattr(self, "card_controls"):
            self.card_controls.refresh_theme(profile)
        self._apply_table_styles()

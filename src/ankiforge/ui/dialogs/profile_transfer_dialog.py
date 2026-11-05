"""Dialogue de transfert élargi de contenu entre profils (notes, cartes, modèles, médias).

Architecture moderne conforme aux DesignTokens et au référentiel DESIGN.md.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.profile_content_transfer import ProfileContentTransfer, TransferReport
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.paths import get_active_profile

logger = logging.getLogger(__name__)


class ProfileTransferDialog(QDialog):
    """Dialogue permettant de transférer des paquets, des notes, des modèles de cartes et des médias depuis un autre profil utilisateur vers le profil actif."""

    transfer_completed = Signal(object)

    def __init__(
        self,
        profiles_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profiles_dir = profiles_dir
        self.pm = ProfileManager()
        if profiles_dir is not None:
            self.pm.profiles_dir = profiles_dir

        self.active_profile = get_active_profile() or "default"
        self._is_updating_preview = False

        self.setWindowTitle(self.tr("Transférer du contenu entre Espaces de Travail — AnkiForge"))
        self.setMinimumSize(640, 680)
        self.resize(680, 720)
        self.setModal(True)

        self._setup_ui()
        self._load_source_profiles()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # ── 1. En-tête ─────────────────────────────────────────────────────────
        header_card = QFrame()
        header_card.setObjectName("TransferHeaderCard")
        header_card.setStyleSheet(f"""
            QFrame#TransferHeaderCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 12px;
            }}
        """)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(14)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.logo_lbl = QLabel()
        self.logo_lbl.setPixmap(load_phosphor_icon("arrows-left-right", color=DesignTokens.ACCENT_PRIMARY).pixmap(32, 32))
        self.logo_lbl.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(self.logo_lbl)

        title_layout = QVBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        self.title_lbl = QLabel(self.tr("Transfert de Contenu Inter-Profils"))
        self.title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.subtitle_lbl = QLabel(tr("Copier des paquets, notes et médias vers le profil actif « %1 ».", self.active_profile))
        self.subtitle_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.subtitle_lbl.setWordWrap(True)

        title_layout.addWidget(self.title_lbl)
        title_layout.addWidget(self.subtitle_lbl)
        header_layout.addLayout(title_layout, 1)

        layout.addWidget(header_card)

        # ── 2. Sélection du profil source ───────────────────────────────────────
        source_frame = QFrame()
        source_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 8px 12px;
            }}
        """)
        source_layout = QHBoxLayout(source_frame)
        source_layout.setContentsMargins(12, 8, 12, 8)
        source_layout.setSpacing(10)

        lbl_source = QLabel(self.tr("Espace source :"))
        lbl_source.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.DemiBold))
        lbl_source.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        source_layout.addWidget(lbl_source)

        self.combo_source = QComboBox()
        self.combo_source.setFixedHeight(34)
        self.combo_source.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 10px;
                font-size: 11px;
            }}
            QComboBox:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                selection-background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        self.combo_source.currentTextChanged.connect(self._on_source_profile_changed)
        source_layout.addWidget(self.combo_source, 1)

        layout.addWidget(source_frame)

        # ── 3. Onglets de sélection de contenu (Decks / Tags) ───────────────────
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                background: {DesignTokens.BG_PANEL};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QTabBar::tab {{
                background: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }}
            QTabBar::tab:selected {{
                background: {DesignTokens.BG_PANEL};
                color: {DesignTokens.ACCENT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # Onglet 1 : Decks
        tab_decks = QWidget()
        decks_layout = QVBoxLayout(tab_decks)
        decks_layout.setContentsMargins(12, 10, 12, 10)
        decks_layout.setSpacing(8)

        self.list_decks = QListWidget()
        self.list_decks.setStyleSheet(self._list_stylesheet())
        self.list_decks.itemChanged.connect(self._on_item_changed)

        deck_actions = QHBoxLayout()
        self.btn_select_all_decks = SecondaryButton("Tout cocher", tooltip=self.tr("Sélectionner tous les paquets"))
        self.btn_select_all_decks.setFixedHeight(28)
        self.btn_select_all_decks.clicked.connect(lambda: self._set_all_checked(self.list_decks, True))
        self.btn_deselect_all_decks = SecondaryButton("Tout décocher", tooltip=self.tr("Désélectionner tous les paquets"))
        self.btn_deselect_all_decks.setFixedHeight(28)
        self.btn_deselect_all_decks.clicked.connect(lambda: self._set_all_checked(self.list_decks, False))
        deck_actions.addWidget(self.btn_select_all_decks)
        deck_actions.addWidget(self.btn_deselect_all_decks)
        deck_actions.addStretch()
        decks_layout.addLayout(deck_actions)

        decks_layout.addWidget(self.list_decks, 1)

        self.tab_widget.addTab(tab_decks, self.tr("Paquets (Decks)"))

        # Onglet 2 : Tags
        tab_tags = QWidget()
        tags_layout = QVBoxLayout(tab_tags)
        tags_layout.setContentsMargins(12, 10, 12, 10)
        tags_layout.setSpacing(8)

        self.list_tags = QListWidget()
        self.list_tags.setStyleSheet(self._list_stylesheet())
        self.list_tags.itemChanged.connect(self._on_item_changed)

        tag_actions = QHBoxLayout()
        self.btn_select_all_tags = SecondaryButton("Tout cocher", tooltip=self.tr("Sélectionner tous les tags"))
        self.btn_select_all_tags.setFixedHeight(28)
        self.btn_select_all_tags.clicked.connect(lambda: self._set_all_checked(self.list_tags, True))
        self.btn_deselect_all_tags = SecondaryButton("Tout décocher", tooltip=self.tr("Désélectionner tous les tags"))
        self.btn_deselect_all_tags.setFixedHeight(28)
        self.btn_deselect_all_tags.clicked.connect(lambda: self._set_all_checked(self.list_tags, False))
        tag_actions.addWidget(self.btn_select_all_tags)
        tag_actions.addWidget(self.btn_deselect_all_tags)
        tag_actions.addStretch()
        tags_layout.addLayout(tag_actions)

        tags_layout.addWidget(self.list_tags, 1)

        self.tab_widget.addTab(tab_tags, self.tr("Tags"))

        # Onglet 3 : Modèles de cartes
        tab_models = QWidget()
        models_layout = QVBoxLayout(tab_models)
        models_layout.setContentsMargins(12, 10, 12, 10)
        models_layout.setSpacing(8)

        self.list_models = QListWidget()
        self.list_models.setStyleSheet(self._list_stylesheet())
        self.list_models.itemChanged.connect(self._on_item_changed)

        models_actions = QHBoxLayout()
        self.btn_select_all_models = SecondaryButton("Tout cocher", tooltip=self.tr("Sélectionner tous les modèles de cartes"))
        self.btn_select_all_models.setFixedHeight(28)
        self.btn_select_all_models.clicked.connect(lambda: self._set_all_checked(self.list_models, True))
        self.btn_deselect_all_models = SecondaryButton("Tout décocher", tooltip=self.tr("Désélectionner tous les modèles de cartes"))
        self.btn_deselect_all_models.setFixedHeight(28)
        self.btn_deselect_all_models.clicked.connect(lambda: self._set_all_checked(self.list_models, False))
        models_actions.addWidget(self.btn_select_all_models)
        models_actions.addWidget(self.btn_deselect_all_models)
        models_actions.addStretch()
        models_layout.addLayout(models_actions)

        models_layout.addWidget(self.list_models, 1)

        self.tab_widget.addTab(tab_models, self.tr("Modèles de cartes"))

        # Onglet 4 : Albums
        tab_albums = QWidget()
        albums_layout = QVBoxLayout(tab_albums)
        albums_layout.setContentsMargins(12, 10, 12, 10)
        albums_layout.setSpacing(8)

        self.list_albums = QListWidget()
        self.list_albums.setStyleSheet(self._list_stylesheet())
        self.list_albums.itemChanged.connect(self._on_item_changed)

        albums_actions = QHBoxLayout()
        self.btn_select_all_albums = SecondaryButton("Tout cocher", tooltip=self.tr("Sélectionner tous les albums"))
        self.btn_select_all_albums.setFixedHeight(28)
        self.btn_select_all_albums.clicked.connect(lambda: self._set_all_checked(self.list_albums, True))
        self.btn_deselect_all_albums = SecondaryButton("Tout décocher", tooltip=self.tr("Désélectionner tous les albums"))
        self.btn_deselect_all_albums.setFixedHeight(28)
        self.btn_deselect_all_albums.clicked.connect(lambda: self._set_all_checked(self.list_albums, False))
        albums_actions.addWidget(self.btn_select_all_albums)
        albums_actions.addWidget(self.btn_deselect_all_albums)
        albums_actions.addStretch()
        albums_layout.addLayout(albums_actions)

        albums_layout.addWidget(self.list_albums, 1)

        self.tab_widget.addTab(tab_albums, self.tr("Albums"))

        layout.addWidget(self.tab_widget, 1)

        # ── 4. Options de réconciliation ───────────────────────────────────────
        self.chk_update_existing = QCheckBox(self.tr("Mettre à jour les notes existantes si le GUID existe déjà (crée une nouvelle version)"))
        self.chk_update_existing.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.chk_update_existing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_update_existing.setStyleSheet(f"""
            QCheckBox {{
                color: {DesignTokens.TEXT_SECONDARY};
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        layout.addWidget(self.chk_update_existing)

        # ── 5. Carte synthétique d'estimation en direct ────────────────────────
        summary_card = QFrame()
        summary_card.setObjectName("TransferSummaryCard")
        summary_card.setStyleSheet(f"""
            QFrame#TransferSummaryCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(14, 10, 14, 10)
        summary_layout.setSpacing(16)

        # 6 métriques : Notes, Modèles de carte, Cartes, Médias, Modèles sélectionnés, Albums sélectionnés
        self.lbl_metric_notes = self._create_metric_widget(self.tr("NOTES"), "0")
        self.lbl_metric_models = self._create_metric_widget(self.tr("MODÈLES DE CARTES"), "0")
        self.lbl_metric_cards = self._create_metric_widget(self.tr("CARTES"), "0")
        self.lbl_metric_media = self._create_metric_widget(self.tr("MÉDIAS"), "0 (0 Ko)")
        self.lbl_metric_models_selected = self._create_metric_widget(self.tr("MODÈLES SÉLECTIONNÉS"), "0")
        self.lbl_metric_albums_selected = self._create_metric_widget(self.tr("ALBUMS SÉLECTIONNÉS"), "0")

        summary_layout.addWidget(self.lbl_metric_notes[0], 1)
        summary_layout.addWidget(self.lbl_metric_models[0], 1)
        summary_layout.addWidget(self.lbl_metric_cards[0], 1)
        summary_layout.addWidget(self.lbl_metric_media[0], 1)
        summary_layout.addWidget(self.lbl_metric_models_selected[0], 1)
        summary_layout.addWidget(self.lbl_metric_albums_selected[0], 1)

        layout.addWidget(summary_card)

        # ── 6. Boutons d'action ────────────────────────────────────────────────
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(10)

        bottom_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler", tooltip=self.tr("Fermer sans rien transférer"))
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        self.btn_transfer = PrimaryButton("Transférer le Contenu", tooltip=self.tr("Lancer l'importation atomique du contenu sélectionné"))
        self.btn_transfer.setFixedHeight(36)
        self.btn_transfer.setIcon(load_on_accent_icon("arrow-right"))
        self.btn_transfer.clicked.connect(self._on_transfer_clicked)
        bottom_layout.addWidget(self.btn_transfer)

        layout.addLayout(bottom_layout)

    def _create_metric_widget(self, label: str, default_val: str) -> tuple[QWidget, QLabel]:
        widget = QWidget()
        box = QVBoxLayout(widget)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)

        lbl_title = QLabel(label)
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 8, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        lbl_val = QLabel(default_val)
        lbl_val.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_val.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; border: none; background: transparent;")

        box.addWidget(lbl_title)
        box.addWidget(lbl_val)
        return widget, lbl_val

    def _list_stylesheet(self) -> str:
        return f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                outline: none;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 6px 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """

    def _load_source_profiles(self) -> None:
        """Remplit la liste déroulante des profils disponibles (autres que l'actif)."""
        profiles = self.pm.list_profiles()
        available = [p for p in profiles if p != self.active_profile]

        self.combo_source.clear()
        if not available:
            self.combo_source.addItem(self.tr("Aucun autre espace de travail disponible"))
            self.combo_source.setEnabled(False)
            self.btn_transfer.setEnabled(False)
            return

        self.combo_source.setEnabled(True)
        self.btn_transfer.setEnabled(True)
        for p in available:
            self.combo_source.addItem(p)

    def _on_source_profile_changed(self, profile_name: str) -> None:
        if not profile_name or profile_name == "Aucun autre espace de travail disponible":
            return
        self._populate_contenu_source(profile_name)
        self._update_preview()

    def _populate_contenu_source(self, profile_name: str) -> None:
        """Remplit les quatre listes cochables (paquets, tags, modèles de cartes, albums)."""
        self._is_updating_preview = True
        try:
            self.list_decks.clear()
            decks = ProfileContentTransfer.list_decks(profile_name, profiles_dir=self.profiles_dir)
            for d in decks:
                item = QListWidgetItem(d, self.list_decks)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)

            self.list_tags.clear()
            tags = ProfileContentTransfer.list_tags(profile_name, profiles_dir=self.profiles_dir)
            for t in tags:
                item = QListWidgetItem(t, self.list_tags)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)

            self.list_models.clear()
            modeles = ProfileContentTransfer.list_note_types(profile_name, profiles_dir=self.profiles_dir)
            for m in modeles:
                nom = str(m["name"])
                item = QListWidgetItem(nom, self.list_models)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, nom)
                item.setToolTip(tr("Modèle de carte : %1\nGabarits : %2", nom, m["templates_count"]))

            self.list_albums.clear()
            albums = ProfileContentTransfer.list_albums(profile_name, profiles_dir=self.profiles_dir)
            for a in albums:
                titre = str(a["title"])
                pages = int(a.get("total_pages") or 0)
                label = tr("%1 (%2 planche%3)", titre, pages, "s" if pages > 1 else "")
                item = QListWidgetItem(label, self.list_albums)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setData(Qt.ItemDataRole.UserRole, int(a["id"]))
                item.setToolTip(tr("Album : %1\nNombre de planches : %2", titre, pages))
        finally:
            self._is_updating_preview = False

    def _set_all_checked(self, list_widget: QListWidget, checked: bool) -> None:
        self._is_updating_preview = True
        try:
            state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item:
                    item.setCheckState(state)
        finally:
            self._is_updating_preview = False
        self._update_preview()

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        if not self._is_updating_preview:
            self._update_preview()

    def get_selected_decks(self) -> list[str]:
        decks: list[str] = []
        for i in range(self.list_decks.count()):
            item = self.list_decks.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                decks.append(item.text())
        return decks

    def get_selected_tags(self) -> list[str]:
        tags: list[str] = []
        for i in range(self.list_tags.count()):
            item = self.list_tags.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                tags.append(item.text())
        return tags

    def get_selected_models(self) -> list[str]:
        modeles: list[str] = []
        for i in range(self.list_models.count()):
            item = self.list_models.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                modeles.append(str(data) if data is not None else item.text())
        return modeles

    def get_selected_albums(self) -> list[int]:
        albums: list[int] = []
        for i in range(self.list_albums.count()):
            item = self.list_albums.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data is not None:
                    albums.append(int(data))
        return albums

    def _update_preview(self) -> None:
        source_profile = self.combo_source.currentText()
        if not source_profile or not self.combo_source.isEnabled():
            return

        selected_decks = self.get_selected_decks()
        selected_tags = self.get_selected_tags()
        selected_models = self.get_selected_models()
        selected_albums = self.get_selected_albums()

        # Si aucun élément n'est coché, estimation à 0
        if not selected_decks and not selected_tags and not selected_models and not selected_albums:
            self.lbl_metric_notes[1].setText(self.tr("0"))
            self.lbl_metric_models[1].setText(self.tr("0"))
            self.lbl_metric_cards[1].setText(self.tr("0"))
            self.lbl_metric_media[1].setText(self.tr("0 (0 Ko)"))
            self.lbl_metric_models_selected[1].setText(self.tr("0"))
            self.lbl_metric_albums_selected[1].setText(self.tr("0"))
            return

        try:
            preview = ProfileContentTransfer.get_transfer_preview(
                source_profile=source_profile,
                deck_names=selected_decks,
                tag_names=selected_tags,
                model_names=selected_models,
                album_ids=selected_albums,
                profiles_dir=self.profiles_dir,
            )
            self.lbl_metric_notes[1].setText(str(preview["notes_count"]))
            self.lbl_metric_models[1].setText(str(preview["note_types_count"]))
            self.lbl_metric_cards[1].setText(str(preview["cards_count"]))
            media_str = f"{preview['media_count']} ({self._human_size(preview['total_media_size'])})"
            self.lbl_metric_media[1].setText(media_str)
            self.lbl_metric_models_selected[1].setText(str(preview.get("models_count", len(selected_models))))
            self.lbl_metric_albums_selected[1].setText(str(preview.get("albums_count", len(selected_albums))))
        except Exception as e:
            logger.warning("Erreur lors de la prévisualisation du transfert : %s", e)

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} o"
        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} Ko"
        return f"{size_bytes / (1024 * 1024):.1f} Mo"

    def _on_transfer_clicked(self) -> None:
        source_profile = self.combo_source.currentText()
        if not source_profile or not self.combo_source.isEnabled():
            return

        selected_decks = self.get_selected_decks()
        selected_tags = self.get_selected_tags()
        selected_models = self.get_selected_models()
        selected_albums = self.get_selected_albums()

        if not selected_decks and not selected_tags and not selected_models and not selected_albums:
            QMessageBox.warning(
                self,
                self.tr("Aucun élément sélectionné"),
                self.tr("Veuillez cocher au moins un paquet, un tag, un modèle de carte ou un album à transférer."),
            )
            return

        update_existing = self.chk_update_existing.isChecked()

        try:
            report: TransferReport = ProfileContentTransfer.transfer_content(
                source_profile=source_profile,
                deck_names=selected_decks,
                tag_names=selected_tags,
                update_existing_notes=update_existing,
                profiles_dir=self.profiles_dir,
            )

            modeles_importes = 0
            erreurs_modeles: list[str] = []
            for nom_modele in selected_models:
                try:
                    ProfileContentTransfer.import_note_type(
                        profile_name=source_profile,
                        note_type_id_or_name=nom_modele,
                        target_profile=None,
                        profiles_dir=self.profiles_dir,
                    )
                    modeles_importes += 1
                except Exception as err:
                    erreurs_modeles.append(f"{nom_modele}: {err}")

            albums_importes = 0
            erreurs_albums: list[str] = []
            for album_id in selected_albums:
                try:
                    ProfileContentTransfer.import_album(
                        profile_name=source_profile,
                        album_id_or_title=album_id,
                        target_profile=None,
                        profiles_dir=self.profiles_dir,
                    )
                    albums_importes += 1
                except Exception as err:
                    erreurs_albums.append(f"album #{album_id}: {err}")

            erreurs = list(report.errors) + erreurs_modeles + erreurs_albums

            msg = (
                f"Transfert terminé avec succès !\n\n"
                f"• Notes importées : {report.notes_imported}\n"
                f"• Notes mises à jour : {report.notes_updated}\n"
                f"• Notes ignorées (doublons) : {report.notes_skipped}\n"
                f"• Paquets créés : {report.decks_created}\n"
                f"• Modèles de carte créés : {report.note_types_created + modeles_importes}\n"
                f"• Albums importés : {albums_importes}\n"
                f"• Médias transférés : {report.media_transferred}"
            )
            if erreurs:
                msg += f"\n\n• Erreurs : {len(erreurs)}"
                QMessageBox.warning(
                    self,
                    self.tr("Transfert terminé avec des avertissements"),
                    tr("Le transfert s'est exécuté avec %1 erreur(s) :\n%2", len(erreurs), "\n".join(erreurs)),
                )
            QMessageBox.information(self, self.tr("Transfert Réussi"), msg)
            self.transfer_completed.emit(report)
            self.accept()
        except Exception as err:
            logger.error("Échec du transfert inter-profils : %s", err, exc_info=True)
            QMessageBox.critical(
                self,
                self.tr("Erreur de Transfert"),
                tr("Une erreur est survenue pendant le transfert :\n%1", err),
            )

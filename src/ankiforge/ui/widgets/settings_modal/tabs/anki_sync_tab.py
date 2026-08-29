import platform
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DeckModel
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import (
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon


class AnkiSyncTab(QWidget):
    """Onglet Formats Anki, Règles de Conflits, Compression et Répertoires locaux (Zéro AnkiConnect)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.lbl_anki_labels: List[QLabel] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : RÈGLES DE SMART MERGE & CONFLITS (RÈGLE 11) ────────────────
        self.lbl_sec_merge = QLabel("RÈGLES DE SMART MERGE & CONFLITS (RÈGLE 11)")
        self.lbl_sec_merge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_merge)

        self.card_merge = SettingsCard()
        merge_layout = QVBoxLayout(self.card_merge)
        merge_layout.setContentsMargins(14, 12, 14, 12)
        merge_layout.setSpacing(10)

        row_policy = QHBoxLayout()
        lbl_pol = QLabel("En cas de divergence de contenu :")
        lbl_pol.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_policy.addWidget(lbl_pol)
        self.lbl_anki_labels.append(lbl_pol)

        self.cb_conflict_policy = StyledComboBox()
        self.cb_conflict_policy.setMinimumWidth(260)
        self.cb_conflict_policy.setFixedHeight(28)
        self.cb_conflict_policy.addItem("Demander via la modale 3 panneaux (MergeView)", "ask")
        self.cb_conflict_policy.addItem("Écraser automatiquement par la Forge Locale", "local")
        self.cb_conflict_policy.addItem("Conserver la version distante d'Anki", "remote")
        saved_pol = str(SettingsService.get("anki/conflict_policy", "ask"))
        for i in range(self.cb_conflict_policy.count()):
            if self.cb_conflict_policy.itemData(i) == saved_pol:
                self.cb_conflict_policy.setCurrentIndex(i)
                break
        row_policy.addStretch()
        row_policy.addWidget(self.cb_conflict_policy)
        merge_layout.addLayout(row_policy)

        self.chk_silent_merge = QCheckBox("Fusionner silencieusement les déplacements de paquets et stats SRS (Règle d'or)")
        self.chk_silent_merge.setChecked(bool(SettingsService.get("anki/silent_meta_merge", True)))
        self.chk_silent_merge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_silent_merge.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px;")
        merge_layout.addWidget(self.chk_silent_merge)

        layout.addWidget(self.card_merge)

        # ── SECTION 2 : COMPRESSION ET FORMATS D'ARCHIVES ────────────────────
        self.lbl_sec_fmt = QLabel("COMPRESSION & FORMATS D'ARCHIVES (.APKG / .COLPKG)")
        self.lbl_sec_fmt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_fmt)

        self.card_fmt = SettingsCard()
        fmt_layout = QVBoxLayout(self.card_fmt)
        fmt_layout.setContentsMargins(14, 12, 14, 12)
        fmt_layout.setSpacing(10)

        row_comp = QHBoxLayout()
        lbl_comp = QLabel("Algorithme de compression des médias :")
        lbl_comp.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_comp.addWidget(lbl_comp)
        self.lbl_anki_labels.append(lbl_comp)

        self.cb_compression = StyledComboBox()
        self.cb_compression.setMinimumWidth(260)
        self.cb_compression.setFixedHeight(28)
        self.cb_compression.addItem("Zstandard (.apkg moderne - Rapide)", "zstd")
        self.cb_compression.addItem("ZIP Déflate standard (Compatibilité maximale)", "zip")
        saved_comp = str(SettingsService.get("anki/compression", "zstd"))
        for i in range(self.cb_compression.count()):
            if self.cb_compression.itemData(i) == saved_comp:
                self.cb_compression.setCurrentIndex(i)
                break
        row_comp.addStretch()
        row_comp.addWidget(self.cb_compression)
        fmt_layout.addLayout(row_comp)

        row_deck = QHBoxLayout()
        lbl_dk = QLabel("Paquet par défaut lors des imports rapides :")
        lbl_dk.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_deck.addWidget(lbl_dk)
        self.lbl_anki_labels.append(lbl_dk)

        self.cb_default_deck = StyledComboBox()
        self.cb_default_deck.setMinimumWidth(260)
        self.cb_default_deck.setFixedHeight(28)
        try:
            decks = list(DeckModel.select())
        except Exception:
            decks = []
        if not decks:
            self.cb_default_deck.addItem("Défaut")
        else:
            for d in decks:
                self.cb_default_deck.addItem(d.name, d.id)
        saved_deck_id = SettingsService.get("anki/default_deck_id", None)
        if saved_deck_id:
            for i in range(self.cb_default_deck.count()):
                if self.cb_default_deck.itemData(i) == saved_deck_id:
                    self.cb_default_deck.setCurrentIndex(i)
                    break
        row_deck.addStretch()
        row_deck.addWidget(self.cb_default_deck)
        fmt_layout.addLayout(row_deck)

        layout.addWidget(self.card_fmt)

        # ── SECTION 3 : RÉPERTOIRE DES COLLECTIONS ANKI LOCALES ──────────────
        self.lbl_sec_dir = QLabel("RÉPERTOIRE DES COLLECTIONS ANKI (HORS-LIGNE)")
        self.lbl_sec_dir.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_dir)

        self.card_dir = SettingsCard()
        dir_layout = QVBoxLayout(self.card_dir)
        dir_layout.setContentsMargins(14, 12, 14, 12)
        dir_layout.setSpacing(8)

        row_dir = QHBoxLayout()
        lbl_d = QLabel("Dossier Anki2 local :")
        lbl_d.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_dir.addWidget(lbl_d)
        self.lbl_anki_labels.append(lbl_d)

        home = Path.home()
        if platform.system() == "Darwin":
            default_anki_dir = str(home / "Library" / "Application Support" / "Anki2")
        elif platform.system() == "Windows":
            default_anki_dir = str(home / "AppData" / "Roaming" / "Anki2")
        else:
            default_anki_dir = str(home / ".local" / "share" / "Anki2")

        self.le_anki_dir = StyledLineEdit()
        self.le_anki_dir.setFixedHeight(28)
        self.le_anki_dir.setText(str(SettingsService.get("anki/collection_dir", default_anki_dir)))
        row_dir.addWidget(self.le_anki_dir, 1)

        btn_browse_anki = SecondaryButton("")
        btn_browse_anki.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        btn_browse_anki.setToolTip("Parcourir le dossier Anki2")
        btn_browse_anki.setFixedHeight(28)
        btn_browse_anki.clicked.connect(self._browse_anki_dir)
        row_dir.addWidget(btn_browse_anki)

        btn_open_anki = SecondaryButton("")
        btn_open_anki.setIcon(load_phosphor_icon("ph.arrow-square-out", color=DesignTokens.TEXT_PRIMARY))
        btn_open_anki.setToolTip("Ouvrir dans l'explorateur")
        btn_open_anki.setFixedHeight(28)
        btn_open_anki.clicked.connect(self._open_anki_dir)
        row_dir.addWidget(btn_open_anki)

        dir_layout.addLayout(row_dir)

        lbl_hint = QLabel("💡 Permet de repérer facilement vos profils et fichiers .anki2 / .colpkg sans dépendance réseau.")
        lbl_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic;")
        dir_layout.addWidget(lbl_hint)

        layout.addWidget(self.card_dir)
        layout.addStretch()

    def _browse_anki_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier Anki2", self.le_anki_dir.text())
        if path:
            self.le_anki_dir.setText(path)

    def _open_anki_dir(self) -> None:
        p = Path(self.le_anki_dir.text().strip())
        if p.exists():
            import webbrowser

            webbrowser.open(p.as_uri())
        else:
            show_toast(self, "Le dossier Anki2 spécifié n'existe pas.", is_error=True)

    def save_tab(self) -> None:
        """Sauvegarde les paramètres de formats et de fusion Anki."""
        SettingsService.set("anki/conflict_policy", self.cb_conflict_policy.currentData(), category="anki")
        SettingsService.set("anki/silent_meta_merge", self.chk_silent_merge.isChecked(), category="anki")
        SettingsService.set("anki/compression", self.cb_compression.currentData(), category="anki")
        SettingsService.set("anki/default_deck_id", self.cb_default_deck.currentData(), category="anki")
        SettingsService.set("anki/collection_dir", self.le_anki_dir.text().strip(), category="anki")

    def refresh_theme(self, profile: Any) -> None:
        self.lbl_sec_merge.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_fmt.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.lbl_sec_dir.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.card_merge.refresh_theme(profile)
        self.card_fmt.refresh_theme(profile)
        self.card_dir.refresh_theme(profile)
        for lbl in self.lbl_anki_labels:
            lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        if hasattr(self, "chk_silent_merge"):
            self.chk_silent_merge.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11.5px;")

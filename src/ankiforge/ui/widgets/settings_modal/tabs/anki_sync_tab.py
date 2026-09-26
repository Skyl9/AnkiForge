import platform
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DeckModel
from ankiforge.services.cards.flag_service import FlagService
from ankiforge.services.settings_service import SettingsService, values_equal
from ankiforge.ui.components import (
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.ui.widgets.settings_modal.dirty import SettingsDirtyMixin
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon


class AnkiSyncTab(SettingsDirtyMixin, QWidget):
    """Onglet Formats Anki, Règles de Conflits, Compression et Répertoires locaux (Zéro AnkiConnect)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lbl_anki_labels: list[QLabel] = []
        self.flag_inputs: dict[int, StyledLineEdit] = {}
        self._setup_ui()
        # Référence des valeurs chargées : évite de marquer « modifié » un réglage auto-sélectionné.
        self._initial: tuple[Any, ...] = (
            self.cb_conflict_policy.currentData(),
            self.chk_silent_merge.isChecked(),
            self.cb_compression.currentData(),
            self.cb_default_deck.currentData(),
            int(self.cb_max_import_size.currentData() or 0),
            self.le_anki_dir.text().strip(),
        )
        self._initial_flags: tuple[str, ...] = tuple(self.flag_inputs[i].text().strip() for i in range(1, 8))

    def _setup_ui(self) -> None:
        from PySide6.QtWidgets import QFrame, QScrollArea

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : RÈGLES DE FUSION & CONFLITS ──────────────────────────
        self.lbl_sec_merge = QLabel("RÈGLES DE FUSION & CONFLITS")
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

        self.chk_silent_merge = QCheckBox("Fusionner silencieusement les déplacements de paquets et statistiques SRS")
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

        row_maxsize = QHBoxLayout()
        lbl_ms = QLabel("Taille max. décompressée à l'import (anti zip-bomb) :")
        lbl_ms.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        row_maxsize.addWidget(lbl_ms)
        self.lbl_anki_labels.append(lbl_ms)

        size_presets = [
            ("512 Mio", 512 * 1024 * 1024),
            ("1 Gio (recommandé)", 1024 * 1024 * 1024),
            ("2 Gio", 2 * 1024 * 1024 * 1024),
            ("4 Gio", 4 * 1024 * 1024 * 1024),
            ("Illimité", 0),
        ]
        self.cb_max_import_size = StyledComboBox()
        self.cb_max_import_size.setMinimumWidth(260)
        self.cb_max_import_size.setFixedHeight(28)
        for label, value in size_presets:
            self.cb_max_import_size.addItem(label, value)
        saved_max_size = int(SettingsService.get("anki/max_import_bytes", 1024 * 1024 * 1024) or 0)
        for i in range(self.cb_max_import_size.count()):
            if self.cb_max_import_size.itemData(i) == saved_max_size:
                self.cb_max_import_size.setCurrentIndex(i)
                break
        row_maxsize.addStretch()
        row_maxsize.addWidget(self.cb_max_import_size)
        fmt_layout.addLayout(row_maxsize)

        layout.addWidget(self.card_fmt)

        # ── SECTION 3 : RÉPERTOIRE DES COLLECTIONS ANKI ──────────────────────
        self.lbl_sec_dir = QLabel("RÉPERTOIRE DES COLLECTIONS ANKI")
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

        row_hint = QHBoxLayout()
        row_hint.setSpacing(6)
        hint_icon = QLabel()
        hint_icon.setPixmap(load_phosphor_icon("ph.lightbulb", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        row_hint.addWidget(hint_icon)
        lbl_hint = QLabel("Permet de repérer facilement vos profils et fichiers .anki2 / .colpkg sans dépendance réseau.")
        lbl_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic;")
        row_hint.addWidget(lbl_hint, 1)
        dir_layout.addLayout(row_hint)

        layout.addWidget(self.card_dir)

        # ── SECTION 4 : DRAPEAUX ANKI (LIBELLÉS DU PROFIL) ───────────────────
        self.lbl_sec_flags = QLabel("DRAPEAUX ANKI (LIBELLÉS DU PROFIL)")
        self.lbl_sec_flags.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_flags)

        self.card_flags = SettingsCard()
        flags_layout = QVBoxLayout(self.card_flags)
        flags_layout.setContentsMargins(14, 12, 14, 12)
        flags_layout.setSpacing(10)

        self.lbl_flags_desc = QLabel("Personnalisez les libellés des 7 drapeaux colorés pour ce profil (laisser vide pour le nom par défaut) :")
        self.lbl_flags_desc.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px;")
        flags_layout.addWidget(self.lbl_flags_desc)

        grid_flags = QGridLayout()
        grid_flags.setHorizontalSpacing(16)
        grid_flags.setVerticalSpacing(8)

        current_labels = FlagService.get_flag_labels()
        for idx in range(1, 8):
            color_hex = DesignTokens.FLAG_COLORS.get(idx, DesignTokens.TEXT_MUTED)
            default_name = DesignTokens.FLAG_NAMES.get(idx, f"Drapeau {idx}")
            saved_name = current_labels.get(idx, "")
            display_text = saved_name if saved_name != default_name else ""

            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            dot = QLabel()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background-color: {color_hex}; border-radius: 6px;")
            row_layout.addWidget(dot)

            lbl_idx = QLabel(f"Drapeau {idx} :")
            lbl_idx.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
            lbl_idx.setFixedWidth(75)
            row_layout.addWidget(lbl_idx)
            self.lbl_anki_labels.append(lbl_idx)

            le = StyledLineEdit()
            le.setFixedHeight(28)
            le.setPlaceholderText(default_name)
            le.setText(display_text)
            row_layout.addWidget(le, 1)

            self.flag_inputs[idx] = le

            row = (idx - 1) // 2
            col = (idx - 1) % 2
            grid_flags.addLayout(row_layout, row, col)

        flags_layout.addLayout(grid_flags)
        layout.addWidget(self.card_flags)
        layout.addStretch()

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

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
        SettingsService.set("anki/max_import_bytes", int(self.cb_max_import_size.currentData() or 0), category="anki")
        SettingsService.set("anki/collection_dir", self.le_anki_dir.text().strip(), category="anki")
        flags_dict = {i: self.flag_inputs[i].text().strip() for i in range(1, 8)}
        FlagService.set_flag_labels(flags_dict)
        self._initial_flags = tuple(self.flag_inputs[i].text().strip() for i in range(1, 8))

    def has_pending_changes(self) -> bool:
        """True si un paramètre de formats/fusion Anki diffère de sa valeur chargée."""
        current = (
            self.cb_conflict_policy.currentData(),
            self.chk_silent_merge.isChecked(),
            self.cb_compression.currentData(),
            self.cb_default_deck.currentData(),
            int(self.cb_max_import_size.currentData() or 0),
            self.le_anki_dir.text().strip(),
        )
        base_changed = any(not values_equal(cur, ini) for cur, ini in zip(current, self._initial, strict=True))
        current_flags = tuple(self.flag_inputs[i].text().strip() for i in range(1, 8))
        flags_changed = any(not values_equal(cur, ini) for cur, ini in zip(current_flags, self._initial_flags, strict=True))
        return base_changed or flags_changed

    def refresh_theme(self, profile: Any) -> None:
        self.lbl_sec_merge.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_fmt.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.lbl_sec_dir.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        if hasattr(self, "lbl_sec_flags"):
            self.lbl_sec_flags.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.card_merge.refresh_theme(profile)
        self.card_fmt.refresh_theme(profile)
        self.card_dir.refresh_theme(profile)
        if hasattr(self, "card_flags"):
            self.card_flags.refresh_theme(profile)
        if hasattr(self, "lbl_flags_desc"):
            self.lbl_flags_desc.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11.5px;")
        for lbl in self.lbl_anki_labels:
            lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        if hasattr(self, "chk_silent_merge"):
            self.chk_silent_merge.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11.5px;")

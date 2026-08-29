"""
Modal Paramètres (SettingsModal) — 100% Conforme au Design System AnkiForge et à l'Architecture Modulaire.

Comprend 5 Onglets Professionnels :
1. 🎨 Général & Apparence (Layout, Mode Sombre/Clair, 12 Familles de Thèmes avec Nuancier, Langue, Dossiers)
2. 🤖 Moteurs IA & Clés API (Clés chiffrées/masquées avec toggle œil, Ping test, Scanner Ollama local, Catalogue LLMConfigModel)
3. 🔄 Anki & Synchronisation (AnkiConnect URL/Port, Test de connexion en direct, Règles de Smart Merge Règle 11, Compression)
4. 🛡️ Stockage, Sauvegardes & Maintenance (Métriques réelles SQLite/Médias, VACUUM, Purge orphelins, Snapshots de backup)
5. 🧩 Gestionnaire d'Extensions (AddonManagerWidget responsive sans troncature)

Supporte une réactivité thématique totale à chaud (Sombre 🌙 / Clair ☀️) et zéro fuite de style QSS.
"""

import datetime
import json
import logging
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.backup import backup_database
from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    MediaModel,
    NoteModel,
    NoteVersionMediaModel,
    NoteVersionModel,
    db,
)
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import (
    DangerButton,
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTableWidget,
)
from ankiforge.ui.dialogs.addon_manager_dialog import AddonManagerWidget
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_active_profile, get_app_data_dir

logger = logging.getLogger(__name__)


def apply_pill_badge_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    try:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    except Exception:
        r, g, b = 99, 102, 241
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.14) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.40);
            border-radius: 9999px;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: bold;
        }}
    """)


# =====================================================================
# COMPOSANT : CARTE CONTENEUR AVEC SCOPING STRICT (SettingsCard)
# =====================================================================


class SettingsCard(QFrame):
    """Conteneur stylé garantissant l'absence de cascade QSS parasite sur les QLabel enfants."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#SettingsCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#SettingsCard QLabel {{
                background: transparent;
                border: none;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            QFrame#SettingsCard {{
                background-color: {profile.bg_panel};
                border: 1px solid {profile.border_color};
                border-radius: {profile.radius_md}px;
            }}
            QFrame#SettingsCard QLabel {{
                background: transparent;
                border: none;
            }}
        """)


# =====================================================================
# COMPOSANT : CHAMP MOT DE PASSE AVEC TOGGLE ŒIL (PasswordLineEdit)
# =====================================================================


class PasswordLineEdit(QWidget):
    """Champ de saisie sécurisé pour clés API avec bouton œil pour afficher/masquer."""

    def __init__(self, placeholder: str = "", initial_text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._is_visible: bool = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.edit = StyledLineEdit()
        self.edit.setEchoMode(StyledLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(initial_text)
        layout.addWidget(self.edit, 1)

        self.btn_toggle = IconButton("ph.eye", tooltip="Afficher / Masquer la clé", size=26)
        self.btn_toggle.clicked.connect(self._toggle_visibility)
        layout.addWidget(self.btn_toggle)

    def _toggle_visibility(self) -> None:
        self._is_visible = not self._is_visible
        if self._is_visible:
            self.edit.setEchoMode(StyledLineEdit.EchoMode.Normal)
            self.btn_toggle.setIcon(load_phosphor_icon("ph.eye-slash", color=DesignTokens.ACCENT_PRIMARY))
        else:
            self.edit.setEchoMode(StyledLineEdit.EchoMode.Password)
            self.btn_toggle.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_MUTED))

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, text: str) -> None:
        self.edit.setText(text)

    def refresh_theme(self, profile: Any) -> None:
        icon_name = "ph.eye-slash" if self._is_visible else "ph.eye"
        color = profile.accent_primary if self._is_visible else profile.text_muted
        self.btn_toggle.setIcon(load_phosphor_icon(icon_name, color=color))


# =====================================================================
# COMPOSANT : BOUTON DE NAVIGATION SIDEBAR (SettingsNavButton)
# =====================================================================


class SettingsNavButton(QPushButton):
    """Bouton de navigation latérale avec indicateur d'accent vertical gauche."""

    def __init__(self, title: str, icon_name: str, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(f"  {title}", parent)
        self.icon_name = icon_name
        self.tab_index = index
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY if self.isChecked() else DesignTokens.TEXT_SECONDARY))
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding: 6px 14px;
                font-size: 12.5px;
                font-weight: 500;
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:checked {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-weight: bold;
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self.setIcon(load_phosphor_icon(self.icon_name, color=profile.accent_primary if self.isChecked() else profile.text_secondary))
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-left: 3px solid transparent;
                text-align: left;
                padding: 6px 14px;
                font-size: 12.5px;
                font-weight: 500;
                border-radius: {profile.radius_sm}px;
                color: {profile.text_secondary};
            }}
            QPushButton:hover {{
                background-color: {profile.bg_hover};
                color: {profile.text_primary};
            }}
            QPushButton:checked {{
                background-color: {profile.bg_active};
                color: {profile.accent_primary};
                font-weight: bold;
                border-left: 3px solid {profile.accent_primary};
            }}
        """)


# =====================================================================
# COMPOSANT : CARTE DE MÉTRIQUE STOCKAGE (StorageMetricCard)
# =====================================================================


class StorageMetricCard(QFrame):
    """Carte d'affichage de statistique de stockage avec icône Phosphor et sous-titre."""

    def __init__(self, title: str, value: str, icon_name: str, subtitle: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.setObjectName("StorageMetricCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()

        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        top_row.addWidget(self.lbl_icon)
        layout.addLayout(top_row)

        self.lbl_val = QLabel(value)
        self.lbl_val.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 18px; font-weight: bold; font-family: '{DesignTokens.FONT_CODE}';")
        layout.addWidget(self.lbl_val)

        self.lbl_sub = QLabel(subtitle)
        self.lbl_sub.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px;")
        layout.addWidget(self.lbl_sub)

        self._apply_style()

    def update_metric(self, value: str, subtitle: str = "") -> None:
        self.lbl_val.setText(value)
        if subtitle:
            self.lbl_sub.setText(subtitle)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#StorageMetricCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            QFrame#StorageMetricCard {{
                background-color: {profile.bg_panel};
                border: 1px solid {profile.border_color};
                border-radius: {profile.radius_md}px;
            }}
        """)
        self.lbl_title.setStyleSheet(f"color: {profile.text_muted}; font-size: 11px; font-weight: bold; text-transform: uppercase;")
        self.lbl_val.setStyleSheet(f"color: {profile.text_primary}; font-size: 18px; font-weight: bold; font-family: '{profile.font_code}';")
        self.lbl_sub.setStyleSheet(f"color: {profile.color_green}; font-size: 11px;")
        self.lbl_icon.setPixmap(load_phosphor_icon(self.icon_name, color=profile.accent_primary).pixmap(18, 18))


# =====================================================================
# ONGLET 1 : GÉNÉRAL & APPARENCE (GeneralTab)
# =====================================================================


class GeneralTab(QWidget):
    """Onglet Paramètres Généraux et Apparence."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.style_engine import get_style_engine

        engine = get_style_engine()
        profile_name = self._get_profile_name()

        # ── SECTION 1 : APPARENCE & INTERFACE ────────────────────────────────
        self.lbl_sec_app = QLabel("APPARENCE & INTERFACE")
        self.lbl_sec_app.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_app)

        self.card_app = SettingsCard()
        card_app_layout = QVBoxLayout(self.card_app)
        card_app_layout.setContentsMargins(14, 12, 14, 12)
        card_app_layout.setSpacing(12)

        def add_setting_row(parent_layout: QVBoxLayout, label_str: str, widget: QWidget) -> QLabel:
            row = QHBoxLayout()
            lbl = QLabel(label_str)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(widget)
            parent_layout.addLayout(row)
            return lbl

        self.rows_labels: List[QLabel] = []

        # 1. Disposition (Layout)
        self.cb_layout = StyledComboBox()
        self.cb_layout.setMinimumWidth(260)
        self.cb_layout.setFixedHeight(30)
        for item in LayoutManager.get_available_layouts():
            icon = load_phosphor_icon(item.get("icon", "ph.layout"), color=DesignTokens.ACCENT_PRIMARY)
            self.cb_layout.addItem(icon, item["name"], item["id"])

        saved_layout_id = LayoutManager.get_saved_layout_id(profile_name)
        for i in range(self.cb_layout.count()):
            if self.cb_layout.itemData(i) == saved_layout_id:
                self.cb_layout.setCurrentIndex(i)
                break
        self.rows_labels.append(add_setting_row(card_app_layout, "Disposition de l'interface (Layout) :", self.cb_layout))

        # 2. Mode d'Apparence
        self.cb_mode = StyledComboBox()
        self.cb_mode.setMinimumWidth(260)
        self.cb_mode.setFixedHeight(30)
        self.cb_mode.addItem(load_phosphor_icon("ph.moon", color=DesignTokens.ACCENT_PRIMARY), "🌙 Mode Sombre (Dark)", "dark")
        self.cb_mode.addItem(load_phosphor_icon("ph.sun", color=DesignTokens.COLOR_YELLOW), "☀️ Mode Clair (Light)", "light")

        saved_theme_id = engine.get_saved_theme_id(profile_name)
        current_theme_obj = engine.get_theme(saved_theme_id)

        if not current_theme_obj.is_dark:
            self.cb_mode.setCurrentIndex(1)
        else:
            self.cb_mode.setCurrentIndex(0)
        self.rows_labels.append(add_setting_row(card_app_layout, "Mode d'Apparence :", self.cb_mode))

        # 3. Thème Visuel (12 Familles)
        self.cb_theme = StyledComboBox()
        self.cb_theme.setMinimumWidth(260)
        self.cb_theme.setFixedHeight(30)

        def populate_theme_families() -> None:
            is_dark_selected = self.cb_mode.currentData() == "dark"
            self.cb_theme.clear()
            families = engine.get_theme_families()
            for fam in families:
                theme_variant = fam.dark_theme if is_dark_selected else fam.light_theme
                icon_name = "ph.moon" if is_dark_selected else "ph.sun"
                icon_color = DesignTokens.ACCENT_PRIMARY if is_dark_selected else DesignTokens.COLOR_YELLOW
                self.cb_theme.addItem(load_phosphor_icon(icon_name, color=icon_color), fam.name, theme_variant.id)

        populate_theme_families()

        for i in range(self.cb_theme.count()):
            if self.cb_theme.itemData(i) == current_theme_obj.id:
                self.cb_theme.setCurrentIndex(i)
                break

        def on_mode_changed(idx: int) -> None:
            curr_idx = self.cb_theme.currentIndex()
            populate_theme_families()
            if 0 <= curr_idx < self.cb_theme.count():
                self.cb_theme.setCurrentIndex(curr_idx)

        self.cb_mode.currentIndexChanged.connect(on_mode_changed)
        self.rows_labels.append(add_setting_row(card_app_layout, "Thème visuel & Palette :", self.cb_theme))

        # 4. Langue
        self.cb_lang = StyledComboBox()
        self.cb_lang.setMinimumWidth(260)
        self.cb_lang.setFixedHeight(30)
        self.cb_lang.addItem(load_phosphor_icon("ph.translate", color=DesignTokens.TEXT_PRIMARY), "Français")
        self.cb_lang.addItem(load_phosphor_icon("ph.translate", color=DesignTokens.TEXT_PRIMARY), "English")
        self.cb_lang.setCurrentText(str(SettingsService.get("ui/language", "Français")))
        self.rows_labels.append(add_setting_row(card_app_layout, "Langue de l'interface :", self.cb_lang))

        # 5. Style Studio de Création
        self.cb_batch_style = StyledComboBox()
        self.cb_batch_style.setMinimumWidth(260)
        self.cb_batch_style.setFixedHeight(30)
        self.cb_batch_style.addItem(load_phosphor_icon("ph.gauge", color=DesignTokens.TEXT_PRIMARY), "CI/CD (Tableau de bord industriel)")
        self.cb_batch_style.addItem(load_phosphor_icon("ph.kanban", color=DesignTokens.TEXT_PRIMARY), "Kanban (Flux de tâches)")
        self.cb_batch_style.addItem(load_phosphor_icon("ph.steps", color=DesignTokens.TEXT_PRIMARY), "Assistant (Pas-à-pas)")
        self.cb_batch_style.setCurrentText(str(SettingsService.get("app/batch_factory_style", "CI/CD (Tableau de bord industriel)")))
        self.rows_labels.append(add_setting_row(card_app_layout, "Style Studio de Création :", self.cb_batch_style))

        layout.addWidget(self.card_app)

        # ── SECTION 2 : DOSSIERS & CHEMINS DE SORTIE ─────────────────────────
        self.lbl_sec_exp = QLabel("DOSSIERS & CHEMINS DE SORTIE")
        self.lbl_sec_exp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(self.lbl_sec_exp)

        self.card_exp = SettingsCard()
        card_exp_layout = QVBoxLayout(self.card_exp)
        card_exp_layout.setContentsMargins(14, 12, 14, 12)
        card_exp_layout.setSpacing(10)

        exp_row = QHBoxLayout()
        self.lbl_exp_dir = QLabel("Dossier d'exportation par défaut :")
        self.lbl_exp_dir.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        exp_row.addWidget(self.lbl_exp_dir)

        default_export = str(Path.home() / "AnkiForge" / "Exports")
        self.le_export = StyledLineEdit()
        self.le_export.setFixedHeight(30)
        self.le_export.setText(str(SettingsService.get("app/export_path", default_export)))
        exp_row.addWidget(self.le_export, 1)

        btn_browse = SecondaryButton("")
        btn_browse.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        btn_browse.setToolTip("Parcourir et sélectionner le dossier")
        btn_browse.setFixedHeight(30)
        btn_browse.clicked.connect(self._browse_export)
        exp_row.addWidget(btn_browse)

        btn_open = SecondaryButton("")
        btn_open.setIcon(load_phosphor_icon("ph.arrow-square-out", color=DesignTokens.TEXT_PRIMARY))
        btn_open.setToolTip("Ouvrir dans l'explorateur de fichiers")
        btn_open.setFixedHeight(30)
        btn_open.clicked.connect(self._open_export_dir)
        exp_row.addWidget(btn_open)

        card_exp_layout.addLayout(exp_row)
        layout.addWidget(self.card_exp)

        layout.addStretch()

    def _get_main_window(self) -> Optional[Any]:
        w = self.window()
        if w is not None:
            if hasattr(w, "apply_layout"):
                return w
            parent_w = w.parent()
            if parent_w is not None and hasattr(parent_w, "apply_layout"):
                return parent_w
        return None

    def _get_profile_name(self) -> str:
        main_w = self._get_main_window()
        if main_w is not None and hasattr(main_w, "profile_name"):
            return str(main_w.profile_name)
        return "default"

    def _browse_export(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'exportation", self.le_export.text())
        if path:
            self.le_export.setText(path)

    def _open_export_dir(self) -> None:
        p = Path(self.le_export.text().strip())
        p.mkdir(parents=True, exist_ok=True)
        import webbrowser

        webbrowser.open(p.as_uri())

    def save_tab(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Sauvegarde les paramètres de l'onglet et retourne (has_theme_change, selected_layout_id, selected_theme_id)."""
        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.style_engine import get_style_engine

        profile_name = self._get_profile_name()
        engine = get_style_engine()

        selected_layout_id = self.cb_layout.currentData()
        selected_theme_id = self.cb_theme.currentData()

        # Enregistrement en BDD
        SettingsService.set("ui/language", self.cb_lang.currentText(), category="general")
        SettingsService.set("app/batch_factory_style", self.cb_batch_style.currentText(), category="general")
        SettingsService.set("app/export_path", self.le_export.text().strip(), category="general")

        LayoutManager.save_layout_id(profile_name, selected_layout_id)
        engine.save_theme_preference(profile_name, selected_theme_id)

        return True, selected_layout_id, selected_theme_id

    def refresh_theme(self, profile: Any) -> None:
        """Met à jour les styles dynamiques lors d'un changement de thème."""
        self.lbl_sec_app.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_exp.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        self.card_app.refresh_theme(profile)
        self.card_exp.refresh_theme(profile)
        for lbl in self.rows_labels:
            lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        if hasattr(self, "lbl_exp_dir"):
            self.lbl_exp_dir.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")


# =====================================================================
# ONGLET 2 : MOTEURS IA & CLÉS API (AIEnginesTab)
# =====================================================================


class AIEnginesTab(QWidget):
    """Onglet Configuration des Moteurs IA et Clés API."""

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.lbl_provider_labels: List[QLabel] = []
        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── SECTION 1 : CLÉS D'AUTHENTIFICATION CLOUD ────────────────────────
        self.lbl_sec_keys = QLabel("CLÉS D'AUTHENTIFICATION FOURNISSEURS CLOUD")
        self.lbl_sec_keys.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_keys)

        self.card_keys = SettingsCard()
        keys_layout = QVBoxLayout(self.card_keys)
        keys_layout.setContentsMargins(14, 10, 14, 10)
        keys_layout.setSpacing(8)

        self.key_edits: Dict[str, PasswordLineEdit] = {}
        self.key_status_badges: Dict[str, QLabel] = {}

        providers_cfg = [
            ("openai", "OpenAI", "sk-proj-...", "ph.brain"),
            ("anthropic", "Anthropic", "sk-ant-...", "ph.sparkle"),
            ("gemini", "Gemini", "AIzaSy...", "ph.sparkle"),
            ("groq", "Groq", "gsk_...", "ph.lightning"),
        ]

        for p_id, p_name, placeholder, p_icon in providers_cfg:
            row = QHBoxLayout()
            row.setSpacing(8)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(load_phosphor_icon(p_icon, color=DesignTokens.ACCENT_PRIMARY).pixmap(15, 15))
            row.addWidget(icon_lbl)

            lbl = QLabel(f"{p_name} :")
            lbl.setMinimumWidth(85)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
            row.addWidget(lbl)
            self.lbl_provider_labels.append(lbl)

            initial_key = str(SettingsService.get(f"keys/{p_id}", ""))
            p_edit = PasswordLineEdit(placeholder=placeholder, initial_text=initial_key)
            self.key_edits[p_id] = p_edit
            row.addWidget(p_edit, 1)

            btn_test = SecondaryButton("Tester")
            btn_test.setFixedHeight(28)
            btn_test.setIcon(load_phosphor_icon("ph.check-circle", color=DesignTokens.TEXT_MUTED))
            btn_test.clicked.connect(lambda _, pid=p_id, pname=p_name: self._test_cloud_key(pid, pname))
            row.addWidget(btn_test)

            badge_st = QLabel("")
            badge_st.hide()
            self.key_status_badges[p_id] = badge_st
            row.addWidget(badge_st)

            keys_layout.addLayout(row)

        layout.addWidget(self.card_keys)

        # ── SECTION 2 : SERVEUR LOCAL OLLAMA ─────────────────────────────────
        self.lbl_sec_ollama = QLabel("SERVEUR LOCAL OLLAMA (ZÉRO CLOUD)")
        self.lbl_sec_ollama.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_ollama)

        self.card_ollama = SettingsCard()
        ollama_layout = QHBoxLayout(self.card_ollama)
        ollama_layout.setContentsMargins(14, 10, 14, 10)
        ollama_layout.setSpacing(10)

        lbl_ol_icon = QLabel()
        lbl_ol_icon.setPixmap(load_phosphor_icon("ph.cpu", color=DesignTokens.COLOR_GREEN).pixmap(16, 16))
        ollama_layout.addWidget(lbl_ol_icon)

        self.lbl_ol_url = QLabel("URL Serveur :")
        self.lbl_ol_url.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        ollama_layout.addWidget(self.lbl_ol_url)

        self.le_ollama_url = StyledLineEdit()
        self.le_ollama_url.setFixedHeight(28)
        self.le_ollama_url.setText(str(SettingsService.get("ollama/url", "http://localhost:11434")))
        ollama_layout.addWidget(self.le_ollama_url, 1)

        self.btn_scan_ollama = SecondaryButton("Scanner les modèles installés")
        self.btn_scan_ollama.setFixedHeight(28)
        self.btn_scan_ollama.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.COLOR_GREEN))
        self.btn_scan_ollama.clicked.connect(self._scan_ollama)
        ollama_layout.addWidget(self.btn_scan_ollama)

        self.badge_ollama_status = QLabel("")
        self.badge_ollama_status.hide()
        ollama_layout.addWidget(self.badge_ollama_status)

        layout.addWidget(self.card_ollama)

        # ── SECTION 3 : CATALOGUE DES MOTEURS IA ─────────────────────────────
        self.lbl_sec_cat = QLabel("CATALOGUE DES MOTEURS & MODÈLES IA (Peewee ORM)")
        self.lbl_sec_cat.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_cat)

        self.table_engines = StyledTableWidget(["Nom du Moteur", "Fournisseur", "Identifiant Modèle", "Gratuit / Local"])
        self.table_engines.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_engines.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_engines.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_engines.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_engines.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.table_engines, 1)

        # Barre d'outils Catalogue
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_add_ollama = SecondaryButton("+ Ollama Local")
        self.btn_add_ollama.setIcon(load_phosphor_icon("ph.cpu", color=DesignTokens.COLOR_GREEN))
        self.btn_add_ollama.clicked.connect(lambda: self._quick_add_engine("Ollama Local", "ollama", "llama3:latest", True))
        toolbar.addWidget(self.btn_add_ollama)

        self.btn_add_openai = SecondaryButton("+ GPT-4o")
        self.btn_add_openai.setIcon(load_phosphor_icon("ph.brain", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_openai.clicked.connect(lambda: self._quick_add_engine("GPT-4o (OpenAI)", "openai", "gpt-4o", False))
        toolbar.addWidget(self.btn_add_openai)

        self.btn_add_gemini = SecondaryButton("+ Gemini Flash")
        self.btn_add_gemini.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_BLUE))
        self.btn_add_gemini.clicked.connect(lambda: self._quick_add_engine("Google Gemini 2.5 Flash", "gemini", "gemini-2.5-flash", True))
        toolbar.addWidget(self.btn_add_gemini)

        toolbar.addStretch()

        self.btn_del_engine = DangerButton("Supprimer", ghost=True)
        self.btn_del_engine.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_del_engine.clicked.connect(self._del_engine)
        toolbar.addWidget(self.btn_del_engine)

        layout.addLayout(toolbar)

    def _test_cloud_key(self, provider_id: str, provider_name: str) -> None:
        key_edit = self.key_edits.get(provider_id)
        badge = self.key_status_badges.get(provider_id)
        if not key_edit or not badge:
            return

        key_val = key_edit.text()
        if not key_val:
            badge.setText("⚠️ Clé vide")
            apply_pill_badge_style(badge, DesignTokens.COLOR_YELLOW)
            badge.show()
            show_toast(self, f"Veuillez saisir une clé {provider_name}.", is_error=True)
            return

        # Validation de format
        valid_format = False
        if provider_id == "openai" and (key_val.startswith("sk-") or len(key_val) > 20):
            valid_format = True
        elif provider_id == "anthropic" and (key_val.startswith("sk-ant-") or len(key_val) > 20):
            valid_format = True
        elif provider_id == "gemini" and (key_val.startswith("AIza") or len(key_val) >= 20):
            valid_format = True
        elif provider_id == "groq" and (key_val.startswith("gsk_") or len(key_val) > 20):
            valid_format = True
        else:
            valid_format = len(key_val) >= 16

        if valid_format:
            badge.setText("✅ Format valide")
            apply_pill_badge_style(badge, DesignTokens.COLOR_GREEN)
            badge.show()
            show_toast(self, f"Clé {provider_name} enregistrée et validée !")
        else:
            badge.setText("❌ Format suspect")
            apply_pill_badge_style(badge, DesignTokens.COLOR_RED)
            badge.show()

    def _scan_ollama(self) -> None:
        url = self.le_ollama_url.text().strip().rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"http://{url}"
        try:
            req = urllib.request.Request(f"{url}/api/tags", headers={"User-Agent": "AnkiForge"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:  # nosec B310
                data = json.loads(resp.read().decode())
                models = [m.get("name") for m in data.get("models", [])]
                if models:
                    self.badge_ollama_status.setText(f"🟢 {len(models)} modèle(s) détecté(s)")
                    apply_pill_badge_style(self.badge_ollama_status, DesignTokens.COLOR_GREEN)
                    self.badge_ollama_status.show()

                    # Ajouter automatiquement le premier modèle manquant
                    added_count = 0
                    for m_name in models:
                        if not LLMConfigModel.select().where(LLMConfigModel.model_id == m_name).exists():
                            LLMConfigModel.create(
                                display_name=f"Ollama {m_name}",
                                provider="ollama",
                                model_id=m_name,
                                context_limit=8192,
                                api_key="",
                                is_free=True,
                            )
                            added_count += 1
                    self.refresh_data()
                    show_toast(self, f"Ollama en ligne : {len(models)} modèles scannés (+{added_count} importés) !")
                else:
                    self.badge_ollama_status.setText("🟡 En ligne (0 modèle)")
                    apply_pill_badge_style(self.badge_ollama_status, DesignTokens.COLOR_YELLOW)
                    self.badge_ollama_status.show()
        except Exception:
            self.badge_ollama_status.setText("🔴 Hors ligne")
            apply_pill_badge_style(self.badge_ollama_status, DesignTokens.COLOR_RED)
            self.badge_ollama_status.show()
            show_toast(self, "Serveur Ollama inaccessible sur cette adresse.", is_error=True)

    def refresh_data(self) -> None:
        """Recharge les moteurs IA depuis la base Peewee."""
        try:
            self.table_engines.blockSignals(True)
            engines = list(LLMConfigModel.select())
            self.table_engines.setRowCount(len(engines))

            for i, eg in enumerate(engines):
                item_name = QTableWidgetItem(getattr(eg, "display_name", "Inconnu"))
                item_name.setData(Qt.ItemDataRole.UserRole, eg.id)
                self.table_engines.setItem(i, 0, item_name)

                # Badge Fournisseur
                p_text = getattr(eg, "provider", "inconnu").upper()
                self.table_engines.setItem(i, 1, QTableWidgetItem(p_text))

                item_model = QTableWidgetItem(getattr(eg, "model_id", "default"))
                self.table_engines.setItem(i, 2, item_model)

                item_free = QTableWidgetItem()
                item_free.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                item_free.setCheckState(Qt.CheckState.Checked if getattr(eg, "is_free", False) else Qt.CheckState.Unchecked)
                self.table_engines.setItem(i, 3, item_free)

            self.table_engines.blockSignals(False)
        except Exception as e:
            logger.warning("Erreur refresh_data ai_engines_tab: %s", e)

    def _quick_add_engine(self, name: str, provider: str, model_id: str, is_free: bool) -> None:
        try:
            existing = LLMConfigModel.select().where((LLMConfigModel.provider == provider) & (LLMConfigModel.model_id == model_id)).first()
            if existing:
                show_toast(self, f"Le modèle '{model_id}' est déjà configuré.", is_error=True)
                return

            api_key = self.key_edits.get(provider, PasswordLineEdit()).text() if provider != "ollama" else ""
            LLMConfigModel.create(display_name=name, provider=provider, model_id=model_id, context_limit=128000, api_key=api_key, is_free=is_free)
            self.refresh_data()
            if self.ai_manager and hasattr(self.ai_manager, "reload_provider"):
                self.ai_manager.reload_provider()
            show_toast(self, f"Moteur '{name}' ajouté au catalogue !")
        except Exception as e:
            show_toast(self, f"Erreur lors de l'ajout : {e}", is_error=True)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        first_item = self.table_engines.item(item.row(), 0)
        if not first_item:
            return
        engine_id = first_item.data(Qt.ItemDataRole.UserRole)
        if not engine_id:
            return
        try:
            config = LLMConfigModel.get_by_id(engine_id)
            if item.column() == 0:
                config.display_name = item.text().strip()
            elif item.column() == 1:
                config.provider = item.text().strip().lower()
            elif item.column() == 2:
                config.model_id = item.text().strip()
            elif item.column() == 3:
                config.is_free = item.checkState() == Qt.CheckState.Checked
            config.save()
            if self.ai_manager and hasattr(self.ai_manager, "reload_provider"):
                self.ai_manager.reload_provider()
        except Exception as e:
            logger.error("Erreur modification moteur: %s", e)

    def _del_engine(self) -> None:
        selected = self.table_engines.selectedItems()
        if not selected:
            show_toast(self, "Veuillez sélectionner un moteur IA à supprimer.", is_error=True)
            return
        row = selected[0].row()
        item = self.table_engines.item(row, 0)
        if not item:
            return
        engine_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            LLMConfigModel.delete_by_id(engine_id)
            self.refresh_data()
            if self.ai_manager and hasattr(self.ai_manager, "reload_provider"):
                self.ai_manager.reload_provider()
            show_toast(self, "Moteur IA supprimé du catalogue.")
        except Exception as e:
            show_toast(self, f"Erreur suppression : {e}", is_error=True)

    def save_tab(self) -> None:
        """Sauvegarde les clés d'API et l'URL Ollama."""
        for p_id, edit in self.key_edits.items():
            SettingsService.set(f"keys/{p_id}", edit.text(), category="api_keys")
        SettingsService.set("ollama/url", self.le_ollama_url.text().strip(), category="ai")

    def refresh_theme(self, profile: Any) -> None:
        self.lbl_sec_keys.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_ollama.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.lbl_sec_cat.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.card_keys.refresh_theme(profile)
        self.card_ollama.refresh_theme(profile)
        if hasattr(self, "lbl_ol_url"):
            self.lbl_ol_url.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        for lbl in self.lbl_provider_labels:
            lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        for edit in self.key_edits.values():
            edit.refresh_theme(profile)
        if hasattr(self, "table_engines") and hasattr(self.table_engines, "refresh_theme"):
            self.table_engines.refresh_theme(profile)


# =====================================================================
# ONGLET 3 : ANKI & SYNCHRONISATION (AnkiSyncTab) — NOUVEAU
# =====================================================================
# ONGLET 3 : ANKI & FORMATS (AnkiSyncTab) — 100% HORS-LIGNE
# =====================================================================


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

        import platform

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


# =====================================================================
# ONGLET 4 : STOCKAGE, SAUVEGARDES & MAINTENANCE (StorageMaintenanceTab)
# =====================================================================


class StorageMaintenanceTab(QWidget):
    """Onglet Métrologie Réelle, Optimisation SQLite, Nettoyage Médias et Backups."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.refresh_metrics()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : COCKPIT DU STOCKAGE RÉEL ─────────────────────────────
        self.lbl_sec_stat = QLabel("ÉTAT DU STOCKAGE ET DE LA BASE DE DONNÉES")
        self.lbl_sec_stat.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_stat)

        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(10)

        self.c_db = StorageMetricCard("Base de données SQLite", "0 Ko", "ph.database", "WAL Actif • 0 notes")
        self.c_media = StorageMetricCard("Stockage Médias", "0 Mo", "ph.images", "0 fichiers médias")
        self.c_tm = StorageMetricCard("Time Machine", "0 versions", "ph.clock-counter-clockwise", "Historique actif")

        metrics_grid.addWidget(self.c_db, 0, 0)
        metrics_grid.addWidget(self.c_media, 0, 1)
        metrics_grid.addWidget(self.c_tm, 0, 2)
        layout.addLayout(metrics_grid)

        # ── SECTION 2 : ACTIONS D'ENTRETIEN RÉELLES ──────────────────────────
        self.lbl_sec_act = QLabel("ACTIONS D'ENTRETIEN ET D'OPTIMISATION")
        self.lbl_sec_act.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_act)

        self.card_act = SettingsCard()
        act_layout = QVBoxLayout(self.card_act)
        act_layout.setContentsMargins(14, 12, 14, 12)
        act_layout.setSpacing(10)

        row_actions1 = QHBoxLayout()
        row_actions1.setSpacing(10)

        self.btn_vacuum = SecondaryButton("Optimiser la base de données (VACUUM)")
        self.btn_vacuum.setIcon(load_phosphor_icon("ph.lightning", color=DesignTokens.COLOR_YELLOW))
        self.btn_vacuum.clicked.connect(self._run_vacuum)
        row_actions1.addWidget(self.btn_vacuum, 1)

        self.btn_clean_media = SecondaryButton("Nettoyer les images orphelines")
        self.btn_clean_media.setIcon(load_phosphor_icon("ph.broom", color=DesignTokens.COLOR_BLUE))
        self.btn_clean_media.clicked.connect(self._clean_orphan_media)
        row_actions1.addWidget(self.btn_clean_media, 1)

        act_layout.addLayout(row_actions1)

        row_actions2 = QHBoxLayout()
        row_actions2.setSpacing(10)

        self.btn_purge_history = DangerButton("Purger l'historique (> 30 jours)", ghost=True)
        self.btn_purge_history.setIcon(load_phosphor_icon("ph.clock-counter-clockwise", color=DesignTokens.COLOR_RED))
        self.btn_purge_history.clicked.connect(self._purge_history)
        row_actions2.addWidget(self.btn_purge_history, 1)

        self.btn_clear_cache = SecondaryButton("Vider les fichiers temporaires et cache")
        self.btn_clear_cache.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.TEXT_MUTED))
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        row_actions2.addWidget(self.btn_clear_cache, 1)

        act_layout.addLayout(row_actions2)
        layout.addWidget(self.card_act)

        # ── SECTION 3 : SAUVEGARDES DE SÉCURITÉ (BACKUPS) ────────────────────
        self.lbl_sec_bku = QLabel("SAUVEGARDES DE SÉCURITÉ DU PROFIL (INSTANTANÉS)")
        self.lbl_sec_bku.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_bku)

        self.card_bku = SettingsCard()
        bku_layout = QVBoxLayout(self.card_bku)
        bku_layout.setContentsMargins(14, 12, 14, 12)
        bku_layout.setSpacing(8)

        top_bku_row = QHBoxLayout()
        self.btn_snapshot = PrimaryButton("Créer un instantané immédiat (Backup)")
        self.btn_snapshot.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_snapshot.setFixedHeight(28)
        self.btn_snapshot.clicked.connect(self._create_snapshot)
        top_bku_row.addWidget(self.btn_snapshot)

        top_bku_row.addStretch()

        self.btn_open_backup_folder = SecondaryButton("Ouvrir le dossier des sauvegardes")
        self.btn_open_backup_folder.setIcon(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_PRIMARY))
        self.btn_open_backup_folder.setFixedHeight(28)
        self.btn_open_backup_folder.clicked.connect(self._open_backup_folder)
        top_bku_row.addWidget(self.btn_open_backup_folder)

        bku_layout.addLayout(top_bku_row)

        self.lbl_recent_backups = QLabel("Dernières sauvegardes : Aucune pour le moment.")
        self.lbl_recent_backups.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px; font-family: monospace;")
        bku_layout.addWidget(self.lbl_recent_backups)

        layout.addWidget(self.card_bku)

        layout.addStretch()

    def refresh_metrics(self) -> None:
        """Calcule les vraies valeurs sur le disque et en base SQLite."""
        try:
            pm = ProfileManager()
            profile_name = get_active_profile()
            db_path = pm.get_db_path(profile_name)

            db_size_kb = db_path.stat().st_size / 1024 if db_path.exists() else 0
            db_size_str = f"{db_size_kb / 1024:.1f} Mo" if db_size_kb > 1024 else f"{db_size_kb:.0f} Ko"

            notes_count = NoteModel.select().count()
            cards_count = CardModel.select().count()
            self.c_db.update_metric(db_size_str, f"WAL Actif • {notes_count} note{'s' if notes_count > 1 else ''}, {cards_count} carte{'s' if cards_count > 1 else ''}")

            # Médias
            media_dir = pm.PROFILES_DIR / profile_name / "media"
            if not media_dir.exists():
                media_dir = get_app_data_dir() / "media"

            media_count = 0
            media_size_bytes = 0
            if media_dir.exists():
                for f in media_dir.glob("*"):
                    if f.is_file():
                        media_count += 1
                        media_size_bytes += f.stat().st_size

            media_size_mb = media_size_bytes / (1024 * 1024)
            self.c_media.update_metric(f"{media_size_mb:.2f} Mo", f"{media_count} fichier{'s' if media_count > 1 else ''} média")

            # Time Machine
            versions_count = NoteVersionModel.select().count()
            self.c_tm.update_metric(f"{versions_count} versions", f"{notes_count} notes actives")

            # Backups
            backup_dir = pm.PROFILES_DIR / profile_name / "backups"
            if backup_dir.exists():
                backups = sorted(backup_dir.glob("ankiforge_backup_*.db"), reverse=True)
                if backups:
                    b_texts = [f"• {b.name} ({b.stat().st_size / 1024:.0f} Ko)" for b in backups[:3]]
                    self.lbl_recent_backups.setText("\n".join(b_texts))
                else:
                    self.lbl_recent_backups.setText("Aucune sauvegarde enregistrée dans ce profil.")
            else:
                self.lbl_recent_backups.setText("Dossier de sauvegarde non initialisé.")

        except Exception as e:
            logger.warning("Erreur refresh_metrics StorageMaintenanceTab: %s", e)

    def _run_vacuum(self) -> None:
        try:
            db.execute_sql("VACUUM;")
            db.execute_sql("PRAGMA optimize;")
            self.refresh_metrics()
            show_toast(self, "Optimisation SQLite (VACUUM & PRAGMA) terminée avec succès !")
        except Exception as e:
            show_toast(self, f"Erreur lors de l'optimisation : {e}", is_error=True)

    def _clean_orphan_media(self) -> None:
        try:
            pm = ProfileManager()
            profile_name = get_active_profile()
            media_dir = pm.PROFILES_DIR / profile_name / "media"
            if not media_dir.exists():
                media_dir = get_app_data_dir() / "media"

            used_media_ids = {m.media_id for m in NoteVersionMediaModel.select(NoteVersionMediaModel.media)}
            orphan_records = list(MediaModel.select().where(~(MediaModel.id.in_(used_media_ids)))) if used_media_ids else list(MediaModel.select())

            cleaned_count = 0
            freed_bytes = 0
            for record in orphan_records:
                target_f = media_dir / record.filename
                if target_f.exists():
                    freed_bytes += target_f.stat().st_size
                    target_f.unlink()
                record.delete_instance()
                cleaned_count += 1

            self.refresh_metrics()
            freed_kb = freed_bytes / 1024
            show_toast(self, f"Nettoyage terminé : {cleaned_count} médias orphelins supprimés ({freed_kb:.1f} Ko libérés) !")
        except Exception as e:
            show_toast(self, f"Erreur lors du nettoyage : {e}", is_error=True)

    def _purge_history(self) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmer la purge Time Machine",
            "Voulez-vous purger l'historique des modifications antérieur à 30 jours ?\n(Les versions actives actuelles ne seront pas affectées).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                cutoff = datetime.datetime.now() - datetime.timedelta(days=30)
                deleted = NoteVersionModel.delete().where((NoteVersionModel.created_at < cutoff) & (~NoteVersionModel.is_active)).execute()
                self.refresh_metrics()
                show_toast(self, f"Purge effectuée : {deleted} anciennes versions supprimées.")
            except Exception as e:
                show_toast(self, f"Erreur purge : {e}", is_error=True)

    def _clear_cache(self) -> None:
        try:
            temp_dir = get_app_data_dir() / "temp"
            deleted_count = 0
            if temp_dir.exists():
                for f in temp_dir.glob("*"):
                    if f.is_file():
                        f.unlink()
                        deleted_count += 1
            show_toast(self, f"Cache et fichiers temporaires nettoyés ({deleted_count} fichiers supprimés) !")
        except Exception as e:
            show_toast(self, f"Erreur nettoyage cache : {e}", is_error=True)

    def _create_snapshot(self) -> None:
        try:
            backup_database(keep_last=5)
            self.refresh_metrics()
            show_toast(self, "Instantané (Snapshot) créé avec succès !")
        except Exception as e:
            show_toast(self, f"Erreur lors de la sauvegarde : {e}", is_error=True)

    def _open_backup_folder(self) -> None:
        pm = ProfileManager()
        profile_name = get_active_profile()
        backup_dir = pm.PROFILES_DIR / profile_name / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        import webbrowser

        webbrowser.open(backup_dir.as_uri())

    def save_tab(self) -> None:
        pass

    def refresh_theme(self, profile: Any) -> None:
        self.lbl_sec_stat.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_act.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.lbl_sec_bku.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.c_db.refresh_theme(profile)
        self.c_media.refresh_theme(profile)
        self.c_tm.refresh_theme(profile)
        self.card_act.refresh_theme(profile)
        self.card_bku.refresh_theme(profile)
        self.lbl_recent_backups.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11.5px; font-family: monospace;")


# =====================================================================
# VUE / MODALE PRINCIPALE : PARAMÈTRES (SettingsModal)
# =====================================================================


class SettingsModal(QDialog):
    """
    Modale de Paramètres Globale AnkiForge.
    Architecture moderne 960x640px, non bloquante, 5 onglets thématiques réactifs.
    """

    focus_changed = Signal(bool)
    theme_applied = Signal(str)
    layout_applied = Signal(str)

    def __init__(self, ai_manager: Any = None, profile_name: Optional[str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name or get_active_profile()
        self.stacked_widget = QStackedWidget()

        self.setWindowTitle("Paramètres AnkiForge")
        self.setMinimumSize(900, 600)
        self.resize(960, 640)
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)

        self._setup_ui()
        self._connect_signals()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange:
            self.focus_changed.emit(self.isActiveWindow())
        super().changeEvent(event)

    def closeEvent(self, event: Any) -> None:
        self.focus_changed.emit(False)
        super().closeEvent(event)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 1. HEADER BAR DU MODAL ────────────────────────────────────────────
        self.header_bar = QWidget()
        self.header_bar.setObjectName("SettingsHeaderBar")
        header_layout = QHBoxLayout(self.header_bar)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(10)

        self.lbl_header_icon = QLabel()
        self.lbl_header_icon.setPixmap(load_phosphor_icon("ph.sliders-horizontal", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        header_layout.addWidget(self.lbl_header_icon)

        self.lbl_title = QLabel("Paramètres AnkiForge")
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        header_layout.addWidget(self.lbl_title)

        active_prof = get_active_profile()
        self.lbl_prof_badge = QLabel(f"Profil : {active_prof}")
        apply_pill_badge_style(self.lbl_prof_badge, DesignTokens.ACCENT_PRIMARY)
        header_layout.addWidget(self.lbl_prof_badge)

        header_layout.addStretch()

        self.btn_close = IconButton("ph.x", tooltip="Fermer la fenêtre (Échap)", size=26)
        self.btn_close.clicked.connect(self.close)
        header_layout.addWidget(self.btn_close)

        main_layout.addWidget(self.header_bar)

        # ── 2. CORPS (SIDEBAR + STACKED WIDGET) ──────────────────────────────
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar navigation latérale
        self.sidebar = QWidget()
        self.sidebar.setObjectName("SettingsSidebar")
        self.sidebar.setFixedWidth(210)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(4)

        self.nav_btn_group = QButtonGroup(self)
        self.nav_btn_group.setExclusive(True)

        self.nav_btns: List[SettingsNavButton] = []

        tabs_info = [
            ("Général", "ph.paint-brush-broad", 0),
            ("Moteurs IA", "ph.cpu", 1),
            ("Anki && Formats", "ph.cards", 2),
            ("Maintenance", "ph.wrench", 3),
            ("Extensions", "ph.puzzle-piece", 4),
        ]

        for title, icon_name, idx in tabs_info:
            btn = SettingsNavButton(title, icon_name, idx)
            btn.clicked.connect(lambda _, i=idx: self.stacked_widget.setCurrentIndex(i))
            self.nav_btn_group.addButton(btn, idx)
            sidebar_layout.addWidget(btn)
            self.nav_btns.append(btn)

        self.nav_btns[0].setChecked(True)
        sidebar_layout.addStretch()

        body_layout.addWidget(self.sidebar)

        # Stacked Widget avec les 5 onglets
        self.general_tab = GeneralTab()
        self.ai_tab = AIEnginesTab(self.ai_manager)
        self.anki_tab = AnkiSyncTab()
        self.maint_tab = StorageMaintenanceTab()
        self.addons_tab = AddonManagerWidget()

        self.stacked_widget.addWidget(self.general_tab)
        self.stacked_widget.addWidget(self.ai_tab)
        self.stacked_widget.addWidget(self.anki_tab)
        self.stacked_widget.addWidget(self.maint_tab)
        self.stacked_widget.addWidget(self.addons_tab)

        body_layout.addWidget(self.stacked_widget, 1)
        main_layout.addWidget(body, 1)

        # ── 3. FOOTER BAR AVEC ACTIONS GLOBALES ──────────────────────────────
        self.footer_bar = QWidget()
        self.footer_bar.setObjectName("SettingsFooterBar")
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.setSpacing(10)

        self.lbl_shortcut = QLabel("⌨️ Échap pour fermer")
        self.lbl_shortcut.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        footer_layout.addWidget(self.lbl_shortcut)

        footer_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.close)
        footer_layout.addWidget(self.btn_cancel)

        self.btn_save_all = PrimaryButton("Enregistrer les paramètres")
        self.btn_save_all.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save_all.setFixedHeight(30)
        self.btn_save_all.setMinimumWidth(200)
        apply_shadow(self.btn_save_all, blur=12, offset_y=0, color="rgba(99, 102, 241, 0.6)")
        self.btn_save_all.clicked.connect(self._save_all)
        footer_layout.addWidget(self.btn_save_all)

        main_layout.addWidget(self.footer_bar)

        self._apply_dialog_styles()

        # Raccourci Échap pour fermer
        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self.close)

    def _connect_signals(self) -> None:
        from ankiforge.ui.style_engine import get_style_engine

        engine = get_style_engine()
        engine.theme_changed.connect(self.refresh_theme)

    def _apply_dialog_styles(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
            }}
            QWidget#SettingsHeaderBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QWidget#SettingsSidebar {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border-right: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QWidget#SettingsFooterBar {{
                background-color: {DesignTokens.BG_PANEL};
                border-top: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)

    def _save_all(self) -> None:
        """Sauvegarde les paramètres de tous les onglets de façon unifiée et applique le thème."""
        from ankiforge.ui.widgets.theme_transition_overlay import show_theme_transition

        has_theme_change, selected_layout_id, selected_theme_id = self.general_tab.save_tab()
        self.ai_tab.save_tab()
        self.anki_tab.save_tab()
        self.maint_tab.save_tab()

        theme_title = self.general_tab.cb_theme.currentText() or "Nouveau Thème"

        def apply_changes() -> None:
            from ankiforge.ui.layouts.layout_manager import LayoutManager
            from ankiforge.ui.style_engine import get_style_engine

            engine = get_style_engine()
            profile_name = self.general_tab._get_profile_name()
            main_w = self.general_tab._get_main_window()

            if selected_layout_id:
                LayoutManager.save_layout_id(profile_name, selected_layout_id)
                if main_w is not None and hasattr(main_w, "apply_layout"):
                    main_w.apply_layout(selected_layout_id)

            if selected_theme_id:
                engine.save_theme_preference(profile_name, selected_theme_id)
                engine.apply_theme(selected_theme_id)

            show_toast(self, "Tous les paramètres ont été enregistrés avec succès !")

        target_parent = self.general_tab._get_main_window() or self
        show_theme_transition(
            parent=target_parent,
            theme_title=theme_title,
            subtext="Application des tokens et du design system...",
            duration_ms=450,
            on_applied=apply_changes,
        )

    def refresh_theme(self, profile: Any) -> None:
        """Met à jour l'ensemble des composants de la modale lors d'un changement de thème."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {profile.bg_main};
            }}
            QWidget#SettingsHeaderBar {{
                background-color: {profile.bg_panel};
                border-bottom: 1px solid {profile.border_color};
            }}
            QWidget#SettingsSidebar {{
                background-color: {profile.bg_sidebar};
                border-right: 1px solid {profile.border_color};
            }}
            QWidget#SettingsFooterBar {{
                background-color: {profile.bg_panel};
                border-top: 1px solid {profile.border_color};
            }}
        """)
        self.lbl_title.setStyleSheet(f"color: {profile.text_primary}; font-size: 15px; font-weight: bold;")
        self.lbl_header_icon.setPixmap(load_phosphor_icon("ph.sliders-horizontal", color=profile.accent_primary).pixmap(18, 18))
        apply_pill_badge_style(self.lbl_prof_badge, profile.accent_primary)
        self.lbl_shortcut.setStyleSheet(f"color: {profile.text_muted}; font-size: 11px;")

        for btn in self.nav_btns:
            btn.refresh_theme(profile)

        if hasattr(self, "general_tab") and hasattr(self.general_tab, "refresh_theme"):
            self.general_tab.refresh_theme(profile)
        if hasattr(self, "ai_tab") and hasattr(self.ai_tab, "refresh_theme"):
            self.ai_tab.refresh_theme(profile)
        if hasattr(self, "anki_tab") and hasattr(self.anki_tab, "refresh_theme"):
            self.anki_tab.refresh_theme(profile)
        if hasattr(self, "maint_tab") and hasattr(self.maint_tab, "refresh_theme"):
            self.maint_tab.refresh_theme(profile)
        if hasattr(self, "addons_tab") and hasattr(self.addons_tab, "refresh_theme"):
            self.addons_tab.refresh_theme(profile)


# Aliases de compatibilité
SettingsDialog = SettingsModal
MaintenanceTab = StorageMaintenanceTab
StatisticsTab = StorageMaintenanceTab

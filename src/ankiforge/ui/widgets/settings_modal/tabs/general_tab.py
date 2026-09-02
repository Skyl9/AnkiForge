from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import (
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.utils.icon_loader import load_phosphor_icon


class GeneralTab(QWidget):
    """Onglet Paramètres Généraux et Apparence."""

    def __init__(self, parent: QWidget | None = None) -> None:
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

        self.rows_labels: list[QLabel] = []

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

        # ── SECTION 3 : ESPACES DE TRAVAIL & DÉMARRAGE ──────────────────────
        self.lbl_sec_startup = QLabel("ESPACES DE TRAVAIL & DÉMARRAGE")
        self.lbl_sec_startup.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(self.lbl_sec_startup)

        self.card_startup = SettingsCard()
        card_startup_layout = QVBoxLayout(self.card_startup)
        card_startup_layout.setContentsMargins(14, 12, 14, 12)
        card_startup_layout.setSpacing(12)

        q_settings = QSettings("AnkiForgeOrg", "AnkiForge")
        auto_open_val = q_settings.value("profiles/auto_open_startup", False, type=bool)
        default_prof_val = str(q_settings.value("profiles/default_startup_profile", profile_name or "default"))

        # 1. Checkbox ouverture automatique
        self.chk_auto_startup = QCheckBox("Toujours ouvrir l'espace par défaut sans demander au lancement")
        self.chk_auto_startup.setChecked(auto_open_val)
        self.chk_auto_startup.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.chk_auto_startup.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        card_startup_layout.addWidget(self.chk_auto_startup)

        # 2. Sélecteur de profil par défaut
        self.cb_default_profile = StyledComboBox()
        self.cb_default_profile.setMinimumWidth(260)
        self.cb_default_profile.setFixedHeight(30)

        pm = ProfileManager()
        available_profiles = pm.list_profiles() or ["default"]
        if default_prof_val and default_prof_val not in available_profiles:
            available_profiles.append(default_prof_val)

        for p_name in available_profiles:
            icon = load_phosphor_icon("cards" if p_name == profile_name else "folder", color=DesignTokens.ACCENT_PRIMARY)
            self.cb_default_profile.addItem(icon, p_name, p_name)

        idx = self.cb_default_profile.findData(default_prof_val)
        if idx >= 0:
            self.cb_default_profile.setCurrentIndex(idx)

        self.rows_labels.append(add_setting_row(card_startup_layout, "Espace de travail de démarrage :", self.cb_default_profile))

        layout.addWidget(self.card_startup)

        # ── SECTION 4 : À PROPOS & MISES À JOUR ─────────────────────────────
        self.lbl_sec_about = QLabel("À PROPOS & MISES À JOUR")
        self.lbl_sec_about.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(self.lbl_sec_about)

        self.card_about = SettingsCard()
        card_about_layout = QVBoxLayout(self.card_about)
        card_about_layout.setContentsMargins(14, 12, 14, 12)
        card_about_layout.setSpacing(12)

        from ankiforge.services.update_checker import SETTINGS_KEY_CHANNEL
        from ankiforge.ui.components.badges import Badge
        from ankiforge.version import VERSION_INFO

        # 1. Version et informations système
        version_row = QHBoxLayout()
        lbl_v_title = QLabel("Version d'AnkiForge :")
        lbl_v_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        self.rows_labels.append(lbl_v_title)
        version_row.addWidget(lbl_v_title)
        version_row.addStretch()

        v_badge = Badge(f"v{VERSION_INFO.version}", variant="primary")
        version_row.addWidget(v_badge)

        lbl_meta = QLabel(f"({VERSION_INFO.commit_hash}) · {VERSION_INFO.platform_str}")
        lbl_meta.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px;")
        version_row.addWidget(lbl_meta)
        card_about_layout.addLayout(version_row)

        # 2. Canal de mise à jour (Stable vs Nightly)
        self.cb_update_channel = StyledComboBox()
        self.cb_update_channel.setMinimumWidth(260)
        self.cb_update_channel.setFixedHeight(30)
        self.cb_update_channel.addItem(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN), "🟢 Canal Stable (Recommandé)", "stable")
        self.cb_update_channel.addItem(load_phosphor_icon("ph.moon", color=DesignTokens.COLOR_YELLOW), "🌙 Canal Nightly (Bêta / Edge)", "nightly")

        saved_channel = str(q_settings.value(SETTINGS_KEY_CHANNEL, "stable"))
        ch_idx = self.cb_update_channel.findData(saved_channel)
        if ch_idx >= 0:
            self.cb_update_channel.setCurrentIndex(ch_idx)

        self.rows_labels.append(add_setting_row(card_about_layout, "Canal de distribution des mises à jour :", self.cb_update_channel))

        # 3. Action de recherche manuelle
        check_row = QHBoxLayout()
        lbl_check_title = QLabel("Recherche de mises à jour :")
        lbl_check_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        self.rows_labels.append(lbl_check_title)
        check_row.addWidget(lbl_check_title)
        check_row.addStretch()

        self.lbl_update_status = QLabel("")
        self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px;")
        check_row.addWidget(self.lbl_update_status)

        self.btn_check_updates = SecondaryButton("Rechercher")
        self.btn_check_updates.setIcon(load_phosphor_icon("ph.arrow-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_check_updates.setFixedHeight(30)
        self.btn_check_updates.clicked.connect(self._on_check_updates_clicked)
        check_row.addWidget(self.btn_check_updates)

        card_about_layout.addLayout(check_row)
        layout.addWidget(self.card_about)

        layout.addStretch()

    def _on_check_updates_clicked(self) -> None:
        """Déclenche manuellement la recherche de mise à jour avec retour visuel."""
        from PySide6.QtCore import QThreadPool

        from ankiforge.services.update_checker import UpdateCheckerWorker, UpdateInfo
        from ankiforge.ui.dialogs.update_dialog import UpdateDialog
        from ankiforge.version import VERSION_INFO

        selected_channel = str(self.cb_update_channel.currentData() or "stable")
        self.btn_check_updates.setEnabled(False)
        self.lbl_update_status.setText("🔍 Recherche en cours...")
        self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11.5px;")

        worker = UpdateCheckerWorker(channel=selected_channel, force=True)

        def on_avail(info: Any) -> None:
            self.btn_check_updates.setEnabled(True)
            self.lbl_update_status.setText(f"🎉 Version v{info.version} disponible !")
            self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11.5px; font-weight: bold;")
            if isinstance(info, UpdateInfo):
                dialog = UpdateDialog(info, parent=self.window())
                dialog.exec()

        def on_none(_cur: str) -> None:
            self.btn_check_updates.setEnabled(True)
            self.lbl_update_status.setText(f"✨ Vous disposez de la version la plus récente (v{VERSION_INFO.version})")
            self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11.5px;")

        def on_err(msg: str) -> None:
            self.btn_check_updates.setEnabled(True)
            self.lbl_update_status.setText(f"⚠️ Échec : {msg}")
            self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 11.5px;")

        worker.signals.update_available.connect(on_avail)
        worker.signals.no_update.connect(on_none)
        worker.signals.check_failed.connect(on_err)
        QThreadPool.globalInstance().start(worker)

    def _get_main_window(self) -> Any | None:
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

    def save_tab(self) -> tuple[bool, str | None, str | None]:
        """Sauvegarde les paramètres de l'onglet et retourne (has_theme_change, selected_layout_id, selected_theme_id)."""
        from ankiforge.services.update_checker import SETTINGS_KEY_CHANNEL
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

        # Enregistrement des préférences de démarrage profil et canal de mise à jour dans QSettings
        q_settings = QSettings("AnkiForgeOrg", "AnkiForge")
        if hasattr(self, "chk_auto_startup"):
            q_settings.setValue("profiles/auto_open_startup", self.chk_auto_startup.isChecked())
        if hasattr(self, "cb_default_profile") and self.cb_default_profile.currentData():
            q_settings.setValue("profiles/default_startup_profile", self.cb_default_profile.currentData())
        if hasattr(self, "cb_update_channel") and self.cb_update_channel.currentData():
            q_settings.setValue(SETTINGS_KEY_CHANNEL, self.cb_update_channel.currentData())

        LayoutManager.save_layout_id(profile_name, selected_layout_id)
        engine.save_theme_preference(profile_name, selected_theme_id)

        return True, selected_layout_id, selected_theme_id

    def refresh_theme(self, profile: Any) -> None:
        """Met à jour les styles dynamiques lors d'un changement de thème."""
        self.lbl_sec_app.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_exp.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        if hasattr(self, "lbl_sec_startup"):
            self.lbl_sec_startup.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        if hasattr(self, "lbl_sec_about"):
            self.lbl_sec_about.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        self.card_app.refresh_theme(profile)
        self.card_exp.refresh_theme(profile)
        if hasattr(self, "card_startup"):
            self.card_startup.refresh_theme(profile)
        if hasattr(self, "card_about"):
            self.card_about.refresh_theme(profile)
        for lbl in self.rows_labels:
            lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        if hasattr(self, "lbl_exp_dir"):
            self.lbl_exp_dir.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        if hasattr(self, "btn_check_updates") and hasattr(self.btn_check_updates, "refresh_theme"):
            self.btn_check_updates.refresh_theme(profile)

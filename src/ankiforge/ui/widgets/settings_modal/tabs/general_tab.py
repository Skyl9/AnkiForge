import logging
from pathlib import Path
from typing import Any

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
from ankiforge.services.settings_service import SettingsService, values_equal
from ankiforge.ui.components import (
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.style_engine.appearance import AppearancePreference, ModeSource
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components import (
    LayoutGridSelector,
    SettingsCard,
)
from ankiforge.ui.widgets.settings_modal.dirty import SettingsDirtyMixin
from ankiforge.utils.i18n import FALLBACK_LANGUAGE, available_languages, language_label, normalize_language, tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class GeneralTab(SettingsDirtyMixin, QWidget):
    """Onglet Paramètres Généraux et Apparence."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._update_worker: Any | None = None
        self._setup_ui()
        self._record_initial_state()

    def _setup_ui(self) -> None:
        from PySide6.QtWidgets import QFrame, QScrollArea

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.style_engine import get_style_engine

        engine = get_style_engine()
        profile_name = self._get_profile_name()

        # ── SECTION 1 : APPARENCE & INTERFACE ────────────────────────────────
        self.lbl_sec_app = QLabel(self.tr("APPARENCE & INTERFACE"))
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

        # 1. Disposition de l'interface (Layout) : Grille de miniatures
        self.lbl_layout_title = QLabel(self.tr("Disposition de l'interface (Layout) :"))
        self.lbl_layout_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        card_app_layout.addWidget(self.lbl_layout_title)

        saved_layout_id = LayoutManager.get_saved_layout_id(profile_name)
        self.layout_selector = LayoutGridSelector(current_layout_id=saved_layout_id)
        card_app_layout.addWidget(self.layout_selector)
        self.cb_layout = self.layout_selector  # Duck-typing pour compatibilité ascendante
        self.rows_labels.append(self.lbl_layout_title)

        # 2. Mode d'Apparence (Source du Mode : manuel sombre / manuel clair / système)
        self.cb_mode = StyledComboBox()
        self.cb_mode.setMinimumWidth(260)
        self.cb_mode.setFixedHeight(30)
        self.cb_mode.addItem(load_phosphor_icon("ph.moon", color=DesignTokens.ACCENT_PRIMARY), self.tr("Mode Sombre (Dark)"), "dark")
        self.cb_mode.addItem(load_phosphor_icon("ph.sun", color=DesignTokens.COLOR_YELLOW), self.tr("Mode Clair (Light)"), "light")
        self.cb_mode.addItem(load_phosphor_icon("ph.monitor", color=DesignTokens.TEXT_PRIMARY), self.tr("Suivre le thème système"), "system")

        # Les deux axes d'apparence sont lus séparément : plus de Variante persistée (ADR 0004).
        self._loaded_preference = engine.get_appearance_preference(profile_name)
        self._last_manual_mode = self._loaded_preference.last_manual_mode
        mode_idx = self.cb_mode.findData(self._loaded_preference.mode_source.value)
        if mode_idx >= 0:
            self.cb_mode.setCurrentIndex(mode_idx)
        else:
            self.cb_mode.setCurrentIndex(0)
        self.rows_labels.append(add_setting_row(card_app_layout, self.tr("Mode d'Apparence :"), self.cb_mode))

        # 3. Famille de Thèmes (12 Familles bivalentes) — axe indépendant du Mode
        self.cb_theme = StyledComboBox()
        self.cb_theme.setMinimumWidth(200)
        self.cb_theme.setFixedHeight(30)

        theme_box = QWidget()
        theme_box_layout = QHBoxLayout(theme_box)
        theme_box_layout.setContentsMargins(0, 0, 0, 0)
        theme_box_layout.setSpacing(6)
        theme_box_layout.addWidget(self.cb_theme, 1)

        self.btn_import_theme = SecondaryButton("")
        self.btn_import_theme.setIcon(load_phosphor_icon("ph.upload-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_theme.setToolTip(self.tr("Importer une famille de thème au format JSON..."))
        self.btn_import_theme.setAccessibleName("Importer une famille de thème")
        self.btn_import_theme.setFixedHeight(30)
        self.btn_import_theme.clicked.connect(self._import_theme)
        theme_box_layout.addWidget(self.btn_import_theme)

        self.btn_export_theme = SecondaryButton("")
        self.btn_export_theme.setIcon(load_phosphor_icon("ph.download-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_export_theme.setToolTip(self.tr("Exporter la famille de thème sélectionnée au format JSON..."))
        self.btn_export_theme.setAccessibleName("Exporter la famille de thème")
        self.btn_export_theme.setFixedHeight(30)
        self.btn_export_theme.clicked.connect(self._export_theme)
        theme_box_layout.addWidget(self.btn_export_theme)

        def select_family(family_id: str | None) -> None:
            """Sélectionne la Famille donnée ; « aucune » est une entrée à part entière."""
            for i in range(self.cb_theme.count()):
                if self.cb_theme.itemData(i) == family_id:
                    self.cb_theme.setCurrentIndex(i)
                    return

        self._select_family = select_family

        # La Famille vit dans `selected_family_id`, initialisée depuis la préférence persistée
        # puis mise à jour par les seuls choix de l'utilisateur : repeupler la liste pour un
        # changement de Mode ne doit donc jamais y toucher.
        selected_family_id: str | None = self._loaded_preference.family_id
        is_repopulating = False

        def on_family_changed(index: int) -> None:
            nonlocal selected_family_id
            if not is_repopulating:
                selected_family_id = self.cb_theme.itemData(index)
            self._update_effective_variant_summary()

        def populate_theme_families() -> None:
            nonlocal is_repopulating
            current_mode = self.cb_mode.currentData()
            is_system_selected = current_mode == "system"
            is_dark_selected = current_mode == "dark"
            is_repopulating = True
            try:
                self.cb_theme.clear()
                # « Aucune Famille choisie » est un état valide : la Famille suit alors le layout actif.
                default_family = engine.get_default_family_for_layout(LayoutManager.get_saved_layout_id(profile_name))
                self.cb_theme.addItem(
                    load_phosphor_icon("ph.arrow-counter-clockwise", color=DesignTokens.TEXT_MUTED),
                    tr("Famille par défaut du layout (%1)", default_family.name),
                    None,
                )
                families = engine.get_theme_families()
                for fam in families:
                    if is_system_selected:
                        icon_name = fam.icon or "ph.palette"
                        icon_color = DesignTokens.TEXT_PRIMARY
                    else:
                        icon_name = fam.icon or ("ph.moon" if is_dark_selected else "ph.sun")
                        icon_color = DesignTokens.ACCENT_PRIMARY if is_dark_selected else DesignTokens.COLOR_YELLOW
                    self.cb_theme.addItem(load_phosphor_icon(icon_name, color=icon_color), fam.name, fam.id)
                # Une Famille persistée mais inconnue de la bibliothèque (thème tiers, ADR 0005)
                # doit survivre à l'enregistrement du Mode : l'ajouter évite de l'effacer.
                if selected_family_id is not None and all(fam.id != selected_family_id for fam in families):
                    self.cb_theme.addItem(
                        load_phosphor_icon("ph.warning-circle", color=DesignTokens.COLOR_YELLOW),
                        tr("%1 (indisponible)", selected_family_id),
                        selected_family_id,
                    )
                select_family(selected_family_id)
            finally:
                is_repopulating = False

        self._populate_theme_families = populate_theme_families
        self.cb_theme.currentIndexChanged.connect(on_family_changed)
        populate_theme_families()

        def on_mode_changed(_idx: int) -> None:
            mode_source = ModeSource.coerce(self.cb_mode.currentData(), default=ModeSource.DARK)
            if mode_source.is_manual:
                self._last_manual_mode = mode_source
            populate_theme_families()
            self._update_effective_variant_summary()

        self.cb_mode.currentIndexChanged.connect(on_mode_changed)

        def on_layout_changed(_idx: int) -> None:
            if self.cb_theme.currentData() is None:
                populate_theme_families()
            self._update_effective_variant_summary()

        self.cb_layout.currentIndexChanged.connect(on_layout_changed)
        self.rows_labels.append(add_setting_row(card_app_layout, self.tr("Famille de Thèmes :"), theme_box))

        # Résumé séparé de la Variante effective (affiché quand la Source est « Système »)
        self.row_effective_variant = QWidget()
        row_effective_layout = QHBoxLayout(self.row_effective_variant)
        row_effective_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_effective_variant_title = QLabel(self.tr("Variante effective appliquée :"))
        self.lbl_effective_variant_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px; font-weight: 500;")
        row_effective_layout.addWidget(self.lbl_effective_variant_title)
        row_effective_layout.addStretch()
        self.lbl_effective_variant_badge = QLabel()
        self.lbl_effective_variant_badge.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_SM}px; "
            "padding: 4px 10px; font-size: 11.5px; font-weight: 500;"
        )
        row_effective_layout.addWidget(self.lbl_effective_variant_badge)
        card_app_layout.addWidget(self.row_effective_variant)

        engine.system_mode_changed.connect(self._on_system_mode_changed)
        engine.theme_changed.connect(self._on_theme_changed)
        self.destroyed.connect(self._cleanup_connections)
        self._update_effective_variant_summary()

        # 4. Langue — la liste vient du dossier de catalogues, pas d'une constante : un
        # catalogue déposé par la build (ou par l'utilisateur) devient sélectionnable sans
        # toucher au code. Le libellé est un endonyme (« Français », « English ») et n'est
        # donc pas traduit ; le code ISO est conservé en ``userData``.
        self.cb_lang = StyledComboBox()
        self.cb_lang.setMinimumWidth(260)
        self.cb_lang.setFixedHeight(30)
        lang_icon = load_phosphor_icon("ph.translate", color=DesignTokens.TEXT_PRIMARY)
        for code in available_languages():
            self.cb_lang.addItem(lang_icon, language_label(code), code)
        current_lang = normalize_language(str(SettingsService.get("ui/language", "")))
        self.cb_lang.setCurrentIndex(max(0, self.cb_lang.findData(current_lang)))
        self.rows_labels.append(add_setting_row(card_app_layout, self.tr("Langue de l'interface :"), self.cb_lang))

        # 5. Style Studio de Création
        self.cb_batch_style = StyledComboBox()
        self.cb_batch_style.setMinimumWidth(260)
        self.cb_batch_style.setFixedHeight(30)
        self.cb_batch_style.addItem(load_phosphor_icon("ph.gauge", color=DesignTokens.TEXT_PRIMARY), self.tr("CI/CD (Tableau de bord industriel)"))
        self.cb_batch_style.addItem(load_phosphor_icon("ph.kanban", color=DesignTokens.TEXT_PRIMARY), self.tr("Kanban (Flux de tâches)"))
        self.cb_batch_style.addItem(load_phosphor_icon("ph.steps", color=DesignTokens.TEXT_PRIMARY), self.tr("Assistant (Pas-à-pas)"))
        self.cb_batch_style.setCurrentText(str(SettingsService.get("app/batch_factory_style", "CI/CD (Tableau de bord industriel)")))
        self.rows_labels.append(add_setting_row(card_app_layout, self.tr("Style Studio de Création :"), self.cb_batch_style))

        layout.addWidget(self.card_app)

        # ── SECTION 2 : DOSSIERS & CHEMINS DE SORTIE ─────────────────────────
        self.lbl_sec_exp = QLabel(self.tr("DOSSIERS & CHEMINS DE SORTIE"))
        self.lbl_sec_exp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(self.lbl_sec_exp)

        self.card_exp = SettingsCard()
        card_exp_layout = QVBoxLayout(self.card_exp)
        card_exp_layout.setContentsMargins(14, 12, 14, 12)
        card_exp_layout.setSpacing(10)

        exp_row = QHBoxLayout()
        self.lbl_exp_dir = QLabel(self.tr("Dossier d'exportation par défaut :"))
        self.lbl_exp_dir.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        exp_row.addWidget(self.lbl_exp_dir)

        default_export = str(Path.home() / "AnkiForge" / "Exports")
        self.le_export = StyledLineEdit()
        self.le_export.setFixedHeight(30)
        self.le_export.setText(str(SettingsService.get("app/export_path", default_export)))
        exp_row.addWidget(self.le_export, 1)

        btn_browse = SecondaryButton("")
        btn_browse.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        btn_browse.setToolTip(self.tr("Parcourir et sélectionner le dossier"))
        btn_browse.setAccessibleName("Parcourir le dossier d'exportation")
        btn_browse.setFixedHeight(30)
        btn_browse.clicked.connect(self._browse_export)
        exp_row.addWidget(btn_browse)

        btn_open = SecondaryButton("")
        btn_open.setIcon(load_phosphor_icon("ph.arrow-square-out", color=DesignTokens.TEXT_PRIMARY))
        btn_open.setToolTip(self.tr("Ouvrir dans l'explorateur de fichiers"))
        btn_open.setAccessibleName("Ouvrir le dossier d'exportation dans l'explorateur")
        btn_open.setFixedHeight(30)
        btn_open.clicked.connect(self._open_export_dir)
        exp_row.addWidget(btn_open)

        card_exp_layout.addLayout(exp_row)
        layout.addWidget(self.card_exp)

        # ── SECTION 3 : ESPACES DE TRAVAIL & DÉMARRAGE ──────────────────────
        self.lbl_sec_startup = QLabel(self.tr("ESPACES DE TRAVAIL & DÉMARRAGE"))
        self.lbl_sec_startup.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(self.lbl_sec_startup)

        self.card_startup = SettingsCard()
        card_startup_layout = QVBoxLayout(self.card_startup)
        card_startup_layout.setContentsMargins(14, 12, 14, 12)
        card_startup_layout.setSpacing(12)

        from ankiforge.utils.environment import get_app_qsettings

        q_settings = get_app_qsettings()
        auto_open_val = q_settings.value("profiles/auto_open_startup", False, type=bool)
        default_prof_val = str(q_settings.value("profiles/default_startup_profile", profile_name or "default"))

        # 1. Checkbox ouverture automatique
        self.chk_auto_startup = QCheckBox(self.tr("Toujours ouvrir l'espace par défaut sans demander au lancement"))
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

        self.rows_labels.append(add_setting_row(card_startup_layout, self.tr("Espace de travail de démarrage :"), self.cb_default_profile))

        layout.addWidget(self.card_startup)

        # ── SECTION 4 : À PROPOS & MISES À JOUR ─────────────────────────────
        self.lbl_sec_about = QLabel(self.tr("À PROPOS & MISES À JOUR"))
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
        lbl_v_title = QLabel(self.tr("Version d'AnkiForge :"))
        lbl_v_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        self.rows_labels.append(lbl_v_title)
        version_row.addWidget(lbl_v_title)
        version_row.addStretch()

        v_badge = Badge(f"v{VERSION_INFO.version}", variant="primary")
        version_row.addWidget(v_badge)

        lbl_meta = QLabel(tr("(%1) · %2", VERSION_INFO.commit_hash, VERSION_INFO.platform_str))
        lbl_meta.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px;")
        version_row.addWidget(lbl_meta)
        card_about_layout.addLayout(version_row)

        # 2. Canal de mise à jour (Stable vs Nightly)
        self.cb_update_channel = StyledComboBox()
        self.cb_update_channel.setMinimumWidth(260)
        self.cb_update_channel.setFixedHeight(30)
        self.cb_update_channel.addItem(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN), self.tr("Canal Stable (Recommandé)"), "stable")
        self.cb_update_channel.addItem(load_phosphor_icon("ph.moon", color=DesignTokens.COLOR_YELLOW), self.tr("Canal Nightly (Bêta / Edge)"), "nightly")

        saved_channel = str(q_settings.value(SETTINGS_KEY_CHANNEL, "stable"))
        ch_idx = self.cb_update_channel.findData(saved_channel)
        if ch_idx >= 0:
            self.cb_update_channel.setCurrentIndex(ch_idx)

        self.rows_labels.append(add_setting_row(card_about_layout, self.tr("Canal de distribution des mises à jour :"), self.cb_update_channel))

        # 3. Fréquence de recherche automatique
        from ankiforge.services.update_checker import get_check_interval_seconds

        self.cb_check_interval = StyledComboBox()
        self.cb_check_interval.setMinimumWidth(260)
        self.cb_check_interval.setFixedHeight(30)
        self.cb_check_interval.addItem(load_phosphor_icon("ph.clock", color=DesignTokens.TEXT_PRIMARY), self.tr("Toutes les 4 heures (Recommandé)"), 14400)
        self.cb_check_interval.addItem(load_phosphor_icon("ph.calendar", color=DesignTokens.TEXT_PRIMARY), self.tr("Quotidien (Toutes les 24 heures)"), 86400)
        self.cb_check_interval.addItem(load_phosphor_icon("ph.lightning", color=DesignTokens.COLOR_GREEN), self.tr("Au démarrage de l'application"), 0)
        self.cb_check_interval.addItem(load_phosphor_icon("ph.pause-circle", color=DesignTokens.COLOR_YELLOW), self.tr("Manuel uniquement (Désactivé)"), -1)

        saved_interval = get_check_interval_seconds()
        int_idx = self.cb_check_interval.findData(saved_interval)
        if int_idx >= 0:
            self.cb_check_interval.setCurrentIndex(int_idx)

        self.rows_labels.append(add_setting_row(card_about_layout, self.tr("Fréquence de recherche automatique :"), self.cb_check_interval))

        # 4. Action de recherche manuelle
        check_row = QHBoxLayout()
        lbl_check_title = QLabel(self.tr("Recherche de mises à jour :"))
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

        # 4. Retours & Boîte à idées
        feedback_row = QHBoxLayout()
        lbl_feedback_title = QLabel(self.tr("Retours & Suggestions :"))
        lbl_feedback_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        self.rows_labels.append(lbl_feedback_title)
        feedback_row.addWidget(lbl_feedback_title)
        feedback_row.addStretch()

        self.btn_open_feedback = SecondaryButton("Signaler un bug ou proposer une idée...")
        self.btn_open_feedback.setIcon(load_phosphor_icon("ph.chat-circle-dots", color=DesignTokens.TEXT_PRIMARY))
        self.btn_open_feedback.setFixedHeight(30)
        self.btn_open_feedback.clicked.connect(self._on_open_feedback_clicked)
        feedback_row.addWidget(self.btn_open_feedback)

        card_about_layout.addLayout(feedback_row)
        layout.addWidget(self.card_about)

        layout.addStretch()

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

    def _on_check_updates_clicked(self) -> None:
        """Déclenche manuellement la recherche de mise à jour avec retour visuel."""
        from PySide6.QtCore import QThreadPool

        from ankiforge.services.update_checker import UpdateCheckerWorker, UpdateInfo
        from ankiforge.ui.dialogs.update_dialog import UpdateDialog
        from ankiforge.version import VERSION_INFO

        selected_channel = str(self.cb_update_channel.currentData() or "stable")
        self.btn_check_updates.setEnabled(False)
        self.lbl_update_status.setText(self.tr("Recherche en cours..."))
        self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11.5px;")

        worker = UpdateCheckerWorker(channel=selected_channel, force=True)
        self._update_worker = worker

        def on_avail(info: Any) -> None:
            self._update_worker = None
            self.btn_check_updates.setEnabled(True)
            self.lbl_update_status.setText(tr("Version v%1 disponible !", info.version))
            self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11.5px; font-weight: bold;")
            if isinstance(info, UpdateInfo):
                dialog = UpdateDialog(info, parent=self.window())
                dialog.exec()

        def on_none(_cur: str) -> None:
            self._update_worker = None
            self.btn_check_updates.setEnabled(True)
            self.lbl_update_status.setText(tr("Vous disposez de la version la plus récente (%1)", VERSION_INFO.short_display_version))
            self.lbl_update_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11.5px;")

        def on_err(msg: str) -> None:
            self._update_worker = None
            self.btn_check_updates.setEnabled(True)
            self.lbl_update_status.setText(tr("Échec : %1", msg))
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

    def _on_system_mode_changed(self, _regime: object = None) -> None:
        self._update_effective_variant_summary()

    def _on_theme_changed(self, _profile: object = None) -> None:
        self._update_effective_variant_summary()

    def _cleanup_connections(self) -> None:
        import contextlib

        from ankiforge.ui.style_engine import get_style_engine

        engine = get_style_engine()
        with contextlib.suppress(Exception):
            engine.system_mode_changed.disconnect(self._on_system_mode_changed)
        with contextlib.suppress(Exception):
            engine.theme_changed.disconnect(self._on_theme_changed)

    def _update_effective_variant_summary(self) -> None:
        """Met à jour le résumé séparé de la variante effective quand la Source est « Système »."""
        from shiboken6 import isValid

        if not isValid(self) or not hasattr(self, "cb_mode") or not isValid(self.cb_mode):
            return

        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.style_engine import get_style_engine, probe_system_mode_source

        engine = get_style_engine()
        mode_val = self.cb_mode.currentData()
        is_system = mode_val == "system"
        if hasattr(self, "row_effective_variant") and isValid(self.row_effective_variant):
            self.row_effective_variant.setVisible(is_system)
        if not is_system or not hasattr(self, "lbl_effective_variant_badge") or not isValid(self.lbl_effective_variant_badge):
            return

        family_id = self.cb_theme.currentData()
        family = engine.get_family_for_theme(family_id) if family_id else None
        if family is None:
            profile_name = self._get_profile_name()
            saved_layout_id = self.cb_layout.currentData() or LayoutManager.get_saved_layout_id(profile_name)
            family = engine.get_default_family_for_layout(saved_layout_id)

        system_regime = probe_system_mode_source()
        if system_regime is None:
            # L'interface ne prétend pas connaître le régime du système avant qu'il ne soit déclaré
            fallback_mode = getattr(self, "_last_manual_mode", ModeSource.DARK)
            fallback_label = "Sombre" if fallback_mode is ModeSource.DARK else "Clair"
            effective_variant = family.dark_theme if fallback_mode is ModeSource.DARK else family.light_theme
            self.lbl_effective_variant_badge.setText(tr("Système non déclaré · Repli %1 → %2", fallback_label, effective_variant.name))
            self.lbl_effective_variant_badge.setToolTip(
                tr(
                    "Le système d'exploitation n'annonce aucun régime clair ou sombre.\nL'application retombe sur votre dernier choix manuel (%1).\nVariante active : %2",
                    fallback_label,
                    effective_variant.name,
                )
            )
        else:
            system_label = "Sombre" if system_regime is ModeSource.DARK else "Clair"
            effective_variant = family.dark_theme if system_regime is ModeSource.DARK else family.light_theme
            self.lbl_effective_variant_badge.setText(tr("Système (%1) → %2", system_label, effective_variant.name))
            self.lbl_effective_variant_badge.setToolTip(tr("Régime système détecté : %1.\nVariante active : %2", system_label, effective_variant.name))

    def _selected_appearance_preference(self) -> AppearancePreference:
        """Préférence d'apparence correspondant aux deux sélecteurs."""
        selected = ModeSource.coerce(self.cb_mode.currentData(), default=self._loaded_preference.mode_source)
        last_manual = getattr(self, "_last_manual_mode", self._loaded_preference.last_manual_mode)
        return AppearancePreference(
            family_id=self.cb_theme.currentData(),
            mode_source=selected,
            last_manual_mode=last_manual,
        )

    def save_tab(self) -> tuple[bool, str | None, str | None]:
        """Sauvegarde les paramètres de l'onglet et retourne (has_change, selected_layout_id, selected_family_id)."""
        from ankiforge.services.update_checker import (
            DEFAULT_CHECK_INTERVAL_SECONDS,
            SETTINGS_KEY_CHANNEL,
            SETTINGS_KEY_CHECK_INTERVAL,
        )
        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.style_engine import get_style_engine

        profile_name = self._get_profile_name()
        engine = get_style_engine()

        selected_layout_id = self.cb_layout.currentData()
        selected_family_id = self.cb_theme.currentData()

        has_change = self.has_pending_changes()

        # Enregistrement uniquement des paramètres réellement modifiés
        for key, current_val, initial_key in (
            ("ui/language", str(self.cb_lang.currentData() or FALLBACK_LANGUAGE), "lang"),
            ("app/batch_factory_style", self.cb_batch_style.currentText(), "batch_style"),
            ("app/export_path", self.le_export.text().strip(), "export_path"),
        ):
            if not hasattr(self, "_initial") or not values_equal(self._initial.get(initial_key), current_val):
                SettingsService.set(key, current_val, category="general")
                has_change = True

        # Enregistrement des préférences de démarrage profil et canal de mise à jour dans QSettings
        from ankiforge.utils.environment import get_app_qsettings

        q_settings = get_app_qsettings()
        if hasattr(self, "chk_auto_startup") and not values_equal(q_settings.value("profiles/auto_open_startup", False, type=bool), self.chk_auto_startup.isChecked()):
            q_settings.setValue("profiles/auto_open_startup", self.chk_auto_startup.isChecked())
            has_change = True
        if (
            hasattr(self, "cb_default_profile")
            and self.cb_default_profile.currentData()
            and not values_equal(q_settings.value("profiles/default_startup_profile", profile_name or "default"), self.cb_default_profile.currentData())
        ):
            q_settings.setValue("profiles/default_startup_profile", self.cb_default_profile.currentData())
            has_change = True
        if hasattr(self, "cb_update_channel") and self.cb_update_channel.currentData() and not values_equal(q_settings.value(SETTINGS_KEY_CHANNEL, "stable"), self.cb_update_channel.currentData()):
            q_settings.setValue(SETTINGS_KEY_CHANNEL, self.cb_update_channel.currentData())
            has_change = True
        if (
            hasattr(self, "cb_check_interval")
            and self.cb_check_interval.currentData() is not None
            and not values_equal(q_settings.value(SETTINGS_KEY_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL_SECONDS), self.cb_check_interval.currentData())
        ):
            q_settings.setValue(SETTINGS_KEY_CHECK_INTERVAL, int(self.cb_check_interval.currentData()))
            has_change = True

        if self._layout_field_changed():
            LayoutManager.save_layout_id(profile_name, selected_layout_id)
        if self._theme_field_changed() or self._mode_field_changed():
            self._loaded_preference = engine.save_appearance_preference(profile_name, self._selected_appearance_preference())

        self._record_initial_state()

        return has_change, selected_layout_id, selected_family_id

    def _record_initial_state(self) -> None:
        """Capture l'état actuel des contrôles en mémoire vive pour la détection dirty à zéro coût BDD."""
        default_profile = self._get_profile_name() or "default"
        self._initial: dict[str, Any] = {
            "layout": self.cb_layout.currentData(),
            "theme": self.cb_theme.currentData(),
            "mode": self.cb_mode.currentData(),
            "lang": str(self.cb_lang.currentData() or FALLBACK_LANGUAGE),
            "batch_style": self.cb_batch_style.currentText(),
            "export_path": self.le_export.text().strip(),
            "auto_startup": self.chk_auto_startup.isChecked() if hasattr(self, "chk_auto_startup") else False,
            "default_profile": (self.cb_default_profile.currentData() or default_profile) if hasattr(self, "cb_default_profile") else default_profile,
            "update_channel": (self.cb_update_channel.currentData() or "stable") if hasattr(self, "cb_update_channel") else "stable",
            "check_interval": (self.cb_check_interval.currentData() if hasattr(self, "cb_check_interval") else 14400),
        }

    def _layout_field_changed(self) -> bool:
        if not hasattr(self, "_initial"):
            return False
        return not values_equal(self.cb_layout.currentData(), self._initial.get("layout"))

    def _theme_field_changed(self) -> bool:
        if not hasattr(self, "_initial"):
            return False
        return not values_equal(self.cb_theme.currentData(), self._initial.get("theme"))

    def _mode_field_changed(self) -> bool:
        if not hasattr(self, "_initial"):
            return False
        return not values_equal(self.cb_mode.currentData(), self._initial.get("mode"))

    def has_pending_changes(self) -> bool:
        """True si au moins un paramètre de l'onglet diffère de sa valeur initiale en mémoire."""
        if not hasattr(self, "_initial"):
            return False
        default_profile = self._get_profile_name() or "default"
        current = {
            "layout": self.cb_layout.currentData(),
            "theme": self.cb_theme.currentData(),
            "mode": self.cb_mode.currentData(),
            "lang": str(self.cb_lang.currentData() or FALLBACK_LANGUAGE),
            "batch_style": self.cb_batch_style.currentText(),
            "export_path": self.le_export.text().strip(),
            "auto_startup": self.chk_auto_startup.isChecked() if hasattr(self, "chk_auto_startup") else False,
            "default_profile": (self.cb_default_profile.currentData() or default_profile) if hasattr(self, "cb_default_profile") else default_profile,
            "update_channel": (self.cb_update_channel.currentData() or "stable") if hasattr(self, "cb_update_channel") else "stable",
        }
        return any(not values_equal(current[k], self._initial.get(k)) for k in current)

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
        if hasattr(self, "btn_open_feedback") and hasattr(self.btn_open_feedback, "refresh_theme"):
            self.btn_open_feedback.refresh_theme(profile)
        if hasattr(self, "btn_import_theme"):
            self.btn_import_theme.setIcon(load_phosphor_icon("ph.upload-simple", color=profile.text_primary))
        if hasattr(self, "btn_export_theme"):
            self.btn_export_theme.setIcon(load_phosphor_icon("ph.download-simple", color=profile.text_primary))
        if hasattr(self, "lbl_effective_variant_title"):
            self.lbl_effective_variant_title.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11.5px; font-weight: 500;")
        if hasattr(self, "lbl_effective_variant_badge"):
            self.lbl_effective_variant_badge.setStyleSheet(
                f"background-color: {profile.bg_input}; color: {profile.text_primary}; "
                f"border: 1px solid {profile.border_color}; border-radius: {profile.radius_sm}px; "
                "padding: 4px 10px; font-size: 11.5px; font-weight: 500;"
            )
        self._update_effective_variant_summary()

    def _import_theme(self) -> None:
        """Importe un fichier de thème JSON dans la bibliothèque globale."""
        from ankiforge.ui.style_engine import get_style_engine
        from ankiforge.ui.widgets.toast import show_toast

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Importer une famille de thèmes",
            "",
            "Thèmes AnkiForge (*.json);;Tous les fichiers (*)",
        )
        if not file_path:
            return

        engine = get_style_engine()
        try:
            family, _ = engine.import_theme(file_path)
            if hasattr(self, "_populate_theme_families"):
                self._populate_theme_families()
            if hasattr(self, "_select_family"):
                self._select_family(family.id)
            show_toast(self, tr("Thème '%1' importé avec succès !", family.name), is_error=False)
        except Exception as err:
            logger.error("Erreur lors de l'import du thème %s : %s", file_path, err)
            show_toast(self, tr("Échec de l'import du thème : %1", err), is_error=True)

    def _export_theme(self) -> None:
        """Exporte la famille de thème sélectionnée au format JSON."""
        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.style_engine import get_style_engine
        from ankiforge.ui.widgets.toast import show_toast

        engine = get_style_engine()
        current_family_id = self.cb_theme.currentData()
        if not current_family_id:
            profile_name = self._get_profile_name()
            layout_id = LayoutManager.get_saved_layout_id(profile_name)
            family = engine.get_default_family_for_layout(layout_id)
        else:
            family = engine.get_family_for_theme(current_family_id)

        if family is None:
            show_toast(self, self.tr("Aucune famille de thème disponible pour l'export."), is_error=True)
            return

        suggested_name = f"{family.id}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter la famille de thèmes en JSON",
            suggested_name,
            "Thèmes AnkiForge (*.json);;Tous les fichiers (*)",
        )
        if not file_path:
            return

        try:
            engine.export_theme(family, file_path)
            show_toast(self, tr("Famille '%1' exportée avec succès !", family.name), is_error=False)
        except Exception as err:
            logger.error("Erreur lors de l'export du thème %s : %s", file_path, err)
            show_toast(self, tr("Échec de l'export du thème : %1", err), is_error=True)

    def _on_open_feedback_clicked(self) -> None:
        """Déclenche l'événement d'ouverture de la boîte de dialogue de feedback."""
        from ankiforge.utils.event_bus import OpenFeedbackRequestedEvent, event_bus

        event_bus.publish(OpenFeedbackRequestedEvent(tab="bug"))

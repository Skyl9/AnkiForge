from typing import Any

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import (
    IconButton,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.dialogs.addon_manager_dialog import AddonManagerWidget
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.settings_modal.components import (
    SettingsNavButton,
    apply_pill_badge_style,
)
from ankiforge.ui.widgets.settings_modal.tabs import (
    AIEnginesTab,
    AnkiSyncTab,
    GeneralTab,
    StorageMaintenanceTab,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_active_profile


class SettingsModal(QDialog):
    """
    Modale de Paramètres Globale AnkiForge.
    Architecture moderne 960x640px, non bloquante, 5 onglets thématiques réactifs.
    """

    focus_changed = Signal(bool)
    theme_applied = Signal(str)
    layout_applied = Signal(str)

    def __init__(self, ai_manager: Any = None, profile_name: str | None = None, parent: QWidget | None = None) -> None:
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

        self.nav_btns: list[SettingsNavButton] = []

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

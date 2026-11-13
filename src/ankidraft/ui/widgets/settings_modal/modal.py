from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankidraft.ui.components import (
    IconButton,
    PrimaryButton,
    SecondaryButton,
)
from ankidraft.ui.theme import DesignTokens, apply_shadow
from ankidraft.ui.widgets.settings_modal.components import (
    CollapsibleSettingsGroup,
    SettingsNavButton,
    SettingsSearchView,
    apply_pill_badge_style,
)
from ankidraft.ui.widgets.settings_modal.search_registry import (
    SettingDescriptor,
    SettingsRegistry,
)
from ankidraft.ui.widgets.settings_modal.tabs.general_tab import GeneralTab
from ankidraft.ui.widgets.toast import show_toast
from ankidraft.utils.environment import is_development
from ankidraft.utils.i18n import tr
from ankidraft.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankidraft.utils.paths import get_active_profile

if TYPE_CHECKING:
    from ankidraft.ui.dialogs.addon_manager_dialog import AddonManagerWidget
    from ankidraft.ui.widgets.settings_modal.tabs import (
        AIEnginesTab,
        AnkiSyncTab,
        DeveloperTab,
        HelpTab,
        KeyboardTab,
        StorageMaintenanceTab,
        TTSSettingsTab,
    )


class SettingsModal(QDialog):
    """Modale de Paramètres Globale AnkiForge.

    Architecture moderne 960x640px, non bloquante, 5 onglets thématiques réactifs.
    """

    focus_changed = Signal(bool)
    theme_applied = Signal(str)
    layout_applied = Signal(str)
    rotate_mcp_token_requested = Signal()

    def __init__(self, ai_manager: Any = None, profile_name: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name or get_active_profile()
        self.stacked_widget = QStackedWidget()

        self._ai_tab: AIEnginesTab | None = None
        self._anki_tab: AnkiSyncTab | None = None
        self._tts_tab: TTSSettingsTab | None = None
        self._maint_tab: StorageMaintenanceTab | None = None
        self._addons_tab: AddonManagerWidget | None = None
        self._support_tab: Any = None
        self._keyboard_tab: KeyboardTab | None = None
        self._help_tab: HelpTab | None = None
        self._dev_tab: DeveloperTab | None = None
        self._tabs: list[QWidget | None] = []
        self._wired_line_edits: set[int] = set()
        self._active_tab_index = 0
        self._search_stack_index: int | None = None
        self._search_field: QLineEdit | None = None
        self._search_view: SettingsSearchView | None = None
        self._pulse_timer: QTimer | None = None
        self._pulse_original: tuple[QWidget, str] | None = None

        self.setWindowTitle(self.tr("Paramètres AnkiForge"))
        self.setMinimumSize(820, 560)
        self.resize(880, 620)
        self.setModal(False)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinMaxButtonsHint)

        self._setup_ui()
        self._connect_signals()

        # Surveillance légère des modifications : désactive « Enregistrer » si rien n'a changé.
        self._dirty_timer = QTimer(self)
        self._dirty_timer.setInterval(450)
        self._dirty_timer.timeout.connect(self._update_save_enabled)
        self._update_save_enabled()

    def showEvent(self, event: Any) -> None:
        self._dirty_timer.start()
        self._update_save_enabled()
        super().showEvent(event)

    def hideEvent(self, event: Any) -> None:
        self._dirty_timer.stop()
        super().hideEvent(event)

    def _tabs_have_changes(self) -> bool:
        for tab in self._tabs:
            if tab is not None:
                checker = getattr(tab, "has_pending_changes", None)
                if checker is not None and checker():
                    return True
        return False

    def _ensure_tab_loaded(self, index: int) -> QWidget:
        """Instancie à la demande (lazy) l'onglet correspondant à l'index s'il n'existe pas encore."""
        if 0 <= index < len(self._tabs) and self._tabs[index] is not None:
            return self._tabs[index]  # type: ignore[return-value]

        tab: QWidget
        if index == 1:
            from ankidraft.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab

            self._ai_tab = AIEnginesTab(self.ai_manager)
            self._ai_tab.rotate_mcp_token_requested.connect(self.rotate_mcp_token_requested.emit)
            tab = self._ai_tab
        elif index == 2:
            from ankidraft.ui.widgets.settings_modal.tabs.anki_sync_tab import AnkiSyncTab

            self._anki_tab = AnkiSyncTab()
            tab = self._anki_tab
        elif index == 3:
            from ankidraft.ui.widgets.settings_modal.tabs.tts_tab import TTSSettingsTab

            self._tts_tab = TTSSettingsTab()
            tab = self._tts_tab
        elif index == 4:
            from ankidraft.ui.widgets.settings_modal.tabs.storage_tab import StorageMaintenanceTab

            self._maint_tab = StorageMaintenanceTab()
            tab = self._maint_tab
        elif index == 5:
            from ankidraft.ui.dialogs.addon_manager_dialog import AddonManagerWidget

            self._addons_tab = AddonManagerWidget()
            tab = self._addons_tab
        elif index == 6:
            from ankidraft.ui.widgets.settings_modal.tabs.support_tab import SupportTab

            self._support_tab = SupportTab()
            tab = self._support_tab
        elif index == 7:
            from ankidraft.ui.widgets.settings_modal.tabs.keyboard_tab import KeyboardTab

            self._keyboard_tab = KeyboardTab(parent=self)
            tab = self._keyboard_tab
        elif index == 8:
            from ankidraft.ui.widgets.settings_modal.tabs.help_tab import HelpTab

            self._help_tab = HelpTab(parent=self)
            tab = self._help_tab
        elif index == 9 and is_development():
            from ankidraft.ui.widgets.settings_modal.tabs.developer_tab import DeveloperTab

            self._dev_tab = DeveloperTab(parent=self)
            tab = self._dev_tab
        else:
            return self.general_tab

        self._tabs[index] = tab

        # Remplacement du placeholder dans le stacked widget
        old_widget = self.stacked_widget.widget(index)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old_widget)
        if old_widget is not None:
            old_widget.deleteLater()
        self.stacked_widget.insertWidget(index, tab)
        self.stacked_widget.blockSignals(False)

        from ankidraft.ui.style_engine import get_style_engine

        current_theme = get_style_engine().current_theme
        if current_theme and hasattr(tab, "refresh_theme"):
            tab.refresh_theme(current_theme)

        self._connect_tab_line_edits(tab)

        return tab

    def _connect_tab_line_edits(self, widget: QWidget) -> None:
        """Connecte le signal returnPressed de tous les QLineEdit enfants à _save_all."""
        for le in widget.findChildren(QLineEdit):
            widget_id = id(le)
            if widget_id in self._wired_line_edits:
                continue
            le.returnPressed.connect(self._save_all)
            self._wired_line_edits.add(widget_id)

    @property
    def ai_tab(self) -> Any:
        return self._ensure_tab_loaded(1)

    @ai_tab.setter
    def ai_tab(self, value: Any) -> None:
        self._ai_tab = value
        self._tabs[1] = value
        old = self.stacked_widget.widget(1)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(1, value)
        self.stacked_widget.blockSignals(False)

    @property
    def anki_tab(self) -> Any:
        return self._ensure_tab_loaded(2)

    @anki_tab.setter
    def anki_tab(self, value: Any) -> None:
        self._anki_tab = value
        self._tabs[2] = value
        old = self.stacked_widget.widget(2)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(2, value)
        self.stacked_widget.blockSignals(False)

    @property
    def tts_tab(self) -> Any:
        return self._ensure_tab_loaded(3)

    @tts_tab.setter
    def tts_tab(self, value: Any) -> None:
        self._tts_tab = value
        self._tabs[3] = value
        old = self.stacked_widget.widget(3)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(3, value)
        self.stacked_widget.blockSignals(False)

    @property
    def maint_tab(self) -> Any:
        return self._ensure_tab_loaded(4)

    @maint_tab.setter
    def maint_tab(self, value: Any) -> None:
        self._maint_tab = value
        self._tabs[4] = value
        old = self.stacked_widget.widget(4)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(4, value)
        self.stacked_widget.blockSignals(False)

    @property
    def addons_tab(self) -> Any:
        return self._ensure_tab_loaded(5)

    @addons_tab.setter
    def addons_tab(self, value: Any) -> None:
        self._addons_tab = value
        self._tabs[5] = value
        old = self.stacked_widget.widget(5)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(5, value)
        self.stacked_widget.blockSignals(False)

    @property
    def support_tab(self) -> Any:
        return self._ensure_tab_loaded(6)

    @support_tab.setter
    def support_tab(self, value: Any) -> None:
        self._support_tab = value
        self._tabs[6] = value
        old = self.stacked_widget.widget(6)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(6, value)
        self.stacked_widget.blockSignals(False)

    @property
    def keyboard_tab(self) -> Any:
        return self._ensure_tab_loaded(7)

    @keyboard_tab.setter
    def keyboard_tab(self, value: Any) -> None:
        self._keyboard_tab = value
        self._tabs[7] = value
        old = self.stacked_widget.widget(7)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(7, value)
        self.stacked_widget.blockSignals(False)

    @property
    def help_tab(self) -> Any:
        return self._ensure_tab_loaded(8)

    @help_tab.setter
    def help_tab(self, value: Any) -> None:
        self._help_tab = value
        self._tabs[8] = value
        old = self.stacked_widget.widget(8)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(8, value)
        self.stacked_widget.blockSignals(False)

    @property
    def dev_tab(self) -> Any:
        if is_development():
            return self._ensure_tab_loaded(9)
        return None

    @dev_tab.setter
    def dev_tab(self, value: Any) -> None:
        if not is_development():
            return
        self._dev_tab = value
        self._tabs[9] = value
        old = self.stacked_widget.widget(9)
        self.stacked_widget.blockSignals(True)
        self.stacked_widget.removeWidget(old)
        if old is not None:
            old.deleteLater()
        self.stacked_widget.insertWidget(9, value)
        self.stacked_widget.blockSignals(False)

    def _update_save_enabled(self) -> None:
        if hasattr(self, "btn_save_all"):
            self.btn_save_all.setEnabled(self._tabs_have_changes())

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange:
            self.focus_changed.emit(self.isActiveWindow())
        super().changeEvent(event)

    def closeEvent(self, event: Any) -> None:
        self.focus_changed.emit(False)
        super().closeEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)) and event.key() == Qt.Key.Key_S:
            self._save_all()
            event.accept()
            return
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() == Qt.Key.Key_F:
            if self._search_field is None:
                return
            self._search_field.setFocus()
            self._search_field.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._is_search_view_active():
                self._restore_active_tab()
                event.accept()
                return
            self.close()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._save_all()
            event.accept()
            return
        super().keyPressEvent(event)

    def accept(self) -> None:
        """Surcharge préventive : QDialog.accept() ne doit jamais fermer sans sauvegarder."""
        self._save_all()

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

        self.lbl_title = QLabel(self.tr("Paramètres AnkiForge"))
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        header_layout.addWidget(self.lbl_title)

        active_prof = get_active_profile()
        self.lbl_prof_badge = QLabel(tr("Profil : %1", active_prof))
        apply_pill_badge_style(self.lbl_prof_badge, DesignTokens.ACCENT_PRIMARY)
        header_layout.addWidget(self.lbl_prof_badge)

        header_layout.addStretch()

        self.btn_close = IconButton("ph.x", tooltip=self.tr("Fermer la fenêtre (Échap)"), size=26)
        self.btn_close.setAutoDefault(False)
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
        self.sidebar.setFixedWidth(215)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(4)

        self.nav_btn_group = QButtonGroup(self)
        self.nav_btn_group.setExclusive(True)

        self.nav_btns: list[SettingsNavButton] = []

        tabs_info = [
            (self.tr("Général"), "ph.paint-brush-broad", 0),
            (self.tr("Moteurs IA"), "ph.cpu", 1),
            (self.tr("Anki && Formats"), "ph.cards", 2),
            (self.tr("Audio && TTS"), "ph.speaker-high", 3),
            (self.tr("Maintenance"), "ph.wrench", 4),
            (self.tr("Extensions"), "ph.puzzle-piece", 5),
            (self.tr("Soutien"), "ph.heart", 6),
            (self.tr("Clavier"), "ph.key", 7),
            (self.tr("Aide && Guides"), "ph.book-open", 8),
        ]
        if is_development():
            tabs_info.append((self.tr("Développeur"), "ph.code", 9))

        for title, icon_name, idx in tabs_info:
            btn = SettingsNavButton(title, icon_name, idx)
            btn.setAutoDefault(False)
            btn.clicked.connect(lambda _, i=idx: self.select_tab(i))
            self.nav_btn_group.addButton(btn, idx)
            sidebar_layout.addWidget(btn)
            self.nav_btns.append(btn)

        self.nav_btns[0].setChecked(True)

        # Champ de recherche instantanée en tête de la barre latérale (Ctrl+F).
        self._search_field = QLineEdit(self.sidebar)
        self._search_field.setObjectName("SettingsSearchField")
        self._search_field.setPlaceholderText(self.tr("Rechercher un paramètre…"))
        self._search_field.setFixedHeight(30)
        self._search_field.addAction(
            load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_MUTED),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self._search_field.setClearButtonEnabled(True)
        sidebar_layout.addWidget(self._search_field)

        sidebar_layout.addStretch()

        body_layout.addWidget(self.sidebar)

        # Stacked Widget avec chargement différé (lazy-loading) des onglets
        self.general_tab = GeneralTab()
        num_additional = 9 if is_development() else 8
        self._tabs = [self.general_tab] + [None] * num_additional

        self.stacked_widget.addWidget(self.general_tab)
        for _ in range(num_additional):
            self.stacked_widget.addWidget(QWidget())

        # Vue aplatie des résultats de recherche (page dédiée du stacked widget).
        self._search_view = SettingsSearchView(self)
        self._search_stack_index = self.stacked_widget.addWidget(self._search_view)

        body_layout.addWidget(self.stacked_widget, 1)
        main_layout.addWidget(body, 1)

        # ── 3. FOOTER BAR AVEC ACTIONS GLOBALES ──────────────────────────────
        self.footer_bar = QWidget()
        self.footer_bar.setObjectName("SettingsFooterBar")
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(16, 10, 16, 10)
        footer_layout.setSpacing(10)

        self.lbl_shortcut = QLabel(self.tr("⌨️ Ctrl+S pour enregistrer • Échap pour fermer"))
        self.lbl_shortcut.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        footer_layout.addWidget(self.lbl_shortcut)

        self.lbl_save_status = QLabel("")
        self.lbl_save_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: 600;")
        self.lbl_save_status.hide()
        footer_layout.addWidget(self.lbl_save_status)

        footer_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.clicked.connect(self.close)
        footer_layout.addWidget(self.btn_cancel)

        self.btn_save_all = PrimaryButton("Enregistrer les paramètres")
        self.btn_save_all.setAutoDefault(False)
        self.btn_save_all.setDefault(False)
        self.btn_save_all.setIcon(load_on_accent_icon("ph.floppy-disk"))
        self.btn_save_all.setFixedHeight(30)
        self.btn_save_all.setMinimumWidth(200)
        apply_shadow(self.btn_save_all, blur=12, offset_y=0, color=DesignTokens.ACCENT_GLOW)
        self.btn_save_all.clicked.connect(self._save_all)
        footer_layout.addWidget(self.btn_save_all)

        main_layout.addWidget(self.footer_bar)

        self._apply_dialog_styles()

        # Connecter returnPressed des champs de saisie du premier onglet
        self._connect_tab_line_edits(self.general_tab)

    def _connect_signals(self) -> None:
        from ankidraft.ui.style_engine import get_style_engine

        engine = get_style_engine()
        engine.theme_changed.connect(self.refresh_theme)

        if self._search_field is None or self._search_view is None:
            return
        self._search_field.textChanged.connect(self._on_search_text_changed)
        self._search_view.result_selected.connect(self._on_search_result_selected)

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
            QPushButton[role="primary"]:disabled {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-color: {DesignTokens.BORDER_COLOR};
            }}
        """)

    def _save_all(self) -> None:
        """Sauvegarde les paramètres modifiés des onglets, applique thème/layout si besoin.

        Aucune écriture BDD/QSettings n'est déclenchée si aucun paramètre n'a changé.
        """
        if not self._tabs_have_changes():
            self.lbl_save_status.setText(self.tr("✓ Aucun paramètre modifié"))
            self.lbl_save_status.show()
            self._update_save_enabled()
            return

        layout_changed = self.general_tab._layout_field_changed()
        theme_changed = self.general_tab._theme_field_changed() or self.general_tab._mode_field_changed()

        _, selected_layout_id, _selected_family_id = self.general_tab.save_tab()
        if self._ai_tab is not None:
            self._ai_tab.save_tab()
        if self._anki_tab is not None:
            self._anki_tab.save_tab()
        if self._tts_tab is not None:
            self._tts_tab.save_tab()
        if self._maint_tab is not None:
            self._maint_tab.save_tab()
        if self._support_tab is not None:
            self._support_tab.save_tab()
        if self._keyboard_tab is not None:
            self._keyboard_tab.save_tab()
        if self._dev_tab is not None:
            self._dev_tab.save_tab()

        theme_title = self.general_tab.cb_theme.currentText() or "Nouveau Thème"
        apply_layout = bool(layout_changed and selected_layout_id)
        # « Aucune Famille choisie » est une valeur valide : l'apparence reste à appliquer.
        apply_theme = theme_changed

        def apply_changes() -> None:
            from ankidraft.ui.layouts.layout_manager import LayoutManager
            from ankidraft.ui.style_engine import get_style_engine

            engine = get_style_engine()
            main_w = self.general_tab._get_main_window()
            profile_name = self.general_tab._get_profile_name() or "default"

            # La persistance BDD/QSettings a déjà eu lieu dans save_tab() : ici on applique à chaud.
            # apply_layout() réapplique déjà l'apparence du profil : inutile de le faire deux fois.
            applied_by_layout = bool(apply_layout and selected_layout_id and main_w is not None and hasattr(main_w, "apply_layout"))
            if applied_by_layout:
                main_w.apply_layout(selected_layout_id)
            elif apply_theme:
                engine.apply_appearance_for_profile(profile_name, LayoutManager.get_saved_layout_id(profile_name))

            from shiboken6 import isValid

            toast_parent = self if isValid(self) else (main_w if main_w and isValid(main_w) else None)
            self.lbl_save_status.setText(tr("✓ Paramètres sauvegardés"))
            self.lbl_save_status.show()
            show_toast(toast_parent, tr("Tous les paramètres ont été enregistrés avec succès !"))

        if apply_layout or apply_theme:
            from ankidraft.ui.widgets.theme_transition_overlay import show_theme_transition

            target_parent = self.general_tab._get_main_window() or self
            show_theme_transition(
                parent=target_parent,
                theme_title=theme_title,
                subtext=self.tr("Application des tokens et du design system..."),
                duration_ms=450,
                on_applied=apply_changes,
            )
        else:
            apply_changes()

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
            QPushButton[role="primary"]:disabled {{
                border: 1px solid {profile.border_color};
                border-color: {profile.border_color};
            }}
        """)
        self.lbl_title.setStyleSheet(f"color: {profile.text_primary}; font-size: 15px; font-weight: bold;")
        self.lbl_header_icon.setPixmap(load_phosphor_icon("ph.sliders-horizontal", color=profile.accent_primary).pixmap(18, 18))
        apply_pill_badge_style(self.lbl_prof_badge, profile.accent_primary)
        self.lbl_shortcut.setStyleSheet(f"color: {profile.text_muted}; font-size: 11px;")

        for btn in self.nav_btns:
            btn.refresh_theme(profile)

        for tab in self._tabs:
            if tab is not None and hasattr(tab, "refresh_theme"):
                tab.refresh_theme(profile)

    def select_tab(self, index: int) -> None:
        """Sélectionne directement un onglet par son index (ex: 1 pour Moteurs IA / MCP)."""
        if 0 <= index < len(self.nav_btns):
            self._active_tab_index = index
            self.nav_btns[index].setChecked(True)
            self._ensure_tab_loaded(index)
            self.stacked_widget.setCurrentIndex(index)
            if not self.isActiveWindow():
                self.raise_()
                self.activateWindow()

    def _is_search_view_active(self) -> bool:
        """True si le stacked widget affiche actuellement la vue de recherche."""
        return self._search_stack_index is not None and self.stacked_widget.currentIndex() == self._search_stack_index

    def _on_search_text_changed(self, text: str) -> None:
        """Bascule vers la vue de recherche dès 2 caractères, restaure l'onglet sinon."""
        if len(text) >= 2:
            if self._search_view is None:
                return
            results = SettingsRegistry.search(text)
            self._search_view.set_results(results, text)
            self.stacked_widget.setCurrentIndex(self._search_stack_index)
        else:
            self._restore_active_tab()

    def _on_search_result_selected(self, descriptor: SettingDescriptor) -> None:
        """Ouvre l'onglet cible, déplie l'accordéon parent, scroll et pulsation du widget."""
        self.select_tab(descriptor.tab_index)
        tab = self.stacked_widget.currentWidget()
        QTimer.singleShot(0, lambda: self._reveal_setting(tab, descriptor))

    def _restore_active_tab(self) -> None:
        """Revient à l'onglet actif précédemment sélectionné et vide le champ de recherche."""
        if self._search_field is None:
            return
        self._search_field.blockSignals(True)
        self._search_field.clear()
        self._search_field.blockSignals(False)
        if self._is_search_view_active():
            self.stacked_widget.setCurrentIndex(self._active_tab_index)

    def _reveal_setting(self, tab: QWidget | None, descriptor: SettingDescriptor) -> None:
        """Déploie l'accordéon parent, fait défiler vers le widget cible et pulse celui-ci."""
        if tab is None:
            return
        # Déplier les accordéons parents pour rendre le widget cible accessible.
        for group in tab.findChildren(CollapsibleSettingsGroup):
            if not group.is_expanded():
                group.set_expanded(True)
        target = self._find_setting_widget(tab, descriptor)
        if target is None:
            return
        scroll = getattr(tab, "scroll", None) or tab.findChild(QScrollArea)
        if scroll is not None:
            scroll.ensureWidgetVisible(target, 50, 50)
        else:
            target.setFocus()
            target.raise_()
        self._pulse_widget(target)

    @staticmethod
    def _find_setting_widget(tab: QWidget, descriptor: SettingDescriptor) -> QWidget | None:
        """Localise le widget cible d'un descripteur dans un onglet (best-effort)."""
        sanitized_key = descriptor.key.replace("/", "::").replace("-", "_")
        candidates: list[QWidget] = []
        for widget in tab.findChildren(QWidget):
            name = widget.objectName()
            if name and name == sanitized_key:
                return widget
            accessible = widget.accessibleName()
            if accessible and (descriptor.widget.lower() in accessible.lower() or descriptor.label.lower() in accessible.lower()):
                candidates.append(widget)
        if candidates:
            return candidates[0]
        return None

    def _pulse_widget(self, widget: QWidget) -> None:
        """Applique une bordure d'accentuation temporaire (1200 ms) autour du widget."""
        if widget is None or not widget.isVisible():
            return
        self._stop_pulse()
        original_style = widget.styleSheet()
        self._pulse_original = (widget, original_style)
        widget.setObjectName("SearchPulseTarget")
        widget.setStyleSheet(f"{original_style}\n#SearchPulseTarget {{ border: 2px solid {DesignTokens.ACCENT_BORDER}; border-radius: {DesignTokens.RADIUS_SM}px; }}")
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setSingleShot(True)
        self._pulse_timer.timeout.connect(self._stop_pulse)
        self._pulse_timer.start(1200)

    def _stop_pulse(self) -> None:
        """Désactive la pulsation en cours et restaure le style d'origine."""
        if self._pulse_original is None:
            return
        widget, original_style = self._pulse_original
        self._pulse_original = None
        if widget is not None:
            widget.setObjectName("")
            widget.setStyleSheet(original_style)


# Aliases de compatibilité
SettingsDialog = SettingsModal
from ankidraft.ui.widgets.settings_modal.tabs.storage_tab import StorageMaintenanceTab  # noqa: E402

MaintenanceTab = StorageMaintenanceTab
StatisticsTab = StorageMaintenanceTab

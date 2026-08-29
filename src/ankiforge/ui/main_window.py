"""
Main Window & Navigation for AnkiForge.
"""

import logging
from typing import Any, cast

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.ui.components.sidebar import ClickableLabel, Sidebar, SidebarItem  # noqa: F401 — re-export rétrocompatible
from ankiforge.ui.components.title_bar import GlobalTitleBar  # noqa: F401 — re-export rétrocompatible
from ankiforge.ui.components.topbar import TopBar  # noqa: F401 — re-export rétrocompatible
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.agents_view import AgentsView

logger = logging.getLogger(__name__)


class DummyView(QWidget):
    """Vue temporaire pour le QStackedWidget."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        lbl = QLabel(f"[{title}] View Content Placeholder")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 24px;")
        layout.addWidget(lbl)

    def refresh_data(self) -> None:
        pass

    def is_dirty(self) -> bool:
        return False


class MainWindow(QMainWindow):
    """Fenêtre principale ankiforge_obsidian."""

    from ankiforge.ui.views.ab_tests_view import ABTestsView
    from ankiforge.ui.views.analysis_view import AnalysisView
    from ankiforge.ui.views.batch_view import BatchView
    from ankiforge.ui.views.card_models_view import CardModelsView
    from ankiforge.ui.views.consultant_view import ConsultantView
    from ankiforge.ui.views.creation_view import CreationView
    from ankiforge.ui.views.dashboard_view import DashboardView
    from ankiforge.ui.views.documents_view import DocumentsView
    from ankiforge.ui.views.edition_view import EditionView
    from ankiforge.ui.views.pipelines_view import PipelinesView

    VIEW_REGISTRY: dict[str, tuple[str, str, str, type[QWidget]]] = {
        # view_id -> (category, icon, title, WidgetClass)
        "dashboard": ("Général", "squares-four", "Tableau de bord", DashboardView),
        "creation": ("Forge & Outils", "magic-wand", "Studio de Création", CreationView),
        "edition": ("Forge & Outils", "cards", "Édition & Navigateur", EditionView),
        "analysis": ("Forge & Outils", "chart-line-up", "Analyse & Audit IA", AnalysisView),
        "consultant": ("Forge & Outils", "robot", "AI Consultant", ConsultantView),
        "batch": ("Forge & Outils", "factory", "Batch Factory", BatchView),
        "documents": ("Bibliothèque", "file-text", "My Documents", DocumentsView),
        "card-models": ("Bibliothèque", "swatches", "Card Models", CardModelsView),
        "agents": ("Laboratoire IA", "cpu", "Éditeur d'Agents", AgentsView),
        "pipelines": ("Laboratoire IA", "git-merge", "Pipelines", PipelinesView),
        "ab-tests": ("Laboratoire IA", "scales", "Tests A/B", ABTestsView),
    }

    def __init__(self, ai_manager: AIManager | None, profile_name: str = "default") -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.setWindowTitle("AnkiForge")
        self.setMinimumSize(1200, 720)

        # Dimensionner intelligemment pour occuper l'espace nécessaire sans tronquer l'affichage
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            w = min(1440, int(geom.width() * 0.90))
            h = min(900, int(geom.height() * 0.88))
            self.resize(w, h)
        else:
            self.resize(1380, 860)

        from ankiforge.ui.layouts.base_layout import BaseLayout
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        self._view_widgets: dict[str, QWidget] = {}
        self._current_view_id: str | None = None
        self._settings_window: QWidget | None = None
        self._import_dialog: QWidget | None = None
        self._export_dialog: QWidget | None = None
        self._notif_popup: QWidget | None = None
        self.current_layout: BaseLayout | None = None
        self.stacked_widget = QStackedWidget()

        # Enregistrement initial des placeholders légers (Lazy Loading)
        for view_id, (_cat, _icon, title, _cls) in self.VIEW_REGISTRY.items():
            placeholder = DummyView(title)
            self.stacked_widget.addWidget(placeholder)
            self._view_widgets[view_id] = placeholder

        # Application du Thème visuel et du Layout actif pour le profil
        from ankiforge.ui.style_engine import get_style_engine

        self.engine = get_style_engine()
        self.engine.theme_changed.connect(self._on_theme_changed)
        saved_theme_id = self.engine.get_saved_theme_id(self.profile_name)
        self.engine.apply_theme(saved_theme_id)

        saved_layout_id = LayoutManager.get_saved_layout_id(self.profile_name)
        self.apply_layout(saved_layout_id)

        self._setup_debug_shortcuts()
        self._setup_global_shortcuts()

    @property
    def sidebar(self) -> Any | None:
        """Propriété de compatibilité pour accéder à la sidebar si présente."""
        if self.current_layout is not None and hasattr(self.current_layout, "sidebar"):
            return self.current_layout.sidebar
        return None

    @property
    def topbar(self) -> Any | None:
        """Propriété de compatibilité pour accéder à la topbar si présente."""
        if self.current_layout is not None and hasattr(self.current_layout, "topbar"):
            return self.current_layout.topbar
        return None

    def apply_layout(self, layout_id: str) -> None:
        """Bascule dynamiquement vers un nouveau layout à chaud (sans redémarrer l'application)."""
        from ankiforge.ui.layouts.layout_manager import LayoutManager

        if self.current_layout is not None:
            try:
                self.current_layout.view_selected.disconnect()
                self.current_layout.settings_requested.disconnect()
                self.current_layout.search_clicked.disconnect()
                self.current_layout.toggle_sidebar_requested.disconnect()
                self.current_layout.profile_switch_requested.disconnect()
            except Exception:
                pass  # nosec B110

        new_layout = LayoutManager.create_layout(layout_id, profile_name=self.profile_name)
        self.current_layout = new_layout
        new_layout.view_selected.connect(self._on_view_selected)
        new_layout.settings_requested.connect(self._open_settings_modal)
        new_layout.search_clicked.connect(self._open_command_palette)
        new_layout.import_requested.connect(self._open_import_dialog)
        new_layout.export_requested.connect(self._open_export_dialog)
        new_layout.notif_requested.connect(self._show_notif_popup)
        new_layout.profile_switch_requested.connect(self._on_switch_profile_requested)

        new_layout.populate_navigation(self.VIEW_REGISTRY)
        new_layout.set_stacked_widget(self.stacked_widget)
        self.setCentralWidget(new_layout)
        LayoutManager.save_layout_id(self.profile_name, layout_id)
        LayoutManager.apply_theme_for_layout(layout_id)
        logger.info("Application du layout '%s' (profil: '%s')", layout_id, self.profile_name)

        if self._current_view_id:
            new_layout.set_active_view(self._current_view_id)
        else:
            self._on_view_selected("dashboard")

    def _setup_debug_shortcuts(self) -> None:
        """Configure les raccourcis de debug (ex: Capture d'écran)."""
        screenshot_shortcut = QShortcut(QKeySequence("Ctrl+F12"), self)
        screenshot_shortcut.activated.connect(self._take_debug_screenshot)

    def _setup_global_shortcuts(self) -> None:
        """Configure les raccourcis clavier universels (Sauvegarde, Exécution, Recherche, Import, Export)."""
        self.shortcut_save = QShortcut(QKeySequence.StandardKey.Save, self)
        self.shortcut_save.activated.connect(self._on_shortcut_save)

        self.shortcut_run = QShortcut(QKeySequence(Qt.Key.Key_Return | Qt.KeyboardModifier.ControlModifier), self)
        self.shortcut_run.activated.connect(self._on_shortcut_run)

        self.shortcut_find = QShortcut(QKeySequence.StandardKey.Find, self)
        self.shortcut_find.activated.connect(self._on_shortcut_find)

        self.shortcut_import = QShortcut(QKeySequence("Ctrl+Shift+I"), self)
        self.shortcut_import.activated.connect(self._open_import_dialog)

        self.shortcut_export = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        self.shortcut_export.activated.connect(self._open_export_dialog)

    def _on_shortcut_save(self) -> None:
        """Déclenche la sauvegarde sur la vue active si elle le supporte."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "_save_card"):
            current_widget._save_card()
        elif hasattr(current_widget, "save"):
            current_widget.save()

    def _on_shortcut_run(self) -> None:
        """Déclenche l'action primaire de la vue active (ex: Générer / Lancer)."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "btn_generate_cards") and current_widget.btn_generate_cards.isEnabled():
            current_widget.btn_generate_cards.click()
        elif hasattr(current_widget, "_on_generate_clicked"):
            current_widget._on_generate_clicked()
        elif hasattr(current_widget, "_on_start_batch"):
            current_widget._on_start_batch()

    def _on_shortcut_find(self) -> None:
        """Donne le focus à l'omnibox ou au champ de recherche de la vue active."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "search_input"):
            current_widget.search_input.setFocus()
            current_widget.search_input.selectAll()
        elif self.topbar and hasattr(self.topbar, "omnibox"):
            self.topbar.omnibox.setFocus()
            self.topbar.omnibox.selectAll()

    def _take_debug_screenshot(self) -> None:
        """Capture l'état actuel de la fenêtre et le sauvegarde."""
        from ankiforge.utils.paths import get_app_data_dir

        output_dir = get_app_data_dir() / "temp"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / "analyse_screenshot.png"
        pixmap = self.grab()
        pixmap.save(str(output_path))
        logger.debug("Capture d'écran de l'UI enregistrée dans : %s", output_path)

    def _on_theme_changed(self, profile: Any) -> None:
        """Propagé immédiatement à la sidebar, la topbar et toutes les vues instanciées."""
        if self.sidebar and hasattr(self.sidebar, "refresh_theme"):
            self.sidebar.refresh_theme(profile)
        if self.topbar and hasattr(self.topbar, "refresh_theme"):
            self.topbar.refresh_theme(profile)
        if self._notif_popup and hasattr(self._notif_popup, "refresh_theme"):
            self._notif_popup.refresh_theme(profile)
        for view_widget in self._view_widgets.values():
            if hasattr(view_widget, "refresh_theme"):
                try:
                    view_widget.refresh_theme(profile)
                except Exception:
                    pass  # nosec B110
        from ankiforge.ui.components.panels import IdePanel

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                try:
                    panel.refresh_theme(profile)
                except Exception:
                    pass  # nosec B110
        if hasattr(self, "_settings_window") and self._settings_window is not None and hasattr(self._settings_window, "refresh_theme"):
            try:
                self._settings_window.refresh_theme(profile)
            except Exception:
                pass  # nosec B110

    def _show_notif_popup(self) -> None:
        """Affiche le menu déroulant des notifications rattaché à la cloche TopBar."""
        from PySide6.QtCore import QPoint

        from ankiforge.services.audit.metrics_service import MetricsService
        from ankiforge.ui.widgets.notification_menu import NotificationMenuPopup

        if not self._notif_popup:
            self._notif_popup = NotificationMenuPopup(self)
            self._notif_popup.action_triggered.connect(self._on_view_selected)
            alerts = MetricsService.get_proactive_diagnostics()
            self._notif_popup.set_notifications(alerts)

        if self.topbar and hasattr(self.topbar, "notif_btn"):
            btn = self.topbar.notif_btn
            pos = btn.mapToGlobal(QPoint(btn.width() - self._notif_popup.width(), btn.height() + 6))
            self._notif_popup.move(pos)

        self._notif_popup.show()
        self._notif_popup.raise_()

    def _on_dashboard_data_updated(self, data: dict) -> None:
        """Synchronise la cloche de notification et le token tracker avec les données du dashboard."""
        diagnostics = data.get("diagnostics", [])
        if self._notif_popup and hasattr(self._notif_popup, "set_notifications"):
            self._notif_popup.set_notifications(diagnostics)
        if self.topbar and hasattr(self.topbar, "update_notif_badge"):
            self.topbar.update_notif_badge(len(diagnostics))
        telemetry = data.get("kpis", {}).get("telemetry", {})
        if self.topbar and hasattr(self.topbar, "update_token_tracker"):
            cost_val = telemetry.get("total_cost_usd", 0.0)
            tokens_val = telemetry.get("total_tokens", 0)
            self.topbar.update_token_tracker(f"{cost_val:.2f}", f"{tokens_val:,}")

    def _on_view_selected(self, view_id: str, data: dict | None = None) -> None:
        """Navigation: instancie la vue à la demande (Lazy Loading), vérifie dirty state et switch."""
        if self._current_view_id == view_id and not data:
            return

        if self._current_view_id != view_id and not self._can_switch_view():
            # Reset sidebar selection visually if rejected
            if self._current_view_id and self.sidebar:
                self.sidebar.set_active_view(self._current_view_id)
            return

        # Lazy Instantiation de la vue réelle si c'est encore un DummyView
        if view_id in self.VIEW_REGISTRY:
            cat, icon, title, cls = self.VIEW_REGISTRY[view_id]
            current_widget = self._view_widgets.get(view_id)
            if isinstance(current_widget, DummyView) and cls != DummyView:
                try:
                    real_widget = cast(Any, cls)(ai_manager=self.ai_manager, profile_name=self.profile_name)
                except TypeError:
                    try:
                        real_widget = cast(Any, cls)(ai_manager=self.ai_manager)
                    except TypeError:
                        real_widget = cast(Any, cls)()

                if hasattr(real_widget, "request_navigation"):
                    real_widget.request_navigation.connect(self._on_view_selected)

                if hasattr(real_widget, "dashboard_data_updated"):
                    real_widget.dashboard_data_updated.connect(self._on_dashboard_data_updated)

                # Remplacer le placeholder par la vraie vue dans QStackedWidget
                idx = self.stacked_widget.indexOf(current_widget)
                if idx != -1:
                    self.stacked_widget.removeWidget(current_widget)
                    current_widget.deleteLater()
                    self.stacked_widget.insertWidget(idx, real_widget)
                    self._view_widgets[view_id] = real_widget

            if self.topbar and hasattr(self.topbar, "update_breadcrumb"):
                self.topbar.update_breadcrumb(title, icon)

        widget = self._view_widgets.get(view_id)
        if widget:
            self.stacked_widget.setCurrentWidget(widget)
            self._current_view_id = view_id
            logger.info("Navigation vers la vue '%s' (avec contexte: %s)", view_id, bool(data))
            if hasattr(self, "current_layout") and self.current_layout:
                self.current_layout.set_active_view(view_id)

            if hasattr(widget, "refresh_data"):
                cast(Any, widget).refresh_data()

            if view_id == "edition" and isinstance(data, dict) and "note_id" in data and hasattr(widget, "select_note_by_id"):
                cast(Any, widget).select_note_by_id(data["note_id"])

            if view_id == "creation" and isinstance(data, dict) and "prompt" in data and hasattr(widget, "_open_document_tab"):
                cast(Any, widget)._open_document_tab(title=data.get("title", "Forge IA"), content=data["prompt"])

            if view_id == "analysis" and isinstance(data, dict) and "tab" in data and hasattr(widget, "set_active_tab_by_name"):
                cast(Any, widget).set_active_tab_by_name(data["tab"])

    def _can_switch_view(self) -> bool:
        """Vérifie is_dirty() sur la vue courante. Dialogue de confirmation si sale."""
        if not self._current_view_id:
            return True

        current_widget = self._view_widgets.get(self._current_view_id)
        if current_widget and hasattr(current_widget, "is_dirty") and cast(Any, current_widget).is_dirty():
            reply = QMessageBox.question(
                self,
                "Modifications non sauvegardées",
                "Vous avez des modifications en cours. Voulez-vous vraiment quitter ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes
        return True

    def _toggle_sidebar(self) -> None:
        if self.sidebar:
            self.sidebar.set_collapsed(not self.sidebar.is_collapsed)

    def _open_settings_modal(self) -> None:
        """Ouvre la fenêtre de paramètres non bloquante."""
        if hasattr(self, "_settings_window") and self._settings_window is not None and self._settings_window.isVisible():
            self._settings_window.raise_()
            self._settings_window.activateWindow()
            if self.sidebar and hasattr(self.sidebar, "settings_btn"):
                self.sidebar.settings_btn.setChecked(True)
            return

        from ankiforge.ui.widgets.settings_modal import SettingsModal

        self._settings_window = SettingsModal(ai_manager=self.ai_manager, profile_name=self.profile_name, parent=self)
        self._settings_window.theme_applied.connect(lambda theme_id: self.engine.apply_theme(theme_id))
        self._settings_window.layout_applied.connect(self.apply_layout)
        self._settings_window.focus_changed.connect(self._on_settings_focus_changed)
        self._settings_window.finished.connect(lambda _: self._on_settings_focus_changed(False))
        if self.sidebar and hasattr(self.sidebar, "settings_btn"):
            self.sidebar.settings_btn.setChecked(True)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _on_settings_focus_changed(self, focused: bool) -> None:
        if self.sidebar and hasattr(self.sidebar, "settings_btn"):
            self.sidebar.settings_btn.setChecked(focused)

    def _open_command_palette(self) -> None:
        """Ouvre la palette de commandes (Omnibox globale)."""
        from ankiforge.ui.widgets.command_palette import CommandPaletteModal

        palette = CommandPaletteModal(self.VIEW_REGISTRY, parent=self)
        palette.view_requested.connect(self._on_view_selected)
        palette.exec()

    def _open_import_dialog(self) -> None:
        """Ouvre la boîte de dialogue d'importation de paquets Anki."""
        from ankiforge.ui.dialogs.import_dialog import ImportDialog

        dialog = ImportDialog(parent=self)
        dialog.exec()

    def _on_import_finished(self, summary: dict) -> None:
        """Rafraîchit la vue active après importation."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "refresh_data"):
            cast(Any, current_widget).refresh_data()
        elif hasattr(current_widget, "load_data"):
            cast(Any, current_widget).load_data()

    def _open_export_dialog(self) -> None:
        """Ouvre la boîte de dialogue d'exportation de paquets Anki."""

        if hasattr(self, "_export_dialog") and self._export_dialog is not None and self._export_dialog.isVisible():
            self._export_dialog.raise_()
            self._export_dialog.activateWindow()
            return

    def _on_switch_profile_requested(self) -> None:
        """Ouvre la boîte de dialogue de sélection/création de profil et bascule à chaud."""
        from PySide6.QtWidgets import QDialog

        from ankiforge.services.profile_manager import ProfileManager
        from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog

        pm = ProfileManager()
        profiles = pm.list_profiles()
        if not profiles:
            profiles = [self.profile_name or "default"]

        dialog = ProfileSelectorDialog(profiles, current_profile=self.profile_name, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_profile = dialog.get_selected_profile()
            if new_profile and new_profile != self.profile_name:
                self.switch_to_profile(new_profile)

    def switch_to_profile(self, new_profile: str) -> None:
        """Bascule l'application vers un autre profil utilisateur (BDD, thèmes, layouts, vues)."""
        from ankiforge.services.profile_manager import ProfileManager
        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.widgets.toast import show_toast

        logger.info("Bascule de l'espace de travail vers le profil '%s'", new_profile)

        # 1. Basculer la base de données Peewee et le répertoire média
        pm = ProfileManager()
        pm.switch_profile(new_profile)
        self.profile_name = new_profile

        # 2. Mettre à jour le profil sur le layout actif
        if self.current_layout is not None:
            self.current_layout.set_profile_name(new_profile)

        # 3. Charger et appliquer le thème du nouveau profil
        saved_theme_id = self.engine.get_saved_theme_id(self.profile_name)
        self.engine.apply_theme(saved_theme_id)

        # 4. Charger et appliquer le layout du nouveau profil si différent
        saved_layout_id = LayoutManager.get_saved_layout_id(self.profile_name)
        if self.current_layout is None or self.current_layout.get_layout_id() != saved_layout_id:
            self.apply_layout(saved_layout_id)

        # 5. Réinitialiser les vues existantes pour repartir sur la nouvelle base de données
        self._reset_view_widgets()

        # 6. Re-charger la vue courante (ou le dashboard)
        target_view = self._current_view_id if (self._current_view_id and self._current_view_id in self.VIEW_REGISTRY) else "dashboard"
        self._current_view_id = None
        self._on_view_selected(target_view)

        show_toast(self, f"Espace de travail actif : « {new_profile} »")

    def _reset_view_widgets(self) -> None:
        """Réinitialise les instances de vues pour nettoyer tout cache BDD lié au précédent profil."""
        for view_id, (_cat, _icon, title, _cls) in self.VIEW_REGISTRY.items():
            old_widget = self._view_widgets.get(view_id)
            if old_widget is not None:
                idx = self.stacked_widget.indexOf(old_widget)
                if idx != -1:
                    self.stacked_widget.removeWidget(old_widget)
                    old_widget.deleteLater()
            placeholder = DummyView(title)
            self.stacked_widget.addWidget(placeholder)
            self._view_widgets[view_id] = placeholder

    def closeEvent(self, event: Any) -> None:
        # Close all floating windows
        from ankiforge.ui.components.tabs.floating_dock import _floating_windows

        for fw in list(_floating_windows):
            fw.close()
        super().closeEvent(event)

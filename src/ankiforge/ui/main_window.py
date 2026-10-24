"""Main Window & Navigation for AnkiForge."""

import contextlib
import logging
import os
import sys
from typing import Any, ClassVar, cast

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.ui.components.sidebar import ClickableLabel, Sidebar, SidebarItem  # noqa: F401 — re-export rétrocompatible
from ankiforge.ui.components.title_bar import GlobalTitleBar  # noqa: F401 — re-export rétrocompatible
from ankiforge.ui.components.topbar import TopBar  # noqa: F401 — re-export rétrocompatible
from ankiforge.ui.shortcuts import ShortcutId, ShortcutManager, ShortcutScope
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.agents_view import AgentsView
from ankiforge.utils.environment import KOFI_URL, is_development, is_testing
from ankiforge.utils.event_bus import (
    OpenConsultantRequestedEvent,
    OpenFeedbackRequestedEvent,
    ProfileSwitchedEvent,
    ThemeChangedEvent,
    event_bus,
)
from ankiforge.utils.i18n import tr
from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)


class DummyView(QWidget):
    """Vue temporaire pour le QStackedWidget."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        lbl = QLabel(tr("[%1] View Content Placeholder", title))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 24px;")
        layout.addWidget(lbl)

    def refresh_data(self) -> None:
        pass

    def is_dirty(self) -> bool:
        return False


class MainWindow(QMainWindow):
    """Fenêtre principale ankiforge_obsidian."""

    #: view_id -> (catégorie, icône, titre, WidgetClass)
    #:
    #: La table est produite par `view_registry()` plutôt que déclarée en dur : les libellés
    #: ne peuvent être résolus qu'une fois le traducteur installé, donc au premier usage. Une
    #: constante de classe figerait le français à l'import du module — c'est-à-dire avant
    #: `install_translator()` — et la navigation resterait française dans une interface
    #: anglaise. La catégorie sert de clef de regroupement dans le layout IDE : la traduire ne
    #: casse rien, les vues d'un même groupe partagent toujours la même clef.
    @staticmethod
    def view_registry() -> dict[str, tuple[str, str, str, type[QWidget]]]:
        from ankiforge.ui.views.ab_tests_view import ABTestsView
        from ankiforge.ui.views.analysis_view import AnalysisView
        from ankiforge.ui.views.batch_view import BatchView
        from ankiforge.ui.views.card_models_view import CardModelsView
        from ankiforge.ui.views.consultant_view import MCPServerView
        from ankiforge.ui.views.creation_view import CreationView
        from ankiforge.ui.views.dashboard_view import DashboardView
        from ankiforge.ui.views.documents_view import DocumentsView
        from ankiforge.ui.views.edition_view import EditionView
        from ankiforge.ui.views.pipelines_view import PipelinesView

        return {
            "dashboard": (tr("Général"), "squares-four", tr("Tableau de bord"), DashboardView),
            "creation": (tr("Forge & Outils"), "magic-wand", tr("Studio de Création"), CreationView),
            "edition": (tr("Forge & Outils"), "cards", tr("Édition & Navigateur"), EditionView),
            "analysis": (tr("Forge & Outils"), "chart-line-up", tr("Analyse & Audit IA"), AnalysisView),
            "consultant": (tr("Forge & Outils"), "plugs-connected", tr("Serveur MCP & Agents"), MCPServerView),
            "batch": (tr("Forge & Outils"), "factory", tr("Batch Factory"), BatchView),
            "documents": (tr("Bibliothèque"), "file-text", tr("My Documents"), DocumentsView),
            "card-models": (tr("Bibliothèque"), "swatches", tr("Types de note"), CardModelsView),
            "agents": (tr("Laboratoire IA"), "cpu", tr("Éditeur d'Agents"), AgentsView),
            "pipelines": (tr("Laboratoire IA"), "git-merge", tr("Pipelines"), PipelinesView),
            "ab-tests": (tr("Laboratoire IA"), "scales", tr("Tests A/B"), ABTestsView),
        }

    mcp_data_mutated = Signal(dict)
    shortcut_manager: ShortcutManager

    # Domaine fonctionnel MCP -> vues autorisées à se rafraîchir.
    # Toute vue absente de cette table n'est jamais réveillée par une mutation externe.
    # L'ordre est déterministe : les vues légères passent avant les vues coûteuses.
    _MCP_DOMAIN_VIEWS: ClassVar[dict[str, tuple[str, ...]]] = {
        "cards": ("edition", "analysis"),
        "decks": ("creation", "batch", "edition"),
        "models": ("card-models", "edition"),
        "docs": ("documents",),
    }

    def __init__(self, ai_manager: AIManager | None, profile_name: str = "default") -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.mcp_daemon: Any | None = None

        from ankiforge import __version__

        title_suffix = f" [DEV] - profil: {profile_name} (v{__version__})" if is_development() else f" - {profile_name}"
        self.setWindowTitle(tr("AnkiForge%1", title_suffix))
        self.setMinimumSize(1200, 720)

        # Application & Window Icon
        icon_path = get_resource_path("src", "ressources", "icons", "ankiforge.png")
        if not icon_path.exists():
            icon_path = get_resource_path("src", "ressources", "icons", "logo.svg")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

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
        self._view_registry = self.view_registry()
        self._register_addon_views()
        self._current_view_id: str | None = None
        self._settings_window: QWidget | None = None
        self._import_dialog: QWidget | None = None
        self._export_dialog: QWidget | None = None
        self._notif_popup: QWidget | None = None
        self._tour_bubble: Any | None = None
        self._web_engine_prewarmer: QWidget | None = None
        self._update_worker: Any | None = None
        self._latest_update_info: Any | None = None
        self._fallback_mcp_status_widget: Any | None = None
        self._crash_dialog: QWidget | None = None
        self._support_dialog: QWidget | None = None
        self.current_layout: BaseLayout | None = None
        self.stacked_widget = QStackedWidget()
        self.shortcut_manager = ShortcutManager(parent=self)
        self.stacked_widget.currentChanged.connect(self._on_stacked_current_changed)

        # Bandeau d'activité global (ADR 0021) : hébergé hors des quatre dispositions
        # enfichables, il reste donc visible quel que soit l'écran et survit à un
        # changement de layout à chaud. Le service singleton de thread principal
        # reçoit l'avancement des déclencheurs et alimente ce bandeau et les toasts.
        from ankiforge.services.reindex_activity_service import ReindexActivityService
        from ankiforge.ui.widgets.reindex_activity_banner import ReindexActivityBanner

        self.reindex_activity = ReindexActivityService.get_instance()
        self._central_container = QWidget()
        self._central_layout = QVBoxLayout(self._central_container)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_layout.setSpacing(0)
        self.reindex_banner = ReindexActivityBanner(self._central_container)
        self._central_layout.addWidget(self.reindex_banner)
        self._hosted_layout: QWidget | None = None
        self.setCentralWidget(self._central_container)
        self._wire_reindex_activity()

        # Enregistrement initial des placeholders légers (Lazy Loading)
        for view_id, (_cat, _icon, title, _cls) in self._view_registry.items():
            placeholder = DummyView(title)
            self.stacked_widget.addWidget(placeholder)
            self._view_widgets[view_id] = placeholder

        # Application du Thème visuel et du Layout actif pour le profil
        from ankiforge.ui.style_engine import get_style_engine

        self.engine = get_style_engine()
        self.engine.theme_changed.connect(self._on_theme_changed)

        # apply_layout() applique aussi l'apparence du profil : le layout ne fournit
        # qu'une famille de repli, la Famille choisie par l'utilisateur prime.
        saved_layout_id = LayoutManager.get_saved_layout_id(self.profile_name)
        self.apply_layout(saved_layout_id)

        # Neutralisation globale du changement d'option à la molette sur les QComboBox fermées
        from ankiforge.ui.components.inputs import ComboBoxWheelFilter

        self._combo_wheel_filter = ComboBoxWheelFilter.install()

        self._prewarm_web_engine()

        self._setup_shortcuts()
        event_bus.subscribe(OpenConsultantRequestedEvent, self._on_open_consultant_requested)
        event_bus.subscribe(OpenFeedbackRequestedEvent, self._on_open_feedback_requested)

        # Configuration du serveur MCP et liaison avec le bouton de la sidebar
        self._wire_mcp_ui()
        self._init_mcp_daemon()

        # Restauration instantanée du badge depuis le cache QSettings (sans HTTP, dès que la topbar est rendue)
        QTimer.singleShot(300, self._restore_cached_update_badge)
        # Vérification d'un éventuel crash report antérieur (invite non-bloquante)
        QTimer.singleShot(1200, self._check_pending_crash_report)
        # Vérification des runs de pipelines interrompus pour reprise
        QTimer.singleShot(1500, self._check_uncompleted_pipeline_runs)
        # Vérification HTTP forcée à chaque lancement pour actualiser le cache et les assets
        QTimer.singleShot(2000, self._check_for_updates)

        # Invitation de soutien Ko-fi temporisée et non bloquante au démarrage.
        # Désactivée automatiquement en mode test, headless ou smoke-test.
        if not (is_testing() or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen" or "--smoke-test" in sys.argv):
            QTimer.singleShot(2500, self._check_startup_support_dialog)

    def _prewarm_web_engine(self) -> None:
        """Préchauffe silencieusement Chromium au démarrage pour éviter tout rechargement visuel lors de la première navigation vers un composant WebEngine."""
        import os

        if os.environ.get("ANKIFORGE_MOCK_WEBENGINE") == "1":
            return
        try:
            from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView

            self._web_engine_prewarmer = SafeWebEngineView(self)
            self._web_engine_prewarmer.setFixedSize(1, 1)
            self._web_engine_prewarmer.move(-100, -100)
            self._web_engine_prewarmer.show()
        except Exception as e:
            logger.debug("Remarque préchauffage WebEngine: %s", e)

    def _register_addon_views(self) -> None:
        """Expose active addon views without changing the native view registry."""
        from ankiforge.services.plugins.plugin_manager import get_plugin_manager

        plugin_manager = get_plugin_manager()
        for addon_info in plugin_manager.get_all_addons():
            api = plugin_manager.get_addon_api(addon_info.id)
            if api is None:
                continue
            for view in api.ui.get_registered_custom_views():
                view_id = str(view["view_id"])
                if view_id in self._view_registry:
                    logger.warning("Vue addon ignorée car l'identifiant existe déjà : %s", view_id)
                    continue
                self._view_registry[view_id] = (
                    "Addons",
                    str(view["icon_name"]),
                    str(view["title"]),
                    cast(Any, view["widget_factory"]),
                )

    def _on_open_consultant_requested(self, event: OpenConsultantRequestedEvent) -> None:
        """Bascule immédiatement sur l'onglet Serveur MCP & Agents."""
        self._on_view_selected("consultant")
        from ankiforge.ui.widgets.toast import show_toast

        show_toast(self, tr("Espace Serveur MCP & Agents actif."))

    def _restore_cached_update_badge(self) -> None:
        """Restaure immédiatement le badge de mise à jour depuis le cache QSettings (sans appel HTTP).

        Appelé 300ms après le démarrage pour afficher le badge dès que la topbar est construite,
        même si la vérification HTTP n'a pas encore eu lieu. Les assets du cache sont vides ;
        ils seront remplacés par les assets réels dès que le worker HTTP aura terminé (2s).
        """
        from ankiforge.services.update_checker import get_cached_update_info

        cached_info = get_cached_update_info()
        if cached_info is not None:
            logger.info(
                "Badge restauré depuis le cache : v%s [%s]",
                cached_info.version,
                cached_info.channel,
            )
            self._on_update_available(cached_info)

    def _check_for_updates(self) -> None:
        """Lance une vérification respectant le cache au démarrage."""
        from PySide6.QtCore import QThreadPool

        from ankiforge.services.update_checker import UpdateCheckerWorker

        worker = UpdateCheckerWorker(force=False)
        self._update_worker = worker
        worker.signals.update_available.connect(self._on_update_available)
        worker.signals.no_update.connect(self._on_no_update)
        worker.signals.check_failed.connect(self._on_update_check_failed)
        QThreadPool.globalInstance().start(worker)

    def _on_no_update(self, _cur: str) -> None:
        """Nettoie la référence du worker lorsqu'aucune mise à jour n'est disponible."""
        self._update_worker = None

    def _on_update_check_failed(self, error_msg: str) -> None:
        """Trace l'échec de vérification au démarrage."""
        self._update_worker = None
        logger.warning("Échec de la vérification de mise à jour au démarrage : %s", error_msg)

    @property
    def mcp_status_widget(self) -> Any:
        """Accède au bouton de statut MCP hébergé dans la barre latérale."""
        if self.sidebar and hasattr(self.sidebar, "mcp_btn"):
            return self.sidebar.mcp_btn
        if not hasattr(self, "_fallback_mcp_status_widget") or self._fallback_mcp_status_widget is None:
            from ankiforge.ui.widgets.mcp_status_widget import MCPStatusWidget

            self._fallback_mcp_status_widget = MCPStatusWidget(initial_status="stopped", parent=self)
        return self._fallback_mcp_status_widget

    def _wire_mcp_ui(self) -> None:
        """Connecte les signaux d'actions du bouton MCP hébergé dans la barre latérale."""
        btn = self.mcp_status_widget
        if btn is not None and not getattr(btn, "_signals_wired", False):
            btn.start_requested.connect(self.start_mcp_server)
            btn.stop_requested.connect(self.stop_mcp_server)
            btn.restart_requested.connect(self.restart_mcp_server)
            btn.rotate_token_requested.connect(self.rotate_mcp_token)
            btn.open_preferences_requested.connect(lambda: self.open_settings(initial_tab=1))
            btn._signals_wired = True

    def _init_mcp_daemon(self) -> None:
        """Initialise ou démarre automatiquement le serveur MCP selon les préférences utilisateur."""
        from ankiforge.utils.environment import get_app_qsettings, is_testing

        q_settings = get_app_qsettings()
        mcp_enabled = q_settings.value("mcp/enabled", True, type=bool)
        mcp_port = q_settings.value("mcp/port", 8765, type=int)

        self._sync_mcp_ui("stopped", port=mcp_port)

        if not is_testing() and mcp_enabled:
            QTimer.singleShot(500, lambda: self.start_mcp_server(port=mcp_port))

    def _sync_mcp_ui(self, status: str, port: int | None = None, token: str | None = None, message: str = "") -> None:
        """Synchronise l'état du serveur MCP sur le bouton de la sidebar et le tableau de bord de la vue MCP & Agents."""
        if hasattr(self, "mcp_status_widget") and self.mcp_status_widget is not None:
            self.mcp_status_widget.set_status(status, port=port, token=token, message=message)
        consultant_view = self._view_widgets.get("consultant")
        if consultant_view and hasattr(consultant_view, "mcp_dashboard"):
            consultant_view.mcp_dashboard.set_status(status, port=port, token=token, message=message)

    def start_mcp_server(self, port: int | None = None) -> bool:
        """Démarre le serveur MCP d'arrière-plan."""
        from ankiforge.services.ai.mcp_daemon import MCPServerDaemon
        from ankiforge.utils.environment import get_app_qsettings

        if port is None:
            q_settings = get_app_qsettings()
            port = q_settings.value("mcp/port", 8765, type=int)

        if self.mcp_daemon is not None and self.mcp_daemon.is_running:
            logger.info("Serveur MCP déjà actif sur le port %d.", self.mcp_daemon.port)
            return True

        self.mcp_daemon = MCPServerDaemon(base_port=port, host="127.0.0.1")
        self.mcp_daemon.signals.mcp_data_mutated.connect(self._on_mcp_data_mutated)
        self.mcp_daemon.signals.mcp_patch_staged.connect(self._on_mcp_patch_staged)

        ok = self.mcp_daemon.start()
        if ok and self.mcp_daemon.port:
            logger.info("Serveur MCP démarré sur le port %d.", self.mcp_daemon.port)
            self._sync_mcp_ui(
                "running",
                port=self.mcp_daemon.port,
                token=self.mcp_daemon.token,
            )
            return True
        else:
            logger.error("Échec du démarrage du serveur MCP.")
            self._sync_mcp_ui("error", port=port, message="Échec démarrage")
            return False

    def stop_mcp_server(self) -> bool:
        """Arrête proprement le serveur MCP d'arrière-plan."""
        if self.mcp_daemon is not None:
            stopped = self.mcp_daemon.stop()
            self._sync_mcp_ui("stopped", port=self.mcp_daemon.port or 8765)
            return stopped
        self._sync_mcp_ui("stopped")
        return True

    def restart_mcp_server(self) -> bool:
        """Redémarre le serveur MCP d'arrière-plan."""
        self.stop_mcp_server()
        return self.start_mcp_server()

    def rotate_mcp_token(self) -> str:
        """Renouvelle le jeton d'authentification Bearer du serveur MCP et met à jour l'IHM."""
        from ankiforge.ui.widgets.toast import show_toast

        if self.mcp_daemon is not None:
            new_token = self.mcp_daemon.rotate_token()
            self._sync_mcp_ui(
                self.mcp_status_widget.current_status,
                port=self.mcp_daemon.port,
                token=new_token,
            )
        else:
            from ankiforge.services.ai.mcp_daemon import rotate_auth_token
            from ankiforge.utils.paths import get_app_data_dir

            data_dir = get_app_data_dir()
            token_file = data_dir / "mcp_auth_token"
            state_file = data_dir / "mcp_server.json"
            new_token = rotate_auth_token(token_file=token_file, state_file=state_file)
            self._sync_mcp_ui(
                self.mcp_status_widget.current_status,
                token=new_token,
            )

        show_toast(self, self.tr("Nouveau jeton d'authentification MCP généré."))
        return new_token

    def _on_mcp_data_mutated(self, mutation: dict[str, Any]) -> None:
        """Traite les mutations émises par les outils MCP (apply_patch, etc.).

        Seules les vues abonnées au domaine fonctionnel impacté sont actualisées.
        Les vues concernées peuvent exposer ``apply_mcp_mutation()`` pour appliquer
        une mise à jour granulaire ; à défaut, ``refresh_data()`` est appelé.
        Aucune navigation, sélection ou position d'ascenseur n'est modifiée ici.
        """
        domain = str(mutation.get("domain") or "").strip().lower()
        if domain not in self._MCP_DOMAIN_VIEWS:
            # Repli pour les producteurs historiques qui n'injectent pas encore le domaine.
            from ankiforge.services.ai.mcp_server import resolve_mcp_mutation_domain

            domain = resolve_mcp_mutation_domain(mutation)
        logger.info(
            "Mutation MCP reçue (domaine=%s, type=%s)",
            domain,
            mutation.get("type") or mutation.get("mutation_type") or "?",
        )
        logger.debug("Charge utile de la mutation MCP : %s", mutation)

        if hasattr(self, "mcp_status_widget") and self.mcp_status_widget is not None:
            self.mcp_status_widget.flash_mutation()

        targets = self._MCP_DOMAIN_VIEWS.get(domain, ())
        for view_id in targets:
            widget = self._view_widgets.get(view_id)
            if widget is None or isinstance(widget, DummyView):
                continue

            granular_handler = getattr(widget, "apply_mcp_mutation", None)
            try:
                if callable(granular_handler):
                    granular_handler(mutation)
                elif hasattr(widget, "refresh_data"):
                    cast(Any, widget).refresh_data()
            except Exception as e:
                logger.warning("Erreur rafraîchissement vue %s après mutation MCP (%s): %s", view_id, domain, e)

        self._refresh_nav_badges()
        self.mcp_data_mutated.emit(mutation)

    def _on_mcp_patch_staged(self, data: dict[str, Any]) -> None:
        """Relaye la notification d'une proposition staged vers le tableau de bord MCP."""
        logger.info("Proposition de patch MCP staged reçue : %s", data.get("patch_id"))
        consultant_view = self._view_widgets.get("consultant")
        if consultant_view and hasattr(consultant_view, "mcp_dashboard"):
            consultant_view.mcp_dashboard.on_patch_staged(data)

    def _check_uncompleted_pipeline_runs(self) -> None:
        """Détecte les runs de pipelines inachevés ou interrompus lors d'une session précédente et propose la reprise."""
        try:
            from ankiforge.database.models import PipelineRunModel

            uncompleted = list(PipelineRunModel.select().where(PipelineRunModel.status.in_(["running", "paused"])).order_by(PipelineRunModel.updated_at.desc()).limit(1))
            if not uncompleted:
                return

            run = uncompleted[0]
            pipe_name = run.pipeline.name if run.pipeline and hasattr(run.pipeline, "name") else f"Pipeline #{run.pipeline_id}"
            step_order = run.current_step_order or 1

            reply = QMessageBox.question(
                self,
                self.tr("Reprise de Pipeline DAG"),
                tr(
                    "Un pipeline DAG « %1 » n'a pas été terminé lors de la session précédente (interrompu à l'étape %2).\n\nSouhaitez-vous reprendre l'exécution de ce pipeline ?",
                    pipe_name,
                    step_order,
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self._resume_pipeline_run(run.id)
            else:
                run.status = "cancelled"
                run.save()
        except Exception as e:
            logger.debug("Vérification des runs inachevés ignorée : %s", e)

    def _resume_pipeline_run(self, run_id: int) -> None:
        """Exécute la reprise d'un run persisté."""
        try:
            from PySide6.QtCore import QThreadPool

            from ankiforge.database.models import PipelineRunModel
            from ankiforge.services.ai.orchestrator import PipelineOrchestrator
            from ankiforge.ui.widgets.toast import show_toast

            run = PipelineRunModel.get_by_id(run_id)
            provider = self.ai_manager.active_provider if self.ai_manager and hasattr(self.ai_manager, "active_provider") else None
            orchestrator = PipelineOrchestrator.resume_run(run_id, ai_provider=provider)
            QThreadPool.globalInstance().start(orchestrator)
            pipe_name = run.pipeline.name if run.pipeline and hasattr(run.pipeline, "name") else f"#{run.pipeline_id}"
            show_toast(self, tr("Reprise du pipeline « %1 » lancée en arrière-plan.", pipe_name))
        except Exception as err:
            logger.warning("Échec de la reprise du run %d : %s", run_id, err)

    def _on_update_available(self, info: Any) -> None:
        """Transmet l'information de mise à jour à la TopBar si présente.

        Appelé deux fois en séquence au démarrage :
        1. Depuis le cache QSettings (300ms) — badge immédiat, assets vides.
        2. Depuis le worker HTTP (≈2s+) — badge mis à jour avec les assets réels.

        La garde sip.isdeleted() évite tout accès à une topbar détruite entre
        le démarrage du worker et l'émission du signal.
        """
        self._latest_update_info = info
        self._update_worker = None
        try:
            import sip

            topbar = self.topbar
            if topbar is not None and not sip.isdeleted(topbar) and hasattr(topbar, "set_update_available"):
                topbar.set_update_available(info)
        except ImportError:
            # sip non disponible (environnement de test ou build alternatif)
            topbar = self.topbar
            if topbar is not None and hasattr(topbar, "set_update_available"):
                topbar.set_update_available(info)

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
            for sig, slot in [
                (getattr(self.current_layout, "view_selected", None), self._on_view_selected),
                (getattr(self.current_layout, "settings_requested", None), self._open_settings_modal),
                (getattr(self.current_layout, "feedback_requested", None), self._open_feedback_dialog),
                (getattr(self.current_layout, "search_clicked", None), self._open_command_palette),
                (getattr(self.current_layout, "import_requested", None), self._open_import_dialog),
                (getattr(self.current_layout, "export_requested", None), self._open_export_dialog),
                (getattr(self.current_layout, "notif_requested", None), self._show_notif_popup),
                (getattr(self.current_layout, "profile_switch_requested", None), self._on_switch_profile_requested),
            ]:
                if sig is not None:
                    with contextlib.suppress(Exception):
                        sig.disconnect(slot)

        new_layout = LayoutManager.create_layout(layout_id, profile_name=self.profile_name)
        self.current_layout = new_layout
        new_layout.view_selected.connect(self._on_view_selected)
        new_layout.settings_requested.connect(self._open_settings_modal)
        new_layout.feedback_requested.connect(self._open_feedback_dialog)
        new_layout.search_clicked.connect(self._open_command_palette)
        new_layout.import_requested.connect(self._open_import_dialog)
        new_layout.export_requested.connect(self._open_export_dialog)
        new_layout.notif_requested.connect(self._show_notif_popup)
        new_layout.profile_switch_requested.connect(self._on_switch_profile_requested)

        new_layout.populate_navigation(self._view_registry)
        new_layout.set_stacked_widget(self.stacked_widget)
        if self._hosted_layout is not None:
            self._central_layout.removeWidget(self._hosted_layout)
            self._hosted_layout.setParent(None)
        self._central_layout.addWidget(new_layout)
        self._hosted_layout = new_layout
        LayoutManager.save_layout_id(self.profile_name, layout_id)
        LayoutManager.apply_theme_for_layout(layout_id, profile_name=self.profile_name)
        logger.info("Application du layout '%s' (profil: '%s')", layout_id, self.profile_name)

        if self._current_view_id:
            new_layout.set_active_view(self._current_view_id)
        else:
            self._on_view_selected("dashboard")

        if self._latest_update_info is not None:
            self._on_update_available(self._latest_update_info)

        self._wire_mcp_ui()
        # `populate_navigation` reconstruit les boutons : republier les pastilles.
        self._refresh_nav_badges()

    def _wire_reindex_activity(self) -> None:
        """Relie le bandeau d'activité global au hub de réindexation (ADR 0021)."""
        service = self.reindex_activity
        service.started.connect(self.reindex_banner.handle_started)
        service.progress.connect(self.reindex_banner.handle_progress)
        service.fragment_progress.connect(self.reindex_banner.handle_fragments)
        service.finished.connect(self._on_reindex_activity_finished)
        service.refused.connect(self._on_reindex_activity_refused)
        self.reindex_banner.cancel_requested.connect(service.request_cancel)

    def _on_reindex_activity_refused(self, current: int, total: int) -> None:
        """Refuse franchement un second déclenchement, par un toast discret."""
        from ankiforge.ui.widgets.toast import show_toast

        show_toast(
            self,
            tr("Une réindexation est déjà en cours (%1/%2).", current, total),
            level="warning",
        )

    def _on_reindex_activity_finished(self, documents: int, fragments: int, errors: int, cancelled: bool) -> None:
        """Masque le bandeau et récapitule la passe (documents, fragments, erreurs)."""
        from ankiforge.ui.widgets.toast import show_toast

        self.reindex_banner.reset()
        if cancelled:
            show_toast(
                self,
                tr("Réindexation interrompue : %1 document(s) et %2 fragment(s) traités.", documents, fragments),
                level="info",
            )
        elif errors:
            show_toast(
                self,
                tr("Réindexation terminée : %1 document(s), %2 fragment(s), %3 erreur(s).", documents, fragments, errors),
                level="warning",
            )
        else:
            show_toast(
                self,
                tr("Réindexation terminée : %1 document(s), %2 fragment(s).", documents, fragments),
            )

    def _on_stacked_current_changed(self, index: int) -> None:
        """Synchronise la vue active du ShortcutManager lors d'un changement de page."""
        widget = self.stacked_widget.widget(index)
        self.shortcut_manager.set_active_view(widget)

    def _get_navigable_view_ids(self) -> list[str]:
        """Renvoie la liste ordonnée des identifiants de vues navigables."""
        return [vid for vid in self._view_registry if vid not in ("settings", "tour")]

    def _select_view_by_index(self, index: int) -> None:
        """Bascule vers la vue correspondant à l'index donné (0-indexed)."""
        view_ids = self._get_navigable_view_ids()
        if 0 <= index < len(view_ids):
            self._on_view_selected(view_ids[index])

    def _select_next_view(self) -> None:
        """Bascule vers la vue navigable suivante de manière cyclique."""
        view_ids = self._get_navigable_view_ids()
        if not view_ids:
            return
        try:
            current_idx = view_ids.index(self._current_view_id) if self._current_view_id in view_ids else 0
        except ValueError:
            current_idx = 0
        next_idx = (current_idx + 1) % len(view_ids)
        self._on_view_selected(view_ids[next_idx])

    def _select_prev_view(self) -> None:
        """Bascule vers la vue navigable précédente de manière cyclique."""
        view_ids = self._get_navigable_view_ids()
        if not view_ids:
            return
        try:
            current_idx = view_ids.index(self._current_view_id) if self._current_view_id in view_ids else 0
        except ValueError:
            current_idx = 0
        prev_idx = (current_idx - 1) % len(view_ids)
        self._on_view_selected(view_ids[prev_idx])

    def _setup_shortcuts(self) -> None:
        """Configure les raccourcis déclaratifs universels et de navigation via ShortcutManager."""
        from collections.abc import Callable

        app_bindings: dict[ShortcutId, Callable[[], None]] = {
            ShortcutId.APP_COMMAND_PALETTE: lambda: self._open_command_palette(),
            ShortcutId.APP_SETTINGS: lambda: self._open_settings_modal(),
            ShortcutId.APP_SAVE: lambda: self._on_shortcut_save(),
            ShortcutId.APP_RUN_PRIMARY: lambda: self._on_shortcut_run(),
            ShortcutId.APP_FIND: lambda: self._on_shortcut_find(),
            ShortcutId.APP_IMPORT: lambda: self._open_import_dialog(),
            ShortcutId.APP_EXPORT: lambda: self._open_export_dialog(),
            ShortcutId.APP_TOUR: lambda: self.start_tour_guide(),
            ShortcutId.APP_DEBUG_SCREENSHOT: lambda: self._take_debug_screenshot(),
            ShortcutId.NAV_NEXT_VIEW: lambda: self._select_next_view(),
            ShortcutId.NAV_PREV_VIEW: lambda: self._select_prev_view(),
        }

        if is_development():
            app_bindings[ShortcutId.APP_DEBUG_GALLERY] = lambda: self._open_dialog_gallery()

        # Liaison des raccourcis de navigation Alt+1..9
        for idx in range(9):
            nav_id = getattr(ShortcutId, f"NAV_VIEW_{idx + 1}", None)
            if nav_id:
                app_bindings[nav_id] = (lambda i=idx: lambda: self._select_view_by_index(i))()

        self.shortcut_manager.bind(self, app_bindings, scope=ShortcutScope.APPLICATION)

    def _on_shortcut_save(self) -> None:
        """Déclenche la sauvegarde sur la vue active si elle le supporte."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "save"):
            current_widget.save()
        elif hasattr(current_widget, "_save_card"):
            current_widget._save_card()
        elif hasattr(current_widget, "_on_save_anki"):
            current_widget._on_save_anki()

    def _on_shortcut_run(self) -> None:
        """Déclenche l'action primaire de la vue active (ex: Générer / Lancer / Reprendre)."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "run_primary_action"):
            current_widget.run_primary_action()
        elif hasattr(current_widget, "btn_generate_cards") and current_widget.btn_generate_cards.isEnabled():
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
        if hasattr(self, "mcp_status_widget") and self.mcp_status_widget is not None:
            self.mcp_status_widget.refresh_theme(profile)
        for view_widget in self._view_widgets.values():
            if hasattr(view_widget, "refresh_theme"):
                try:
                    view_widget.refresh_theme(profile)
                except Exception as err:
                    logger.debug("Refresh du thème d'une vue ignoré : %s", err)
        from ankiforge.ui.components.panels import IdePanel

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                try:
                    panel.refresh_theme(profile)
                except Exception as err:
                    logger.debug("Refresh du thème d'un panneau ignoré : %s", err)
        if hasattr(self, "_settings_window") and self._settings_window is not None and hasattr(self._settings_window, "refresh_theme"):
            try:
                self._settings_window.refresh_theme(profile)
            except Exception as err:
                logger.debug("Refresh du thème de la fenêtre de réglages ignoré : %s", err)
        theme_id = getattr(profile, "theme_id", "") if profile else ""
        event_bus.publish(ThemeChangedEvent(theme_name=str(theme_id)))

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
        """Navigation: instancie la vue à la demande (Lazy Loading) et switch.

        La navigation est volontairement libre : les vues vivent dans un `QStackedWidget`
        et survivent au switch, changer d'onglet n'est pas une action destructive. Le
        contrôle `is_dirty()` est réservé à `closeEvent` et `switch_to_profile` via
        `_confirm_discard_unsaved_work()`.
        """
        if view_id == "settings":
            self._open_settings_modal()
            return
        if view_id == "shortcuts":
            self.open_settings(initial_tab=7)
            return
        if view_id == "shortcuts_doc":
            from ankiforge.ui.widgets.settings_modal.tabs.keyboard_tab import DOC_SHORTCUTS_URL

            QDesktopServices.openUrl(QUrl(DOC_SHORTCUTS_URL))
            return
        if view_id == "tour":
            self.start_tour_guide()
            return

        if self._current_view_id == view_id and not data:
            return

        # Lazy Instantiation de la vue réelle si c'est encore un DummyView
        if view_id in self._view_registry:
            cat, icon, title, cls = self._view_registry[view_id]
            current_widget = self._view_widgets.get(view_id)
            if isinstance(current_widget, DummyView) and cls != DummyView:
                try:
                    real_widget = cast(Any, cls)(ai_manager=self.ai_manager, profile_name=self.profile_name)
                except TypeError:
                    try:
                        real_widget = cast(Any, cls)(ai_manager=self.ai_manager)
                    except TypeError:
                        real_widget = cast(Any, cls)()

                if hasattr(real_widget, "set_shortcut_manager") and hasattr(self, "shortcut_manager"):
                    real_widget.set_shortcut_manager(self.shortcut_manager)

                if hasattr(real_widget, "request_navigation"):
                    real_widget.request_navigation.connect(self._on_view_selected)

                if hasattr(real_widget, "dashboard_data_updated"):
                    real_widget.dashboard_data_updated.connect(self._on_dashboard_data_updated)

                if view_id == "consultant":
                    if hasattr(real_widget, "mcp_start_requested"):
                        real_widget.mcp_start_requested.connect(self.start_mcp_server)
                    if hasattr(real_widget, "mcp_stop_requested"):
                        real_widget.mcp_stop_requested.connect(self.stop_mcp_server)
                    if hasattr(real_widget, "mcp_restart_requested"):
                        real_widget.mcp_restart_requested.connect(self.restart_mcp_server)
                    if hasattr(real_widget, "mcp_rotate_token_requested"):
                        real_widget.mcp_rotate_token_requested.connect(self.rotate_mcp_token)

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
            if hasattr(self, "shortcut_manager") and self.shortcut_manager:
                self.shortcut_manager.set_active_view(widget)
            self._current_view_id = view_id
            logger.info("Navigation vers la vue '%s' (avec contexte: %s)", view_id, bool(data))
            if hasattr(self, "current_layout") and self.current_layout:
                self.current_layout.set_active_view(view_id)

            if hasattr(widget, "refresh_data"):
                cast(Any, widget).refresh_data()

            if view_id == "edition" and isinstance(data, dict):
                if "note_id" in data and hasattr(widget, "select_note_by_id"):
                    cast(Any, widget).select_note_by_id(data["note_id"])
                if "note_type_id" in data and hasattr(widget, "_on_model_selected"):
                    cast(Any, widget)._on_model_selected(data["note_type_id"], data.get("note_type_name", ""))

            if view_id == "creation" and isinstance(data, dict):
                if hasattr(widget, "load_context"):
                    cast(Any, widget).load_context(data)
                elif "prompt" in data and hasattr(widget, "_open_document_tab"):
                    cast(Any, widget)._open_document_tab(title=data.get("title", "Forge IA"), content=data["prompt"])

            if view_id == "analysis" and isinstance(data, dict):
                if "tab" in data and hasattr(widget, "set_active_tab_by_name"):
                    cast(Any, widget).set_active_tab_by_name(data["tab"])
                if "doc_id" in data and hasattr(widget, "open_document_inspector"):
                    cast(Any, widget).open_document_inspector(data["doc_id"])

            if view_id == "documents" and isinstance(data, dict) and "doc_id" in data and hasattr(widget, "_select_doc_id_in_tree"):
                cast(Any, widget)._select_doc_id_in_tree(data["doc_id"])

        self._refresh_nav_badges()

    def _refresh_nav_badges(self) -> None:
        """Publie vers la navigation le nombre d'éléments de travail en cours de chaque vue.

        Les vues exposent `pending_work_count()` (contrat optionnel) ; celles qui ne le
        déclarent pas sont simplement publiées sans pastille. Les placeholders jamais
        instanciés ne sont pas interrogés.
        """
        layout = self.current_layout
        if layout is None:
            return
        for view_id, widget in self._view_widgets.items():
            count: int | None = None
            if not isinstance(widget, DummyView) and hasattr(widget, "pending_work_count"):
                try:
                    reported = cast(Any, widget).pending_work_count()
                except Exception as e:
                    logger.debug("Pastille de navigation indisponible pour '%s' : %s", view_id, e)
                else:
                    count = int(reported) if reported else None
            with contextlib.suppress(Exception):
                layout.set_nav_badge(view_id, count)

    def _dirty_views(self) -> list[str]:
        """Titres des vues instanciées déclarant un état de travail non sauvegardé."""
        dirty: list[str] = []
        for view_id, widget in self._view_widgets.items():
            if isinstance(widget, DummyView) or not hasattr(widget, "is_dirty"):
                continue
            try:
                if cast(Any, widget).is_dirty():
                    dirty.append(self._view_registry.get(view_id, ("", "", view_id, DummyView))[2])
            except Exception as e:
                logger.debug("is_dirty() en échec sur la vue '%s' : %s", view_id, e)
        return dirty

    def _confirm_discard_unsaved_work(self, action_label: str) -> bool:
        """Demande confirmation avant une action destructrice (fermeture, changement de profil).

        Réservé à la perte effective de l'état en mémoire : la navigation entre vues
        n'appelle jamais ce garde-fou.
        """
        dirty = self._dirty_views()
        if not dirty:
            return True
        titles = "\n".join(f"• {title}" for title in dirty)
        reply = QMessageBox.question(
            self,
            self.tr("Modifications non sauvegardées"),
            tr("Vous avez du travail non enregistré dans :\n%1\n\nVoulez-vous vraiment %2 ? Ce travail sera perdu.", titles, action_label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _toggle_sidebar(self) -> None:
        if self.sidebar:
            self.sidebar.set_collapsed(not self.sidebar.is_collapsed)

    def open_settings(self, initial_tab: int | None = None) -> None:
        """Ouvre la fenêtre de paramètres non bloquante."""
        if hasattr(self, "_settings_window") and self._settings_window is not None and self._settings_window.isVisible():
            if initial_tab is not None and hasattr(self._settings_window, "select_tab"):
                self._settings_window.select_tab(initial_tab)
            self._settings_window.raise_()
            self._settings_window.activateWindow()
            if self.sidebar and hasattr(self.sidebar, "settings_btn"):
                self.sidebar.settings_btn.setChecked(True)
            return

        from ankiforge.ui.widgets.settings_modal import SettingsModal

        self._settings_window = SettingsModal(ai_manager=self.ai_manager, profile_name=self.profile_name, parent=self)
        if initial_tab is not None and hasattr(self._settings_window, "select_tab"):
            self._settings_window.select_tab(initial_tab)
        self._settings_window.theme_applied.connect(lambda theme_id: self.engine.apply_theme(theme_id))
        self._settings_window.layout_applied.connect(self.apply_layout)
        self._settings_window.focus_changed.connect(self._on_settings_focus_changed)
        self._settings_window.finished.connect(lambda _: self._on_settings_focus_changed(False))
        self._settings_window.rotate_mcp_token_requested.connect(self.rotate_mcp_token)
        if self.sidebar and hasattr(self.sidebar, "settings_btn"):
            self.sidebar.settings_btn.setChecked(True)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def _open_settings_modal(self) -> None:
        """Alias rétrocompatible pour open_settings."""
        self.open_settings()

    def _on_settings_focus_changed(self, focused: bool) -> None:
        if self.sidebar and hasattr(self.sidebar, "settings_btn"):
            self.sidebar.settings_btn.setChecked(focused)

    def _open_command_palette(self) -> None:
        """Ouvre la palette de commandes (Omnibox globale)."""
        from ankiforge.ui.widgets.command_palette import CommandPaletteModal

        palette = CommandPaletteModal(self._view_registry, parent=self)
        palette.view_requested.connect(self._on_view_selected)
        palette.command_selected.connect(self._on_command_selected)
        palette.exec()

    def _on_command_selected(self, command_id: str) -> None:
        """Traite les actions globales déclenchées depuis la palette de commandes."""
        if command_id == "action.import":
            self._open_import_dialog()
        elif command_id == "action.export":
            self._open_export_dialog()
        elif command_id == "action.settings":
            self._open_settings_modal()
        elif command_id == "action.shortcuts":
            self.open_settings(initial_tab=7)
        elif command_id == "action.shortcuts_doc":
            from ankiforge.ui.widgets.settings_modal.tabs.keyboard_tab import DOC_SHORTCUTS_URL

            QDesktopServices.openUrl(QUrl(DOC_SHORTCUTS_URL))
        elif command_id == "action.tour":
            self.start_tour_guide()
        elif command_id == "action.feedback":
            self._open_feedback_dialog()
        elif command_id == "action.crash_report":
            self._open_crash_report_dialog()
        elif command_id == "action.support":
            QDesktopServices.openUrl(QUrl(KOFI_URL))
        elif command_id == "action.dialog_gallery":
            self._open_dialog_gallery()

    def _open_dialog_gallery(self) -> None:
        """Ouvre la galerie des boîtes de dialogue en mode développement."""
        if not is_development():
            return
        from ankiforge.ui.dialogs.dialog_gallery_dialog import DialogGalleryDialog

        gallery = DialogGalleryDialog(parent=self)
        gallery.exec()

    def _open_feedback_dialog(self, tab: str = "bug", initial_title: str = "", context_error: str = "") -> None:
        """Ouvre la boîte de dialogue de retours utilisateurs et boîte à idées."""
        from ankiforge.ui.dialogs.feedback_dialog import FeedbackDialog

        dialog = FeedbackDialog(tab=tab, initial_title=initial_title, context_error=context_error, parent=self)
        dialog.exec()

    def _on_open_feedback_requested(self, event: Any) -> None:
        """Répond à l'événement de bus demandant l'ouverture de la boîte de feedback."""
        tab = getattr(event, "tab", "bug")
        initial_title = getattr(event, "initial_title", "")
        context_error = getattr(event, "context_error", "")
        self._open_feedback_dialog(tab=tab, initial_title=initial_title, context_error=context_error)

    def _check_startup_support_dialog(self) -> None:
        """Affiche l'invitation de soutien Ko-fi si la préférence utilisateur le permet."""
        from ankiforge.utils.environment import get_app_qsettings

        try:
            show_dialog = get_app_qsettings().value("app/show_startup_support_dialog", True, type=bool)
        except Exception:
            show_dialog = True
        if not show_dialog:
            return

        from ankiforge.ui.dialogs.support_dialog import SupportDialog

        dialog = SupportDialog(parent=self)
        self._support_dialog = dialog
        dialog.show()

    def _check_pending_crash_report(self) -> None:
        """Vérifie si un rapport de crash antérieur doit être proposé à l'utilisateur."""
        try:
            from ankiforge.services.crash_reporter_service import CrashReporterService
            from ankiforge.ui.dialogs.crash_report_dialog import CrashReportDialog

            if not CrashReporterService.has_pending_crash():
                return

            crash_info = CrashReporterService.get_latest_crash()
            if crash_info is None:
                return

            self._crash_dialog = CrashReportDialog(crash_info=crash_info, parent=self)
            self._crash_dialog.show()
        except Exception as e:
            logger.debug("Vérification du crash report ignorée : %s", e)

    def _open_crash_report_dialog(self) -> None:
        """Ouvre la boîte de dialogue de rapport du dernier crash."""
        from ankiforge.services.crash_reporter_service import CrashReporterService
        from ankiforge.ui.dialogs.crash_report_dialog import CrashReportDialog

        crash_info = CrashReporterService.get_latest_crash()
        if crash_info is None:
            from ankiforge.ui.widgets.toast import ToastLevel, show_toast

            show_toast(parent=self, message=self.tr("Aucun incident n'est enregistré dans crash.log."), level=ToastLevel.INFO)
            return

        self._crash_dialog = CrashReportDialog(crash_info=crash_info, parent=self)
        self._crash_dialog.show()

    def start_tour_guide(self) -> None:
        """Lance la visite guidée interactive d'AnkiForge."""
        from ankiforge.ui.widgets.tour_guide import TourBubble, create_default_tour_steps

        if self._tour_bubble is None:
            self._tour_bubble = TourBubble(self)
        steps = create_default_tour_steps(self)
        self._tour_bubble.set_scenario(steps)
        self._tour_bubble.start_tour()

    def _open_import_dialog(self) -> None:
        """Ouvre la boîte de dialogue d'importation de paquets Anki."""
        from ankiforge.ui.dialogs.import_dialog import ImportDialog

        dialog = ImportDialog(parent=self)
        dialog.import_finished.connect(self._on_import_finished)
        dialog.exec()

    def _on_import_finished(self, summary: dict) -> None:
        """Rafraîchit la vue active après importation."""
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "refresh_data"):
            cast(Any, current_widget).refresh_data()
        elif hasattr(current_widget, "load_data"):
            cast(Any, current_widget).load_data()

    def _open_export_dialog(self) -> None:
        """Ouvre la boîte de dialogue d'exportation de paquets Anki en mode modal."""
        from ankiforge.ui.dialogs.export_dialog import ExportDialog

        dialog = ExportDialog(parent=self)
        self._export_dialog = dialog
        dialog.exec()

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
        from PySide6.QtWidgets import QMessageBox

        from ankiforge.services.profile_lock_service import ProfileLockService
        from ankiforge.services.profile_manager import ProfileManager
        from ankiforge.ui.layouts.layout_manager import LayoutManager
        from ankiforge.ui.widgets.toast import show_toast

        # Action destructive : changer de profil détruit les instances de vues (donc la
        # file batch et les cartes générées) via `_reset_view_widgets`.
        if not self._confirm_discard_unsaved_work(f"basculer vers l'espace « {new_profile} »"):
            logger.info("Bascule de profil annulée : travail non enregistré détecté.")
            return

        # Vérifier et acquérir le verrou sur le nouveau profil
        acquired, lock_info = ProfileLockService.acquire_lock(new_profile)
        if not acquired:
            pid_hint = f" (PID {lock_info.pid})" if lock_info else ""
            QMessageBox.warning(
                self,
                self.tr("Profil en cours d'utilisation"),
                tr(
                    "Impossible de basculer vers l'espace « %1 » : il est actuellement ouvert par une autre instance%2.\n\nL'accès simultané au même profil est bloqué pour protéger vos "
                    "données contre les corruptions.",
                    new_profile,
                    pid_hint,
                ),
            )
            return

        # Libérer l'ancien profil
        if self.profile_name and self.profile_name != new_profile:
            ProfileLockService.release_lock(self.profile_name)

        logger.info("Bascule de l'espace de travail vers le profil '%s'", new_profile)

        # 1. Basculer la base de données Peewee et le répertoire média
        pm = ProfileManager()
        pm.switch_profile(new_profile)
        self.profile_name = new_profile

        # 2. Mettre à jour le profil sur le layout actif
        if self.current_layout is not None:
            self.current_layout.set_profile_name(new_profile)

        # 3. Charger et appliquer l'apparence du nouveau profil
        saved_layout_id = LayoutManager.get_saved_layout_id(self.profile_name)

        # 4. Charger et appliquer le layout du nouveau profil si différent
        if self.current_layout is None or self.current_layout.get_layout_id() != saved_layout_id:
            self.apply_layout(saved_layout_id)
        else:
            self.engine.apply_appearance_for_profile(self.profile_name, saved_layout_id)

        # 5. Réinitialiser les vues existantes pour repartir sur la nouvelle base de données
        self._reset_view_widgets()

        # 6. Re-charger la vue courante (ou le dashboard)
        target_view = self._current_view_id if (self._current_view_id and self._current_view_id in self._view_registry) else "dashboard"
        self._current_view_id = None
        self._on_view_selected(target_view)

        event_bus.publish(ProfileSwitchedEvent(profile_name=new_profile))
        show_toast(self, tr("Espace de travail actif : « %1 »", new_profile))

    def _reset_view_widgets(self) -> None:
        """Réinitialise les instances de vues pour nettoyer tout cache BDD lié au précédent profil."""
        for view_id, (_cat, _icon, title, _cls) in self._view_registry.items():
            old_widget = self._view_widgets.get(view_id)
            if old_widget is not None:
                idx = self.stacked_widget.indexOf(old_widget)
                if idx != -1:
                    if hasattr(old_widget, "cleanup"):
                        cast(Any, old_widget).cleanup()
                    self.stacked_widget.removeWidget(old_widget)
                    old_widget.deleteLater()
            placeholder = DummyView(title)
            self.stacked_widget.addWidget(placeholder)
            self._view_widgets[view_id] = placeholder

    def closeEvent(self, event: Any) -> None:
        # Action destructive : on interroge les vues AVANT tout arrêt de service,
        # pour ne pas couper le serveur MCP ni purger la base si l'utilisateur renonce.
        if not self._confirm_discard_unsaved_work("quitter l'application"):
            logger.info("Fermeture annulée : travail non enregistré détecté.")
            event.ignore()
            return

        event_bus.unsubscribe(OpenConsultantRequestedEvent, self._on_open_consultant_requested)
        # Arrêt propre du serveur MCP d'arrière-plan
        if hasattr(self, "mcp_daemon") and self.mcp_daemon is not None and self.mcp_daemon.is_running:
            try:
                self.mcp_daemon.stop()
            except Exception as e:
                logger.warning("Erreur arrêt daemon MCP lors de la fermeture : %s", e)
        # Close all floating windows
        from ankiforge.ui.components.tabs.floating_dock import _floating_windows

        for fw in list(_floating_windows):
            fw.close()

        # Maintenance orchestrée à la fermeture propre (checkpoint WAL, purge orphelins optionnelle et libération verrous)
        from ankiforge.database.maintenance import execute_clean_shutdown
        from ankiforge.utils.environment import get_app_qsettings

        settings = get_app_qsettings()
        clean_media = settings.value("storage/clean_media_on_exit", False, type=bool)

        if clean_media:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication

            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                execute_clean_shutdown(self.profile_name, clean_orphan_media=True)
            finally:
                QApplication.restoreOverrideCursor()
        else:
            execute_clean_shutdown(self.profile_name, clean_orphan_media=False)

        super().closeEvent(event)

"""
Contrat d'API Publique (AnkiForgeAPI) et points d'ancrage typés pour les addons AnkiForge.
Assure une séparation stricte entre les extensions et le cœur de l'application (Nuitka-Safe).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ankiforge.services.plugins.event_bus import EventBus
from ankiforge.services.plugins.manifest_schema import AddonManifest

logger = logging.getLogger(__name__)


class UIHooksAPI:
    """Points d'ancrage pour l'extension de l'interface utilisateur PySide6."""

    def __init__(self, addon_id: str) -> None:
        self.addon_id = addon_id
        self._registered_editor_actions: List[Dict[str, Any]] = []
        self._registered_custom_views: List[Dict[str, Any]] = []

    def add_editor_action(
        self,
        action_id: str,
        label: str,
        icon_name: str,
        callback: Callable[[], None],
        tooltip: str = "",
        shortcut: str = "",
        group: str = "custom",
    ) -> None:
        """
        Ajoute une action rapide / bouton d'outil dans la barre d'édition de notes.
        """
        scoped_id = f"{self.addon_id}:{action_id}"
        self._registered_editor_actions.append(
            {
                "addon_id": self.addon_id,
                "action_id": scoped_id,
                "label": label,
                "icon_name": icon_name,
                "callback": callback,
                "tooltip": tooltip or label,
                "shortcut": shortcut,
                "group": group,
            }
        )
        logger.info(f"[{self.addon_id}] Action d'éditeur enregistrée : '{scoped_id}'")

    def add_custom_view(
        self,
        view_id: str,
        title: str,
        icon_name: str,
        widget_factory: Callable[[], Any],
    ) -> None:
        """
        Enregistre une vue personnalisée qui peut être injectée dans la navigation AnkiForge.
        """
        scoped_id = f"{self.addon_id}:{view_id}"
        self._registered_custom_views.append(
            {
                "addon_id": self.addon_id,
                "view_id": scoped_id,
                "title": title,
                "icon_name": icon_name,
                "widget_factory": widget_factory,
            }
        )
        logger.info(f"[{self.addon_id}] Vue personnalisée enregistrée : '{scoped_id}'")

    def notify_info(self, message: str, title: str = "Information") -> None:
        """Affiche un toast ou notification d'information."""
        try:
            from PySide6.QtWidgets import QApplication
            from ankiforge.ui.widgets.toast import show_toast

            win = QApplication.activeWindow()
            if win:
                show_toast(win, message, is_error=False)
            else:
                logger.info(f"[{title}] {message}")
        except Exception:
            logger.info(f"[{title}] {message}")

    def notify_success(self, message: str, title: str = "Succès") -> None:
        """Affiche un toast de succès."""
        self.notify_info(message, title=title)

    def notify_warning(self, message: str, title: str = "Attention") -> None:
        """Affiche un toast d'avertissement."""
        try:
            from PySide6.QtWidgets import QApplication
            from ankiforge.ui.widgets.toast import show_toast

            win = QApplication.activeWindow()
            if win:
                show_toast(win, message, is_error=True)
            else:
                logger.warning(f"[{title}] {message}")
        except Exception:
            logger.warning(f"[{title}] {message}")

    def notify_error(self, message: str, title: str = "Erreur") -> None:
        """Affiche un toast d'erreur."""
        self.notify_warning(message, title=title)

    def get_registered_editor_actions(self) -> List[Dict[str, Any]]:
        return list(self._registered_editor_actions)

    def get_registered_custom_views(self) -> List[Dict[str, Any]]:
        return list(self._registered_custom_views)


class PipelineHooksAPI:
    """Points d'ancrage pour le moteur de pipelines DAG."""

    # Registre global de tous les types d'étapes enregistrés par les plugins
    _step_registry: Dict[str, Callable[..., Any]] = {}

    def __init__(self, addon_id: str) -> None:
        self.addon_id = addon_id

    def register_step_type(self, step_type_name: str, executor_callable: Callable[..., Any]) -> None:
        """
        Enregistre un nouveau type d'étape exécutable par le PipelineOrchestrator.
        """
        step_type = step_type_name.strip().upper()
        PipelineHooksAPI._step_registry[step_type] = executor_callable
        logger.info(f"[{self.addon_id}] Type d'étape de pipeline enregistré : '{step_type}'")

    @classmethod
    def get_registered_steps(cls) -> Dict[str, Callable[..., Any]]:
        return dict(cls._step_registry)


class MCPHooksAPI:
    """Points d'ancrage pour les outils IA ReAct et le serveur MCP."""

    _tools_registry: Dict[str, Dict[str, Any]] = {}

    def __init__(self, addon_id: str) -> None:
        self.addon_id = addon_id

    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        description: str = "",
        parameters_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Enregistre un outil déterministe invocable par le Consultant IA / agent ReAct.
        """
        tool_name = name.strip()
        doc = description or (handler.__doc__ or "Outil fourni par un addon AnkiForge").strip()
        MCPHooksAPI._tools_registry[tool_name] = {
            "addon_id": self.addon_id,
            "name": tool_name,
            "handler": handler,
            "description": doc,
            "parameters": parameters_schema or {},
        }
        logger.info(f"[{self.addon_id}] Outil MCP enregistré : '{tool_name}'")

    @classmethod
    def get_registered_tools(cls) -> Dict[str, Dict[str, Any]]:
        return dict(cls._tools_registry)


class EventBusAPI:
    """Façade sécurisée pour le bus d'événements scoped à l'addon."""

    def __init__(self, addon_id: str) -> None:
        self.addon_id = addon_id
        self._bus = EventBus.get_instance()
        self._my_listeners: List[tuple[str, Callable[..., Any]]] = []

    def on(self, event_name: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Abonne un callback à un événement global."""
        self._bus.on(event_name, handler)
        self._my_listeners.append((event_name, handler))
        return handler

    def off(self, event_name: str, handler: Callable[..., Any]) -> bool:
        """Désabonne un callback."""
        res = self._bus.off(event_name, handler)
        if (event_name, handler) in self._my_listeners:
            self._my_listeners.remove((event_name, handler))
        return res

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> List[Any]:
        """Déclenche un événement."""
        return self._bus.emit(event_name, *args, **kwargs)

    # Raccourcis typés
    def on_note_created(self, handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
        return self.on("note_created", handler)

    def on_note_saved(self, handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
        return self.on("note_saved", handler)

    def on_note_deleted(self, handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
        return self.on("note_deleted", handler)

    def on_deck_imported(self, handler: Callable[[str, int], Any]) -> Callable[[str, int], Any]:
        return self.on("deck_imported", handler)

    def on_export_apkg(self, handler: Callable[[str, int], Any]) -> Callable[[str, int], Any]:
        return self.on("export_apkg", handler)

    def on_pipeline_started(self, handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
        return self.on("pipeline_started", handler)

    def on_pipeline_finished(self, handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
        return self.on("pipeline_finished", handler)

    def unregister_all(self) -> None:
        """Désabonne tous les écouteurs de cet addon."""
        for event_name, handler in self._my_listeners:
            self._bus.off(event_name, handler)
        self._my_listeners.clear()


class AddonConfigAPI:
    """Gestionnaire de persistance et lecture des réglages (config.json) de l'addon."""

    def __init__(self, addon_folder: Path) -> None:
        self.addon_folder = addon_folder
        self.config_file = addon_folder / "config.json"
        self._cached_config: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self._cached_config = json.load(f)
            except Exception as e:
                logger.warning(f"Impossible de charger config.json pour {self.addon_folder.name}: {e}")
                self._cached_config = {}
        else:
            self._cached_config = {}

    def get_config(self) -> Dict[str, Any]:
        """Retourne une copie du dictionnaire de configuration complet."""
        return dict(self._cached_config)

    def set_config(self, new_config: Dict[str, Any]) -> None:
        """Écrit et sauvegarde la nouvelle configuration dans config.json."""
        self._cached_config = dict(new_config)
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._cached_config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur d'écriture dans config.json de {self.addon_folder.name}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur de configuration."""
        return self._cached_config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Définit une valeur et sauvegarde automatiquement."""
        self._cached_config[key] = value
        self.set_config(self._cached_config)


class AnkiForgeAPI:
    """
    Façade principale injectée dans chaque addon au démarrage :
    def init_addon(api: AnkiForgeAPI) -> None
    """

    def __init__(self, manifest: AddonManifest, addon_folder: Path) -> None:
        self.manifest = manifest
        self.addon_folder = addon_folder
        self.addon_id = manifest.id

        self.ui = UIHooksAPI(self.addon_id)
        self.pipelines = PipelineHooksAPI(self.addon_id)
        self.mcp = MCPHooksAPI(self.addon_id)
        self.events = EventBusAPI(self.addon_id)
        self.config = AddonConfigAPI(addon_folder)

    def __repr__(self) -> str:
        return f"<AnkiForgeAPI addon_id={self.addon_id} version={self.manifest.version}>"

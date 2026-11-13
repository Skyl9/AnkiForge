"""Package du Système d'Addons et Plugins pour AnkiForge."""

from ankidraft.services.plugins.api import (
    AddonConfigAPI,
    AnkiForgeAPI,
    EventBusAPI,
    MCPHooksAPI,
    PipelineHooksAPI,
    UIHooksAPI,
)
from ankidraft.services.plugins.event_bus import EventBus, event_bus
from ankidraft.services.plugins.manifest_schema import AddonInfo, AddonManifest, AddonStatus
from ankidraft.services.plugins.plugin_manager import PluginManager, get_plugin_manager

__all__ = [
    "AddonConfigAPI",
    "AddonInfo",
    "AddonManifest",
    "AddonStatus",
    "AnkiForgeAPI",
    "EventBus",
    "EventBusAPI",
    "MCPHooksAPI",
    "PipelineHooksAPI",
    "PluginManager",
    "UIHooksAPI",
    "event_bus",
    "get_plugin_manager",
]

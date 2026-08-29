"""
Package Tabs d'AnkiForge.
Re-exporte l'ensemble des barres d'onglets, boutons et fenêtrages détachables pour rétrocompatibilité 100%.
"""

from ankiforge.ui.components.tabs.bars import (
    IdeTabBar,
    PillTabBar,
    ScrollableTabBarWidget,
    SettingsTabBar,
)
from ankiforge.ui.components.tabs.floating_dock import FloatingDockWindow
from ankiforge.ui.components.tabs.tab_button import TabButton
from ankiforge.ui.components.tabs.tab_container import TabContainer

__all__ = [
    "IdeTabBar",
    "PillTabBar",
    "SettingsTabBar",
    "TabButton",
    "TabContainer",
    "ScrollableTabBarWidget",
    "FloatingDockWindow",
]

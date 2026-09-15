"""
Module des Layouts Enfichables pour AnkiForge.
"""

from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.dashboard_layout import DashboardLayout
from ankiforge.ui.layouts.glass_layout import GlassmorphismLayout
from ankiforge.ui.layouts.ide_layout import IdeLayout
from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.layouts.macos_layout import MacosLayout

__all__ = [
    "BaseLayout",
    "IdeLayout",
    "MacosLayout",
    "DashboardLayout",
    "GlassmorphismLayout",
    "LayoutManager",
]

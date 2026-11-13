"""Module des Layouts Enfichables pour AnkiForge."""

from ankidraft.ui.layouts.base_layout import BaseLayout
from ankidraft.ui.layouts.dashboard_layout import DashboardLayout
from ankidraft.ui.layouts.glass_layout import GlassmorphismLayout
from ankidraft.ui.layouts.ide_layout import IdeLayout
from ankidraft.ui.layouts.layout_manager import LayoutManager
from ankidraft.ui.layouts.macos_layout import MacosLayout

__all__ = [
    "BaseLayout",
    "IdeLayout",
    "MacosLayout",
    "DashboardLayout",
    "GlassmorphismLayout",
    "LayoutManager",
]

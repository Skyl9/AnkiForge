"""Module de compatibilité pour SegmentedTabBar.

Permet l'import direct depuis ankiforge.ui.components.segmented_tab_bar
tout en conservant la structure interne ankiforge.ui.components.tabs.segmented_tab_bar.
"""

from __future__ import annotations

from ankiforge.ui.components.tabs.segmented_tab_bar import (
    SegmentedTabBar,
    SegmentedTabButton,
    SubTabButton,
)

__all__ = ["SegmentedTabBar", "SegmentedTabButton", "SubTabButton"]

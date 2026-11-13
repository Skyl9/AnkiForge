"""Module de compatibilité pour SegmentedTabBar.

Permet l'import direct depuis ankidraft.ui.components.segmented_tab_bar
tout en conservant la structure interne ankidraft.ui.components.tabs.segmented_tab_bar.
"""

from __future__ import annotations

from ankidraft.ui.components.tabs.segmented_tab_bar import (
    SegmentedTabBar,
    SegmentedTabButton,
    SubTabButton,
)

__all__ = ["SegmentedTabBar", "SegmentedTabButton", "SubTabButton"]

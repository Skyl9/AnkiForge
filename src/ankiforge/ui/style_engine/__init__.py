"""
Moteur de Style Centralisé pour AnkiForge.
"""

from ankiforge.ui.style_engine.engine import StyleEngine, get_style_engine
from ankiforge.ui.style_engine.theme_profile import ThemeProfile
from ankiforge.ui.style_engine.themes import (
    BUILTIN_THEMES,
    CYBER_GLASS,
    CYBER_GLASS_LIGHT,
    DRACULA_LIGHT,
    DRACULA_OFFICIAL,
    EMERALD_DASHBOARD,
    EMERALD_LIGHT,
    JETBRAINS_DARK,
    JETBRAINS_LIGHT,
    MACOS_DARK,
    MACOS_LIGHT,
    MACOS_SLATE,
    MONOKAI_LIGHT,
    MONOKAI_PRO,
    SYNTHWAVE_84,
    SYNTHWAVE_LIGHT,
    ThemeFamily,
    get_family_for_theme,
    get_theme_families,
    get_unique_builtin_themes,
)

__all__ = [
    "StyleEngine",
    "get_style_engine",
    "ThemeProfile",
    "ThemeFamily",
    "BUILTIN_THEMES",
    "JETBRAINS_DARK",
    "JETBRAINS_LIGHT",
    "MACOS_DARK",
    "MACOS_LIGHT",
    "MACOS_SLATE",
    "EMERALD_DASHBOARD",
    "EMERALD_LIGHT",
    "CYBER_GLASS",
    "CYBER_GLASS_LIGHT",
    "SYNTHWAVE_84",
    "SYNTHWAVE_LIGHT",
    "MONOKAI_PRO",
    "MONOKAI_LIGHT",
    "DRACULA_OFFICIAL",
    "DRACULA_LIGHT",
    "get_theme_families",
    "get_family_for_theme",
    "get_unique_builtin_themes",
]

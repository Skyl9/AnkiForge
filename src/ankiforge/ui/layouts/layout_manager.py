"""
Layout Manager pour l'Architecture UI Enfichable d'AnkiForge.
Permet d'instancier, enregistrer et basculer à chaud entre les différents layouts et leurs thèmes visuels.
"""

from typing import Dict, List, Type
from PySide6.QtCore import QSettings

from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.dashboard_layout import DashboardLayout
from ankiforge.ui.layouts.glass_layout import GlassmorphismLayout
from ankiforge.ui.layouts.ide_layout import IdeLayout
from ankiforge.ui.layouts.macos_layout import MacosLayout
from ankiforge.ui.theme import DesignTokens


class LayoutManager:
    """
    Gestionnaire central des layouts et des thèmes visuels associés de l'application.
    """

    LAYOUTS: Dict[str, Type[BaseLayout]] = {
        "ide": IdeLayout,
        "macos": MacosLayout,
        "dashboard": DashboardLayout,
        "glassmorphism": GlassmorphismLayout,
    }

    DEFAULT_LAYOUT_ID = "ide"

    @classmethod
    def get_available_layouts(cls) -> List[Dict[str, str]]:
        """Renvoie la liste des métadonnées de tous les layouts disponibles pour les paramètres."""
        results = []
        for layout_id, layout_class in cls.LAYOUTS.items():
            temp = layout_class.__new__(layout_class)
            results.append(
                {
                    "id": layout_id,
                    "name": temp.get_display_name() if hasattr(temp, "get_display_name") else layout_id.capitalize(),
                    "description": temp.get_description() if hasattr(temp, "get_description") else "",
                }
            )
        return results

    @classmethod
    def apply_theme_for_layout(cls, layout_id: str) -> None:
        """Adapte le thème pour le layout donné en respectant le mode clair/sombre actif."""
        from ankiforge.ui.style_engine import get_style_engine

        engine = get_style_engine()
        target_id = layout_id if layout_id in cls.LAYOUTS else cls.DEFAULT_LAYOUT_ID
        # Résoudre la famille correspondante au layout (ex: ide -> jetbrains, dashboard -> emerald...)
        family_map = {
            "ide": "jetbrains",
            "dashboard": "emerald",
            "glassmorphism": "glassmorphism",
            "macos": "macos",
        }
        family_id = family_map.get(target_id, "jetbrains")
        family = engine.get_family_for_theme(family_id)
        if family:
            target_theme = family.dark_theme if DesignTokens.is_dark_mode() else family.light_theme
            engine.apply_theme(target_theme)

    @classmethod
    def create_layout(cls, layout_id: str, profile_name: str = "default") -> BaseLayout:
        """Instancie un layout par son identifiant."""
        target_id = layout_id if layout_id in cls.LAYOUTS else cls.DEFAULT_LAYOUT_ID
        layout_class = cls.LAYOUTS[target_id]
        return layout_class(profile_name=profile_name)

    @classmethod
    def get_saved_layout_id(cls, profile_name: str = "default") -> str:
        """Récupère l'identifiant du layout enregistré pour le profil donné depuis la BDD (ou QSettings)."""
        try:
            from ankiforge.database.models import SettingModel

            val = SettingModel.get_value(f"profiles/{profile_name}/layout_id")
            if val and str(val) in cls.LAYOUTS:
                return str(val)
        except Exception:
            pass  # nosec B110

        settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")
        saved_id = str(settings.value(f"profiles/{profile_name}/layout_id", cls.DEFAULT_LAYOUT_ID))
        if saved_id not in cls.LAYOUTS:
            return cls.DEFAULT_LAYOUT_ID
        return saved_id

    @classmethod
    def save_layout_id(cls, profile_name: str, layout_id: str) -> None:
        """Enregistre le layout préféré pour le profil utilisateur en BDD."""
        if layout_id in cls.LAYOUTS:
            try:
                from ankiforge.database.models import SettingModel

                SettingModel.set_value(f"profiles/{profile_name}/layout_id", layout_id, category="appearance")
            except Exception:
                pass  # nosec B110

            settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")
            settings.setValue(f"profiles/{profile_name}/layout_id", layout_id)

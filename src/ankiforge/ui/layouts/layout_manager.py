"""
Layout Manager pour l'Architecture UI Enfichable d'AnkiForge.
Permet d'instancier, enregistrer et basculer à chaud entre les différents layouts et leurs thèmes visuels.
"""

import logging
from pathlib import Path

from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.dashboard_layout import DashboardLayout
from ankiforge.ui.layouts.glass_layout import GlassmorphismLayout
from ankiforge.ui.layouts.ide_layout import IdeLayout
from ankiforge.ui.layouts.macos_layout import MacosLayout
from ankiforge.ui.style_engine.theme_profile import ThemeProfile

logger = logging.getLogger(__name__)


class LayoutManager:
    """
    Gestionnaire central des layouts et des thèmes visuels associés de l'application.
    """

    LAYOUTS: dict[str, type[BaseLayout]] = {
        "ide": IdeLayout,
        "macos": MacosLayout,
        "dashboard": DashboardLayout,
        "glassmorphism": GlassmorphismLayout,
    }

    DEFAULT_LAYOUT_ID = "ide"

    # Famille proposée par défaut pour chaque layout. Ce n'est qu'un repli : une Famille
    # choisie explicitement par l'utilisateur n'est jamais remplacée par celle du layout.
    LAYOUT_DEFAULT_FAMILY: dict[str, str] = {
        "ide": "jetbrains",
        "dashboard": "emerald",
        "glassmorphism": "glassmorphism",
        "macos": "macos",
    }
    DEFAULT_FAMILY_ID = "jetbrains"

    @classmethod
    def resolve_layout_id(cls, layout_id: str) -> str:
        """Normalise un identifiant de layout inconnu vers le layout par défaut."""
        return layout_id if layout_id in cls.LAYOUTS else cls.DEFAULT_LAYOUT_ID

    @classmethod
    def get_default_family_id(cls, layout_id: str) -> str:
        """Famille de Thème proposée par défaut pour un layout (jamais imposée)."""
        return cls.LAYOUT_DEFAULT_FAMILY.get(cls.resolve_layout_id(layout_id), cls.DEFAULT_FAMILY_ID)

    @classmethod
    def get_layout_thumbnail_path(cls, layout_id: str) -> Path | None:
        """Localise la miniature statique d'un layout sur le disque, ou None si manquante."""
        from ankiforge.utils.paths import get_resource_path

        target_id = cls.resolve_layout_id(layout_id)
        candidate = get_resource_path("resources", "layouts", f"{target_id}.png")
        return candidate if candidate.is_file() else None

    @classmethod
    def get_available_layouts(cls) -> list[dict[str, str]]:
        """Renvoie la liste des métadonnées de tous les layouts disponibles pour les paramètres."""
        results = []
        for layout_id, layout_class in cls.LAYOUTS.items():
            temp = layout_class.__new__(layout_class)
            results.append(
                {
                    "id": layout_id,
                    "name": temp.get_display_name() if hasattr(temp, "get_display_name") else layout_id.capitalize(),
                    "description": temp.get_description() if hasattr(temp, "get_description") else "",
                    "icon": temp.get_icon() if hasattr(temp, "get_icon") else "ph.layout",
                    "thumbnail": f"{layout_id}.png",
                }
            )
        return results

    @classmethod
    def apply_theme_for_layout(cls, layout_id: str, profile_name: str = "default") -> ThemeProfile:
        """Réapplique l'apparence du profil pour le layout donné.

        Le layout ne fournit plus qu'une famille de repli : le régime visuel vient de la
        Source du Mode persistée et la Famille choisie par l'utilisateur prime sur la
        famille par défaut du layout.
        """
        from ankiforge.ui.style_engine import get_style_engine

        engine = get_style_engine()
        return engine.apply_appearance_for_profile(profile_name, cls.resolve_layout_id(layout_id))

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
        except Exception as err:
            logger.debug("Lecture du layout en BDD ignorée : %s", err)

        from ankiforge.utils.environment import get_app_qsettings

        settings = get_app_qsettings("obsidian")
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
            except Exception as err:
                logger.debug("Sauvegarde du layout en BDD ignorée : %s", err)

            from ankiforge.utils.environment import get_app_qsettings

            settings = get_app_qsettings("obsidian")
            settings.setValue(f"profiles/{profile_name}/layout_id", layout_id)

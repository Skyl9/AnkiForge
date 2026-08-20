"""
Base Layout for Pluggable UI Architecture in AnkiForge.
"""

from abc import abstractmethod
from typing import Dict, Optional, Tuple, Type
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QWidget


class BaseLayout(QWidget):
    """
    Classe de base pour toutes les coquilles d'interface (Layouts).
    Reçoit le QStackedWidget central contenant les vues réelles uniques et gère la navigation / l'ergonomie.
    """

    view_selected = Signal(str, object)  # (view_id, optional_data_dict)
    settings_requested = Signal()
    toggle_sidebar_requested = Signal()
    search_clicked = Signal()

    def __init__(self, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.profile_name = profile_name
        self.stacked_widget: Optional[QStackedWidget] = None
        self._current_view_id: str = "dashboard"

    @abstractmethod
    def get_layout_id(self) -> str:
        """Identifiant unique du layout (ex: 'ide', 'macos', 'dashboard', 'glassmorphism')."""
        pass

    @abstractmethod
    def get_display_name(self) -> str:
        """Nom affiché dans la modale des paramètres."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Description succincte de l'ergonomie du layout."""
        pass

    @abstractmethod
    def set_stacked_widget(self, stacked_widget: QStackedWidget) -> None:
        """Intègre le conteneur de vues partagé dans la zone centrale du layout."""
        pass

    @abstractmethod
    def set_active_view(self, view_id: str) -> None:
        """Met à jour l'état visuel de la navigation (bouton actif)."""
        pass

    @abstractmethod
    def populate_navigation(self, view_registry: Dict[str, Tuple[str, str, str, Type[QWidget]]]) -> None:
        """Construit les éléments de navigation à partir du registre central des vues."""
        pass

    def update_daemon_status(self, status: str, text: str) -> None:
        """Met à jour l'indicateur de statut du daemon en arrière-plan."""
        pass

    def update_token_tracker(self, cost: str, tokens: str) -> None:
        """Met à jour l'affichage des dépenses IA."""
        pass

    def set_profile_name(self, profile_name: str) -> None:
        """Met à jour le nom du profil affiché."""
        self.profile_name = profile_name

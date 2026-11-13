"""Package CardModelsView d'AnkiForge (Atelier de Modèles de Cartes).

Re-exporte l'ensemble des composants, dialogues, utilitaires et la vue principale pour 100% de rétrocompatibilité.
"""

from ankidraft.ui.views.card_models_view.utils import extract_css_classes
from ankidraft.ui.views.card_models_view.view import CardModelsTab, CardModelsView
from ankidraft.ui.views.card_models_view.widgets import (
    ResponsiveTopActionBar,
    SubTabButton,
    TagPillButton,
)

__all__ = [
    "CardModelsView",
    "CardModelsTab",
    "ResponsiveTopActionBar",
    "SubTabButton",
    "TagPillButton",
    "extract_css_classes",
]

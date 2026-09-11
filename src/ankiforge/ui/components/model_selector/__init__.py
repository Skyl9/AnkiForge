"""
Package Model Selector d'AnkiForge.
Fournit les composants de sélection, badges de capacités et dialogue de découverte des modèles LLM.
"""

from ankiforge.ui.components.model_selector.badges import CapabilityPill, ModelCapabilityBadgesWidget
from ankiforge.ui.components.model_selector.dialog import ModelCardWidget, ModelDiscoveryDialog
from ankiforge.ui.components.model_selector.selector import ModelSelectorWidget

__all__ = [
    "CapabilityPill",
    "ModelCapabilityBadgesWidget",
    "ModelCardWidget",
    "ModelDiscoveryDialog",
    "ModelSelectorWidget",
]

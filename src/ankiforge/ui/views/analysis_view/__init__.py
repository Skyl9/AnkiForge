"""
Package AnalysisView d'AnkiForge (Analyse, Audit IA, Couverture, SRS et Doublons).
Re-exporte l'ensemble des composants pour 100% de rétrocompatibilité.
"""

from ankiforge.ui.views.analysis_view.tabs import (
    AIDuplicatesMergeTab,
    AISourcesDiagnosticTab,
    AITokensSrsTab,
    AIWozniakLinterTab,
    ClickableChunkWidget,
    DocumentInspectorPanel,
)
from ankiforge.ui.views.analysis_view.view import AnalysisView

__all__ = [
    "AnalysisView",
    "AIWozniakLinterTab",
    "AISourcesDiagnosticTab",
    "ClickableChunkWidget",
    "DocumentInspectorPanel",
    "AITokensSrsTab",
    "AIDuplicatesMergeTab",
]

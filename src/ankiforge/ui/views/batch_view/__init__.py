"""
Package BatchView d'AnkiForge (Batch Factory CI/CD).
Re-exporte l'ensemble des composants, utilitaires et la vue principale pour 100% de rétrocompatibilité.
"""

from ankiforge.ui.views.batch_view.constants import apply_pill_style
from ankiforge.ui.views.batch_view.view import BatchTab, BatchView
from ankiforge.ui.views.batch_view.widgets import (
    CicdMetricCard,
    ProgressTableCellWidget,
)

__all__ = [
    "BatchView",
    "BatchTab",
    "CicdMetricCard",
    "ProgressTableCellWidget",
    "apply_pill_style",
]

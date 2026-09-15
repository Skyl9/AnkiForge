"""
Package ABTestsView d'AnkiForge (Laboratoire de Tests A/B).
Re-exporte l'ensemble des composants, constantes et la vue principale pour 100% de rétrocompatibilité.
"""

from ankiforge.ui.views.ab_tests_view.constants import apply_pill_style
from ankiforge.ui.views.ab_tests_view.view import ABTestsTab, ABTestsView
from ankiforge.ui.views.ab_tests_view.widgets import (
    BranchKpiWidget,
    SubTabButton,
)

__all__ = [
    "ABTestsView",
    "ABTestsTab",
    "BranchKpiWidget",
    "SubTabButton",
    "apply_pill_style",
]

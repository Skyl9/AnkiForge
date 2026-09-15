"""
Package EditionView d'AnkiForge (Navigateur & Éditeur de Cartes).
Re-exporte l'ensemble des composants, utilitaires et la vue principale pour 100% de rétrocompatibilité.
"""

from ankiforge.ui.views.edition_view.utils import (
    format_tags_display,
    strip_html_tags,
)
from ankiforge.ui.views.edition_view.view import EditionTab, EditionView

__all__ = [
    "EditionView",
    "EditionTab",
    "strip_html_tags",
    "format_tags_display",
]

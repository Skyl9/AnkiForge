"""Famille « shell » de la galerie : coquille applicative et fenêtre de paramètres.

La fenêtre principale réelle n'est **pas** instanciée : elle démarre des timers réseau,
un worker de métriques et le démon MCP, effets de bord incompatibles avec un aperçu.
:class:`ShellPreviewWindow` recompose donc sa coquille à partir des vrais layouts et du
vrai registre de vues, chaque vue étant remplacée par un substitut textuel. La fenêtre
de paramètres, elle, est un dialogue autonome et s'ouvre en modal.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import QWidget

from ankiforge.ui.widget_gallery.previews import ShellPreviewWindow
from ankiforge.ui.widget_gallery.registry import gallery_widget
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)


def _make_shell_preview() -> QWidget:
    return ShellPreviewWindow()


def _make_settings_modal() -> QWidget:
    from ankiforge.ui.widgets.settings_modal.modal import SettingsModal

    return SettingsModal()


# Correspondance classe de référence → factory, source unique de la couverture.
SHELL_FACTORIES: dict[str, Callable[[], QWidget]] = {
    "MainWindow": _make_shell_preview,
    "SettingsModal": _make_settings_modal,
}

# Classe réellement couverte par chaque entrée (la coquille est rendue par un aperçu).
SHELL_CLASS_IDS: dict[str, str] = {
    "MainWindow": "MainWindow",
    "SettingsModal": "SettingsModal",
}

# Entrées dont l'aperçu s'ouvre légitimement en modal.
SHELL_MODAL_IDS = frozenset({"SettingsModal"})


def shell_labels() -> dict[str, str]:
    """Libellés français affichés dans l'arbre de la galerie (extractibles par lupdate)."""
    return {
        "MainWindow": tr("Coquille de la fenêtre principale"),
        "SettingsModal": tr("Préférences et paramètres"),
    }


def register() -> None:
    """Enregistre la coquille et les paramètres dans la galerie (idempotent)."""
    labels = shell_labels()
    for class_name, factory in SHELL_FACTORIES.items():
        label = labels.get(class_name)
        if label is None:
            logger.warning("Libellé de galerie manquant pour la coquille « %s »", class_name)
            label = class_name
        gallery_widget(family="shell", name=label, modal=class_name in SHELL_MODAL_IDS)(factory)

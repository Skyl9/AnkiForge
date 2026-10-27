"""Famille « viewmodels » de la galerie : état réactif MVVM (``QObject``).

Un ViewModel n'est pas un widget : chaque entrée l'instancie puis l'enveloppe dans un
:class:`ObjectPreview`, qui rend observables ses signaux et ses états d'occupation ou
d'erreur. Les ViewModels sont construits sans chargement de données ; seul l'aperçu
connecte leurs signaux, et ``dispose()`` est appelé à la fermeture pour libérer les
abonnements au bus d'événements.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import QWidget

from ankiforge.ui.viewmodels.agents_viewmodel import AgentsViewModel
from ankiforge.ui.viewmodels.analysis_viewmodel import AnalysisViewModel
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.ui.viewmodels.batch_viewmodel import BatchViewModel
from ankiforge.ui.viewmodels.creation_viewmodel import CreationViewModel
from ankiforge.ui.viewmodels.dashboard_viewmodel import DashboardViewModel
from ankiforge.ui.viewmodels.documents_viewmodel import DocumentsViewModel
from ankiforge.ui.viewmodels.edition_viewmodel import EditionViewModel
from ankiforge.ui.viewmodels.pipeline_viewmodel import PipelineViewModel
from ankiforge.ui.widget_gallery.previews import ObjectPreview
from ankiforge.ui.widget_gallery.registry import gallery_widget
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)


def _preview_viewmodel(viewmodel: BaseViewModel) -> QWidget:
    """Enveloppe un ViewModel dans son inspecteur de signaux."""
    return ObjectPreview(
        viewmodel,
        title=type(viewmodel).__name__,
        subtitle=tr("Signaux et états d'occupation exposés par ce ViewModel."),
    )


def _make_base_viewmodel() -> QWidget:
    return _preview_viewmodel(BaseViewModel())


def _make_agents_viewmodel() -> QWidget:
    return _preview_viewmodel(AgentsViewModel())


def _make_analysis_viewmodel() -> QWidget:
    return _preview_viewmodel(AnalysisViewModel())


def _make_batch_viewmodel() -> QWidget:
    return _preview_viewmodel(BatchViewModel())


def _make_creation_viewmodel() -> QWidget:
    return _preview_viewmodel(CreationViewModel())


def _make_dashboard_viewmodel() -> QWidget:
    return _preview_viewmodel(DashboardViewModel())


def _make_documents_viewmodel() -> QWidget:
    return _preview_viewmodel(DocumentsViewModel())


def _make_edition_viewmodel() -> QWidget:
    return _preview_viewmodel(EditionViewModel())


def _make_pipeline_viewmodel() -> QWidget:
    return _preview_viewmodel(PipelineViewModel())


# Correspondance ViewModel → factory, source unique de la couverture.
VIEWMODEL_FACTORIES: dict[str, Callable[[], QWidget]] = {
    "BaseViewModel": _make_base_viewmodel,
    "AgentsViewModel": _make_agents_viewmodel,
    "AnalysisViewModel": _make_analysis_viewmodel,
    "BatchViewModel": _make_batch_viewmodel,
    "CreationViewModel": _make_creation_viewmodel,
    "DashboardViewModel": _make_dashboard_viewmodel,
    "DocumentsViewModel": _make_documents_viewmodel,
    "EditionViewModel": _make_edition_viewmodel,
    "PipelineViewModel": _make_pipeline_viewmodel,
}


def viewmodel_labels() -> dict[str, str]:
    """Libellés français affichés dans l'arbre de la galerie (extractibles par lupdate)."""
    return {
        "BaseViewModel": tr("ViewModel de base"),
        "AgentsViewModel": tr("ViewModel des agents IA"),
        "AnalysisViewModel": tr("ViewModel d'analyse"),
        "BatchViewModel": tr("ViewModel de la file de lots"),
        "CreationViewModel": tr("ViewModel de création"),
        "DashboardViewModel": tr("ViewModel du tableau de bord"),
        "DocumentsViewModel": tr("ViewModel documentaire"),
        "EditionViewModel": tr("ViewModel d'édition"),
        "PipelineViewModel": tr("ViewModel des pipelines"),
    }


def register() -> None:
    """Enregistre les ViewModels dans la galerie (idempotent)."""
    labels = viewmodel_labels()
    for class_name, factory in VIEWMODEL_FACTORIES.items():
        label = labels.get(class_name)
        if label is None:
            logger.warning("Libellé de galerie manquant pour le ViewModel « %s »", class_name)
            label = class_name
        gallery_widget(family="viewmodels", name=label)(factory)

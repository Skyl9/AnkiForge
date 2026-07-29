"""
Tests unitaires PySide6 / pytest-qt pour le workflow de la vue AnalysisView.
Workflow: Aucun paquet par défaut -> Choix du paquet -> Clic 'Analyser ce paquet'.
"""

from unittest.mock import MagicMock
from ankiforge.ui.views.edition_view import EditionView
from ankiforge.ui.views.analysis_view import AnalysisView, AIWozniakLinterTab, AISourcesDiagnosticTab


def test_edition_view_instantiation(qtbot):
    """Vérifie l'instanciation de la vue d'Édition & Navigateur."""
    view = EditionView(ai_manager=MagicMock())
    qtbot.addWidget(view)
    assert view is not None
    assert view.card_list is not None


def test_analysis_view_instantiation_default_state(qtbot):
    """Vérifie l'état par défaut neutre d'AnalysisView (aucun paquet sélectionné, 0 calcul)."""
    view = AnalysisView()
    qtbot.addWidget(view)
    assert view is not None
    assert view.stack.count() == 4

    # Vérifier que le paquet par défaut est None
    assert view.tab_wozniak.selected_deck_id is None
    assert view.tab_sources.selected_deck_id is None
    assert "Score : -- / 100" in view.tab_wozniak.score_badge.text()


def test_wozniak_linter_workflow_selection_and_analysis(qtbot):
    """Vérifie le workflow : Choix d'un paquet -> Clic Analyser ce paquet -> Calculs Wozniak."""
    tab = AIWozniakLinterTab()
    qtbot.addWidget(tab)

    # 1. Sélection simulée d'un paquet (id=1, name='Informatique::C++')
    tab.selected_deck_id = 1
    tab.selected_deck_name = "Informatique::C++"
    tab.btn_deck.setText("Informatique::C++ (142 cartes)")

    # 2. Clic sur 'Analyser ce paquet'
    tab.btn_analyze.click()

    # 3. Vérification des résultats calculés
    assert tab.score_badge.text() != "Score : -- / 100"
    assert tab.cards_layout.count() > 0


def test_sources_diagnostic_workflow(qtbot):
    """Vérifie le workflow du diagnostic des sources à la demande."""
    tab = AISourcesDiagnosticTab()
    qtbot.addWidget(tab)

    # 1. Sélection simulée du paquet
    tab.selected_deck_id = 1
    tab.btn_analyze.click()

    # 2. Vérification de l'affichage des sources
    assert tab.lbl_score.text() != "Score Global Précision : -- %"

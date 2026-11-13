"""Tests headless Qt de la vue aplatie de recherche de paramètres.

Vérifie le rendu des résultats (cartes, fil d'Ariane, surlignage), l'état vide
et l'émission du signal de sélection de résultat.
"""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ankidraft.ui.widgets.settings_modal.components.search_view import SettingsSearchView
from ankidraft.ui.widgets.settings_modal.search_registry import (
    SettingDescriptor,
    SettingSearchResult,
    SettingsRegistry,
)


def _make_result(key: str, label: str, description: str, tab_index: int) -> SettingSearchResult:
    descriptor = SettingDescriptor(
        key=key,
        label=label,
        description=description,
        keywords=(key.split("/")[-1],),
        tab="Général",
        section="Apparence",
        widget=label,
        tab_index=tab_index,
    )
    return SettingSearchResult(descriptor=descriptor, score=5.0, matched_fields=("label",))


def _show(view: SettingsSearchView, qtbot) -> None:
    """Affiche la vue pour que les états visibles/résultat soient évaluables."""
    qtbot.addWidget(view)
    view.show()
    QApplication.processEvents()


def test_search_view_affiche_resultats_sous_forme_de_cartes(qtbot) -> None:
    """Des résultats sont rendus sous forme de cartes avec titre et fil d'Ariane."""
    view = SettingsSearchView()
    _show(view, qtbot)
    resultats = [
        _make_result("ui/theme", "Famille de thème", "Choisit l'identité graphique.", 0),
        _make_result("ui/language", "Langue de l'interface", "Définit la langue affichée.", 0),
    ]
    view.set_results(resultats, "thème")

    assert view.list_results.isVisible()
    assert view.empty_widget.isHidden()
    assert view.list_results.count() == 2

    première_carte = view.list_results.itemWidget(view.list_results.item(0))
    assert première_carte is not None
    assert "Famille de" in première_carte.lbl_title.text()
    assert "thème" in première_carte.lbl_title.text()
    assert "Général" in première_carte.lbl_breadcrumb.text()
    assert "Apparence" in première_carte.lbl_breadcrumb.text()


def test_search_view_affiche_etat_vide_sans_resultat(qtbot) -> None:
    """L'état vide s'affiche quand aucun réglage ne correspond."""
    view = SettingsSearchView()
    _show(view, qtbot)
    view.set_results([], "zzz_inconnu")

    assert view.list_results.isHidden()
    assert view.empty_widget.isVisible()
    assert "Aucun réglage" in view.lbl_empty_text.text()


def test_search_view_surligne_les_termes_correspondants(qtbot) -> None:
    """Le surlignage HTML entoure les termes de la requête dans le libellé."""
    view = SettingsSearchView()
    _show(view, qtbot)
    resultats = [_make_result("ui/theme", "Famille de thème", "Choisit l'identité graphique.", 0)]
    view.set_results(resultats, "thème")

    carte = view.list_results.itemWidget(view.list_results.item(0))
    html = carte.lbl_title.text()
    assert "thème" in html
    assert "span" in html  # balise de surlignage présente


def test_search_view_émet_result_selected_lors_du_clic(qtbot) -> None:
    """Un clic sur une carte émet le signal result_selected avec le descripteur."""
    view = SettingsSearchView()
    _show(view, qtbot)
    résultat = _make_result("ui/layout", "Disposition", "Coquille d'interface.", 0)
    view.set_results([résultat], "disposition")

    capturés: list = []
    view.result_selected.connect(capturés.append)

    carte = view.list_results.itemWidget(view.list_results.item(0))
    QTest.mouseClick(carte, Qt.MouseButton.LeftButton)

    assert len(capturés) == 1
    assert capturés[0].key == "ui/layout"
    assert capturés[0].tab_index == 0


def test_search_view_recherche_registre_vide(qtbot) -> None:
    """set_results avec la liste vide du registre affiche l'état vide."""
    view = SettingsSearchView()
    _show(view, qtbot)
    view.set_results(SettingsRegistry.search("zzz_aucun_resultat"), "zzz_aucun_resultat")

    assert view.empty_widget.isVisible()
    assert view.list_results.count() == 0


def test_search_view_query_retourne_la_dernière_saisie(qtbot) -> None:
    """La requête mémorisée correspond à la dernière saisie affichée."""
    view = SettingsSearchView()
    _show(view, qtbot)
    view.set_results([], "température")
    assert view.query() == "température"

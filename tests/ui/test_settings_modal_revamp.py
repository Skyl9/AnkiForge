"""Tests headless Qt de l'intégration de la recherche dans SettingsModal.

Vérifie le champ de recherche en barre latérale, le raccourci Ctrl+F, la bascule
vers la vue aplitée dès 2 caractères, la restauration de l'onglet actif et le
traitement d'un clic sur un résultat.
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ankiforge.ui.widgets.settings_modal import SettingsModal
from ankiforge.ui.widgets.settings_modal.search_registry import SettingDescriptor, SettingSearchResult


def _un_descriptor(tab_index: int) -> SettingDescriptor:
    return SettingDescriptor(
        key="ui/theme",
        label="Famille de thème",
        description="Choisit l'identité graphique.",
        keywords=("thème",),
        tab="Général",
        section="Apparence",
        widget="Famille de thème",
        tab_index=tab_index,
    )


def test_modal_expose_champ_recherche_dans_sidebar(qtbot) -> None:
    """Le champ de recherche est présent dans la barre latérale avec icône et placeholder."""
    modal = SettingsModal()
    qtbot.addWidget(modal)

    assert modal._search_field is not None
    assert "Rechercher un paramètre" in modal._search_field.placeholderText()
    assert modal._search_field in modal.sidebar.findChildren(modal._search_field.__class__)


def test_ctrl_f_place_le_focus_sur_le_champ_recherche(qtbot) -> None:
    """Le raccourci Ctrl+F place le focus sur le champ de recherche."""
    modal = SettingsModal()
    qtbot.addWidget(modal)
    modal.show()
    modal.activateWindow()
    modal.setFocus()
    QApplication.processEvents()

    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    modal.keyPressEvent(ev)
    assert modal._search_field.hasFocus()


def test_saisie_de_deux_caracteres_bascule_sur_la_vue_recherche(qtbot) -> None:
    """Dès 2 caractères, le stacked widget affiche SettingsSearchView."""
    modal = SettingsModal()
    qtbot.addWidget(modal)

    index_actif = modal.stacked_widget.currentIndex()
    modal._search_field.setText("thème")

    assert modal._search_stack_index is not None
    assert modal.stacked_widget.currentIndex() == modal._search_stack_index
    assert modal.stacked_widget.currentIndex() != index_actif


def test_vidage_du_champ_restaure_l_onglet_actif(qtbot) -> None:
    """Effacer la recherche revient à l'onglet précédemment sélectionné."""
    modal = SettingsModal()
    qtbot.addWidget(modal)

    modal.select_tab(1)
    assert modal._active_tab_index == 1

    modal._search_field.setText("thème")
    assert modal._is_search_view_active()

    modal._search_field.clear()
    assert modal.stacked_widget.currentIndex() == modal._active_tab_index


def test_echap_restaure_l_onglet_actif_depuis_la_vue_recherche(qtbot) -> None:
    """La touche Échap quitte la vue de recherche et restaure l'onglet actif."""
    modal = SettingsModal()
    qtbot.addWidget(modal)

    modal.select_tab(2)
    modal._search_field.setText("thème")
    assert modal._is_search_view_active()

    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    modal.keyPressEvent(ev)

    assert not modal._is_search_view_active()
    assert modal.stacked_widget.currentIndex() == modal._active_tab_index


def test_clic_resultat_selectionne_l_onglet_cible(qtbot) -> None:
    """Un clic sur un résultat sélectionne l'onglet cible (chargement à la demande)."""
    modal = SettingsModal()
    qtbot.addWidget(modal)

    résultat = SettingSearchResult(
        descriptor=_un_descriptor(0),
        score=5.0,
        matched_fields=("label",),
    )
    modal._on_search_result_selected(résultat.descriptor)

    assert modal.stacked_widget.currentIndex() == 0
    assert modal._tabs[0] is not None


def test_recherche_une_seule_lettre_ne_bascule_pas(qtbot) -> None:
    """Une seule lettre ne déclenche pas la bascule vers la vue de recherche."""
    modal = SettingsModal()
    qtbot.addWidget(modal)

    index_actif = modal.stacked_widget.currentIndex()
    modal._search_field.setText("t")

    assert modal.stacked_widget.currentIndex() == index_actif
    assert not modal._is_search_view_active()

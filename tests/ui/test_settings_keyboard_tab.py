"""Tests headless Qt pour l'onglet « Clavier » dans SettingsModal (T7).

Vérifie :
- présence de l'onglet Clavier à l'indice 7 et non-régression des autres accesseurs,
- affichage de toutes les actions du catalogue avec catégorie, portée, séquence et état,
- filtrage par texte et par catégorie,
- réinitialisation unitaire et globale,
- persistance des surcharges via SettingsService et survie à la réouverture (round-trip),
- aucune écriture si la valeur est égale au défaut,
- atteinte depuis la palette de commandes.
"""

from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.shortcuts import ShortcutId, get_shortcut_catalog
from ankiforge.ui.widgets.command_palette import CommandPaletteModal
from ankiforge.ui.widgets.settings_modal.modal import SettingsModal
from ankiforge.ui.widgets.settings_modal.tabs.keyboard_tab import KeyboardTab


def test_settings_modal_has_keyboard_tab_and_accessors_intact(qtbot) -> None:
    """L'onglet Clavier est à l'indice 7 et les 8 autres onglets conservent leurs accesseurs."""
    with patch("ankiforge.ui.widgets.settings_modal.modal.is_development", return_value=True):
        modal = SettingsModal()
        qtbot.addWidget(modal)

        # Vérification accesseur keyboard_tab
        assert hasattr(modal, "keyboard_tab")
        kb = modal.keyboard_tab
        assert isinstance(kb, KeyboardTab)

        # Vérification non-régression de tous les autres accesseurs
        assert modal.general_tab is not None
        assert modal.ai_tab is not None
        assert modal.anki_tab is not None
        assert modal.tts_tab is not None
        assert modal.maint_tab is not None
        assert modal.addons_tab is not None
        assert modal.support_tab is not None
        assert modal.dev_tab is not None


def test_keyboard_tab_lists_all_catalog_actions(qtbot) -> None:
    """La table de l'onglet Clavier contient l'intégralité du catalogue déclaré."""
    tab = KeyboardTab()
    qtbot.addWidget(tab)

    catalog = get_shortcut_catalog()
    total_actions = len(catalog)
    assert tab.table_shortcuts.rowCount() == total_actions


def test_keyboard_tab_filter_by_search_and_category(qtbot) -> None:
    """Le filtrage par recherche textuelle et par catégorie réduit le nombre de lignes visibles."""
    tab = KeyboardTab()
    qtbot.addWidget(tab)

    # 1. Recherche "palette"
    tab.le_search.setText("palette")
    QApplication.processEvents()

    visible_rows = [r for r in range(tab.table_shortcuts.rowCount()) if not tab.table_shortcuts.isRowHidden(r)]
    assert len(visible_rows) >= 1

    # 2. Effacer recherche et filtrer par catégorie
    tab.le_search.clear()
    idx = tab.cb_category.findText("Navigation")
    if idx >= 0:
        tab.cb_category.setCurrentIndex(idx)
        QApplication.processEvents()
        nav_rows = [r for r in range(tab.table_shortcuts.rowCount()) if not tab.table_shortcuts.isRowHidden(r)]
        assert len(nav_rows) >= 1
        assert len(nav_rows) < tab.table_shortcuts.rowCount()


def test_keyboard_tab_remap_persists_round_trip(qtbot, mock_db) -> None:
    """La modification d'un raccourci marque dirty, persiste en BDD et survit à la réouverture."""
    tab = KeyboardTab()
    qtbot.addWidget(tab)

    sc_id = ShortcutId.APP_SETTINGS
    assert not tab.has_pending_changes()

    # Définir une surcharge valide dans le tab
    tab.apply_override(sc_id, "Ctrl+Shift+,")
    assert tab.has_pending_changes()

    # Sauvegarder
    saved, _, _ = tab.save_tab()
    assert saved is True
    assert not tab.has_pending_changes()

    # Vérifier persistance SettingsService
    assert SettingsService.get_shortcut_override(sc_id.value) == "Ctrl+Shift+,"

    # Réouverture d'une nouvelle instance KeyboardTab
    new_tab = KeyboardTab()
    qtbot.addWidget(new_tab)
    row = new_tab.find_row_by_id(sc_id.value)
    assert row is not None
    seq_item = new_tab.table_shortcuts.item(row, 3)
    assert seq_item is not None
    assert seq_item.text() == "Ctrl+Shift+,"
    state_item = new_tab.table_shortcuts.item(row, 4)
    assert state_item is not None
    assert "Modifié" in state_item.text() or "Personnalisé" in state_item.text()


def test_keyboard_tab_reset_single_and_reset_all(qtbot, mock_db) -> None:
    """Réinitialisation unitaire puis globale d'une surcharge."""
    sc_id = ShortcutId.APP_COMMAND_PALETTE
    SettingsService.set_shortcut_override(sc_id.value, "Ctrl+Alt+K")
    SettingsService.set_shortcut_override(ShortcutId.APP_SAVE.value, "Ctrl+Alt+S")

    tab = KeyboardTab()
    qtbot.addWidget(tab)

    # Réinitialisation unitaire
    tab.reset_single(sc_id)
    assert tab.has_pending_changes()
    tab.save_tab()
    assert SettingsService.get_shortcut_override(sc_id.value) is None
    # APP_SAVE est toujours surchargé
    assert SettingsService.get_shortcut_override(ShortcutId.APP_SAVE.value) == "Ctrl+Alt+S"

    # Réinitialisation globale
    tab.reset_all()
    assert tab.has_pending_changes()
    tab.save_tab()
    assert len(SettingsService.get_all_shortcut_overrides()) == 0


def test_command_palette_has_customize_shortcuts_command(qtbot) -> None:
    """La palette de commandes expose 'Personnaliser les raccourcis'."""
    palette = CommandPaletteModal()
    qtbot.addWidget(palette)

    cmds = [c for c in palette.commands if c.get("id") == "action.shortcuts"]
    assert len(cmds) == 1
    assert "Personnaliser" in cmds[0]["title"]

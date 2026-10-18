"""Tests unitaires et d'intégration pour la persistance des raccourcis dans SettingsService.

Vérifie :
- round-trip de persistance des surcharges de raccourcis,
- aucune écriture si la valeur est égale au défaut,
- réinitialisation unitaire et globale,
- méthodes delete_value et delete_category sur SettingModel.
"""

from ankiforge.database.models import SettingModel
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.shortcuts import ShortcutId


def test_setting_model_delete_value(mock_db) -> None:
    """SettingModel.delete_value doit supprimer une clé existante et renvoyer True."""
    SettingModel.set_value("test/key_to_delete", "val1", category="test_cat")
    assert SettingModel.get_value("test/key_to_delete") == "val1"

    deleted = SettingModel.delete_value("test/key_to_delete")
    assert deleted is True
    assert SettingModel.get_value("test/key_to_delete") is None

    # Suppression d'une clé inexistante renvoie False
    assert SettingModel.delete_value("test/key_nonexistent") is False


def test_setting_model_delete_category(mock_db) -> None:
    """SettingModel.delete_category doit supprimer tous les enregistrements de la catégorie."""
    SettingModel.set_value("cat_test/1", "a", category="batch_delete")
    SettingModel.set_value("cat_test/2", "b", category="batch_delete")
    SettingModel.set_value("cat_test/3", "c", category="batch_delete")
    SettingModel.set_value("other/1", "keep", category="other_cat")

    count = SettingModel.delete_category("batch_delete")
    assert count == 3
    assert SettingModel.get_value("cat_test/1") is None
    assert SettingModel.get_value("cat_test/2") is None
    assert SettingModel.get_value("cat_test/3") is None
    assert SettingModel.get_value("other/1") == "keep"


def test_settings_service_shortcut_override_lifecycle(mock_db) -> None:
    """Cycle de vie complet des surcharges de raccourcis dans SettingsService."""
    sc_id = ShortcutId.APP_SETTINGS.value
    default_seq = "Ctrl+,"

    # 1. Aucun override initialement
    assert SettingsService.get_shortcut_override(sc_id) is None

    # 2. Définir un override différent du défaut
    SettingsService.set_shortcut_override(sc_id, "Ctrl+Shift+,", default_sequence=default_seq)
    assert SettingsService.get_shortcut_override(sc_id) == "Ctrl+Shift+,"

    all_overrides = SettingsService.get_all_shortcut_overrides()
    assert all_overrides.get(sc_id) == "Ctrl+Shift+,"

    # 3. Réinitialisation unitaire via remove_shortcut_override
    SettingsService.remove_shortcut_override(sc_id)
    assert SettingsService.get_shortcut_override(sc_id) is None
    assert sc_id not in SettingsService.get_all_shortcut_overrides()


def test_settings_service_no_write_if_equal_to_default(mock_db) -> None:
    """Aucune écriture si la valeur est égale au défaut, et suppression d'un override préexistant."""
    sc_id = ShortcutId.APP_SAVE.value
    default_seq = "Ctrl+S"

    # Mettre un override initial
    SettingsService.set_shortcut_override(sc_id, "Ctrl+Alt+S", default_sequence=default_seq)
    assert SettingsService.get_shortcut_override(sc_id) == "Ctrl+Alt+S"

    # Réassigner la valeur par défaut -> doit supprimer l'override sans écrire
    SettingsService.set_shortcut_override(sc_id, default_seq, default_sequence=default_seq)
    assert SettingsService.get_shortcut_override(sc_id) is None
    assert SettingModel.get_value(f"shortcuts/{sc_id}") is None


def test_settings_service_clear_all_shortcut_overrides(mock_db) -> None:
    """clear_all_shortcut_overrides doit vider toutes les surcharges de raccourcis."""
    SettingsService.set_shortcut_override(ShortcutId.APP_SAVE.value, "Ctrl+Alt+S")
    SettingsService.set_shortcut_override(ShortcutId.APP_FIND.value, "Ctrl+Alt+F")

    assert len(SettingsService.get_all_shortcut_overrides()) >= 2

    SettingsService.clear_all_shortcut_overrides()
    assert len(SettingsService.get_all_shortcut_overrides()) == 0
    assert SettingsService.get_shortcut_override(ShortcutId.APP_SAVE.value) is None
    assert SettingsService.get_shortcut_override(ShortcutId.APP_FIND.value) is None

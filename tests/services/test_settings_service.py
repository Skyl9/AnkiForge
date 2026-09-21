"""
Tests unitaires pour SettingsService (Persistance BDD Peewee et fallback QSettings).
"""

from ankiforge.database.models import SettingModel
from ankiforge.services.settings_service import SettingsService


def test_settings_service_get_and_set():
    """Vérifie l'écriture et la lecture de paramètres via SettingsService."""
    SettingsService.set("custom/feature_flag", True, category="experimental")
    assert SettingsService.get("custom/feature_flag") is True

    # Vérifier que la valeur a bien été inscrite en base de données SQLite
    db_record = SettingModel.get_or_none(SettingModel.key == "custom/feature_flag")
    assert db_record is not None
    assert db_record.category == "experimental"

    # Mise à jour
    SettingsService.set("custom/feature_flag", False, category="experimental")
    assert SettingsService.get("custom/feature_flag") is False


def test_settings_service_batch_and_category():
    """Vérifie le traitement par lot et la récupération par catégorie."""
    payload = {
        "appearance/theme_family": "jetbrains",
        "appearance/color_mode": "light",
        "appearance/compact_sidebar": False,
    }
    SettingsService.set_batch(payload, category="appearance")

    cat_data = SettingsService.get_category("appearance")
    assert cat_data.get("appearance/theme_family") == "jetbrains"
    assert cat_data.get("appearance/color_mode") == "light"
    assert cat_data.get("appearance/compact_sidebar") is False


def test_settings_service_fallback():
    """Vérifie le retour de la valeur par défaut pour une clé inconnue."""
    assert SettingsService.get("unknown_key_xyz", default="fallback_val") == "fallback_val"


def test_settings_service_set_skips_identical_value(monkeypatch):
    """Retaper la même valeur ne doit déclencher aucune écriture (BDD ni QSettings)."""
    from unittest.mock import patch

    SettingsService.set("ai/temperature", 0.7, category="ai")
    record = SettingModel.get(SettingModel.key == "ai/temperature")
    first_updated_at = record.updated_at

    with patch("ankiforge.database.models.SettingModel.set_value") as mock_set_value:
        SettingsService.set("ai/temperature", 0.7, category="ai")
    mock_set_value.assert_not_called()

    # La valeur inchangée ne bump pas la date de mise à jour
    record = SettingModel.get(SettingModel.key == "ai/temperature")
    assert record.updated_at == first_updated_at


def test_setting_model_set_value_skips_identical_write():
    """SettingModel.set_value n'écrit pas si la valeur et la catégorie sont identiques."""
    SettingModel.set_value("ui/language", "Français", category="general")
    record = SettingModel.get(SettingModel.key == "ui/language")
    first_updated_at = record.updated_at

    SettingModel.set_value("ui/language", "Français", category="general")
    record = SettingModel.get(SettingModel.key == "ui/language")
    assert record.updated_at == first_updated_at

    SettingModel.set_value("ui/language", "English", category="general")
    assert SettingModel.get_value("ui/language") == "English"

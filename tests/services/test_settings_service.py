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

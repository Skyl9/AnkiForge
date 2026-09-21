from typing import Any

from ankiforge.services.settings_service import values_equal


class SettingsDirtyMixin:
    """Détection de modifications non persistées pour un onglet de réglages.

    Les onglets persistés (Général, Moteurs IA, Anki, TTS) implémentent
    ``has_pending_changes()`` en comparant chaque contrôle à la valeur
    actuellement enregistrée (SettingsService.get / QSettings).
    """

    def has_pending_changes(self) -> bool:
        raise NotImplementedError

    @staticmethod
    def _values_equal(a: Any, b: Any) -> bool:
        return values_equal(a, b)

    def _changed(self, key: str, current: Any, default: Any = None) -> bool:
        from ankiforge.services.settings_service import SettingsService

        return not values_equal(current, SettingsService.get(key, default))

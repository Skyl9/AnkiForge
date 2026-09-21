from typing import Any

from ankiforge.services.settings_service import values_equal


class SettingsDirtyMixin:
    """Détection en mémoire des modifications non persistées pour un onglet de réglages.

    Les onglets persistés (Général, Moteurs IA, Anki, TTS) doivent implémenter
    ``has_pending_changes()`` en comparant leurs contrôles à un instantané (snapshot)
    des valeurs initiales conservé en mémoire (RAM).

    IMPORTANT : Ne JAMAIS interroger la base de données (SettingsService.get, Peewee)
    ni le système de fichiers dans ``has_pending_changes()``, car cette méthode est
    invoquée fréquemment par le timer de surveillance de la modale.
    """

    def has_pending_changes(self) -> bool:
        raise NotImplementedError

    @staticmethod
    def _values_equal(a: Any, b: Any) -> bool:
        return values_equal(a, b)

    def _changed(self, key: str, current: Any, default: Any = None) -> bool:
        """Déprécié : effectue une requête BDD à chaque appel.

        Préférer la comparaison en mémoire via un instantané ``self._initial``.
        """
        from ankiforge.services.settings_service import SettingsService

        return not values_equal(current, SettingsService.get(key, default))

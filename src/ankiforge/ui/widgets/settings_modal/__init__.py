"""
Package SettingsModal d'AnkiForge.
Re-exporte l'ensemble des composants, onglets et dialogue principal pour rétrocompatibilité 100%.
"""

from ankiforge.database.backup import backup_database
from ankiforge.ui.widgets.settings_modal.components import (
    PasswordLineEdit,
    SettingsCard,
    SettingsNavButton,
    StorageMetricCard,
    apply_pill_badge_style,
)
from ankiforge.ui.widgets.settings_modal.modal import (
    MaintenanceTab,
    SettingsDialog,
    SettingsModal,
    StatisticsTab,
)
from ankiforge.ui.widgets.settings_modal.tabs import (
    AIEnginesTab,
    AnkiSyncTab,
    GeneralTab,
    StorageMaintenanceTab,
    TTSSettingsTab,
)

__all__ = [
    "SettingsModal",
    "SettingsDialog",
    "GeneralTab",
    "AIEnginesTab",
    "AnkiSyncTab",
    "StorageMaintenanceTab",
    "TTSSettingsTab",
    "MaintenanceTab",
    "StatisticsTab",
    "SettingsCard",
    "PasswordLineEdit",
    "SettingsNavButton",
    "StorageMetricCard",
    "apply_pill_badge_style",
    "backup_database",
]

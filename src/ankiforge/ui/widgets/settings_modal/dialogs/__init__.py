"""Dialogues spécialisés pour la fenêtre de paramètres (SettingsModal)."""

from ankiforge.ui.widgets.settings_modal.dialogs.model_config_dialog import ModelConfigDialog
from ankiforge.ui.widgets.settings_modal.dialogs.shortcut_capture_dialog import (
    ShortcutCaptureDialog,
    key_event_to_sequence_str,
)

__all__ = ["ModelConfigDialog", "ShortcutCaptureDialog", "key_event_to_sequence_str"]

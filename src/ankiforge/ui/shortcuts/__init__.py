"""Package des raccourcis clavier déclaratifs d'AnkiForge (ADR 0032)."""

from ankiforge.ui.shortcuts.catalog import (
    SHORTCUT_CATALOG,
    get_shortcut_catalog,
    get_shortcut_definition,
    get_shortcut_label,
    get_shortcut_sequence,
    validate_catalog,
)
from ankiforge.ui.shortcuts.manager import (
    ShortcutManager,
    is_text_input_focused,
)
from ankiforge.ui.shortcuts.models import (
    RESERVED_SEQUENCES,
    ShortcutCategory,
    ShortcutDefinition,
    ShortcutId,
    ShortcutScope,
    is_reserved_sequence,
)

__all__ = [
    "RESERVED_SEQUENCES",
    "SHORTCUT_CATALOG",
    "ShortcutCategory",
    "ShortcutDefinition",
    "ShortcutId",
    "ShortcutManager",
    "ShortcutScope",
    "get_shortcut_catalog",
    "get_shortcut_definition",
    "get_shortcut_label",
    "get_shortcut_sequence",
    "is_reserved_sequence",
    "is_text_input_focused",
    "validate_catalog",
]

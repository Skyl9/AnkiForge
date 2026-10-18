"""Tests unitaires du registre déclaratif des raccourcis clavier (AnkiForge ADR 0032)."""

import pytest

from ankiforge.ui.shortcuts.catalog import (
    SHORTCUT_CATALOG,
    get_shortcut_definition,
    get_shortcut_label,
    get_shortcut_sequence,
    validate_catalog,
)
from ankiforge.ui.shortcuts.models import (
    RESERVED_SEQUENCES,
    ShortcutCategory,
    ShortcutDefinition,
    ShortcutId,
    ShortcutScope,
    is_reserved_sequence,
)

pytestmark = pytest.mark.unit


def test_shortcut_scope_hierarchy() -> None:
    """Vérifie l'ordre hiérarchique strict : Dialogue > Widget > Vue > Application."""
    assert ShortcutScope.DIALOGUE > ShortcutScope.WIDGET
    assert ShortcutScope.WIDGET > ShortcutScope.VUE
    assert ShortcutScope.VUE > ShortcutScope.APPLICATION


def test_reserved_sequences_detection() -> None:
    """Vérifie la détection et la liste noire des séquences réservées."""
    assert "Ctrl+C" in RESERVED_SEQUENCES
    assert "Ctrl+V" in RESERVED_SEQUENCES
    assert "Ctrl+W" in RESERVED_SEQUENCES
    assert "Ctrl+Q" in RESERVED_SEQUENCES

    assert is_reserved_sequence("Ctrl+C") is True
    assert is_reserved_sequence("ctrl+c") is True
    assert is_reserved_sequence("Ctrl+K") is False
    assert is_reserved_sequence("Alt+1") is False


def test_catalog_validation_passes() -> None:
    """Le catalogue par défaut doit passer toutes les vérifications d'intégrité."""
    validate_catalog(SHORTCUT_CATALOG)


def test_catalog_uniqueness_within_application_scope() -> None:
    """Toutes les séquences en portée APPLICATION doivent être strictement uniques."""
    app_sequences: dict[str, ShortcutId] = {}
    for sc_id, definition in SHORTCUT_CATALOG.items():
        if definition.scope == ShortcutScope.APPLICATION:
            seq = definition.default_sequence
            assert seq not in app_sequences, f"Collision de séquence en portée APPLICATION : {seq} partagée par {app_sequences[seq]} et {sc_id}"
            app_sequences[seq] = sc_id


def test_catalog_no_reserved_sequences() -> None:
    """Aucune séquence du catalogue ne doit empiéter sur la liste noire."""
    for sc_id, definition in SHORTCUT_CATALOG.items():
        assert not is_reserved_sequence(definition.default_sequence), f"Le raccourci {sc_id} utilise une séquence réservée : {definition.default_sequence}"


def test_catalog_bare_keys_only_in_widget_scope() -> None:
    """Les touches nues ne sont admises qu'en portée Widget avec allow_bare_key=True."""
    for sc_id, definition in SHORTCUT_CATALOG.items():
        if definition.allow_bare_key or len(definition.default_sequence) == 1:
            assert definition.scope == ShortcutScope.WIDGET, f"Touche nue interdite hors portée Widget : {sc_id} ({definition.default_sequence})"
            assert definition.allow_bare_key is True


def test_lazy_translation_resolution() -> None:
    """Les libellés doivent être résolus paresseusement à l'évaluation de la propriété title."""
    call_count = 0

    def mock_getter() -> str:
        nonlocal call_count
        call_count += 1
        return f"Titre dynamique {call_count}"

    sc = ShortcutDefinition(
        id=ShortcutId.APP_COMMAND_PALETTE,
        category=ShortcutCategory.APPLICATION,
        scope=ShortcutScope.APPLICATION,
        default_sequence="Ctrl+K",
        title_getter=mock_getter,
    )

    assert call_count == 0
    assert sc.title == "Titre dynamique 1"
    assert call_count == 1
    assert sc.title == "Titre dynamique 2"
    assert call_count == 2


def test_get_shortcut_helpers() -> None:
    """Vérifie le bon fonctionnement des helpers d'accès au catalogue."""
    defn = get_shortcut_definition(ShortcutId.APP_COMMAND_PALETTE)
    assert defn.default_sequence == "Ctrl+K"
    assert defn.scope == ShortcutScope.APPLICATION

    seq = get_shortcut_sequence(ShortcutId.APP_COMMAND_PALETTE)
    assert seq == "Ctrl+K"

    label = get_shortcut_label(ShortcutId.APP_COMMAND_PALETTE)
    assert isinstance(label, str)
    assert len(label) > 0


def test_get_shortcut_sequence_with_settings_override() -> None:
    """La séquence effective doit refléter une surcharge de SettingsService si présente."""

    class DummySettings:
        def get_shortcut_override(self, sc_id: str) -> str | None:
            if sc_id == ShortcutId.APP_COMMAND_PALETTE.value:
                return "Ctrl+Alt+K"
            return None

    settings = DummySettings()
    seq = get_shortcut_sequence(ShortcutId.APP_COMMAND_PALETTE, settings_service=settings)
    assert seq == "Ctrl+Alt+K"

    # Sans surcharge, on a la valeur par défaut
    seq_settings = get_shortcut_sequence(ShortcutId.APP_SETTINGS, settings_service=settings)
    assert seq_settings == "Ctrl+,"


def test_validate_catalog_rejects_reserved_sequence() -> None:
    """validate_catalog doit lever ValueError si une séquence réservée est présente."""
    bad_catalog = {
        ShortcutId.APP_SAVE: ShortcutDefinition(
            id=ShortcutId.APP_SAVE,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+C",  # Réservée !
            title_getter=lambda: "Sauvegarder",
        )
    }
    with pytest.raises(ValueError, match="séquence réservée"):
        validate_catalog(bad_catalog)


def test_validate_catalog_rejects_scope_collision() -> None:
    """validate_catalog doit lever ValueError en cas de collision dans la même portée."""
    bad_catalog = {
        ShortcutId.APP_SAVE: ShortcutDefinition(
            id=ShortcutId.APP_SAVE,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+S",
            title_getter=lambda: "Sauvegarder",
        ),
        ShortcutId.APP_RUN_PRIMARY: ShortcutDefinition(
            id=ShortcutId.APP_RUN_PRIMARY,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+S",  # Collision avec APP_SAVE !
            title_getter=lambda: "Exécuter",
        ),
    }
    with pytest.raises(ValueError, match="Collision de séquence"):
        validate_catalog(bad_catalog)


def test_edition_shortcuts_catalog_integrity() -> None:
    """Vérifie que tous les raccourcis d'Édition & Navigateur sont enregistrés et valides."""
    expected_ids = [
        ShortcutId.EDITION_MOVE_TO_DECK,
        ShortcutId.EDITION_NEW_DECK,
        ShortcutId.EDITION_DESELECT_ALL,
        ShortcutId.EDITION_EDIT_NOTE,
        ShortcutId.EDITION_EDIT_NOTE_BARE,
        ShortcutId.EDITION_CHANGE_MODEL,
        ShortcutId.EDITION_TOGGLE_DISPLAY_MODE,
        ShortcutId.EDITION_FIND_REPLACE,
        ShortcutId.EDITION_DELETE,
        ShortcutId.EDITION_SUSPEND,
        ShortcutId.EDITION_SUSPEND_BARE,
        ShortcutId.EDITION_GROUP_EDIT,
        ShortcutId.EDITION_TOGGLE_PREVIEW,
        ShortcutId.EDITION_TOGGLE_TABLE,
        ShortcutId.EDITION_PREV_CARD,
        ShortcutId.EDITION_NEXT_CARD,
        ShortcutId.EDITION_FORMAT_BOLD,
        ShortcutId.EDITION_FORMAT_ITALIC,
        ShortcutId.EDITION_FORMAT_UNDERLINE,
        ShortcutId.EDITION_FORMAT_CLOZE,
        ShortcutId.EDITION_FORMAT_MATH,
        ShortcutId.VIEW_HISTORY,
    ]
    # Drapeaux 0 à 7
    for f in range(8):
        expected_ids.append(getattr(ShortcutId, f"EDITION_FLAG_{f}"))

    catalog = SHORTCUT_CATALOG
    for sc_id in expected_ids:
        assert sc_id in catalog, f"Raccourci manquant au catalogue : {sc_id}"
        defn = catalog[sc_id]
        assert defn.category == ShortcutCategory.EDITION or (sc_id == ShortcutId.VIEW_HISTORY and defn.category == ShortcutCategory.APPLICATION)
        assert len(defn.default_sequence) > 0
        assert len(defn.title) > 0

    # Vérifications des spécificités d'Édition
    assert catalog[ShortcutId.EDITION_MOVE_TO_DECK].default_sequence == "Ctrl+D"
    assert catalog[ShortcutId.EDITION_GROUP_EDIT].default_sequence == "Ctrl+Shift+E"
    assert catalog[ShortcutId.EDITION_SUSPEND_BARE].default_sequence == "!"
    assert catalog[ShortcutId.EDITION_SUSPEND_BARE].scope == ShortcutScope.WIDGET
    assert catalog[ShortcutId.EDITION_SUSPEND_BARE].allow_bare_key is True

    assert catalog[ShortcutId.EDITION_EDIT_NOTE_BARE].default_sequence == "E"
    assert catalog[ShortcutId.EDITION_EDIT_NOTE_BARE].scope == ShortcutScope.WIDGET
    assert catalog[ShortcutId.EDITION_EDIT_NOTE_BARE].allow_bare_key is True

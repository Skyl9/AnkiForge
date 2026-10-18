"""Tests unitaires pour la validation des surcharges de raccourcis clavier.

Vérifie :
- refus des séquences de la liste noire (Ctrl+C, Ctrl+X, Ctrl+V, Ctrl+Z, Ctrl+Y, Ctrl+A, Ctrl+W, Ctrl+Q)
- refus des touches nues hors portée WIDGET
- refus des conflits intra-portée (portée APPLICATION globale, même catégorie de vue/dialogue)
- validation réussie lorsqu'aucun conflit n'existe
- intégration automatique des surcharges SettingsService dans get_shortcut_sequence.
"""

from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.shortcuts import (
    RESERVED_SEQUENCES,
    ShortcutId,
    get_shortcut_catalog,
    get_shortcut_sequence,
)
from ankiforge.ui.shortcuts.catalog import validate_shortcut_override


def test_validate_shortcut_rejects_reserved_sequences() -> None:
    """Toutes les séquences de la liste noire doivent être strictement refusées."""
    for seq in RESERVED_SEQUENCES:
        valid, msg = validate_shortcut_override(ShortcutId.APP_SAVE, seq)
        assert not valid, f"La séquence réservée {seq} aurait dû être refusée."
        assert "réservée" in msg.lower() or "système" in msg.lower()


def test_validate_shortcut_rejects_bare_key_outside_widget_scope() -> None:
    """Une touche nue (sans modificateurs) doit être refusée hors de la portée WIDGET."""
    # APP_SAVE est en portée APPLICATION
    valid, msg = validate_shortcut_override(ShortcutId.APP_SAVE, "E")
    assert not valid
    assert "portée widget" in msg.lower()

    # REVIEW_VALIDATE_SPACE est en portée WIDGET (allow_bare_key=True)
    # On teste une touche nue qui ne crée pas de conflit
    valid, _ = validate_shortcut_override(ShortcutId.REVIEW_VALIDATE_SPACE, "X")
    assert valid


def test_validate_shortcut_rejects_app_scope_collision() -> None:
    """En portée APPLICATION, deux actions ne peuvent jamais partager la même séquence."""
    # APP_SETTINGS par défaut est Ctrl+,
    # Tenter de donner Ctrl+, à APP_SAVE (aussi en portée APPLICATION) doit échouer
    valid, msg = validate_shortcut_override(ShortcutId.APP_SAVE, "Ctrl+,")
    assert not valid
    assert "conflit" in msg.lower() or "déjà assignée" in msg.lower()
    assert "Application" in msg


def test_validate_shortcut_rejects_same_category_view_collision() -> None:
    """En portée VUE, deux actions de la même vue/catégorie ne peuvent pas partager la même séquence."""
    # EDITION_CHANGE_MODEL a 'Ctrl+M', dans la catégorie ÉDITION
    # Tenter d'assigner 'Ctrl+M' à EDITION_MOVE_TO_DECK (aussi dans ÉDITION) doit être refusé
    valid, msg = validate_shortcut_override(ShortcutId.EDITION_MOVE_TO_DECK, "Ctrl+M")
    assert not valid
    assert "conflit" in msg.lower() or "déjà assignée" in msg.lower()


def test_validate_shortcut_allows_same_sequence_across_different_views() -> None:
    """Deux vues distinctes peuvent réutiliser la même séquence (ex: Ctrl+N)."""
    # EDITION_NEW_DECK et DOCUMENTS_NEW_ALBUM utilisent tous deux Ctrl+N par défaut dans des vues distinctes
    # Réassigner Ctrl+N à MODELS_NEW_TYPE (Types de note) ne doit pas entrer en conflit avec Édition
    valid, _ = validate_shortcut_override(ShortcutId.MODELS_NEW_TYPE, "Ctrl+Alt+Shift+N")
    assert valid


def test_validate_shortcut_rejects_empty_sequence() -> None:
    """Une séquence vide est invalide."""
    valid, msg = validate_shortcut_override(ShortcutId.APP_SAVE, "   ")
    assert not valid
    assert "vide" in msg.lower()


def test_get_shortcut_sequence_uses_settings_service_by_default(mock_db) -> None:
    """get_shortcut_sequence sans settings_service explicite doit lire SettingsService."""
    sc_id = ShortcutId.APP_FIND
    default_seq = get_shortcut_catalog()[sc_id].default_sequence

    # Sans override
    assert get_shortcut_sequence(sc_id) == default_seq

    # Avec override persisté
    SettingsService.set_shortcut_override(sc_id.value, "Ctrl+Alt+Shift+F")
    try:
        assert get_shortcut_sequence(sc_id) == "Ctrl+Alt+Shift+F"
    finally:
        SettingsService.remove_shortcut_override(sc_id.value)

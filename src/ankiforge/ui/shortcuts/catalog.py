"""Catalogue central déclaratif des raccourcis clavier d'AnkiForge.

Unique source de vérité pour tous les bindings, libellés et documentations.
Conforme à l'ADR 0013 (zéro tr() à l'import, résolution paresseuse) et à l'ADR 0032.
"""

from typing import Any

from ankiforge.ui.shortcuts.models import (
    ShortcutCategory,
    ShortcutDefinition,
    ShortcutId,
    ShortcutScope,
    is_reserved_sequence,
)
from ankiforge.utils.i18n import tr


def build_shortcut_catalog() -> dict[ShortcutId, ShortcutDefinition]:
    """Construit et retourne le catalogue exhaustif déclaratif des raccourcis.

    Encapsulé dans une fonction pour garantir zéro évaluation de tr() au chargement du module.
    """
    return {
        # Actions d'application
        ShortcutId.APP_COMMAND_PALETTE: ShortcutDefinition(
            id=ShortcutId.APP_COMMAND_PALETTE,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+K",
            title_getter=lambda: tr("Palette de commandes"),
            description_getter=lambda: tr("Ouvre la palette de commandes globale omnibox"),
        ),
        ShortcutId.APP_SETTINGS: ShortcutDefinition(
            id=ShortcutId.APP_SETTINGS,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+,",
            title_getter=lambda: tr("Paramètres"),
            description_getter=lambda: tr("Ouvre la boîte de dialogue des paramètres"),
        ),
        ShortcutId.APP_SAVE: ShortcutDefinition(
            id=ShortcutId.APP_SAVE,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+S",
            title_getter=lambda: tr("Enregistrer"),
            description_getter=lambda: tr("Routeur unique d'enregistrement dans la vue active"),
        ),
        ShortcutId.APP_RUN_PRIMARY: ShortcutDefinition(
            id=ShortcutId.APP_RUN_PRIMARY,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Return",
            title_getter=lambda: tr("Action primaire de la vue"),
            description_getter=lambda: tr("Déclenche l'action principale de la vue active (génération, exécution)"),
        ),
        ShortcutId.APP_FIND: ShortcutDefinition(
            id=ShortcutId.APP_FIND,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+F",
            title_getter=lambda: tr("Rechercher"),
            description_getter=lambda: tr("Active le champ de recherche de la vue active"),
        ),
        ShortcutId.APP_IMPORT: ShortcutDefinition(
            id=ShortcutId.APP_IMPORT,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Shift+I",
            title_getter=lambda: tr("Importer un paquet Anki (.apkg)"),
            description_getter=lambda: tr("Ouvre l'assistant d'importation de collection ou de paquet"),
        ),
        ShortcutId.APP_EXPORT: ShortcutDefinition(
            id=ShortcutId.APP_EXPORT,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Alt+E",
            title_getter=lambda: tr("Exporter des cartes Anki (.apkg)"),
            description_getter=lambda: tr("Ouvre la boîte de dialogue d'export de cartes"),
        ),
        ShortcutId.APP_TOUR: ShortcutDefinition(
            id=ShortcutId.APP_TOUR,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="F1",
            title_getter=lambda: tr("Visite guidée d'AnkiForge"),
            description_getter=lambda: tr("Lance la visite interactive des fonctionnalités"),
        ),
        ShortcutId.APP_DEBUG_SCREENSHOT: ShortcutDefinition(
            id=ShortcutId.APP_DEBUG_SCREENSHOT,
            category=ShortcutCategory.OUTILLAGE,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+F12",
            title_getter=lambda: tr("Capture d'écran debug"),
            description_getter=lambda: tr("Enregistre un instantané de l'interface pour diagnostic"),
        ),
        ShortcutId.APP_DEBUG_GALLERY: ShortcutDefinition(
            id=ShortcutId.APP_DEBUG_GALLERY,
            category=ShortcutCategory.OUTILLAGE,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Alt+D",
            title_getter=lambda: tr("Galerie des dialogues (Dev)"),
            description_getter=lambda: tr("Affiche la vitrine des boîtes de dialogue en mode développement"),
        ),
        # Navigation entre les vues
        ShortcutId.NAV_VIEW_1: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_1,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+1",
            title_getter=lambda: tr("Aller à la vue 1"),
        ),
        ShortcutId.NAV_VIEW_2: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_2,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+2",
            title_getter=lambda: tr("Aller à la vue 2"),
        ),
        ShortcutId.NAV_VIEW_3: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_3,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+3",
            title_getter=lambda: tr("Aller à la vue 3"),
        ),
        ShortcutId.NAV_VIEW_4: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_4,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+4",
            title_getter=lambda: tr("Aller à la vue 4"),
        ),
        ShortcutId.NAV_VIEW_5: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_5,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+5",
            title_getter=lambda: tr("Aller à la vue 5"),
        ),
        ShortcutId.NAV_VIEW_6: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_6,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+6",
            title_getter=lambda: tr("Aller à la vue 6"),
        ),
        ShortcutId.NAV_VIEW_7: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_7,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+7",
            title_getter=lambda: tr("Aller à la vue 7"),
        ),
        ShortcutId.NAV_VIEW_8: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_8,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+8",
            title_getter=lambda: tr("Aller à la vue 8"),
        ),
        ShortcutId.NAV_VIEW_9: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_9,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+9",
            title_getter=lambda: tr("Aller à la vue 9"),
        ),
        ShortcutId.NAV_NEXT_VIEW: ShortcutDefinition(
            id=ShortcutId.NAV_NEXT_VIEW,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Tab",
            title_getter=lambda: tr("Vue suivante"),
        ),
        ShortcutId.NAV_PREV_VIEW: ShortcutDefinition(
            id=ShortcutId.NAV_PREV_VIEW,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Shift+Tab",
            title_getter=lambda: tr("Vue précédente"),
        ),
    }


_catalog_cache: dict[ShortcutId, ShortcutDefinition] | None = None


def get_shortcut_catalog() -> dict[ShortcutId, ShortcutDefinition]:
    """Renvoie le catalogue central des raccourcis clavier déclaratifs."""
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = build_shortcut_catalog()
    return _catalog_cache


def __getattr__(name: str) -> Any:
    """Accès paresseux à SHORTCUT_CATALOG pour éviter tout appel tr() au chargement de module."""
    if name == "SHORTCUT_CATALOG":
        return get_shortcut_catalog()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def get_shortcut_definition(shortcut_id: ShortcutId) -> ShortcutDefinition:
    """Récupère la définition immuable d'un raccourci dans le catalogue."""
    catalog = get_shortcut_catalog()
    try:
        return catalog[shortcut_id]
    except KeyError:
        raise KeyError(f"Identifiant de raccourci non répertorié au catalogue : {shortcut_id}") from None


def get_shortcut_sequence(shortcut_id: ShortcutId, settings_service: Any = None) -> str:
    """Récupère la séquence effective d'un raccourci (en tenant compte d'une éventuelle surcharge)."""
    if settings_service is not None and hasattr(settings_service, "get_shortcut_override"):
        override = settings_service.get_shortcut_override(shortcut_id.value)
        if isinstance(override, str) and override.strip():
            return override.strip()

    definition = get_shortcut_definition(shortcut_id)
    return definition.default_sequence


def get_shortcut_label(shortcut_id: ShortcutId) -> str:
    """Renvoie le libellé traduit du raccourci."""
    return get_shortcut_definition(shortcut_id).title


def validate_catalog(catalog: dict[ShortcutId, ShortcutDefinition] | None = None) -> None:
    """Valide la cohérence interne du catalogue de raccourcis.

    Vérifie l'absence de séquences réservées, l'unicité des séquences en portée
    APPLICATION et la stricte isolation des touches nues à la portée WIDGET.
    """
    effective_catalog = catalog if catalog is not None else get_shortcut_catalog()
    seen_app_sequences: dict[str, ShortcutId] = {}

    for sc_id, definition in effective_catalog.items():
        seq = definition.default_sequence

        # 1. Vérification liste noire réservée
        if is_reserved_sequence(seq):
            raise ValueError(f"Le raccourci {sc_id} utilise une séquence réservée interdite : '{seq}'")

        # 2. Vérification unicité en portée APPLICATION
        if definition.scope == ShortcutScope.APPLICATION:
            norm_seq = seq.upper()
            if norm_seq in seen_app_sequences:
                existing_id = seen_app_sequences[norm_seq]
                raise ValueError(f"Collision de séquence en portée APPLICATION : '{seq}' est attribuée à '{existing_id}' et '{sc_id}'")
            seen_app_sequences[norm_seq] = sc_id

        # 3. Vérification des touches nues (admises uniquement en portée WIDGET)
        is_bare = definition.allow_bare_key or len(seq) == 1
        if is_bare:
            if definition.scope != ShortcutScope.WIDGET:
                raise ValueError(f"Touche nue '{seq}' interdite pour le raccourci '{sc_id}' : seule la portée WIDGET est autorisée.")
            if not definition.allow_bare_key:
                raise ValueError(f"Touche nue '{seq}' détectée pour '{sc_id}' sans allow_bare_key=True.")

        # 4. Vérification de la validité du libellé (ADR 0013)
        if not callable(definition.title_getter):
            raise ValueError(f"title_getter du raccourci {sc_id} n'est pas un appelable.")
        title = definition.title
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Le titre du raccourci {sc_id} ne renvoie pas une chaîne valide.")

"""Modèles et structures de données du registre déclaratif des raccourcis clavier.

Conforme à l'ADR 0032 et aux conventions d'architecture AnkiForge.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum


class ShortcutScope(IntEnum):
    """Portée hiérarchique d'un raccourci clavier.

    Ordre de priorité stricte : DIALOGUE > WIDGET > VUE > APPLICATION.
    À résolution égale, la portée la plus spécifique gagne.
    """

    APPLICATION = 1
    VUE = 2
    WIDGET = 3
    DIALOGUE = 4


class ShortcutCategory(StrEnum):
    """Catégories organisationnelles des raccourcis."""

    APPLICATION = "Application"
    NAVIGATION = "Navigation"
    EDITION = "Édition"
    STUDIO = "Studio & Batch"
    DOCUMENTS = "Documents"
    PIPELINES = "Pipelines & Agents"
    OUTILLAGE = "Outillage & Debug"
    DIALOGUE = "Dialogues"


class ShortcutId(StrEnum):
    """Identifiants uniques déclaratifs des actions clavier."""

    # Application & Globaux
    APP_COMMAND_PALETTE = "app.command_palette"
    APP_SETTINGS = "app.settings"
    APP_SAVE = "app.save"
    APP_RUN_PRIMARY = "app.run_primary"
    APP_FIND = "app.find"
    APP_IMPORT = "app.import"
    APP_EXPORT = "app.export"
    APP_TOUR = "app.tour"
    APP_DEBUG_SCREENSHOT = "app.debug_screenshot"
    APP_DEBUG_GALLERY = "app.debug_gallery"

    # Navigation entre vues
    NAV_VIEW_1 = "nav.view_1"
    NAV_VIEW_2 = "nav.view_2"
    NAV_VIEW_3 = "nav.view_3"
    NAV_VIEW_4 = "nav.view_4"
    NAV_VIEW_5 = "nav.view_5"
    NAV_VIEW_6 = "nav.view_6"
    NAV_VIEW_7 = "nav.view_7"
    NAV_VIEW_8 = "nav.view_8"
    NAV_VIEW_9 = "nav.view_9"
    NAV_NEXT_VIEW = "nav.next_view"
    NAV_PREV_VIEW = "nav.prev_view"

    # Invariants transverses (spécification épic T1-T8)
    VIEW_NEW = "view.new"
    VIEW_DUPLICATE = "view.duplicate"
    VIEW_DELETE = "view.delete"
    VIEW_HISTORY = "view.history"
    VIEW_EXPORT = "view.export"
    VIEW_IMPORT = "view.import"
    VIEW_SCOPE = "view.scope"
    VIEW_SIDEBAR = "view.sidebar"
    VIEW_INSPECTOR = "view.inspector"

    # Édition & Navigateur (T2)
    EDITION_MOVE_TO_DECK = "edition.move_to_deck"
    EDITION_NEW_DECK = "edition.new_deck"
    EDITION_DESELECT_ALL = "edition.deselect_all"
    EDITION_EDIT_NOTE = "edition.edit_note"
    EDITION_EDIT_NOTE_BARE = "edition.edit_note_bare"
    EDITION_CHANGE_MODEL = "edition.change_model"
    EDITION_TOGGLE_DISPLAY_MODE = "edition.toggle_display_mode"
    EDITION_FIND_REPLACE = "edition.find_replace"
    EDITION_DELETE = "edition.delete"
    EDITION_SUSPEND = "edition.suspend"
    EDITION_SUSPEND_BARE = "edition.suspend_bare"
    EDITION_GROUP_EDIT = "edition.group_edit"
    EDITION_TOGGLE_PREVIEW = "edition.toggle_preview"
    EDITION_TOGGLE_TABLE = "edition.toggle_table"
    EDITION_PREV_CARD = "edition.prev_card"
    EDITION_NEXT_CARD = "edition.next_card"
    EDITION_FLAG_0 = "edition.flag_0"
    EDITION_FLAG_1 = "edition.flag_1"
    EDITION_FLAG_2 = "edition.flag_2"
    EDITION_FLAG_3 = "edition.flag_3"
    EDITION_FLAG_4 = "edition.flag_4"
    EDITION_FLAG_5 = "edition.flag_5"
    EDITION_FLAG_6 = "edition.flag_6"
    EDITION_FLAG_7 = "edition.flag_7"
    EDITION_FORMAT_BOLD = "edition.format_bold"
    EDITION_FORMAT_ITALIC = "edition.format_italic"
    EDITION_FORMAT_UNDERLINE = "edition.format_underline"
    EDITION_FORMAT_CLOZE = "edition.format_cloze"
    EDITION_FORMAT_MATH = "edition.format_math"


#: Séquences protégées (liste noire non remappable protégeant la saisie de texte et l'OS).
RESERVED_SEQUENCES: frozenset[str] = frozenset(
    {
        "Ctrl+C",
        "Ctrl+X",
        "Ctrl+V",
        "Ctrl+Z",
        "Ctrl+Y",
        "Ctrl+A",
        "Ctrl+W",
        "Ctrl+Q",
    }
)


def normalize_sequence_text(sequence: str) -> str:
    """Normalise une chaîne de séquence pour comparaison insensible à la casse."""
    return sequence.strip()


def is_reserved_sequence(sequence: str) -> bool:
    """Indique si une séquence de touches appartient à la liste noire réservée."""
    norm = normalize_sequence_text(sequence).upper()
    return any(norm == reserved.upper() for reserved in RESERVED_SEQUENCES)


@dataclass(frozen=True)
class ShortcutDefinition:
    """Définition immuable d'un raccourci déclaratif dans le catalogue.

    Conformément à l'ADR 0013, le libellé (title) et la description optionnelle
    sont fournis via des fonctions résolues paresseusement à l'appel.
    """

    id: ShortcutId
    category: ShortcutCategory
    scope: ShortcutScope
    default_sequence: str
    title_getter: Callable[[], str]
    description_getter: Callable[[], str] | None = None
    allow_bare_key: bool = False
    is_configurable: bool = True

    @property
    def title(self) -> str:
        """Libellé traduit à la demande."""
        return self.title_getter()

    @property
    def description(self) -> str:
        """Description optionnelle traduite à la demande."""
        return self.description_getter() if self.description_getter is not None else ""

"""Catalogue canonique des types de note d'usine d'AnkiForge.

Un profil vierge ne reçoit qu'un unique modèle « Basique » (ADR 0037). Les modèles
spécialisés (`Texte à trous (Cloze)`, `Image Occlusion Enhanced`) ne sont plus injectés
d'office : ils sont installables à la demande via le Starter Pack, ou créés
automatiquement au premier usage (dialogue d'occlusion, par exemple).

Ce module est volontairement indépendant de la couche ORM à l'import (import différé de
`NoteTypeModel` dans `seed_default_note_types`) : il peut donc être consommé par le seed
d'amorçage comme par les services de cartes sans introduire de cycle d'import.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

BASIC_NOTE_TYPE_NAME = "Basique"
CLOZE_NOTE_TYPE_NAME = "Texte à trous (Cloze)"

#: Noms canoniques du modèle basique selon la langue de la collection Anki.
BASIC_NOTE_TYPE_ALIASES: frozenset[str] = frozenset({"basique", "basic"})

_STANDARD_CARD_CSS = (
    ".card {\n"
    "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;\n"
    "  font-size: 18px;\n"
    "  text-align: center;\n"
    "  color: #1e293b;\n"
    "  background-color: #ffffff;\n"
    "}"
)

_CLOZE_CARD_CSS = _STANDARD_CARD_CSS + "\n.cloze {\n  font-weight: bold;\n  color: #3b82f6;\n}"


def is_basic_note_type_name(name: str) -> bool:
    """Indique si un nom de modèle désigne le modèle basique (français ou anglais)."""
    return name.strip().casefold() in BASIC_NOTE_TYPE_ALIASES


def basic_note_type_definition() -> dict[str, Any]:
    """Retourne la définition canonique du modèle basique d'usine (sans `anki_id`)."""
    return {
        "name": BASIC_NOTE_TYPE_NAME,
        "description": "Questions directes, définitions conceptuelles, relations de cause à effet simples. Format Q/R standard.",
        "fields_schema": ["Recto", "Verso"],
        "templates": [
            {
                "name": "Carte 1",
                "qfmt": "{{Recto}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Verso}}",
            }
        ],
        "css_style": _STANDARD_CARD_CSS,
    }


def cloze_note_type_definition() -> dict[str, Any]:
    """Retourne la définition canonique du modèle « Texte à trous (Cloze) »."""
    return {
        "name": CLOZE_NOTE_TYPE_NAME,
        "description": "Phrases denses, citations, listes ordonnées et dates clés. Utilise la syntaxe {{c1::mot}} pour masquer l'information clé dans le champ Texte.",
        "fields_schema": ["Texte", "Remarques extra"],
        "templates": [
            {
                "name": "Texte à trous",
                "qfmt": "{{cloze:Texte}}",
                "afmt": "{{cloze:Texte}}<br><br><hr id=answer><br>{{Remarques extra}}",
            }
        ],
        "css_style": _CLOZE_CARD_CSS,
    }


def cloze_starter_pack_entry() -> dict[str, Any]:
    """Retourne l'entrée Starter Pack permettant d'activer le modèle Cloze à la demande."""
    definition = cloze_note_type_definition()
    return {
        "id": "cloze",
        "name": definition["name"],
        "category": "Mémorisation",
        "author": "AnkiForge",
        "version": "1.0.0",
        "description": definition["description"],
        "fields_schema": definition["fields_schema"],
        "templates": definition["templates"],
        "css_style": definition["css_style"],
        "demo_cards": [
            {
                "Texte": "La mitochondrie produit l'ATP par {{c1::phosphorylation oxydative}}.",
                "Remarques extra": "Bioénergétique cellulaire",
            }
        ],
    }


def seed_default_note_types() -> None:
    """Crée le modèle basique d'usine s'il est absent (idempotent).

    L'idempotence couvre les deux noms canoniques (`Basique` et `Basic`) : une fois le
    seed adopté par un premier import Anki, il n'est pas recréé au démarrage suivant.

    Le modèle est créé sans `anki_id` afin qu'un premier import Anki puisse adopter
    silencieusement son identité (nom, champs, gabarits, CSS) au lieu de dupliquer
    un modèle `(Importé)`.
    """
    from ankiforge.database.models import NoteTypeModel

    existing_names = {str(row.name).strip().casefold() for row in NoteTypeModel.select(NoteTypeModel.name)}
    if existing_names & BASIC_NOTE_TYPE_ALIASES:
        return

    definition = basic_note_type_definition()
    NoteTypeModel.create(
        name=str(definition["name"]),
        description=str(definition["description"]),
        fields_schema=json.dumps(definition["fields_schema"], ensure_ascii=False),
        templates=json.dumps(definition["templates"], ensure_ascii=False),
        css_style=str(definition["css_style"]),
    )
    logger.info("Modèle basique d'usine '%s' créé (profil vierge).", definition["name"])

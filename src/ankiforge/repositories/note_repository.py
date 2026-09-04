"""
Repository for Note, Card, NoteType, and Version models.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.repositories.base import BaseRepository
from ankiforge.ui.theme import DesignTokens

logger = logging.getLogger(__name__)


class NoteRepository(BaseRepository):
    """Data access repository for notes, cards, and note types."""

    def get_note_by_id(self, note_id: int) -> NoteModel | None:
        """Retrieve a note by its primary key ID."""
        try:
            return NoteModel.get_or_none(NoteModel.id == note_id)
        except Exception as e:
            logger.error("Failed to retrieve note %s: %s", note_id, e)
            return None

    def get_note_by_guid(self, guid: str) -> NoteModel | None:
        """Retrieve a note by its GUID."""
        try:
            return NoteModel.get_or_none(NoteModel.guid == guid)
        except Exception as e:
            logger.error("Failed to retrieve note by guid %s: %s", guid, e)
            return None

    def get_all_notes(self, limit: int | None = None, offset: int = 0) -> list[NoteModel]:
        """Retrieve all notes, ordered by ID."""
        query = NoteModel.select().order_by(NoteModel.id.asc())
        if limit is not None:
            query = query.limit(limit).offset(offset)
        return list(query)

    def get_notes_by_deck(self, deck_id: int) -> list[NoteModel]:
        """Retrieve all notes containing cards placed in a specific deck."""
        return list(NoteModel.select().join(CardModel).where(CardModel.deck == deck_id).distinct().order_by(NoteModel.id.asc()))

    def get_notes_by_model(self, model_id: int) -> list[NoteModel]:
        """Retrieve notes associated with a specific NoteTypeModel."""
        return list(NoteModel.select().where(NoteModel.note_type == model_id).order_by(NoteModel.id.asc()))

    def get_all_note_types(self) -> list[NoteTypeModel]:
        """Retrieve all note types (card templates)."""
        return list(NoteTypeModel.select().order_by(NoteTypeModel.name.asc()))

    def get_note_type_by_id(self, model_id: int) -> NoteTypeModel | None:
        """Retrieve a note type by ID."""
        try:
            return NoteTypeModel.get_or_none(NoteTypeModel.id == model_id)
        except Exception as e:
            logger.error("Failed to get note type %s: %s", model_id, e)
            return None

    def get_note_type_by_name(self, name: str) -> NoteTypeModel | None:
        """Retrieve a note type by its name."""
        try:
            return NoteTypeModel.get_or_none(NoteTypeModel.name == name)
        except Exception as e:
            logger.error("Failed to get note type by name %s: %s", name, e)
            return None

    def create_note_type(
        self,
        name: str,
        fields_schema: list[str] | str,
        templates: list[dict[str, Any]] | str,
        css_style: str = "",
        description: str = "",
    ) -> NoteTypeModel:
        """Create a new note type."""
        fields_str = json.dumps(fields_schema) if isinstance(fields_schema, list) else fields_schema
        templates_str = json.dumps(templates) if isinstance(templates, list) else templates

        return NoteTypeModel.create(
            name=name,
            fields_schema=fields_str,
            templates=templates_str,
            css_style=css_style,
            description=description,
        )

    def create_note(
        self,
        note_type: NoteTypeModel,
        deck: DeckModel,
        fields_data: dict[str, str],
        tags: list[str] | None = None,
        status: str = "new",
        source: str = "ai",
    ) -> NoteModel:
        """Create a note, its initial active version, and the corresponding card."""
        tags_str = " ".join(tags) if tags else ""

        with self.atomic():
            note = NoteModel.create(
                note_type=note_type,
                tags=tags_str,
                status=status,
            )
            NoteVersionModel.create(
                note=note,
                version_number=1,
                content=json.dumps(fields_data, ensure_ascii=False),
                source=source,
                is_active=True,
            )
            CardModel.create(
                note=note,
                deck=deck,
                template_index=0,
            )
            return note

    def update_note_content(
        self,
        note_id: int,
        fields_data: dict[str, str],
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> NoteModel | None:
        """Create a new version for the note and optionally update tags."""
        note = self.get_note_by_id(note_id)
        if not note:
            return None

        with self.atomic():
            if tags is not None:
                note.tags = " ".join(tags)
                note.save()

            note.add_version(fields_data, source=source)
            return note

    def update_note_tags(self, note_id: int, tags: list[str]) -> bool:
        """Update tags for a note."""
        note = self.get_note_by_id(note_id)
        if not note:
            return False
        note.tags = " ".join(tags)
        note.save()
        return True

    def delete_note(self, note_id: int) -> bool:
        """Delete a note and its associated cards and versions."""
        note = self.get_note_by_id(note_id)
        if not note:
            return False
        with self.atomic():
            note.delete_instance(recursive=True)
            return True

    def get_active_version(self, note: NoteModel) -> NoteVersionModel | None:
        """Retrieve the currently active version of a note."""
        return NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712

    def get_versions(self, note: NoteModel) -> list[NoteVersionModel]:
        """Retrieve all versions of a note ordered descending."""
        return list(NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()))

    def get_cards_by_note(self, note_id: int) -> list[CardModel]:
        """Retrieve all cards belonging to a specific note."""
        return list(CardModel.select().where(CardModel.note == note_id))

    def get_cards_by_deck(self, deck_id: int) -> list[CardModel]:
        """Retrieve all cards belonging to a specific deck."""
        return list(CardModel.select().where(CardModel.deck == deck_id))

    def count_notes(self) -> int:
        """Count total notes in database."""
        return int(NoteModel.select().count())

    def count_cards(self) -> int:
        """Count total cards in database."""
        return int(CardModel.select().count())

    def set_card_flag(self, card_id: int, flag: int) -> bool:
        """Déclare ou modifie le drapeau (0..7) d'une carte individuelle."""
        try:
            flag_val = max(0, min(7, int(flag)))
            with self.atomic():
                updated = CardModel.update(flags=flag_val).where(CardModel.id == card_id).execute()
                return bool(updated > 0)
        except Exception as e:
            logger.error("Erreur lors de la modification du drapeau de la carte %s: %s", card_id, e)
            return False

    def set_note_flag(self, note_id: int, flag: int) -> bool:
        """Assigne un drapeau (0..7) à toutes les cartes associées à une note."""
        try:
            flag_val = max(0, min(7, int(flag)))
            with self.atomic():
                updated = CardModel.update(flags=flag_val).where(CardModel.note_id == note_id).execute()
                return bool(updated > 0)
        except Exception as e:
            logger.error("Erreur lors de la modification du drapeau pour la note %s: %s", note_id, e)
            return False

    def get_note_flag(self, note_id: int) -> int:
        """Récupère le drapeau maximal parmi les cartes associées à une note (0 si aucun)."""
        try:
            cards = list(CardModel.select(CardModel.flags).where(CardModel.note_id == note_id))
            if not cards:
                return 0
            return max(int(getattr(c, "flags", 0) or 0) for c in cards)
        except Exception as e:
            logger.debug("Erreur récupération drapeau note %s: %s", note_id, e)
            return 0

    def search_notes(self, query: str, limit: int = 50) -> list[NoteModel]:
        """Recherche les notes correspondant à une requête texte et/ou syntaxe de drapeau Anki."""
        raw_query = query.strip()
        if not raw_query:
            return self.get_all_notes(limit=limit)

        flag_filter: int | None = None
        invert_flag: bool = False

        # Détection de la syntaxe Anki flag:X ou -flag:X
        flag_match = re.search(r"(-?)flag:(\w+)", raw_query, flags=re.IGNORECASE)
        if flag_match:
            neg, val_str = flag_match.group(1), flag_match.group(2).lower()
            invert_flag = bool(neg)
            if val_str in DesignTokens.FLAG_SEARCH_MAP:
                flag_filter = DesignTokens.FLAG_SEARCH_MAP[val_str]
            # Épuration du token flag de la requête textuelle
            raw_query = re.sub(r"(-?)flag:\w+", "", raw_query, flags=re.IGNORECASE).strip()

        db_query = NoteModel.select().distinct()

        # Filtrage par drapeau
        if flag_filter is not None:
            if flag_filter == 0:
                if invert_flag:
                    # -flag:0 => cartes ayant au moins un drapeau actif (> 0)
                    flagged_nids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.flags > 0)]
                    db_query = db_query.where(NoteModel.id.in_(flagged_nids))
                else:
                    # flag:0 => cartes sans aucun drapeau (flags == 0 ou sans drapeaux > 0)
                    flagged_nids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.flags > 0)]
                    db_query = db_query.where(NoteModel.id.not_in(flagged_nids))
            else:
                if invert_flag:
                    matched_nids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.flags == flag_filter)]
                    db_query = db_query.where(NoteModel.id.not_in(matched_nids))
                else:
                    matched_nids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.flags == flag_filter)]
                    db_query = db_query.where(NoteModel.id.in_(matched_nids))

        # Filtrage textuel résiduel sur le contenu ou les tags
        if raw_query:
            db_query = db_query.join(NoteVersionModel).where(
                NoteVersionModel.is_active & (NoteVersionModel.content.contains(raw_query) | (NoteModel.tags.is_null(False) & NoteModel.tags.contains(raw_query)))
            )

        return list(db_query.order_by(NoteModel.id.asc()).limit(limit))

    def get_all_tags(self) -> list[str]:
        """Extract all unique tags from notes."""
        tags_set: set[str] = set()
        for note in NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False)):
            if note.tags:
                for t in note.tags.split():
                    clean = t.strip()
                    if clean:
                        tags_set.add(clean)
        return sorted(tags_set)

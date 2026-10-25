"""Dépôt des modèles Note, Card, NoteType et Version."""

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
from ankiforge.services.cards.flag_service import FlagService
from ankiforge.services.search.fts_service import FTSService
from ankiforge.utils.hierarchy import descendants_prefix
from ankiforge.utils.tags import parse_note_tags, serialize_note_tags

logger = logging.getLogger(__name__)


class NoteRepository(BaseRepository):
    """Dépôt d'accès aux données des notes, des cartes et des types de note."""

    def get_note_by_id(self, note_id: int) -> NoteModel | None:
        """Retourne une note par sa clé primaire."""
        try:
            return NoteModel.get_or_none(NoteModel.id == note_id)
        except Exception as e:
            logger.error("Failed to retrieve note %s: %s", note_id, e)
            return None

    def get_note_by_guid(self, guid: str) -> NoteModel | None:
        """Retourne une note par son GUID."""
        try:
            return NoteModel.get_or_none(NoteModel.guid == guid)
        except Exception as e:
            logger.error("Failed to retrieve note by guid %s: %s", guid, e)
            return None

    def get_all_notes(self, limit: int | None = None, offset: int = 0) -> list[NoteModel]:
        """Retourne toutes les notes, triées par ID."""
        query = NoteModel.select().order_by(NoteModel.id.asc())
        if limit is not None:
            query = query.limit(limit).offset(offset)
        return list(query)

    def get_notes_by_deck(self, deck_id: int) -> list[NoteModel]:
        """Retourne toutes les notes contenant des cartes placées dans un paquet donné."""
        return list(NoteModel.select().join(CardModel).where(CardModel.deck == deck_id).distinct().order_by(NoteModel.id.asc()))

    def get_notes_by_model(self, model_id: int) -> list[NoteModel]:
        """Retourne les notes associées à un NoteTypeModel donné."""
        return list(NoteModel.select().where(NoteModel.note_type == model_id).order_by(NoteModel.id.asc()))

    def get_all_note_types(self) -> list[NoteTypeModel]:
        """Retourne tous les types de note (modèles de cartes)."""
        return list(NoteTypeModel.select().order_by(NoteTypeModel.name.asc()))

    def get_note_type_by_id(self, model_id: int) -> NoteTypeModel | None:
        """Retourne un type de note par son ID."""
        try:
            return NoteTypeModel.get_or_none(NoteTypeModel.id == model_id)
        except Exception as e:
            logger.error("Failed to get note type %s: %s", model_id, e)
            return None

    def get_note_type_by_name(self, name: str) -> NoteTypeModel | None:
        """Retourne un type de note par son nom."""
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
        """Crée un nouveau type de note."""
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
        """Crée une note, sa version active initiale et la carte correspondante."""
        tags_str = serialize_note_tags(tags)
        from ankiforge.utils.anki_renderer import compute_sort_field

        sort_field_val = compute_sort_field(fields_data)

        with self.atomic():
            note = NoteModel.create(
                note_type=note_type,
                tags=tags_str,
                status=status,
                sort_field=sort_field_val,
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
            FTSService.sync_note(note.id)
            return note

    def update_note_content(
        self,
        note_id: int,
        fields_data: dict[str, str],
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> NoteModel | None:
        """Crée une nouvelle version de la note et met éventuellement à jour les tags."""
        note = self.get_note_by_id(note_id)
        if not note:
            return None

        with self.atomic():
            if tags is not None:
                note.tags = serialize_note_tags(tags)
                note.save()

            note.add_version(fields_data, source=source)
            FTSService.sync_note(note.id)
            return note

    def update_note_tags(self, note_id: int, tags: list[str]) -> bool:
        """Met à jour les tags d'une note."""
        note = self.get_note_by_id(note_id)
        if not note:
            return False
        with self.atomic():
            note.tags = serialize_note_tags(tags)
            note.save()
            FTSService.sync_note(note.id)
        return True

    def delete_note(self, note_id: int) -> bool:
        """Supprime une note ainsi que ses cartes et versions associées."""
        note = self.get_note_by_id(note_id)
        if not note:
            return False
        with self.atomic():
            FTSService.delete_note(note_id)
            note.delete_instance(recursive=True)
            return True

    def get_active_version(self, note: NoteModel) -> NoteVersionModel | None:
        """Retourne la version actuellement active d'une note."""
        return NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712

    def get_versions(self, note: NoteModel) -> list[NoteVersionModel]:
        """Retourne toutes les versions d'une note, triées par ordre décroissant."""
        return list(NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()))

    def get_cards_by_note(self, note_id: int) -> list[CardModel]:
        """Retourne toutes les cartes appartenant à une note donnée."""
        return list(CardModel.select().where(CardModel.note == note_id))

    def get_cards_by_deck(self, deck_id: int) -> list[CardModel]:
        """Retourne toutes les cartes appartenant à un paquet donné."""
        return list(CardModel.select().where(CardModel.deck == deck_id))

    def count_notes(self) -> int:
        """Compte le nombre total de notes en base de données."""
        return int(NoteModel.select().count())

    def count_cards(self) -> int:
        """Compte le nombre total de cartes en base de données."""
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

    def suspend_card(self, card_id: int, suspend: bool = True) -> bool:
        """Suspend ou réactive une carte individuelle."""
        try:
            with self.atomic():
                updated = CardModel.update(is_suspended=suspend).where(CardModel.id == card_id).execute()
                return bool(updated > 0)
        except Exception as e:
            logger.error("Erreur lors de la modification de l'état suspendu de la carte %s: %s", card_id, e)
            return False

    def suspend_note(self, note_id: int, suspend: bool = True) -> bool:
        """Suspend ou réactive toutes les cartes associées à une note."""
        try:
            with self.atomic():
                updated = CardModel.update(is_suspended=suspend).where(CardModel.note_id == note_id).execute()
                return bool(updated > 0)
        except Exception as e:
            logger.error("Erreur lors de la modification de l'état suspendu pour la note %s: %s", note_id, e)
            return False

    def is_note_suspended(self, note_id: int) -> bool:
        """Vérifie si toutes les cartes de la note sont suspendues (True si au moins une et toutes sont suspendues)."""
        try:
            cards = list(CardModel.select(CardModel.is_suspended).where(CardModel.note_id == note_id))
            if not cards:
                return False
            return all(bool(getattr(c, "is_suspended", False)) for c in cards)
        except Exception as e:
            logger.debug("Erreur récupération état suspendu note %s: %s", note_id, e)
            return False

    def search_notes(self, query: str, limit: int = 50) -> list[NoteModel]:
        """Recherche les notes correspondant à une requête texte, drapeau (flag:X) et/ou suspension (is:suspended)."""
        raw_query = query.strip()
        if not raw_query:
            return self.get_all_notes(limit=limit)

        flag_filter: int | None = None
        invert_flag: bool = False

        # Détection de la syntaxe Anki flag:X ou -flag:X (supporte les guillemets pour les libellés multi-mots)
        flag_match = re.search(r'(-?)flag:(?:"([^"]+)"|(\S+))', raw_query, flags=re.IGNORECASE)
        if flag_match:
            neg = flag_match.group(1)
            val_str = (flag_match.group(2) or flag_match.group(3) or "").lower().strip()
            invert_flag = bool(neg)
            flag_search_map = FlagService.get_flag_search_map()
            flag_filter = flag_search_map.get(val_str, -1)
            # Épuration du token flag de la requête textuelle
            raw_query = re.sub(r'(-?)flag:(?:"[^"]+"|\S+)', "", raw_query, count=1, flags=re.IGNORECASE).strip()

        # Détection de la syntaxe Anki is:suspended ou -is:suspended
        suspended_filter: bool | None = None
        susp_match = re.search(r"(-?)is:suspended", raw_query, flags=re.IGNORECASE)
        if susp_match:
            neg_susp = bool(susp_match.group(1))
            suspended_filter = not neg_susp  # True si is:suspended, False si -is:suspended
            raw_query = re.sub(r"(-?)is:suspended", "", raw_query, flags=re.IGNORECASE).strip()

        db_query = NoteModel.select().distinct()

        # Filtrage par drapeau
        if flag_filter is not None:
            if flag_filter == -1:
                if not invert_flag:
                    return []
            elif flag_filter == 0:
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

        # Filtrage par état suspendu
        if suspended_filter is not None:
            if suspended_filter:
                # is:suspended => notes ayant au moins une carte suspendue
                susp_nids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.is_suspended == True)]  # noqa: E712
                db_query = db_query.where(NoteModel.id.in_(susp_nids))
            else:
                # -is:suspended => notes n'ayant aucune carte suspendue
                susp_nids = [c.note_id for c in CardModel.select(CardModel.note).where(CardModel.is_suspended == True)]  # noqa: E712
                db_query = db_query.where(NoteModel.id.not_in(susp_nids))

        # Filtrage textuel résiduel sur le contenu ou les tags
        if raw_query:
            if FTSService.is_available():
                try:
                    fts_results = FTSService.search(raw_query, limit=max(limit * 4, 150), as_prefix=True)
                    if not fts_results:
                        return []
                    fts_ids = [res.note_id for res in fts_results]
                    db_query = db_query.where(NoteModel.id.in_(fts_ids))
                    notes = list(db_query)
                    notes_map = {n.id: n for n in notes}
                    ordered = [notes_map[nid] for nid in fts_ids if nid in notes_map]
                    return ordered[:limit]
                except Exception as e:
                    logger.warning("Recherche FTS5 échouée, repli vers LIKE: %s", e)
                    db_query = db_query.join(NoteVersionModel).where(
                        NoteVersionModel.is_active & (NoteVersionModel.content.contains(raw_query) | (NoteModel.tags.is_null(False) & NoteModel.tags.contains(raw_query)))
                    )
            else:
                db_query = db_query.join(NoteVersionModel).where(
                    NoteVersionModel.is_active & (NoteVersionModel.content.contains(raw_query) | (NoteModel.tags.is_null(False) & NoteModel.tags.contains(raw_query)))
                )

        return list(db_query.order_by(NoteModel.id.asc()).limit(limit))

    def get_all_tags(self) -> list[str]:
        """Extrait tous les tags uniques des notes."""
        return self.get_tags_for_scope(deck_id=None)

    def get_tags_for_scope(
        self,
        deck_id: int | None = None,
        include_descendants: bool = True,
    ) -> list[str]:
        """Extrait tous les tags uniques pour une portée donnée (paquet et sous-paquets ou collection globale).

        Args:
            deck_id: ID du paquet sélectionné ou None pour toute la collection.
            include_descendants: Si True, inclut les sous-paquets du paquet spécifié.

        Returns:
            Liste triée alphabétiquement de tous les tags uniques normalisés.
        """
        tags_set: set[str] = set()

        if deck_id is not None:
            active_deck = DeckModel.get_or_none(DeckModel.id == deck_id)
            if not active_deck:
                return []

            if include_descendants:
                deck_ids = [d.id for d in DeckModel.select(DeckModel.id).where((DeckModel.id == active_deck.id) | (DeckModel.name.startswith(descendants_prefix(active_deck.name))))]
            else:
                deck_ids = [active_deck.id]

            if not deck_ids:
                return []

            subq = CardModel.select(CardModel.note_id).where(CardModel.deck.in_(deck_ids))
            query = NoteModel.select(NoteModel.tags).where(NoteModel.id.in_(subq) & NoteModel.tags.is_null(False))
            for note in query:
                if note.tags:
                    for t in parse_note_tags(note.tags):
                        tags_set.add(t)
        else:
            query = NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False))
            for note in query:
                if note.tags:
                    for t in parse_note_tags(note.tags):
                        tags_set.add(t)

        return sorted(tags_set)

    def get_tags_with_counts(
        self,
        deck_id: int | None = None,
        include_descendants: bool = True,
    ) -> dict[str, int]:
        """Extrait tous les tags uniques pour une portée donnée avec leur nombre d'occurrences.

        Args:
            deck_id: ID du paquet sélectionné ou None pour toute la collection.
            include_descendants: Si True, inclut les sous-paquets du paquet spécifié.

        Returns:
            Dictionnaire associant chaque tag à son nombre de notes.
        """
        counts: dict[str, int] = {}

        if deck_id is not None:
            active_deck = DeckModel.get_or_none(DeckModel.id == deck_id)
            if not active_deck:
                return {}

            if include_descendants:
                deck_ids = [d.id for d in DeckModel.select(DeckModel.id).where((DeckModel.id == active_deck.id) | (DeckModel.name.startswith(descendants_prefix(active_deck.name))))]
            else:
                deck_ids = [active_deck.id]

            if not deck_ids:
                return {}

            subq = CardModel.select(CardModel.note_id).where(CardModel.deck.in_(deck_ids))
            query = NoteModel.select(NoteModel.tags).where(NoteModel.id.in_(subq) & NoteModel.tags.is_null(False))
        else:
            query = NoteModel.select(NoteModel.tags).where(NoteModel.tags.is_null(False))

        for note in query:
            if note.tags:
                for t in parse_note_tags(note.tags):
                    counts[t] = counts.get(t, 0) + 1

        return counts

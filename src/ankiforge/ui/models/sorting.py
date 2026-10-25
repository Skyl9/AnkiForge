"""Moteur de tri multi-critères Peewee pour l'explorateur de notes et la vue d'Édition (ADR 0044).

Fournit les structures typées (SortCriterion, SortDirection, SortOrder) et le constructeur
de requêtes Peewee ordonnées avec clé de départage déterministe (sort_field, id) pour
les modes Notes et Cartes à haute performance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

import peewee

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel

logger = logging.getLogger(__name__)


class SortDirection(StrEnum):
    """Direction de tri pour les requêtes Peewee."""

    ASC = "asc"
    DESC = "desc"

    def toggle(self) -> SortDirection:
        """Bascule entre ascendant et descendant."""
        return SortDirection.DESC if self == SortDirection.ASC else SortDirection.ASC

    @property
    def is_asc(self) -> bool:
        return self == SortDirection.ASC

    @property
    def is_desc(self) -> bool:
        return self == SortDirection.DESC


class SortCriterion(StrEnum):
    """Critères de tri canoniques supportés par la vue d'Édition."""

    # Dates
    CREATED_AT = "created_at"
    MODIFIED_AT = "modified_at"

    # Contenu textuel
    RECTO = "recto"
    VERSO = "verso"
    SPECIFIC_FIELD = "field"

    # Organisation
    DECK = "deck"
    NOTE_TYPE = "note_type"
    TAGS = "tags"

    # Statuts
    FLAGS = "flags"
    SUSPENDED = "suspended"

    # Métriques SRS / FSRS (Mode Cartes)
    LAPSES = "lapses"
    IVL = "ivl"
    REPS = "reps"
    STABILITY = "stability"
    DIFFICULTY = "difficulty"


@dataclass(frozen=True)
class SortOrder:
    """Configuration immuable d'un ordre de tri."""

    criterion: SortCriterion = SortCriterion.CREATED_AT
    direction: SortDirection = SortDirection.ASC
    field_name: str | None = None

    @classmethod
    def default_for_mode(cls, mode: Literal["notes", "cards"]) -> SortOrder:
        """Retourne l'ordre de tri par défaut pour un mode donné."""
        return cls(criterion=SortCriterion.CREATED_AT, direction=SortDirection.ASC)

    def toggled(self) -> SortOrder:
        """Retourne une configuration avec la direction opposée."""
        return SortOrder(
            criterion=self.criterion,
            direction=self.direction.toggle(),
            field_name=self.field_name,
        )

    def with_criterion(self, criterion: SortCriterion, field_name: str | None = None) -> SortOrder:
        """Retourne une configuration avec un nouveau critère (direction par défaut sémantique)."""
        # Pour les chutes/sangsues ou drapeaux, la direction naturelle de découverte est souvent décroissante
        direction = SortDirection.DESC if criterion in (SortCriterion.LAPSES, SortCriterion.FLAGS) else SortDirection.ASC
        return SortOrder(criterion=criterion, direction=direction, field_name=field_name)

    def to_dict(self) -> dict[str, Any]:
        """Sérialise en dictionnaire compatible JSON / QSettings."""
        return {
            "criterion": self.criterion.value,
            "direction": self.direction.value,
            "field_name": self.field_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SortOrder:
        """Désérialise depuis un dictionnaire."""
        if not data or not isinstance(data, dict):
            return cls()
        raw_crit = str(data.get("criterion", SortCriterion.CREATED_AT.value))
        try:
            criterion = SortCriterion(raw_crit)
        except ValueError:
            criterion = SortCriterion.CREATED_AT

        raw_dir = str(data.get("direction", SortDirection.ASC.value))
        try:
            direction = SortDirection(raw_dir)
        except ValueError:
            direction = SortDirection.ASC

        field_name = data.get("field_name")
        return cls(
            criterion=criterion,
            direction=direction,
            field_name=str(field_name) if field_name else None,
        )


def _has_model_join(query: peewee.Query, model: type[peewee.Model]) -> bool:
    """Vérifie si un modèle a déjà été joint à la requête Peewee."""
    for joins_list in getattr(query, "_joins", {}).values():
        for item in joins_list:
            if item and item[0] == model:
                return True
    return False


def apply_query_sorting(
    query: peewee.Query,
    sort_order: SortOrder,
    display_mode: Literal["notes", "cards"],
) -> peewee.Query:
    """Applique dynamiquement le tri Peewee avec clé de départage déterministe (ADR 0044).

    En mode Notes :
      - Clé secondaire de départage : NoteModel.sort_field.asc()
      - Clé tertiaire de départage : NoteModel.id.desc()
    En mode Cartes :
      - Clé secondaire de départage : NoteModel.sort_field.asc()
      - Clé tertiaire de départage : CardModel.id.desc()

    Args:
        query: Requête Peewee Select sur NoteModel ou CardModel.
        sort_order: Configuration du critère et de la direction.
        display_mode: 'notes' ou 'cards'.

    Returns:
        Requête Peewee enrichie des jointures requises et de la clause ORDER BY.
    """
    if display_mode == "notes":
        return _apply_notes_sorting(query, sort_order)
    return _apply_cards_sorting(query, sort_order)


def _apply_notes_sorting(query: peewee.Query, sort_order: SortOrder) -> peewee.Query:
    """Applique les clauses d'ordonnancement pour les requêtes sur NoteModel."""
    crit = sort_order.criterion
    is_asc = sort_order.direction.is_asc

    primary_clauses: list[Any] = []
    tie_breakers: list[Any] = []

    # 1. Dates
    if crit == SortCriterion.CREATED_AT:
        primary_clauses.append(NoteModel.id.asc() if is_asc else NoteModel.id.desc())
        tie_breakers.append(NoteModel.sort_field.asc())

    elif crit == SortCriterion.MODIFIED_AT:
        if not _has_model_join(query, NoteVersionModel):
            query = query.join(
                NoteVersionModel,
                peewee.JOIN.LEFT_OUTER,
                on=((NoteVersionModel.note == NoteModel.id) & (NoteVersionModel.is_active == True)),  # noqa: E712
            )
        primary_clauses.append(NoteVersionModel.created_at.asc() if is_asc else NoteVersionModel.created_at.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    # 2. Contenu textuel
    elif crit == SortCriterion.RECTO:
        primary_clauses.append(NoteModel.sort_field.asc() if is_asc else NoteModel.sort_field.desc())
        tie_breakers.append(NoteModel.id.desc())

    elif crit == SortCriterion.VERSO:
        if not _has_model_join(query, NoteVersionModel):
            query = query.join(
                NoteVersionModel,
                peewee.JOIN.LEFT_OUTER,
                on=((NoteVersionModel.note == NoteModel.id) & (NoteVersionModel.is_active == True)),  # noqa: E712
            )
        verso_expr = peewee.fn.COALESCE(
            peewee.fn.json_extract(NoteVersionModel.content, "$.Verso"),
            peewee.fn.json_extract(NoteVersionModel.content, "$.Back"),
            "",
        )
        primary_clauses.append(verso_expr.asc() if is_asc else verso_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.SPECIFIC_FIELD:
        field_target = sort_order.field_name or "Front"
        if not _has_model_join(query, NoteVersionModel):
            query = query.join(
                NoteVersionModel,
                peewee.JOIN.LEFT_OUTER,
                on=((NoteVersionModel.note == NoteModel.id) & (NoteVersionModel.is_active == True)),  # noqa: E712
            )
        field_expr = peewee.fn.COALESCE(
            peewee.fn.json_extract(NoteVersionModel.content, f"$.{field_target}"),
            "",
        )
        primary_clauses.append(field_expr.asc() if is_asc else field_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    # 3. Organisation
    elif crit == SortCriterion.DECK:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        if not _has_model_join(query, DeckModel):
            query = query.join(DeckModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.deck == DeckModel.id))
        query = query.group_by(NoteModel.id)
        deck_expr = peewee.fn.MIN(DeckModel.name) if is_asc else peewee.fn.MAX(DeckModel.name)
        primary_clauses.append(deck_expr.asc() if is_asc else deck_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.NOTE_TYPE:
        if not _has_model_join(query, NoteTypeModel):
            query = query.join(NoteTypeModel, peewee.JOIN.LEFT_OUTER, on=(NoteModel.note_type == NoteTypeModel.id))
        primary_clauses.append(NoteTypeModel.name.asc() if is_asc else NoteTypeModel.name.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.TAGS:
        tags_expr = peewee.fn.COALESCE(NoteModel.tags, "")
        primary_clauses.append(tags_expr.asc() if is_asc else tags_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    # 4. Statuts
    elif crit == SortCriterion.FLAGS:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        query = query.group_by(NoteModel.id)
        flag_expr = peewee.fn.COALESCE(peewee.fn.MAX(CardModel.flags), 0)
        primary_clauses.append(flag_expr.asc() if is_asc else flag_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.SUSPENDED:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        query = query.group_by(NoteModel.id)
        susp_expr = peewee.fn.COALESCE(peewee.fn.MIN(CardModel.is_suspended), 0)
        primary_clauses.append(susp_expr.asc() if is_asc else susp_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    # 5. Métriques SRS / FSRS (Agrégées pour la note)
    elif crit == SortCriterion.LAPSES:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        query = query.group_by(NoteModel.id)
        lapses_expr = peewee.fn.COALESCE(peewee.fn.MAX(CardModel.lapses), 0)
        primary_clauses.append(lapses_expr.asc() if is_asc else lapses_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.IVL:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        query = query.group_by(NoteModel.id)
        ivl_expr = peewee.fn.COALESCE(peewee.fn.MAX(CardModel.ivl), 0)
        primary_clauses.append(ivl_expr.asc() if is_asc else ivl_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.REPS:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        query = query.group_by(NoteModel.id)
        reps_expr = peewee.fn.COALESCE(peewee.fn.MAX(CardModel.reps), 0)
        primary_clauses.append(reps_expr.asc() if is_asc else reps_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.STABILITY:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        query = query.group_by(NoteModel.id)
        stab_expr = peewee.fn.COALESCE(peewee.fn.MIN(CardModel.stability), 0.0)
        primary_clauses.append(stab_expr.asc() if is_asc else stab_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    elif crit == SortCriterion.DIFFICULTY:
        if not _has_model_join(query, CardModel):
            query = query.join(CardModel, peewee.JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
        query = query.group_by(NoteModel.id)
        diff_expr = peewee.fn.COALESCE(peewee.fn.MAX(CardModel.difficulty), 0.0)
        primary_clauses.append(diff_expr.asc() if is_asc else diff_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), NoteModel.id.desc()])

    else:
        primary_clauses.append(NoteModel.id.asc() if is_asc else NoteModel.id.desc())
        tie_breakers.append(NoteModel.sort_field.asc())

    all_order_clauses = primary_clauses + tie_breakers
    return query.order_by(*all_order_clauses)


def _apply_cards_sorting(query: peewee.Query, sort_order: SortOrder) -> peewee.Query:
    """Applique les clauses d'ordonnancement pour les requêtes sur CardModel."""
    crit = sort_order.criterion
    is_asc = sort_order.direction.is_asc

    primary_clauses: list[Any] = []
    tie_breakers: list[Any] = []

    # S'assurer que NoteModel est joint car sort_field est la clé secondaire universelle
    if not _has_model_join(query, NoteModel):
        query = query.join(NoteModel, peewee.JOIN.LEFT_OUTER)

    # 1. Dates
    if crit == SortCriterion.CREATED_AT:
        primary_clauses.append(CardModel.id.asc() if is_asc else CardModel.id.desc())
        tie_breakers.append(NoteModel.sort_field.asc())

    elif crit == SortCriterion.MODIFIED_AT:
        if not _has_model_join(query, NoteVersionModel):
            query = (
                query.switch(NoteModel)
                .join(
                    NoteVersionModel,
                    peewee.JOIN.LEFT_OUTER,
                    on=((NoteVersionModel.note == NoteModel.id) & (NoteVersionModel.is_active == True)),  # noqa: E712
                )
                .switch(CardModel)
            )
        primary_clauses.append(NoteVersionModel.created_at.asc() if is_asc else NoteVersionModel.created_at.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    # 2. Contenu textuel
    elif crit == SortCriterion.RECTO:
        primary_clauses.append(NoteModel.sort_field.asc() if is_asc else NoteModel.sort_field.desc())
        tie_breakers.append(CardModel.id.desc())

    elif crit == SortCriterion.VERSO:
        if not _has_model_join(query, NoteVersionModel):
            query = (
                query.switch(NoteModel)
                .join(
                    NoteVersionModel,
                    peewee.JOIN.LEFT_OUTER,
                    on=((NoteVersionModel.note == NoteModel.id) & (NoteVersionModel.is_active == True)),  # noqa: E712
                )
                .switch(CardModel)
            )
        verso_expr = peewee.fn.COALESCE(
            peewee.fn.json_extract(NoteVersionModel.content, "$.Verso"),
            peewee.fn.json_extract(NoteVersionModel.content, "$.Back"),
            "",
        )
        primary_clauses.append(verso_expr.asc() if is_asc else verso_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.SPECIFIC_FIELD:
        field_target = sort_order.field_name or "Front"
        if not _has_model_join(query, NoteVersionModel):
            query = (
                query.switch(NoteModel)
                .join(
                    NoteVersionModel,
                    peewee.JOIN.LEFT_OUTER,
                    on=((NoteVersionModel.note == NoteModel.id) & (NoteVersionModel.is_active == True)),  # noqa: E712
                )
                .switch(CardModel)
            )
        field_expr = peewee.fn.COALESCE(
            peewee.fn.json_extract(NoteVersionModel.content, f"$.{field_target}"),
            "",
        )
        primary_clauses.append(field_expr.asc() if is_asc else field_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    # 3. Organisation
    elif crit == SortCriterion.DECK:
        if not _has_model_join(query, DeckModel):
            query = query.switch(CardModel).join(DeckModel, peewee.JOIN.LEFT_OUTER)
        primary_clauses.append(DeckModel.name.asc() if is_asc else DeckModel.name.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.NOTE_TYPE:
        if not _has_model_join(query, NoteTypeModel):
            query = query.switch(NoteModel).join(NoteTypeModel, peewee.JOIN.LEFT_OUTER).switch(CardModel)
        primary_clauses.append(NoteTypeModel.name.asc() if is_asc else NoteTypeModel.name.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.TAGS:
        tags_expr = peewee.fn.COALESCE(NoteModel.tags, "")
        primary_clauses.append(tags_expr.asc() if is_asc else tags_expr.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    # 4. Statuts
    elif crit == SortCriterion.FLAGS:
        primary_clauses.append(CardModel.flags.asc() if is_asc else CardModel.flags.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.SUSPENDED:
        primary_clauses.append(CardModel.is_suspended.asc() if is_asc else CardModel.is_suspended.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    # 5. Métriques SRS / FSRS
    elif crit == SortCriterion.LAPSES:
        primary_clauses.append(CardModel.lapses.asc() if is_asc else CardModel.lapses.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.IVL:
        primary_clauses.append(CardModel.ivl.asc() if is_asc else CardModel.ivl.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.REPS:
        primary_clauses.append(CardModel.reps.asc() if is_asc else CardModel.reps.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.STABILITY:
        primary_clauses.append(CardModel.stability.asc() if is_asc else CardModel.stability.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    elif crit == SortCriterion.DIFFICULTY:
        primary_clauses.append(CardModel.difficulty.asc() if is_asc else CardModel.difficulty.desc())
        tie_breakers.extend([NoteModel.sort_field.asc(), CardModel.id.desc()])

    else:
        primary_clauses.append(CardModel.id.asc() if is_asc else CardModel.id.desc())
        tie_breakers.append(NoteModel.sort_field.asc())

    all_order_clauses = primary_clauses + tie_breakers
    return query.order_by(*all_order_clauses)

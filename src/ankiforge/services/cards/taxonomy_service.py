"""Service d'administration et de maintenance de la taxonomie des tags.

Fournit le renommage hiérarchique avec propagation contrôlée, la suppression globale,
l'audit de conformité syntaxique et la réparation assistée par grappe sous transaction atomique.
Conforme à l'ADR 0040, GEMINI.md Règles 2, 3, 20 et DESIGN.md.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from ankiforge.database.models import CardModel, DeckModel, NoteModel, db
from ankiforge.utils.hierarchy import descendants_prefix
from ankiforge.utils.tags import (
    detect_tag_anomalies,
    is_provenance_tag,
    normalize_tag_input,
    parse_note_tags,
    serialize_note_tags,
    split_tag_tokens,
)

logger = logging.getLogger(__name__)


@dataclass
class TagRenameResult:
    """Résultat de l'opération de renommage d'un tag."""

    success: bool
    modified_notes_count: int = 0
    modified_note_ids: list[int] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class TagDeleteResult:
    """Résultat de l'opération de suppression globale d'un tag."""

    success: bool
    modified_notes_count: int = 0
    modified_note_ids: list[int] = field(default_factory=list)
    error_message: str | None = None


@dataclass
class TaxonomyAnomaly:
    """Anomalie syntaxique détectée sur un tag de la collection."""

    tag: str
    anomalies: list[str]
    notes_count: int
    suggested_repair: str
    suggested_mode: str = "replace"  # "replace" ou "split"


@dataclass
class TaxonomyAuditReport:
    """Rapport de conformité de l'audit de taxonomie."""

    anomalies: list[TaxonomyAnomaly] = field(default_factory=list)
    total_anomalies_count: int = 0
    total_notes_impacted: int = 0


@dataclass
class TaxonomyRepairAction:
    """Action de réparation planifiée sur un tag non conforme."""

    old_tag: str
    repair_mode: str = "replace"  # "replace" ou "split"
    target_tag: str | None = None
    split_tags: list[str] | None = None


@dataclass
class TaxonomyRepairResult:
    """Résultat de l'application des réparations de taxonomie."""

    success: bool
    repaired_tags_count: int = 0
    modified_notes_count: int = 0
    error_message: str | None = None


class TaxonomyService:
    """Service d'administration globale de la taxonomie des tags AnkiForge."""

    @classmethod
    def _get_target_notes(cls, deck_id: int | None = None) -> list[NoteModel]:
        """Récupère l'ensemble des notes de la portée spécifiée."""
        if deck_id is not None and deck_id != -1:
            selected_deck = DeckModel.get_or_none(DeckModel.id == deck_id)
            if selected_deck:
                matching_decks = list(DeckModel.select().where((DeckModel.id == selected_deck.id) | DeckModel.name.startswith(descendants_prefix(selected_deck.name))))
                deck_notes = {c.note_id for c in CardModel.select(CardModel.note_id).where(CardModel.deck.in_(matching_decks))}
                return list(NoteModel.select().where(NoteModel.id.in_(list(deck_notes))))
            return []
        return list(NoteModel.select())

    @classmethod
    def rename_tag(
        cls,
        old_tag: str,
        new_tag: str,
        propagate_subtags: bool = True,
        deck_id: int | None = None,
        allow_provenance: bool = False,
    ) -> TagRenameResult:
        """Renomme un tag avec ou sans propagation à sa sous-arborescence descendante.

        Garde-fou : rejette les tags de traçabilité documentaire sans confirmation explicite.
        """
        old_clean = old_tag.strip()
        new_clean = normalize_tag_input(new_tag)

        if not old_clean or not new_clean:
            return TagRenameResult(success=False, error_message="Les tags source et cible doivent être non vides.")

        if old_clean == new_clean:
            return TagRenameResult(success=True)

        if is_provenance_tag(old_clean) and not allow_provenance:
            return TagRenameResult(
                success=False,
                error_message=f"Modification bloquée : le tag '{old_clean}' est un tag de traçabilité/provenance documentaire.",
            )

        notes = cls._get_target_notes(deck_id)
        modified_ids: list[int] = []
        prefix_old = f"{old_clean}::"

        try:
            database = NoteModel._meta.database or db
            with database.atomic():
                for note in notes:
                    current_tags = parse_note_tags(note.tags)
                    updated_tags: list[str] = []
                    mutated = False

                    for t in current_tags:
                        if t == old_clean:
                            if new_clean not in updated_tags:
                                updated_tags.append(new_clean)
                            mutated = True
                        elif propagate_subtags and t.startswith(prefix_old):
                            suffix = t[len(prefix_old) :]
                            sub_new = f"{new_clean}::{suffix}"
                            if sub_new not in updated_tags:
                                updated_tags.append(sub_new)
                            mutated = True
                        else:
                            if t not in updated_tags:
                                updated_tags.append(t)

                    if mutated and updated_tags != current_tags:
                        note.tags = serialize_note_tags(updated_tags)
                        note.save(only=[NoteModel.tags])
                        modified_ids.append(note.id)

                for nid in modified_ids:
                    n_obj = next((n for n in notes if n.id == nid), None)
                    if n_obj:
                        try:
                            from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                            CoverageAlignmentService.sync_note_coverage(n_obj)
                        except Exception as e:
                            logger.debug("Coverage sync skipped note %d: %s", nid, e)

            logger.info("TaxonomyService.rename_tag : %s -> %s (%d notes impactées).", old_clean, new_clean, len(modified_ids))
            return TagRenameResult(
                success=True,
                modified_notes_count=len(modified_ids),
                modified_note_ids=modified_ids,
            )
        except Exception as e:
            logger.exception("Erreur lors du renommage du tag %s : %s", old_clean, e)
            return TagRenameResult(success=False, error_message=str(e))

    @classmethod
    def delete_tag(
        cls,
        tag: str,
        delete_subtags: bool = False,
        deck_id: int | None = None,
        allow_provenance: bool = False,
    ) -> TagDeleteResult:
        """Supprime un tag sur l'ensemble de la portée, avec option pour ses sous-tags.

        Garde-fou : protège les tags de provenance contre toute suppression accidentelle.
        """
        tag_clean = tag.strip()
        if not tag_clean:
            return TagDeleteResult(success=True)

        if is_provenance_tag(tag_clean) and not allow_provenance:
            return TagDeleteResult(
                success=False,
                error_message="Suppression bloquée : le tag est un tag de traçabilité/provenance documentaire.",
            )

        notes = cls._get_target_notes(deck_id)
        modified_ids: list[int] = []
        prefix_sub = f"{tag_clean}::"

        try:
            database = NoteModel._meta.database or db
            with database.atomic():
                for note in notes:
                    current_tags = parse_note_tags(note.tags)
                    updated_tags: list[str] = []
                    mutated = False

                    for t in current_tags:
                        if t == tag_clean or (delete_subtags and t.startswith(prefix_sub)):
                            if is_provenance_tag(t) and not allow_provenance:
                                updated_tags.append(t)
                            else:
                                mutated = True
                        else:
                            updated_tags.append(t)

                    if mutated and updated_tags != current_tags:
                        note.tags = serialize_note_tags(updated_tags)
                        note.save(only=[NoteModel.tags])
                        modified_ids.append(note.id)

                for nid in modified_ids:
                    n_obj = next((n for n in notes if n.id == nid), None)
                    if n_obj:
                        try:
                            from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                            CoverageAlignmentService.sync_note_coverage(n_obj)
                        except Exception as e:
                            logger.debug("Coverage sync skipped note %d: %s", nid, e)

            logger.info("TaxonomyService.delete_tag : suppression de %s (%d notes impactées).", tag_clean, len(modified_ids))
            return TagDeleteResult(
                success=True,
                modified_notes_count=len(modified_ids),
                modified_note_ids=modified_ids,
            )
        except Exception as e:
            logger.exception("Erreur lors de la suppression du tag %s : %s", tag_clean, e)
            return TagDeleteResult(success=False, error_message=str(e))

    @classmethod
    def audit_taxonomy(cls, deck_id: int | None = None) -> TaxonomyAuditReport:
        """Audite la collection pour détecter les anomalies de tags (espaces, segments vides, syntaxe)."""
        notes = cls._get_target_notes(deck_id)
        tag_notes_map: dict[str, set[int]] = {}

        for note in notes:
            for t in parse_note_tags(note.tags):
                tag_notes_map.setdefault(t, set()).add(note.id)

        anomalies: list[TaxonomyAnomaly] = []
        impacted_notes: set[int] = set()

        for tag_str, n_set in sorted(tag_notes_map.items()):
            tag_issues = detect_tag_anomalies(tag_str)
            if tag_issues:
                # Préconisation de réparation
                suggested_clean = normalize_tag_input(tag_str)
                suggested_mode = "replace"
                if "has_spaces" in tag_issues:
                    # Remplacement automatique par tiret bas par défaut selon l'ADR 0040
                    suggested_clean = normalize_tag_input(tag_str)
                anomalies.append(
                    TaxonomyAnomaly(
                        tag=tag_str,
                        anomalies=tag_issues,
                        notes_count=len(n_set),
                        suggested_repair=suggested_clean or "tag",
                        suggested_mode=suggested_mode,
                    )
                )
                impacted_notes.update(n_set)

        # Détection des doublons de casse (ex: 'anatomie' vs 'Anatomie')
        case_map: dict[str, list[str]] = {}
        for tag_str in tag_notes_map:
            if not is_provenance_tag(tag_str) and tag_str.strip().lower() != "ankiforge_generated":
                case_map.setdefault(tag_str.lower(), []).append(tag_str)

        for _low, variants in sorted(case_map.items()):
            if len(variants) > 1:
                # Élection de la variante la plus fréquente
                sorted_vars = sorted(variants, key=lambda v: (-len(tag_notes_map[v]), v))
                canonical = sorted_vars[0]
                for non_canon in sorted_vars[1:]:
                    if not any(a.tag == non_canon for a in anomalies):
                        anomalies.append(
                            TaxonomyAnomaly(
                                tag=non_canon,
                                anomalies=["case_variant"],
                                notes_count=len(tag_notes_map[non_canon]),
                                suggested_repair=canonical,
                                suggested_mode="replace",
                            )
                        )
                        impacted_notes.update(tag_notes_map[non_canon])

        return TaxonomyAuditReport(
            anomalies=anomalies,
            total_anomalies_count=len(anomalies),
            total_notes_impacted=len(impacted_notes),
        )

    @classmethod
    def apply_taxonomy_repairs(
        cls,
        repairs: Sequence[TaxonomyRepairAction],
        deck_id: int | None = None,
    ) -> TaxonomyRepairResult:
        """Applique les réparations planifiées sur les tags non conformes dans une transaction atomique."""
        if not repairs:
            return TaxonomyRepairResult(success=True)

        notes = cls._get_target_notes(deck_id)
        modified_ids: list[int] = []

        # Construction des tables de remplacement ou scission
        replace_map: dict[str, str] = {}
        split_map: dict[str, list[str]] = {}

        for rep in repairs:
            old = rep.old_tag.strip()
            if not old:
                continue
            if rep.repair_mode == "split":
                splits = rep.split_tags or split_tag_tokens(old)
                if splits:
                    split_map[old] = splits
            else:
                target = normalize_tag_input(rep.target_tag or "")
                if target and target != old:
                    replace_map[old] = target

        if not replace_map and not split_map:
            return TaxonomyRepairResult(success=True)

        try:
            database = NoteModel._meta.database or db
            with database.atomic():
                for note in notes:
                    current_tags = parse_note_tags(note.tags)
                    new_tags: list[str] = []
                    mutated = False

                    for t in current_tags:
                        if t in replace_map:
                            t_rep = replace_map[t]
                            if t_rep not in new_tags:
                                new_tags.append(t_rep)
                            mutated = True
                        elif t in split_map:
                            for sp in split_map[t]:
                                if sp not in new_tags:
                                    new_tags.append(sp)
                            mutated = True
                        else:
                            if t not in new_tags:
                                new_tags.append(t)

                    if mutated and new_tags != current_tags:
                        note.tags = serialize_note_tags(new_tags)
                        note.save(only=[NoteModel.tags])
                        modified_ids.append(note.id)

                for nid in modified_ids:
                    n_obj = next((n for n in notes if n.id == nid), None)
                    if n_obj:
                        try:
                            from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                            CoverageAlignmentService.sync_note_coverage(n_obj)
                        except Exception as e:
                            logger.debug("Coverage sync skipped note %d: %s", nid, e)

            logger.info("TaxonomyService.apply_taxonomy_repairs : %d réparations appliquées sur %d notes.", len(repairs), len(modified_ids))
            return TaxonomyRepairResult(
                success=True,
                repaired_tags_count=len(repairs),
                modified_notes_count=len(modified_ids),
            )
        except Exception as e:
            logger.exception("Erreur lors de l'application des réparations de taxonomie : %s", e)
            return TaxonomyRepairResult(success=False, error_message=str(e))

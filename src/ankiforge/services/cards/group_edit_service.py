"""Édition groupée atomique de notes Anki (ajout de tags, mise à jour de champs).

Applique les modifications à un lot de notes dans une transaction SQLite unique afin de
préserver la cohérence et de générer les versions de note correspondantes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ankiforge.database.models import NoteModel, NoteVersionModel, db
from ankiforge.utils.tags import (
    is_provenance_tag,
    parse_note_tags,
    serialize_note_tags,
)

logger = logging.getLogger(__name__)


@dataclass
class GroupEditOptions:
    """Paramètres pour l'opération d'édition groupée de notes."""

    tags_to_add: list[str] = field(default_factory=list)
    tags_to_remove: list[str] = field(default_factory=list)
    field_name: str | None = None
    field_action: str | None = None  # "replace", "append", "prepend", "find_replace"
    field_value: str = ""
    find_text: str = ""
    allow_remove_provenance_tags: bool = False


@dataclass
class GroupEditResult:
    """Résultat de l'exécution d'une édition groupée atomique."""

    success: bool
    modified_note_ids: list[int] = field(default_factory=list)
    skipped_note_ids: list[int] = field(default_factory=list)
    error_message: str | None = None
    tags_by_note_id: dict[int, list[str]] = field(default_factory=dict)
    content_by_note_id: dict[int, dict[str, str]] = field(default_factory=dict)


class GroupEditService:
    """Service appliquant des modifications en masse (tags, champs) de façon strictement atomique."""

    @classmethod
    def apply_group_edit(
        cls,
        note_ids: list[int],
        options: GroupEditOptions,
    ) -> GroupEditResult:
        """Applique les options d'édition groupée à toutes les notes spécifiées dans une seule transaction atomique.

        En cas d'erreur sur l'une des notes, l'ensemble de la transaction est annulé (rollback).
        """
        if not note_ids:
            return GroupEditResult(success=True)

        tags_add_clean: list[str] = []
        for raw_tag in options.tags_to_add:
            for parsed_tag in parse_note_tags(raw_tag):
                if parsed_tag not in tags_add_clean:
                    tags_add_clean.append(parsed_tag)

        tags_remove_clean: list[str] = []
        for raw_tag in options.tags_to_remove:
            for parsed_tag in parse_note_tags(raw_tag):
                if parsed_tag not in tags_remove_clean:
                    tags_remove_clean.append(parsed_tag)

        has_tag_mods = bool(tags_add_clean or tags_remove_clean)
        has_field_mods = bool(options.field_name and options.field_action)

        if not has_tag_mods and not has_field_mods:
            return GroupEditResult(success=True)

        modified_ids: list[int] = []
        skipped_ids: list[int] = []
        tags_by_note: dict[int, list[str]] = {}
        content_by_note: dict[int, dict[str, str]] = {}

        try:
            database = NoteModel._meta.database or db
            with database.atomic():
                notes = list(NoteModel.select().where(NoteModel.id.in_(note_ids)))
                note_map = {n.id: n for n in notes}

                for nid in note_ids:
                    note = note_map.get(nid)
                    if not note:
                        skipped_ids.append(nid)
                        continue

                    note_modified = False

                    if has_tag_mods:
                        current_tags = parse_note_tags(note.tags)
                        new_tags_list = list(current_tags)

                        if tags_remove_clean:
                            filtered_tags: list[str] = []
                            for t in new_tags_list:
                                if t in tags_remove_clean:
                                    # Protection des tags de provenance sauf demande explicite
                                    if is_provenance_tag(t) and not options.allow_remove_provenance_tags:
                                        filtered_tags.append(t)
                                    else:
                                        note_modified = True
                                else:
                                    filtered_tags.append(t)
                            new_tags_list = filtered_tags

                        if tags_add_clean:
                            for t in tags_add_clean:
                                if t not in new_tags_list:
                                    new_tags_list.append(t)
                                    note_modified = True

                        if new_tags_list != current_tags:
                            note.tags = serialize_note_tags(new_tags_list)
                            note.save(only=[NoteModel.tags])
                            tags_by_note[nid] = new_tags_list
                        else:
                            tags_by_note[nid] = current_tags

                    if has_field_mods and options.field_name and options.field_action:
                        active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                        if not active_version:
                            active_version = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

                        content: dict[str, Any] = {}
                        if active_version and active_version.content:
                            try:
                                parsed_c = json.loads(active_version.content)
                                if isinstance(parsed_c, dict):
                                    content = {str(k): str(v) for k, v in parsed_c.items()}
                            except Exception as e:
                                logger.warning("Erreur décodage contenu note %d: %s", nid, e)

                        target_field = options.field_name
                        val_before = content.get(target_field, "")
                        val_after = val_before

                        if options.field_action == "replace":
                            val_after = options.field_value
                        elif options.field_action == "append":
                            val_after = f"{val_before} {options.field_value}" if val_before else options.field_value
                        elif options.field_action == "prepend":
                            val_after = f"{options.field_value} {val_before}" if val_before else options.field_value
                        elif options.field_action == "find_replace" and options.find_text:
                            val_after = val_before.replace(options.find_text, options.field_value)

                        if val_after != val_before or target_field not in content:
                            content[target_field] = val_after
                            note.add_version(content, source="batch_edit")
                            note_modified = True
                            content_by_note[nid] = content

                    if note_modified:
                        modified_ids.append(nid)
                    else:
                        skipped_ids.append(nid)

                # Synchronisation de la couverture pour les notes modifiées
                for nid in modified_ids:
                    n_obj = note_map.get(nid)
                    if n_obj:
                        try:
                            from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                            CoverageAlignmentService.sync_note_coverage(n_obj)
                        except Exception as e:
                            logger.debug("Coverage sync skipped for note %d: %s", nid, e)

            return GroupEditResult(
                success=True,
                modified_note_ids=modified_ids,
                skipped_note_ids=skipped_ids,
                tags_by_note_id=tags_by_note,
                content_by_note_id=content_by_note,
            )

        except Exception as e:
            logger.exception("Échec de l'édition groupée : transaction annulée.")
            return GroupEditResult(
                success=False,
                error_message=str(e),
                modified_note_ids=[],
                skipped_note_ids=note_ids,
            )

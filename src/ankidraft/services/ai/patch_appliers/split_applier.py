"""Stratégie d'application chirurgicale des scissions atomiques de cartes (split, card_split)."""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any

from ankidraft.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteVersionModel,
    StagedPatchModel,
    db,
)
from ankidraft.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)

logger = logging.getLogger(__name__)


class NoteSplitPatchApplier(PatchApplierStrategy):
    """Applique la scission atomique d'une note monolithique en plusieurs cartes élémentaires."""

    SUPPORTED_TYPES = ("split", "card_split")

    def can_apply(self, patch_type: str) -> bool:
        return patch_type.lower().strip() in self.SUPPORTED_TYPES

    def apply(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None = None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        target_nid = patch.target_id or diff_data.get("note_id")
        note = NoteModel.get_or_none(NoteModel.id == target_nid) if target_nid else None
        if not note:
            return {"status": "error", "message": f"Note #{target_nid} introuvable en base."}

        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
        if patch.original_version_id is not None and (not active_v or active_v.id != patch.original_version_id):
            return {
                "status": "conflict",
                "message": f"Conflit de version : la note #{note.id} a été modifiée après la création de la scission.",
                "patch_id": patch_id,
            }

        cards_to_apply = diff_data.get("modified") or diff_data.get("new_cards") or diff_data.get("cards") or []
        if not isinstance(cards_to_apply, list) or not cards_to_apply:
            return {"status": "error", "message": "Aucune carte valide trouvée dans la scission."}

        card_rel = note.cards.first()
        target_deck = card_rel.deck if card_rel else DeckModel.select().first()

        created_notes: list[int] = []
        with db.atomic():
            for c_data in cards_to_apply:
                new_n = NoteModel.create(
                    guid=str(uuid.uuid4())[:12],
                    note_type=note.note_type,
                    tags=note.tags,
                    status="pending",
                )
                NoteVersionModel.create(
                    note=new_n,
                    version_number=1,
                    content=json.dumps(c_data, ensure_ascii=False) if isinstance(c_data, dict) else str(c_data),
                    source="consultant_staged_split",
                    is_active=True,
                )
                if target_deck:
                    CardModel.create(note=new_n, deck=target_deck, template_index=0)
                created_notes.append(new_n.id)

            note.status = "archived"
            note.save()

            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("card_split", note.id, {"parent_id": note.id, "created_ids": created_notes})

        return {
            "status": "applied",
            "patch_id": patch_id,
            "parent_note_id": note.id,
            "created_note_ids": created_notes,
            "message": f"Note #{note.id} scindée en {len(created_notes)} cartes atomiques.",
        }

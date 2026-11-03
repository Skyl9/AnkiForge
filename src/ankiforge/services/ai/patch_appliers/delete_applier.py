"""Stratégie d'application des suppressions chirurgicales de notes et cartes vides."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from ankiforge.database.models import (
    CardModel,
    NoteModel,
    NoteVersionModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)

logger = logging.getLogger(__name__)


class NoteDeletePatchApplier(PatchApplierStrategy):
    """Gère la suppression unitaire ou par lot de notes (avec verrou optimiste) et de cartes vides."""

    SUPPORTED_TYPES = (
        "card_delete",
        "note_delete",
        "batch_card_deletion",
        "batch_note_delete",
        "empty_cards_delete",
        "delete_empty_cards",
    )

    def can_apply(self, patch_type: str) -> bool:
        return patch_type.lower().strip() in self.SUPPORTED_TYPES

    def apply(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None = None,
    ) -> dict[str, Any]:
        p_type = patch.patch_type.lower().strip()
        if p_type in ("empty_cards_delete", "delete_empty_cards"):
            return self._apply_empty_cards_delete(patch, diff_data, notify_mutation)
        return self._apply_notes_delete(patch, diff_data, notify_mutation)

    def _apply_notes_delete(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        target_ids = diff_data.get("note_ids") or ([patch.target_id] if patch.target_id else [])
        if not target_ids:
            return {"status": "error", "message": "Aucune note ciblée pour suppression.", "patch_id": patch_id}

        # Verrouillage optimiste sur note_delete si original_version_id
        if len(target_ids) == 1 and patch.original_version_id is not None:
            note = NoteModel.get_or_none(NoteModel.id == target_ids[0])
            if note:
                active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if active_v and active_v.id != patch.original_version_id:
                    return {
                        "status": "conflict",
                        "message": f"Conflit de version : la note #{note.id} a été modifiée après la proposition de suppression.",
                        "patch_id": patch_id,
                        "current_version_id": active_v.id,
                        "expected_version_id": patch.original_version_id,
                    }

        with db.atomic():
            notes_to_delete = list(NoteModel.select().where(NoteModel.id.in_(target_ids)))
            for n in notes_to_delete:
                n.delete_instance(recursive=True)
            deleted_count = len(notes_to_delete)
            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("note_delete", patch.target_id, {"deleted_count": deleted_count, "note_ids": target_ids, "patch_id": patch_id})
        return {"status": "applied", "patch_id": patch_id, "deleted_count": deleted_count, "note_ids": target_ids}

    def _apply_empty_cards_delete(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        card_ids = diff_data.get("card_ids") or []
        if not card_ids:
            return {"status": "error", "message": "Aucune carte vide ciblée pour suppression.", "patch_id": patch_id}

        with db.atomic():
            deleted_count = CardModel.delete().where(CardModel.id.in_(card_ids)).execute()
            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("delete_empty_cards", 0, {"card_ids": card_ids, "deleted_count": deleted_count, "patch_id": patch_id})
        return {
            "status": "applied",
            "patch_id": patch_id,
            "deleted_count": deleted_count,
            "card_ids": card_ids,
            "message": f"{deleted_count} carte(s) vide(s) supprimée(s) avec succès.",
        }

"""Stratégie d'application des opérations sur les tags (set_tags, tag_add, tag_remove, etc.)."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from ankiforge.database.models import StagedPatchModel, db
from ankiforge.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)

logger = logging.getLogger(__name__)


class TagPatchApplier(PatchApplierStrategy):
    """Gère l'application des modifications en masse de tags sur les notes."""

    SUPPORTED_TYPES = ("set_tags", "set_tags_bulk", "tag_add", "tag_remove", "tags")

    def can_apply(self, patch_type: str) -> bool:
        return patch_type.lower().strip() in self.SUPPORTED_TYPES

    def apply(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None = None,
    ) -> dict[str, Any]:
        p_type = patch.patch_type.lower().strip()
        patch_id = patch.patch_id

        note_ids = diff_data.get("note_ids") or ([patch.target_id] if patch.target_id else [])
        tags = diff_data.get("tags") or diff_data.get("tags_added") or []
        mode = str(diff_data.get("mode") or ("add" if p_type == "tag_add" else ("remove" if p_type == "tag_remove" else "add")))

        from ankiforge.services.cards.bulk_hygiene_service import BulkHygieneService

        res = BulkHygieneService.set_tags_bulk(note_ids=note_ids, tags=tags, mode=mode)
        if res.get("status") == "error":
            return {"status": "error", "message": res.get("message", "Erreur tagging"), "patch_id": patch_id}

        with db.atomic():
            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("set_tags_bulk", patch.target_id, {"note_ids": note_ids, "tags": tags, "mode": mode})
        return {"status": "applied", "patch_id": patch_id, "note_ids": note_ids, "tags": tags}

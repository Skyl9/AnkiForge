"""Stratégie d'application chirurgicale des modifications de cartes et notes (card, note_update)."""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from ankidraft.database.models import (
    NoteModel,
    NoteVersionModel,
    StagedPatchModel,
    db,
)
from ankidraft.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)
from ankidraft.utils.tags import serialize_note_tags, split_tag_tokens

logger = logging.getLogger(__name__)


class NoteUpdatePatchApplier(PatchApplierStrategy):
    """Applique les modifications de champs et tags sur une note existante avec contrôle optimiste de version."""

    SUPPORTED_TYPES = ("card", "note_update")

    def can_apply(self, patch_type: str) -> bool:
        return patch_type.lower().strip() in self.SUPPORTED_TYPES

    def _compute_final_content(self, active_v: NoteVersionModel | None, diff_data: dict[str, Any]) -> dict[str, Any]:
        modified = diff_data.get("modified", {})
        if isinstance(modified, str):
            try:
                modified = json.loads(modified)
            except Exception:
                modified = {"Front": modified}

        orig_content_dict: dict[str, Any] = {}
        if active_v and active_v.content:
            try:
                loaded = json.loads(active_v.content) if isinstance(active_v.content, str) else active_v.content
                orig_content_dict = loaded if isinstance(loaded, dict) else {"Front": str(loaded)}
            except Exception:
                orig_content_dict = {"Front": str(active_v.content)}
        elif "original" in diff_data and isinstance(diff_data["original"], dict):
            orig_content_dict = dict(diff_data["original"])

        if isinstance(modified, dict):
            return {**orig_content_dict, **modified}
        return {**orig_content_dict, "Front": str(modified)}

    def _update_tags_if_present(self, note: NoteModel, diff_data: dict[str, Any]) -> None:
        if "modified_tags" in diff_data:
            raw_tags = diff_data["modified_tags"]
            note.tags = serialize_note_tags(split_tag_tokens(raw_tags))
            note.save()
            try:
                from ankidraft.services.audit.coverage_alignment_service import CoverageAlignmentService

                CoverageAlignmentService.sync_note_coverage(note)
            except Exception as cov_err:
                logger.debug("Synchronisation de la couverture ignorée : %s", cov_err)

    def apply(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None = None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        note = NoteModel.get_or_none(NoteModel.id == patch.target_id)
        if not note:
            return {"status": "error", "message": f"Note #{patch.target_id} introuvable en base."}

        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712

        # Verrouillage optimiste de concurrence
        if patch.original_version_id is not None and (not active_v or active_v.id != patch.original_version_id):
            logger.warning("Conflit optimiste sur le patch %s : note #%s modifiée concurremment.", patch_id, note.id)
            return {
                "status": "conflict",
                "message": f"Conflit de version : la note #{note.id} a été modifiée après la création du patch.",
                "patch_id": patch_id,
                "current_version_id": active_v.id if active_v else None,
                "expected_version_id": patch.original_version_id,
            }

        final_content_dict = self._compute_final_content(active_v, diff_data)

        with db.atomic():
            prev_v_num = active_v.version_number if active_v else 0
            if active_v:
                active_v.is_active = False
                active_v.save()

            new_v_num = prev_v_num + 1
            NoteVersionModel.create(
                note=note,
                version_number=new_v_num,
                content=json.dumps(final_content_dict, ensure_ascii=False),
                source="staged_patch",
                is_active=True,
            )

            self._update_tags_if_present(note, diff_data)

            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("note_update", note.id, {"note_id": note.id, "patch_id": patch_id})

        return {
            "status": "applied",
            "patch_id": patch_id,
            "note_id": note.id,
            "version_number": new_v_num,
            "message": f"Patch #{patch_id} appliqué avec succès sur la note #{note.id} (version {new_v_num}).",
        }

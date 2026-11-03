"""Stratégie d'application des patchs d'étape déléguée MCP (traces d'audit et validation)."""

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


class DelegatedStepPatchApplier(PatchApplierStrategy):
    """Gère l'application (validation / archivage d'audit) d'une étape de pipeline déléguée."""

    SUPPORTED_TYPES = ("pipeline_step_delegated",)

    def can_apply(self, patch_type: str) -> bool:
        return patch_type.lower().strip() in self.SUPPORTED_TYPES

    def apply(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None = None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        step_order = diff_data.get("step_order") or patch.step_order or 0

        with db.atomic():
            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        logger.info("Trace d'audit d'étape déléguée validée : patch %s (étape %s)", patch_id, step_order)

        if notify_mutation:
            notify_mutation(
                "pipeline_step_delegated",
                patch.id or 0,
                {
                    "patch_id": patch_id,
                    "step_order": step_order,
                    "pipeline_id": diff_data.get("pipeline_id"),
                    "run_id": diff_data.get("run_id"),
                },
            )

        return {
            "status": "applied",
            "patch_id": patch_id,
            "patch_type": patch.patch_type,
            "step_order": step_order,
            "message": f"Étape déléguée #{step_order} validée (trace d'audit).",
        }

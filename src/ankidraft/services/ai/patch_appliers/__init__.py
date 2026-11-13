"""Package des stratégies modulaires d'application des staged patches (ADR 0054)."""

from __future__ import annotations

from ankidraft.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)
from ankidraft.services.ai.patch_appliers.card_applier import NoteUpdatePatchApplier
from ankidraft.services.ai.patch_appliers.create_applier import NoteCreatePatchApplier
from ankidraft.services.ai.patch_appliers.deck_applier import DeckPatchApplier
from ankidraft.services.ai.patch_appliers.delegated_applier import DelegatedStepPatchApplier
from ankidraft.services.ai.patch_appliers.delete_applier import NoteDeletePatchApplier
from ankidraft.services.ai.patch_appliers.model_applier import ModelPatchApplier
from ankidraft.services.ai.patch_appliers.split_applier import NoteSplitPatchApplier
from ankidraft.services.ai.patch_appliers.tag_applier import TagPatchApplier

_APPLIERS: list[PatchApplierStrategy] = [
    NoteUpdatePatchApplier(),
    NoteSplitPatchApplier(),
    ModelPatchApplier(),
    NoteCreatePatchApplier(),
    DeckPatchApplier(),
    TagPatchApplier(),
    NoteDeletePatchApplier(),
    DelegatedStepPatchApplier(),
]


def get_patch_applier(patch_type: str) -> PatchApplierStrategy | None:
    """Retourne la stratégie adéquate pour le type de patch spécifié, ou None si non pris en charge."""
    normalized_type = patch_type.lower().strip()
    for applier in _APPLIERS:
        if applier.can_apply(normalized_type):
            return applier
    return None


__all__ = [
    "DelegatedStepPatchApplier",
    "NotifyMutationCallback",
    "PatchApplierStrategy",
    "get_patch_applier",
]

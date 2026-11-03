"""Stratégie d'application des modifications sur les paquets de cartes (création, renommage, suppression)."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    StagedPatchModel,
    db,
)
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)

logger = logging.getLogger(__name__)


class DeckPatchApplier(PatchApplierStrategy):
    """Gère la création, le renommage et la suppression de paquets (decks)."""

    SUPPORTED_TYPES = (
        "deck_create",
        "create_deck",
        "deck_rename",
        "rename_deck",
        "deck_delete",
        "delete_deck",
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
        if p_type in ("deck_create", "create_deck"):
            return self._apply_create(patch, diff_data, notify_mutation)
        if p_type in ("deck_rename", "rename_deck"):
            return self._apply_rename(patch, diff_data, notify_mutation)
        if p_type in ("deck_delete", "delete_deck"):
            return self._apply_delete(patch, diff_data, notify_mutation)
        return {"status": "error", "message": f"Type de patch non supporté : '{patch.patch_type}'."}

    def _apply_create(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        deck_name = str(diff_data.get("deck_name") or diff_data.get("deck") or "").strip()
        description = str(diff_data.get("description") or "").strip()
        if not deck_name:
            return {"status": "error", "message": "Nom de paquet manquant pour 'deck_create'.", "patch_id": patch_id}

        repo = DeckRepository()
        created_deck = repo.get_or_create_deck_hierarchical(deck_name, description=description)

        with db.atomic():
            patch.target_id = created_deck.id
            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("create_deck", created_deck.id, {"deck_id": created_deck.id, "deck_name": created_deck.name, "is_new": True})
        return {
            "status": "applied",
            "patch_id": patch_id,
            "deck_id": created_deck.id,
            "deck_name": created_deck.name,
            "message": f"Paquet '{created_deck.name}' créé avec succès.",
        }

    def _apply_rename(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        old_name = str(diff_data.get("old_name") or diff_data.get("deck_name") or "").strip()
        new_name = str(diff_data.get("new_name") or "").strip()
        if not old_name or not new_name:
            return {"status": "error", "message": "Noms d'origine et de destination requis pour 'deck_rename'.", "patch_id": patch_id}

        deck = DeckModel.get_or_none(DeckModel.name == old_name)
        if not deck:
            return {"status": "error", "message": f"Paquet '{old_name}' introuvable.", "patch_id": patch_id}

        repo = DeckRepository()
        with db.atomic():
            repo.rename_deck(deck.id, new_name)
            patch.target_id = deck.id
            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("deck_rename", deck.id, {"deck_id": deck.id, "old_name": old_name, "new_name": new_name})
        return {"status": "applied", "patch_id": patch_id, "deck_id": deck.id, "new_name": new_name}

    def _apply_delete(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        deck_name = str(diff_data.get("deck_name") or diff_data.get("deck") or "").strip()
        move_to = str(diff_data.get("move_cards_to_deck") or "").strip()

        deck = DeckModel.get_or_none(DeckModel.name == deck_name)
        if not deck:
            return {"status": "error", "message": f"Paquet '{deck_name}' introuvable.", "patch_id": patch_id}

        repo = DeckRepository()
        descendant_ids = [d.id for d in repo.get_descendant_decks(deck.name)]

        with db.atomic():
            if move_to:
                target_deck = repo.get_or_create_deck_hierarchical(move_to)
                CardModel.update(deck=target_deck).where(CardModel.deck.in_(descendant_ids)).execute()

            repo.delete_deck(deck.id)
            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("deck_delete", deck.id, {"deck_id": deck.id, "deck_name": deck_name})
        return {"status": "applied", "patch_id": patch_id, "deck_id": deck.id}

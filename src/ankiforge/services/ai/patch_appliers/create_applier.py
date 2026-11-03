"""Stratégie d'application des créations de notes unitaires et par lot (note_create, batch_note_create)."""

from __future__ import annotations

import ast
import datetime
import json
import logging
from typing import Any

from ankiforge.database.models import (
    DeckModel,
    NoteTypeModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.mcp_tool_registry import robust_json_loads
from ankiforge.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)
from ankiforge.services.cards.note_manager import NoteManager
from ankiforge.utils.tags import split_tag_tokens

logger = logging.getLogger(__name__)


class NoteCreatePatchApplier(PatchApplierStrategy):
    """Gère la création chirurgicale de notes uniques ou groupées par lot."""

    SUPPORTED_TYPES = ("note_create", "batch_note_create")

    def can_apply(self, patch_type: str) -> bool:
        return patch_type.lower().strip() in self.SUPPORTED_TYPES

    def apply(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None = None,
    ) -> dict[str, Any]:
        p_type = patch.patch_type.lower().strip()
        if p_type == "note_create":
            return self._apply_single(patch, diff_data, notify_mutation)
        if p_type == "batch_note_create":
            return self._apply_batch(patch, diff_data, notify_mutation)
        return {"status": "error", "message": f"Type de patch non supporté : '{patch.patch_type}'."}

    def _resolve_note_type(self, payload: dict[str, Any], diff_data: dict[str, Any]) -> NoteTypeModel | None:
        nt_id = payload.get("note_type_id") or diff_data.get("note_type_id")
        nt_name = str(payload.get("note_type_name") or payload.get("note_type") or diff_data.get("note_type_name") or diff_data.get("note_type") or "").strip()
        nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(nt_id)) if nt_id else None
        if not nt and nt_name:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name)
        return nt

    def _resolve_deck(self, payload: dict[str, Any], diff_data: dict[str, Any]) -> DeckModel | None:
        deck_id = payload.get("deck_id") or diff_data.get("deck_id")
        deck_name = str(payload.get("deck_name") or payload.get("deck") or diff_data.get("deck_name") or diff_data.get("deck") or "").strip()
        target_deck = DeckModel.get_or_none(DeckModel.id == int(deck_id)) if deck_id else None
        if not target_deck and deck_name:
            target_deck = DeckModel.get_or_none(DeckModel.name == deck_name)
        return target_deck

    def _parse_fields(self, raw_fields: Any) -> dict[str, Any]:
        if isinstance(raw_fields, str):
            try:
                parsed = json.loads(raw_fields)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return raw_fields if isinstance(raw_fields, dict) else {}

    def _apply_single(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        payload = diff_data.get("modified") if isinstance(diff_data.get("modified"), dict) else diff_data
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Payload invalide pour la création de note.", "patch_id": patch_id}

        nt = self._resolve_note_type(payload, diff_data)
        if not nt:
            return {"status": "error", "message": "Type de note introuvable.", "patch_id": patch_id}

        target_deck = self._resolve_deck(payload, diff_data)
        if not target_deck:
            return {"status": "error", "message": "Paquet introuvable.", "patch_id": patch_id}

        raw_fields = payload.get("fields") or payload.get("fields_dict") or payload.get("content_dict") or diff_data.get("fields") or {}
        fields = self._parse_fields(raw_fields)
        if not fields:
            return {"status": "error", "message": "Format de champs invalide.", "patch_id": patch_id}

        raw_tags = payload.get("tags") if payload.get("tags") is not None else diff_data.get("tags", [])
        tags_list = split_tag_tokens(raw_tags)
        source = str(payload.get("source") or diff_data.get("source", "mcp_agent"))

        try:
            with db.atomic():
                created_note = NoteManager.create_note(
                    note_type=nt,
                    deck=target_deck,
                    content_dict=fields,
                    tags=tags_list,
                    source=source,
                )
                patch.target_id = created_note.id
                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            if notify_mutation:
                notify_mutation("note_create", created_note.id, {"note_id": created_note.id, "patch_id": patch_id, "deck_id": target_deck.id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "note_id": created_note.id,
                "deck_name": target_deck.name,
                "note_type_name": nt.name,
                "message": f"Note #{created_note.id} créée avec succès dans '{target_deck.name}'.",
            }
        except Exception as err:
            logger.error("Erreur application note_create : %s", err)
            return {"status": "error", "message": str(err), "patch_id": patch_id}

    def _parse_notes_list(self, payload: dict[str, Any], diff_data: dict[str, Any]) -> list[dict[str, Any]]:
        raw_notes = payload.get("notes") or diff_data.get("notes")
        if isinstance(raw_notes, str):
            try:
                raw_notes = robust_json_loads(raw_notes)
            except Exception:
                try:
                    raw_notes = ast.literal_eval(raw_notes)
                except Exception:
                    raw_notes = []
        if isinstance(raw_notes, list):
            return [n for n in raw_notes if isinstance(n, dict)]
        return []

    def _create_batch_item(
        self,
        idx: int,
        n_item: dict[str, Any],
        default_deck_name: str,
        default_nt_name: str,
        default_tags: list[str],
        default_source: str,
    ) -> int:
        dk_name = str(n_item.get("deck") or n_item.get("deck_name") or default_deck_name).strip()
        dk = DeckModel.get_or_none(DeckModel.name == dk_name)
        if not dk:
            raise ValueError(f"Note #{idx} : Paquet '{dk_name}' introuvable.")

        nt_name = str(n_item.get("note_type") or n_item.get("note_type_name") or default_nt_name).strip()
        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name)
        if not nt:
            raise ValueError(f"Note #{idx} : Type de note '{nt_name}' introuvable.")

        raw_f = n_item.get("fields") or n_item.get("content_dict") or {}
        fields = self._parse_fields(raw_f)
        item_tags = n_item.get("tags")
        item_tags_list: list[str] = split_tag_tokens(item_tags) if item_tags is not None else []
        combined_tags: list[str] = list(dict.fromkeys(default_tags + item_tags_list))
        source = str(n_item.get("source") or default_source)

        created_n = NoteManager.create_note(
            note_type=nt,
            deck=dk,
            content_dict=fields,
            tags=combined_tags,
            source=source,
        )
        return int(created_n.id)

    def _apply_batch(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        payload = diff_data.get("modified") if isinstance(diff_data.get("modified"), dict) else diff_data
        if not isinstance(payload, dict):
            return {"status": "error", "message": "Payload invalide pour la création de notes par lot.", "patch_id": patch_id}

        notes_list = self._parse_notes_list(payload, diff_data)
        if not notes_list:
            return {"status": "error", "message": "Aucune note valide fournie dans le lot.", "patch_id": patch_id}

        default_deck_name = str(payload.get("default_deck") or payload.get("deck_name") or diff_data.get("default_deck") or "").strip()
        default_nt_name = str(payload.get("default_note_type") or payload.get("note_type_name") or diff_data.get("default_note_type") or "").strip()
        raw_default_tags = payload.get("default_tags") if payload.get("default_tags") is not None else diff_data.get("default_tags", [])
        default_tags = split_tag_tokens(raw_default_tags)
        default_source = str(payload.get("source") or diff_data.get("source", "mcp_agent"))

        created_note_ids: list[int] = []
        try:
            with db.atomic():
                for idx, n_item in enumerate(notes_list, 1):
                    nid = self._create_batch_item(idx, n_item, default_deck_name, default_nt_name, default_tags, default_source)
                    created_note_ids.append(nid)

                patch.target_id = created_note_ids[0] if created_note_ids else 0
                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            if notify_mutation:
                notify_mutation("batch_note_create", 0, {"created_note_ids": created_note_ids, "patch_id": patch_id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "created_note_ids": created_note_ids,
                "count": len(created_note_ids),
                "message": f"{len(created_note_ids)} note(s) créée(s) avec succès par lot.",
            }
        except Exception as err:
            logger.error("Erreur application batch_note_create : %s", err)
            return {"status": "error", "message": str(err), "patch_id": patch_id}

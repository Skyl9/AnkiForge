"""Registre persistant pour la gestion des patchs chirurgicaux (Two-Phase Commit)."""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedPatchModel,
    db,
)

logger = logging.getLogger(__name__)


class StagedPatchRegistry:
    """Gère le cycle de vie des propositions de patchs chirurgicaux avec verrouillage optimiste."""

    @classmethod
    def create_patch(
        cls,
        patch_type: str,
        target_id: int = 0,
        original_version_id: int | None = None,
        diff_payload: dict[str, Any] | None = None,
    ) -> StagedPatchModel:
        """Enregistre un nouveau patch en attente de validation humaine."""
        p_id = f"patch_{uuid.uuid4().hex[:10]}"
        payload = diff_payload or {}
        serialized_payload = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else str(payload)

        # Si original_version_id n'est pas fourni et qu'une note est ciblée, récupérer la version active courante
        if original_version_id is None and target_id and target_id > 0 and patch_type in ("card", "note_update", "split", "card_split"):
            note = NoteModel.get_or_none(NoteModel.id == target_id)
            if note:
                active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if active_v:
                    original_version_id = active_v.id

        with db.atomic():
            patch = StagedPatchModel.create(
                patch_id=p_id,
                patch_type=patch_type,
                target_id=target_id,
                original_version_id=original_version_id,
                diff_payload=serialized_payload,
                status="pending",
                created_at=datetime.datetime.now(),
            )

        logger.info("Patch en attente créé : %s (type: %s, cible: %s)", p_id, patch_type, target_id)
        return patch

    @classmethod
    def get_patch(cls, patch_id: str) -> StagedPatchModel | None:
        """Récupère un patch par son identifiant unique."""
        return StagedPatchModel.get_or_none(StagedPatchModel.patch_id == patch_id.strip())

    @classmethod
    def apply_staged_patch(cls, patch_id: str) -> dict[str, Any]:
        """
        Applique un patch en attente avec validation optimiste de concurrence.
        Retourne un dictionnaire avec le statut ('applied', 'conflict', ou 'error').
        """
        patch = cls.get_patch(patch_id)
        if not patch:
            return {"status": "error", "message": f"Patch '{patch_id}' introuvable."}

        if patch.status != "pending":
            return {"status": "error", "message": f"Le patch '{patch_id}' ne peut pas être appliqué (statut actuel: {patch.status})."}

        try:
            diff_data = json.loads(patch.diff_payload) if isinstance(patch.diff_payload, str) else patch.diff_payload
        except Exception:
            diff_data = {}

        p_type = patch.patch_type.lower().strip()

        # 1. Type CARD / NOTE_UPDATE
        if p_type in ("card", "note_update"):
            note = NoteModel.get_or_none(NoteModel.id == patch.target_id)
            if not note:
                return {"status": "error", "message": f"Note #{patch.target_id} introuvable en base."}

            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712

            # Verrouillage optimiste
            if patch.original_version_id is not None and (not active_v or active_v.id != patch.original_version_id):
                logger.warning("Conflit optimiste sur le patch %s : note #%s modifiée concurremment.", patch_id, note.id)
                return {
                    "status": "conflict",
                    "message": f"Conflit de version : la note #{note.id} a été modifiée après la création du patch.",
                    "patch_id": patch_id,
                    "current_version_id": active_v.id if active_v else None,
                    "expected_version_id": patch.original_version_id,
                }

            modified = diff_data.get("modified", {})
            if isinstance(modified, str):
                try:
                    modified = json.loads(modified)
                except Exception:
                    modified = {"Front": modified}

            with db.atomic():
                prev_v_num = active_v.version_number if active_v else 0
                if active_v:
                    active_v.is_active = False
                    active_v.save()

                new_v_num = prev_v_num + 1
                NoteVersionModel.create(
                    note=note,
                    version_number=new_v_num,
                    content=json.dumps(modified, ensure_ascii=False),
                    source="staged_patch",
                    is_active=True,
                )

                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            # Notification pour synchronisation des vues
            cls._notify_mutation("note_update", note.id, {"note_id": note.id, "patch_id": patch_id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "note_id": note.id,
                "version_number": new_v_num,
                "message": f"Patch #{patch_id} appliqué avec succès sur la note #{note.id} (version {new_v_num}).",
            }

        # 2. Type SPLIT / CARD_SPLIT
        if p_type in ("split", "card_split"):
            note = NoteModel.get_or_none(NoteModel.id == patch.target_id)
            if not note:
                return {"status": "error", "message": f"Note #{patch.target_id} introuvable en base."}

            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            if patch.original_version_id is not None and (not active_v or active_v.id != patch.original_version_id):
                return {
                    "status": "conflict",
                    "message": f"Conflit de version : la note #{note.id} a été modifiée après la création de la scission.",
                    "patch_id": patch_id,
                }

            cards_to_apply = diff_data.get("modified", [])
            if not isinstance(cards_to_apply, list) or not cards_to_apply:
                return {"status": "error", "message": "Aucune carte valide trouvée dans la scission."}

            card_rel = note.cards.first()
            target_deck = card_rel.deck if card_rel else DeckModel.select().first()

            created_notes = []
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

            cls._notify_mutation("card_split", note.id, {"parent_id": note.id, "created_ids": created_notes})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "parent_note_id": note.id,
                "created_note_ids": created_notes,
                "message": f"Note #{note.id} scindée en {len(created_notes)} cartes atomiques.",
            }

        # 3. Type CSS / CSS_TUNE
        if p_type in ("css", "css_tune"):
            meta = diff_data.get("metadata", {})
            model_name = meta.get("note_type_name", "") or diff_data.get("note_type_name", "")
            snippet = meta.get("snippet", "") or diff_data.get("modified", "")

            nt = NoteTypeModel.get_or_none(NoteTypeModel.name == model_name) if model_name else NoteTypeModel.select().first()
            if not nt:
                return {"status": "error", "message": f"Modèle de note '{model_name}' introuvable."}

            with db.atomic():
                nt.css_style = (nt.css_style or "") + f"\n\n/* Appliqué via patch {patch_id} */\n{snippet}"
                nt.save()

                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            cls._notify_mutation("css_tune", nt.id, {"note_type_name": nt.name, "patch_id": patch_id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "note_type_name": nt.name,
                "message": f"Style CSS appliqué sur le modèle '{nt.name}'.",
            }

        return {"status": "error", "message": f"Type de patch non supporté : '{patch.patch_type}'."}

    @classmethod
    def reject_staged_patch(cls, patch_id: str, reason: str = "") -> dict[str, Any]:
        """Rejette un patch en attente sans modifier la base de données."""
        patch = cls.get_patch(patch_id)
        if not patch:
            return {"status": "error", "message": f"Patch '{patch_id}' introuvable."}

        with db.atomic():
            patch.status = "rejected"
            patch.save()

        logger.info("Patch rejeté : %s (raison: %s)", patch_id, reason)
        return {
            "status": "rejected",
            "patch_id": patch_id,
            "reason": reason,
            "message": f"Le patch '{patch_id}' a été rejeté.",
        }

    @classmethod
    def _notify_mutation(cls, mutation_type: str, target_id: int, details: dict[str, Any]) -> None:
        """Déclenche la notification sur le bus d'événements si disponible."""
        try:
            from ankiforge.services.ai.mcp_server import _notify_mcp_mutation

            _notify_mcp_mutation({"type": mutation_type, "target_id": target_id, **details})
        except Exception as e:
            logger.debug("Erreur notification mutation patch : %s", e)

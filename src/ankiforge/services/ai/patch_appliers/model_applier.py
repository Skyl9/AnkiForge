"""Stratégie d'application des modifications structurelles de modèles et styles (css, note_type, etc.)."""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from ankiforge.database.models import (
    NoteModel,
    NoteTypeModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.patch_appliers.base import (
    NotifyMutationCallback,
    PatchApplierStrategy,
)

logger = logging.getLogger(__name__)


def _normalize_json_field(val: Any) -> str:
    if isinstance(val, str) and val.strip().startswith("["):
        try:
            val = json.loads(val)
        except Exception:
            pass
    return json.dumps(val, ensure_ascii=False) if isinstance(val, list) else str(val)


class ModelPatchApplier(PatchApplierStrategy):
    """Gère l'application des modifications de CSS, de schéma de modèle, création et migration de types de notes."""

    SUPPORTED_TYPES = (
        "css",
        "css_tune",
        "model",
        "note_type",
        "note_type_create",
        "note_type_change",
        "bulk_html_sanitize",
        "html_sanitize",
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

        if p_type in ("css", "css_tune"):
            return self._apply_css(patch, diff_data, notify_mutation)
        if p_type in ("model", "note_type"):
            return self._apply_model(patch, diff_data, notify_mutation)
        if p_type == "note_type_create":
            return self._apply_note_type_create(patch, diff_data, notify_mutation)
        if p_type == "note_type_change":
            return self._apply_note_type_change(patch, diff_data, notify_mutation)
        if p_type in ("bulk_html_sanitize", "html_sanitize"):
            return self._apply_html_sanitize(patch, diff_data, notify_mutation)

        return {"status": "error", "message": f"Type de patch non supporté : '{patch.patch_type}'."}

    def _apply_css(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        meta = diff_data.get("metadata", {})
        model_name = meta.get("note_type_name", "") or diff_data.get("note_type_name", "")
        snippet = meta.get("snippet", "") or diff_data.get("snippet", "")
        modified_css = diff_data.get("modified") if isinstance(diff_data.get("modified"), str) else ""

        nt = None
        if patch.target_id and patch.target_id > 0:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.id == patch.target_id)
        if not nt and model_name:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.name == model_name)
        if not nt:
            nt = NoteTypeModel.select().first()
        if not nt:
            return {"status": "error", "message": f"Modèle de note '{model_name}' introuvable."}

        with db.atomic():
            if modified_css:
                nt.css_style = modified_css
            else:
                nt.css_style = (nt.css_style or "") + f"\n\n/* Appliqué via patch {patch_id} */\n{snippet}"
            nt.save()

            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("css_tune", nt.id, {"note_type_name": nt.name, "patch_id": patch_id})
        return {
            "status": "applied",
            "patch_id": patch_id,
            "note_type_name": nt.name,
            "message": f"Style CSS appliqué sur le modèle '{nt.name}'.",
        }

    def _resolve_target_note_type(self, patch: StagedPatchModel, diff_data: dict[str, Any]) -> NoteTypeModel | None:
        if patch.target_id and patch.target_id > 0:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.id == patch.target_id)
            if nt:
                return nt
        meta = diff_data.get("metadata", {}) if isinstance(diff_data.get("metadata"), dict) else {}
        m_id = meta.get("note_type_id") or diff_data.get("note_type_id")
        if m_id:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(m_id))
            if nt:
                return nt
        m_name = meta.get("note_type_name") or diff_data.get("note_type_name")
        if m_name:
            return NoteTypeModel.get_or_none(NoteTypeModel.name == str(m_name).strip())
        return None

    def _update_model_attributes(self, nt: NoteTypeModel, modified: Any) -> None:
        if isinstance(modified, str):
            if modified.strip().startswith("{"):
                try:
                    modified = json.loads(modified)
                except Exception:
                    pass
            else:
                nt.css_style = modified
                return

        if not isinstance(modified, dict):
            return

        if "css_style" in modified:
            nt.css_style = str(modified["css_style"])
        if "fields_schema" in modified:
            nt.fields_schema = _normalize_json_field(modified["fields_schema"])
        if "templates" in modified:
            nt.templates = _normalize_json_field(modified["templates"])
        if "description" in modified:
            nt.description = str(modified["description"])

    def _apply_model(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        nt = self._resolve_target_note_type(patch, diff_data)
        if not nt:
            return {"status": "error", "message": f"Modèle de note cible introuvable pour le patch {patch_id}."}

        modified = diff_data.get("modified", {})
        with db.atomic():
            self._update_model_attributes(nt, modified)
            nt.save()

            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("note_type_update", nt.id, {"note_type_id": nt.id, "note_type_name": nt.name, "patch_id": patch_id})
        return {
            "status": "applied",
            "patch_id": patch_id,
            "note_type_id": nt.id,
            "note_type_name": nt.name,
            "message": f"Modèle de note '{nt.name}' mis à jour avec succès en BDD.",
        }

    def _extract_model_create_data(self, diff_data: dict[str, Any], model_data: dict[str, Any]) -> dict[str, Any]:
        def _pick(*keys: str, default: Any = "") -> Any:
            for k in keys:
                if k in model_data and model_data[k]:
                    return model_data[k]
                if isinstance(diff_data, dict) and k in diff_data and diff_data[k]:
                    return diff_data[k]
            return default

        return {
            "name": str(_pick("name")).strip(),
            "fields_schema": _pick("fields_schema", default=[]),
            "templates": _pick("templates", default=[]),
            "css_style": _pick("css_style", "css", default=""),
            "description": _pick("description", default=""),
            "on_conflict": str(_pick("on_conflict", default="error")),
        }

    def _apply_note_type_create(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        from ankiforge.services.cards.card_model_io import CardModelIO

        patch_id = patch.patch_id
        model_data = diff_data.get("model_data") or diff_data.get("modified") or diff_data
        if not isinstance(model_data, dict):
            return {"status": "error", "message": "Payload invalide pour la création de type de note."}

        parsed = self._extract_model_create_data(diff_data, model_data)

        try:
            with db.atomic():
                created_nt, _ = CardModelIO.save_model_to_db(
                    {
                        "name": parsed["name"],
                        "fields_schema": parsed["fields_schema"],
                        "templates": parsed["templates"],
                        "css_style": parsed["css_style"],
                        "description": parsed["description"],
                    },
                    on_conflict=parsed["on_conflict"],
                )
                patch.target_id = created_nt.id
                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            if notify_mutation:
                notify_mutation("note_type_create", created_nt.id, {"note_type_id": created_nt.id, "note_type_name": created_nt.name, "patch_id": patch_id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "note_type_id": created_nt.id,
                "note_type_name": created_nt.name,
                "message": f"Type de note '{created_nt.name}' créé avec succès en base de données.",
            }
        except Exception as err:
            logger.error("Erreur application note_type_create : %s", err)
            return {"status": "error", "message": str(err), "patch_id": patch_id}

    def _extract_target_model(self, payload: dict[str, Any], diff_data: dict[str, Any]) -> Any:
        for k in ("target_model", "target_model_name", "target_model_id"):
            if k in payload and payload[k]:
                return payload[k]
            if isinstance(diff_data, dict) and k in diff_data and diff_data[k]:
                return diff_data[k]
        return None

    def _apply_note_type_change(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        from ankiforge.services.cards.note_type_service import NoteTypeService

        patch_id = patch.patch_id
        raw_payload = diff_data.get("modified")
        payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else (diff_data if isinstance(diff_data, dict) else {})
        note_ids = payload.get("note_ids") or (diff_data.get("note_ids") if isinstance(diff_data, dict) else []) or []
        target_model = self._extract_target_model(payload, diff_data)
        mapping_champs = payload.get("mapping_champs") if "mapping_champs" in payload else (diff_data.get("mapping_champs") if isinstance(diff_data, dict) else None)
        template_mapping = payload.get("template_mapping") if "template_mapping" in payload else (diff_data.get("template_mapping") if isinstance(diff_data, dict) else None)
        clean_cloze = payload.get("clean_cloze", True) if "clean_cloze" in payload else (diff_data.get("clean_cloze", True) if isinstance(diff_data, dict) else True)

        if not note_ids:
            return {"status": "error", "message": "Aucune note spécifiée pour la migration.", "patch_id": patch_id}
        if not target_model:
            return {"status": "error", "message": "Modèle cible non spécifié pour la migration.", "patch_id": patch_id}

        try:
            res = NoteTypeService.change_note_type(
                note_ids=note_ids,
                target_model=target_model,
                mapping_champs=mapping_champs,
                template_mapping=template_mapping,
                clean_cloze=clean_cloze,
            )
            with db.atomic():
                patch.target_id = res["target_model_id"]
                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            if notify_mutation:
                notify_mutation(
                    "note_type_change",
                    res["target_model_id"],
                    {
                        "note_type_id": res["target_model_id"],
                        "target_model": res["target_model_name"],
                        "note_ids": note_ids,
                        "patch_id": patch_id,
                    },
                )
            return {
                "status": "applied",
                "patch_id": patch_id,
                "count": res["migrated_count"],
                "note_type_id": res["target_model_id"],
                "target_model_name": res["target_model_name"],
                "cards_preserved": res.get("cards_preserved", 0),
                "cards_created": res.get("cards_created", 0),
                "cards_deleted": res.get("cards_deleted", 0),
                "warnings": res.get("warnings", []),
                "message": f"{res['migrated_count']} note(s) migrée(s) vers '{res['target_model_name']}'.",
            }
        except Exception as err:
            logger.error("Erreur application note_type_change : %s", err)
            return {"status": "error", "message": str(err), "patch_id": patch_id}

    def _apply_html_sanitize(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None,
    ) -> dict[str, Any]:
        patch_id = patch.patch_id
        diffs = diff_data.get("diffs", [])
        if not isinstance(diffs, list):
            return {"status": "error", "message": "Diffs invalides pour le nettoyage HTML.", "patch_id": patch_id}

        applied_notes: list[int] = []
        with db.atomic():
            for d in diffs:
                nid = d.get("note_id")
                after_content = d.get("after")
                if not nid or not after_content:
                    continue
                note = NoteModel.get_or_none(NoteModel.id == nid)
                if note:
                    note.add_version(after_content, source="staged_patch_html_sanitize")
                    applied_notes.append(note.id)

            patch.status = "applied"
            patch.applied_at = datetime.datetime.now()
            patch.save()

        if notify_mutation:
            notify_mutation("bulk_html_sanitize", 0, {"note_ids": applied_notes, "patch_id": patch_id})
        return {
            "status": "applied",
            "patch_id": patch_id,
            "count": len(applied_notes),
            "note_ids": applied_notes,
            "message": f"Nettoyage HTML appliqué avec succès sur {len(applied_notes)} note(s).",
        }

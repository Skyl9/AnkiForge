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


def staged_patch_id(payload: dict[str, Any]) -> str | None:
    """Identifiant Two-Phase Commit d'une proposition : champ de tête, sinon `metadata.patch_id`.

    C'est la clé d'identité utilisée aussi bien pour recharger un patch depuis la BDD que pour
    éviter de l'empiler deux fois dans la file du Workspace Inspector.
    """
    metadata = payload.get("metadata")
    candidate = payload.get("patch_id") or (metadata.get("patch_id") if isinstance(metadata, dict) else None)
    return str(candidate) if candidate else None


def staged_payload_of(staged: StagedPatchModel) -> dict[str, Any]:
    """Décode le `diff_payload` d'un patch (JSON ou dict déjà décodé).

    Renvoie un dictionnaire vide si le payload est illisible ou inattendu : l'anomalie est
    journalisée en WARNING et laissée au consommateur le décider (ignorer un patch inutilisable
    vaut mieux que lui présenter — ou lui appliquer — un contenu tronqué).
    """
    try:
        data = json.loads(staged.diff_payload) if isinstance(staged.diff_payload, str) else staged.diff_payload
    except Exception as err:
        logger.warning("Payload illisible du patch %s : %s", staged.patch_id, err)
        return {}
    if not isinstance(data, dict):
        logger.warning("Payload inattendu du patch %s (type %s) : ignoré.", staged.patch_id, type(data).__name__)
        return {}
    return data


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
        cls._notify_staged_patch(
            patch_id=p_id,
            patch_type=patch_type,
            target_id=target_id,
            title=str(payload.get("title") or f"Proposition — {patch_type} #{target_id}"),
            details=payload,
        )
        return patch

    @classmethod
    def get_patch(cls, patch_id: str) -> StagedPatchModel | None:
        """Récupère un patch par son identifiant unique."""
        return StagedPatchModel.get_or_none(StagedPatchModel.patch_id == patch_id.strip())

    @classmethod
    def list_pending(cls) -> list[StagedPatchModel]:
        """Liste les patchs encore en attente de validation humaine, du plus ancien au plus récent.

        Sert à recharger la file du Workspace Inspector à l'ouverture d'une session ou de la vue,
        afin qu'une proposition non tranchée ne devienne pas un orphelin après redémarrage.
        """
        return list(StagedPatchModel.select().where(StagedPatchModel.status == "pending").order_by(StagedPatchModel.created_at.asc(), StagedPatchModel.id.asc()))

    @classmethod
    def apply_staged_patch(cls, patch_id: str) -> dict[str, Any]:
        """Applique un patch en attente avec validation optimiste de concurrence.

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

        # 4. Type MODEL / NOTE_TYPE (Évolution structurelle de modèle)
        if p_type in ("model", "note_type"):
            nt = None
            if patch.target_id and patch.target_id > 0:
                nt = NoteTypeModel.get_or_none(NoteTypeModel.id == patch.target_id)
            meta = diff_data.get("metadata", {}) if isinstance(diff_data.get("metadata"), dict) else {}
            if not nt:
                m_id = meta.get("note_type_id") or diff_data.get("note_type_id")
                if m_id:
                    nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(m_id))
            if not nt:
                m_name = meta.get("note_type_name") or diff_data.get("note_type_name")
                if m_name:
                    nt = NoteTypeModel.get_or_none(NoteTypeModel.name == str(m_name).strip())

            if not nt:
                return {"status": "error", "message": f"Modèle de note cible introuvable pour le patch {patch_id}."}

            modified = diff_data.get("modified", {})
            if isinstance(modified, str) and modified.strip().startswith("{"):
                try:
                    modified = json.loads(modified)
                except Exception:
                    pass

            with db.atomic():
                if isinstance(modified, dict):
                    if "css_style" in modified:
                        nt.css_style = str(modified["css_style"])
                    if "fields_schema" in modified:
                        f_val = modified["fields_schema"]
                        if isinstance(f_val, str) and f_val.strip().startswith("["):
                            try:
                                f_val = json.loads(f_val)
                            except Exception:
                                pass
                        nt.fields_schema = json.dumps(f_val, ensure_ascii=False) if isinstance(f_val, list) else str(f_val)
                    if "templates" in modified:
                        t_val = modified["templates"]
                        if isinstance(t_val, str) and t_val.strip().startswith("["):
                            try:
                                t_val = json.loads(t_val)
                            except Exception:
                                pass
                        nt.templates = json.dumps(t_val, ensure_ascii=False) if isinstance(t_val, list) else str(t_val)
                    if "description" in modified:
                        nt.description = str(modified["description"])
                elif isinstance(modified, str):
                    nt.css_style = modified

                nt.save()

                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            cls._notify_mutation("note_type_update", nt.id, {"note_type_id": nt.id, "note_type_name": nt.name, "patch_id": patch_id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "note_type_id": nt.id,
                "note_type_name": nt.name,
                "message": f"Modèle de note '{nt.name}' mis à jour avec succès en BDD.",
            }

        # 5. Type NOTE_TYPE_CREATE (Création d'un type de note)
        if p_type == "note_type_create":
            from ankiforge.services.cards.card_model_io import CardModelIO

            model_data = diff_data.get("model_data") or diff_data.get("modified") or diff_data
            if not isinstance(model_data, dict):
                return {"status": "error", "message": "Payload invalide pour la création de type de note."}

            name = str(model_data.get("name", "")).strip()
            fields_schema = model_data.get("fields_schema", [])
            templates = model_data.get("templates", [])
            css_style = model_data.get("css_style") or model_data.get("css", "")
            description = model_data.get("description", "")
            on_conflict = str(model_data.get("on_conflict", "error"))

            try:
                with db.atomic():
                    created_nt, is_new = CardModelIO.save_model_to_db(
                        {
                            "name": name,
                            "fields_schema": fields_schema,
                            "templates": templates,
                            "css_style": css_style,
                            "description": description,
                        },
                        on_conflict=on_conflict,
                    )
                    patch.target_id = created_nt.id
                    patch.status = "applied"
                    patch.applied_at = datetime.datetime.now()
                    patch.save()

                cls._notify_mutation("note_type_create", created_nt.id, {"note_type_id": created_nt.id, "note_type_name": created_nt.name, "patch_id": patch_id})
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

        # 6. Type NOTE_TYPE_CHANGE (Migration de notes vers un autre type)
        if p_type == "note_type_change":
            from ankiforge.services.cards.note_type_service import NoteTypeService

            payload = diff_data.get("modified") if isinstance(diff_data.get("modified"), dict) else diff_data
            note_ids = payload.get("note_ids", [])
            target_model = payload.get("target_model") or payload.get("target_model_name") or payload.get("target_model_id")
            mapping_champs = payload.get("mapping_champs")

            if not note_ids:
                return {"status": "error", "message": "Aucune note spécifiée pour la migration.", "patch_id": patch_id}
            if not target_model:
                return {"status": "error", "message": "Modèle cible non spécifié pour la migration.", "patch_id": patch_id}

            try:
                res = NoteTypeService.change_note_type(
                    note_ids=note_ids,
                    target_model=target_model,
                    mapping_champs=mapping_champs,
                )
                with db.atomic():
                    patch.target_id = res["target_model_id"]
                    patch.status = "applied"
                    patch.applied_at = datetime.datetime.now()
                    patch.save()

                cls._notify_mutation(
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
                    "warnings": res.get("warnings", []),
                    "message": f"{res['migrated_count']} note(s) migrée(s) vers '{res['target_model_name']}'.",
                }
            except Exception as err:
                logger.error("Erreur application note_type_change : %s", err)
                return {"status": "error", "message": str(err), "patch_id": patch_id}

        # 7. Type BULK_HTML_SANITIZE / HTML_SANITIZE
        if p_type in ("bulk_html_sanitize", "html_sanitize"):
            diffs = diff_data.get("diffs", [])
            if not isinstance(diffs, list):
                return {"status": "error", "message": "Diffs invalides pour le nettoyage HTML.", "patch_id": patch_id}

            applied_notes = []
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

            cls._notify_mutation("bulk_html_sanitize", 0, {"note_ids": applied_notes, "patch_id": patch_id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "count": len(applied_notes),
                "note_ids": applied_notes,
                "message": f"Nettoyage HTML appliqué avec succès sur {len(applied_notes)} note(s).",
            }

        # 8. Type NOTE_CREATE (Création unitaire d'une note)
        if p_type == "note_create":
            from ankiforge.services.cards.note_manager import NoteManager

            payload = diff_data.get("modified") if isinstance(diff_data.get("modified"), dict) else diff_data
            if not isinstance(payload, dict):
                return {"status": "error", "message": "Payload invalide pour la création de note.", "patch_id": patch_id}

            nt_id = payload.get("note_type_id") or diff_data.get("note_type_id")
            nt_name = str(payload.get("note_type_name") or payload.get("note_type") or diff_data.get("note_type_name") or diff_data.get("note_type") or "").strip()
            nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(nt_id)) if nt_id else None
            if not nt and nt_name:
                nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name)

            if not nt:
                return {"status": "error", "message": f"Type de note '{nt_name or nt_id}' introuvable.", "patch_id": patch_id}

            deck_id = payload.get("deck_id") or diff_data.get("deck_id")
            deck_name = str(payload.get("deck_name") or payload.get("deck") or diff_data.get("deck_name") or diff_data.get("deck") or "").strip()
            deck = DeckModel.get_or_none(DeckModel.id == int(deck_id)) if deck_id else None
            if not deck and deck_name:
                deck = DeckModel.get_or_none(DeckModel.name == deck_name)

            if not deck:
                return {"status": "error", "message": f"Paquet '{deck_name or deck_id}' introuvable.", "patch_id": patch_id}

            fields = payload.get("fields") or payload.get("fields_dict") or payload.get("content_dict") or diff_data.get("fields") or {}
            if isinstance(fields, str):
                try:
                    fields = json.loads(fields)
                except Exception:
                    fields = {}
            if not isinstance(fields, dict):
                return {"status": "error", "message": "Format de champs invalide.", "patch_id": patch_id}

            raw_tags = payload.get("tags") if payload.get("tags") is not None else diff_data.get("tags", [])
            tags_list: list[str]
            if isinstance(raw_tags, str):
                tags_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif isinstance(raw_tags, (list, tuple)):
                tags_list = [str(t).strip() for t in raw_tags if str(t).strip()]
            else:
                tags_list = []

            source = str(payload.get("source") or diff_data.get("source", "mcp_agent"))

            try:
                with db.atomic():
                    created_note = NoteManager.create_note(
                        note_type=nt,
                        deck=deck,
                        content_dict=fields,
                        tags=tags_list,
                        source=source,
                    )
                    patch.target_id = created_note.id
                    patch.status = "applied"
                    patch.applied_at = datetime.datetime.now()
                    patch.save()

                cls._notify_mutation("note_create", created_note.id, {"note_id": created_note.id, "patch_id": patch_id, "deck_id": deck.id})
                return {
                    "status": "applied",
                    "patch_id": patch_id,
                    "note_id": created_note.id,
                    "deck_name": deck.name,
                    "note_type_name": nt.name,
                    "message": f"Note #{created_note.id} créée avec succès dans '{deck.name}'.",
                }
            except Exception as err:
                logger.error("Erreur application note_create : %s", err)
                return {"status": "error", "message": str(err), "patch_id": patch_id}

        # 9. Type BATCH_NOTE_CREATE (Création groupée de notes par lot)
        if p_type == "batch_note_create":
            from ankiforge.services.cards.note_manager import NoteManager

            payload = diff_data.get("modified") if isinstance(diff_data.get("modified"), dict) else diff_data
            if not isinstance(payload, dict):
                return {"status": "error", "message": "Payload invalide pour la création de notes par lot.", "patch_id": patch_id}

            notes_list = payload.get("notes") or diff_data.get("notes", [])
            if not isinstance(notes_list, list) or not notes_list:
                return {"status": "error", "message": "Aucune note valide fournie dans le lot.", "patch_id": patch_id}

            default_deck_name = str(payload.get("default_deck") or payload.get("deck_name") or diff_data.get("default_deck") or "").strip()
            default_nt_name = str(payload.get("default_note_type") or payload.get("note_type_name") or diff_data.get("default_note_type") or "").strip()
            raw_default_tags = payload.get("default_tags") if payload.get("default_tags") is not None else diff_data.get("default_tags", [])
            default_tags: list[str]
            if isinstance(raw_default_tags, str):
                default_tags = [t.strip() for t in raw_default_tags.split(",") if t.strip()]
            elif isinstance(raw_default_tags, (list, tuple)):
                default_tags = [str(t).strip() for t in raw_default_tags if str(t).strip()]
            else:
                default_tags = []

            created_note_ids: list[int] = []
            try:
                with db.atomic():
                    for idx, n_item in enumerate(notes_list, 1):
                        if not isinstance(n_item, dict):
                            continue
                        dk_name = str(n_item.get("deck") or n_item.get("deck_name") or default_deck_name).strip()
                        dk = DeckModel.get_or_none(DeckModel.name == dk_name)
                        if not dk:
                            raise ValueError(f"Note #{idx} : Paquet '{dk_name}' introuvable.")

                        nt_name = str(n_item.get("note_type") or n_item.get("note_type_name") or default_nt_name).strip()
                        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name)
                        if not nt:
                            raise ValueError(f"Note #{idx} : Type de note '{nt_name}' introuvable.")

                        fields = n_item.get("fields") or n_item.get("content_dict") or {}
                        if isinstance(fields, str):
                            try:
                                fields = json.loads(fields)
                            except Exception:
                                fields = {}

                        item_tags = n_item.get("tags")
                        item_tags_list: list[str] = []
                        if isinstance(item_tags, str):
                            item_tags_list = [t.strip() for t in item_tags.split(",") if t.strip()]
                        elif isinstance(item_tags, (list, tuple)):
                            item_tags_list = [str(t).strip() for t in item_tags if str(t).strip()]

                        combined_tags: list[str] = list(dict.fromkeys(default_tags + item_tags_list))

                        source = str(n_item.get("source") or payload.get("source") or diff_data.get("source", "mcp_agent"))

                        created_n = NoteManager.create_note(
                            note_type=nt,
                            deck=dk,
                            content_dict=fields,
                            tags=combined_tags,
                            source=source,
                        )
                        created_note_ids.append(created_n.id)

                    patch.target_id = created_note_ids[0] if created_note_ids else 0
                    patch.status = "applied"
                    patch.applied_at = datetime.datetime.now()
                    patch.save()

                cls._notify_mutation("batch_note_create", 0, {"created_note_ids": created_note_ids, "patch_id": patch_id})
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
    def sync_direct_edit(cls, patch_id: str, new_modified: Any) -> bool:
        """Met à jour le contenu proposé (modified) dans le diff_payload d'un patch en attente."""
        patch = cls.get_patch(patch_id)
        if not patch or patch.status != "pending":
            return False

        data = staged_payload_of(patch)
        if not data:
            return False

        if data.get("modified") == new_modified:
            return True

        data["modified"] = new_modified
        with db.atomic():
            patch.diff_payload = json.dumps(data, ensure_ascii=False)
            patch.save()

        logger.info("Patch %s synchronisé avec l'édition directe utilisateur.", patch_id)
        return True

    @classmethod
    def _notify_mutation(cls, mutation_type: str, target_id: int, details: dict[str, Any]) -> None:
        """Déclenche la notification sur le bus d'événements si disponible."""
        try:
            from ankiforge.services.ai.mcp_server import _notify_mcp_mutation

            _notify_mcp_mutation({"type": mutation_type, "target_id": target_id, **details})
        except Exception as e:
            logger.debug("Erreur notification mutation patch : %s", e)

    @classmethod
    def _notify_staged_patch(cls, patch_id: str, patch_type: str, target_id: int, title: str, details: dict[str, Any]) -> None:
        """Déclenche la notification de création de patch staged sur le bus d'événements et vers MCP."""
        try:
            from ankiforge.utils.event_bus import MCPPatchStagedEvent, event_bus

            event_bus.publish(
                MCPPatchStagedEvent(
                    patch_id=patch_id,
                    patch_type=patch_type,
                    target_id=target_id,
                    title=title,
                    details=details,
                )
            )
        except Exception as e:
            logger.debug("Erreur publication event_bus MCPPatchStagedEvent : %s", e)

        try:
            from ankiforge.services.ai.mcp_server import _notify_mcp_patch_staged

            _notify_mcp_patch_staged(
                {
                    "patch_id": patch_id,
                    "patch_type": patch_type,
                    "target_id": target_id,
                    "title": title,
                    **details,
                }
            )
        except Exception as e:
            logger.debug("Erreur notification listeners MCP patch staged : %s", e)

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
    StagedBundleModel,
    StagedPatchModel,
    db,
)

logger = logging.getLogger(__name__)


class StagedOverlay:
    """Contexte virtuel intra-bundle permettant la résolution des dépendances avant écriture physique."""

    def __init__(self, bundle_id: str) -> None:
        self.bundle_id = bundle_id
        self.created_decks: set[str] = set()
        self.renamed_decks: dict[str, str] = {}
        self.created_notes_first_fields: dict[str, list[str]] = {}
        self.deleted_notes: set[int] = set()

    def register_created_deck(self, deck_name: str) -> None:
        clean = deck_name.strip()
        if clean:
            self.created_decks.add(clean)

    def register_renamed_deck(self, old_name: str, new_name: str) -> None:
        old_clean = old_name.strip()
        new_clean = new_name.strip()
        if old_clean and new_clean:
            self.renamed_decks[old_clean] = new_clean

    def register_created_note_first_field(self, deck_name: str, first_field_value: str) -> None:
        dk_clean = deck_name.strip()
        val_clean = first_field_value.strip().lower()
        if dk_clean and val_clean:
            self.created_notes_first_fields.setdefault(dk_clean, []).append(val_clean)

    def register_deleted_note(self, note_id: int) -> None:
        if note_id > 0:
            self.deleted_notes.add(note_id)

    def is_deck_available(self, deck_name: str) -> bool:
        clean = deck_name.strip()
        if not clean:
            return False
        return clean in self.created_decks or clean in self.renamed_decks.values()

    def has_duplicate_first_field(self, deck_name: str, first_field_value: str) -> bool:
        dk_clean = deck_name.strip()
        val_clean = first_field_value.strip().lower()
        existing = self.created_notes_first_fields.get(dk_clean, [])
        return val_clean in existing

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "created_decks": sorted(list(self.created_decks)),
            "renamed_decks": dict(self.renamed_decks),
            "created_notes_count": sum(len(v) for v in self.created_notes_first_fields.values()),
            "deleted_notes": sorted(list(self.deleted_notes)),
        }


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

    _active_bundles: dict[str, StagedOverlay] = {}
    _current_bundle_id: str | None = None

    @classmethod
    def create_patch(
        cls,
        patch_type: str,
        target_id: int = 0,
        original_version_id: int | None = None,
        diff_payload: dict[str, Any] | None = None,
        bundle_id: str | None = None,
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

        # Résolution du bundle (uniquement s'il est en cours de construction)
        target_bundle_id = bundle_id or cls._current_bundle_id
        bundle_obj: StagedBundleModel | None = None
        step_order = 1

        if target_bundle_id:
            candidate = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == target_bundle_id.strip())
            if candidate and candidate.status == "building":
                bundle_obj = candidate

        with db.atomic():
            if bundle_obj:
                step_order = bundle_obj.total_steps + 1
                bundle_obj.total_steps = step_order
                bundle_obj.save()

            patch = StagedPatchModel.create(
                patch_id=p_id,
                bundle=bundle_obj,
                step_order=step_order,
                patch_type=patch_type,
                target_id=target_id,
                original_version_id=original_version_id,
                diff_payload=serialized_payload,
                status="pending",
                created_at=datetime.datetime.now(),
            )

        # Alimentation du StagedOverlay si rattaché à un bundle
        if bundle_obj:
            overlay = cls._active_bundles.get(bundle_obj.bundle_id)
            if overlay:
                if patch_type in ("deck_create", "create_deck"):
                    dk = payload.get("deck_name") or payload.get("deck")
                    if dk:
                        overlay.register_created_deck(str(dk))
                elif patch_type in ("deck_rename", "rename_deck"):
                    old_dk = payload.get("old_name") or payload.get("deck_name")
                    new_dk = payload.get("new_name")
                    if old_dk and new_dk:
                        overlay.register_renamed_deck(str(old_dk), str(new_dk))
                elif patch_type == "note_create":
                    dk = payload.get("deck_name") or payload.get("deck")
                    f_dict = payload.get("fields") or {}
                    first_f = next(iter(f_dict.values()), "") if isinstance(f_dict, dict) and f_dict else ""
                    if dk and first_f:
                        overlay.register_created_note_first_field(str(dk), str(first_f))
                elif patch_type == "batch_note_create":
                    notes = payload.get("notes") or []
                    for n in notes:
                        if isinstance(n, dict):
                            dk = n.get("deck") or payload.get("default_deck")
                            f_dict = n.get("fields") or {}
                            first_f = next(iter(f_dict.values()), "") if isinstance(f_dict, dict) and f_dict else ""
                            if dk and first_f:
                                overlay.register_created_note_first_field(str(dk), str(first_f))
                elif patch_type in ("note_delete", "card_delete", "batch_note_delete", "batch_card_deletion"):
                    t_id = target_id or payload.get("note_id") or 0
                    if t_id:
                        overlay.register_deleted_note(int(t_id))
                    for n_id in payload.get("note_ids", []):
                        if n_id:
                            overlay.register_deleted_note(int(n_id))

        logger.info("Patch en attente créé : %s (type: %s, cible: %s, bundle: %s, step: %s)", p_id, patch_type, target_id, bundle_obj.bundle_id if bundle_obj else None, step_order)

        # Les patchs individuels hors bundle ou scellés notifient immédiatement l'IHM
        if not bundle_obj or bundle_obj.status != "building":
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

                # Prise en charge des tags modifiés (remplacement ou incrémental)
                if "modified_tags" in diff_data:
                    raw_tags = diff_data["modified_tags"]
                    if isinstance(raw_tags, list):
                        note.tags = " ".join(t.strip() for t in raw_tags if t and str(t).strip())
                    elif isinstance(raw_tags, str):
                        note.tags = raw_tags.strip()
                    note.save()

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
            target_nid = patch.target_id or diff_data.get("note_id")
            note = NoteModel.get_or_none(NoteModel.id == target_nid) if target_nid else None
            if not note:
                return {"status": "error", "message": f"Note #{target_nid} introuvable en base."}

            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            if patch.original_version_id is not None and (not active_v or active_v.id != patch.original_version_id):
                return {
                    "status": "conflict",
                    "message": f"Conflit de version : la note #{note.id} a été modifiée après la création de la scission.",
                    "patch_id": patch_id,
                }

            cards_to_apply = diff_data.get("modified") or diff_data.get("new_cards") or diff_data.get("cards") or []
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

            name = str(model_data.get("name") or (diff_data.get("name") if isinstance(diff_data, dict) else "") or "").strip()
            fields_schema = model_data.get("fields_schema") or (diff_data.get("fields_schema") if isinstance(diff_data, dict) else []) or []
            templates = model_data.get("templates") or (diff_data.get("templates") if isinstance(diff_data, dict) else []) or []
            css_style = model_data.get("css_style") or model_data.get("css") or (diff_data.get("css_style") if isinstance(diff_data, dict) else "") or ""
            description = model_data.get("description") or (diff_data.get("description") if isinstance(diff_data, dict) else "") or ""
            on_conflict = str(model_data.get("on_conflict") or (diff_data.get("on_conflict") if isinstance(diff_data, dict) else "error") or "error")

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
            note_ids = payload.get("note_ids") or (diff_data.get("note_ids") if isinstance(diff_data, dict) else []) or []
            target_model = (
                payload.get("target_model")
                or payload.get("target_model_name")
                or payload.get("target_model_id")
                or (diff_data.get("target_model") if isinstance(diff_data, dict) else None)
                or (diff_data.get("target_model_name") if isinstance(diff_data, dict) else None)
                or (diff_data.get("target_model_id") if isinstance(diff_data, dict) else None)
            )
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
                    "cards_preserved": res.get("cards_preserved", 0),
                    "cards_created": res.get("cards_created", 0),
                    "cards_deleted": res.get("cards_deleted", 0),
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

        # 7bis. Type DECK_CREATE (Création d'un paquet)
        if p_type in ("deck_create", "create_deck"):
            from ankiforge.repositories.deck_repository import DeckRepository

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

            cls._notify_mutation("create_deck", created_deck.id, {"deck_id": created_deck.id, "deck_name": created_deck.name, "is_new": True})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "deck_id": created_deck.id,
                "deck_name": created_deck.name,
                "message": f"Paquet '{created_deck.name}' créé avec succès.",
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
            target_deck = DeckModel.get_or_none(DeckModel.id == int(deck_id)) if deck_id else None
            if not target_deck and deck_name:
                target_deck = DeckModel.get_or_none(DeckModel.name == deck_name)

            if not target_deck:
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
                        deck=target_deck,
                        content_dict=fields,
                        tags=tags_list,
                        source=source,
                    )
                    patch.target_id = created_note.id
                    patch.status = "applied"
                    patch.applied_at = datetime.datetime.now()
                    patch.save()

                cls._notify_mutation("note_create", created_note.id, {"note_id": created_note.id, "patch_id": patch_id, "deck_id": target_deck.id})
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

        # 9. Type BATCH_NOTE_CREATE (Création groupée de notes par lot)
        if p_type == "batch_note_create":
            from ankiforge.services.cards.note_manager import NoteManager

            payload = diff_data.get("modified") if isinstance(diff_data.get("modified"), dict) else diff_data
            if not isinstance(payload, dict):
                return {"status": "error", "message": "Payload invalide pour la création de notes par lot.", "patch_id": patch_id}

            raw_notes = payload.get("notes")
            if isinstance(raw_notes, list) and raw_notes:
                notes_list = raw_notes
            elif isinstance(diff_data.get("notes"), list) and diff_data["notes"]:
                notes_list = diff_data["notes"]
            elif isinstance(raw_notes, str):
                try:
                    from ankiforge.services.ai.mcp_tool_registry import robust_json_loads

                    parsed = robust_json_loads(raw_notes)
                    if isinstance(parsed, list):
                        notes_list = parsed
                    else:
                        import ast

                        parsed_ast = ast.literal_eval(raw_notes)
                        notes_list = parsed_ast if isinstance(parsed_ast, list) else []
                except Exception:
                    notes_list = diff_data.get("notes", []) if isinstance(diff_data.get("notes"), list) else []
            else:
                notes_list = diff_data.get("notes", []) if isinstance(diff_data.get("notes"), list) else []

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

        # 10. Type DECK_RENAME
        if p_type in ("deck_rename", "rename_deck"):
            from ankiforge.repositories.deck_repository import DeckRepository

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

            cls._notify_mutation("deck_rename", deck.id, {"deck_id": deck.id, "old_name": old_name, "new_name": new_name})
            return {"status": "applied", "patch_id": patch_id, "deck_id": deck.id, "new_name": new_name}

        # 11. Type SET_TAGS / SET_TAGS_BULK
        if p_type in ("set_tags", "set_tags_bulk", "tag_add", "tag_remove", "tags"):
            from ankiforge.services.cards.bulk_hygiene_service import BulkHygieneService

            note_ids = diff_data.get("note_ids") or ([patch.target_id] if patch.target_id else [])
            tags = diff_data.get("tags") or diff_data.get("tags_added") or []
            mode = str(diff_data.get("mode") or ("add" if p_type == "tag_add" else ("remove" if p_type == "tag_remove" else "add")))

            res = BulkHygieneService.set_tags_bulk(note_ids=note_ids, tags=tags, mode=mode)
            if res.get("status") == "error":
                return {"status": "error", "message": res.get("message", "Erreur tagging"), "patch_id": patch_id}

            with db.atomic():
                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            cls._notify_mutation("set_tags_bulk", patch.target_id, {"note_ids": note_ids, "tags": tags, "mode": mode})
            return {"status": "applied", "patch_id": patch_id, "note_ids": note_ids, "tags": tags}

        # 12. Type CARD_DELETE / NOTE_DELETE
        if p_type in ("card_delete", "note_delete", "batch_card_deletion", "batch_note_delete"):
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
                for note in notes_to_delete:
                    note.delete_instance(recursive=True)
                deleted_count = len(notes_to_delete)
                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            cls._notify_mutation("note_delete", patch.target_id, {"deleted_count": deleted_count, "note_ids": target_ids, "patch_id": patch_id})
            return {"status": "applied", "patch_id": patch_id, "deleted_count": deleted_count, "note_ids": target_ids}

        # 12bis. Type EMPTY_CARDS_DELETE
        if p_type in ("empty_cards_delete", "delete_empty_cards"):
            card_ids = diff_data.get("card_ids") or []
            if not card_ids:
                return {"status": "error", "message": "Aucune carte vide ciblée pour suppression.", "patch_id": patch_id}

            with db.atomic():
                deleted_count = CardModel.delete().where(CardModel.id.in_(card_ids)).execute()
                patch.status = "applied"
                patch.applied_at = datetime.datetime.now()
                patch.save()

            cls._notify_mutation("delete_empty_cards", 0, {"card_ids": card_ids, "deleted_count": deleted_count, "patch_id": patch_id})
            return {
                "status": "applied",
                "patch_id": patch_id,
                "deleted_count": deleted_count,
                "card_ids": card_ids,
                "message": f"{deleted_count} carte(s) vide(s) supprimée(s) avec succès.",
            }

        # 13. Type DECK_DELETE
        if p_type in ("deck_delete", "delete_deck"):
            from ankiforge.repositories.deck_repository import DeckRepository

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

            cls._notify_mutation("deck_delete", deck.id, {"deck_id": deck.id, "deck_name": deck_name})
            return {"status": "applied", "patch_id": patch_id, "deck_id": deck.id}

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
    def abort_staged_patch(cls, patch_id: str, reason: str = "") -> dict[str, Any]:
        """Annule un patch staged précis sans modifier ses éventuels patches frères."""
        patch = cls.get_patch(patch_id)
        if not patch:
            return {"status": "error", "message": f"Patch '{patch_id}' introuvable."}

        if patch.status != "pending":
            return {
                "status": "error",
                "patch_id": patch.patch_id,
                "message": f"Le patch '{patch.patch_id}' ne peut pas être annulé (statut actuel: {patch.status}).",
            }

        bundle_id = patch.bundle.bundle_id if patch.bundle else None
        with db.atomic():
            patch.status = "aborted"
            patch.save()

        logger.info("Patch annulé : %s (raison: %s)", patch.patch_id, reason)
        return {
            "status": "aborted",
            "patch_id": patch.patch_id,
            "bundle_id": bundle_id,
            "reason": reason,
            "message": f"Le patch '{patch.patch_id}' a été annulé.",
        }

    @classmethod
    def sync_direct_edit(cls, patch_id: str, new_modified: Any) -> bool:
        """Met à jour le contenu proposé (modified ou payload complet) dans le diff_payload d'un patch en attente."""
        patch = cls.get_patch(patch_id)
        if not patch or patch.status != "pending":
            return False

        data = staged_payload_of(patch)
        if not data:
            return False

        if isinstance(new_modified, dict):
            # Si le patch contient déjà une section 'modified' pour les cartes
            if "modified" in data and not any(k in new_modified for k in ("deck_name", "tags", "tags_added", "new_name", "reason")):
                data["modified"] = new_modified
            else:
                data.update(new_modified)
                if "modified" in data and isinstance(data["modified"], dict):
                    data["modified"].update(new_modified)
        else:
            data["modified"] = new_modified

        with db.atomic():
            patch.diff_payload = json.dumps(data, ensure_ascii=False)
            patch.save()

        logger.info("Patch %s synchronisé avec l'édition directe utilisateur.", patch_id)
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Moteur de Session & Staged Bundles (ADR 0043)
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def begin_bundle(cls, title: str, explanation: str = "") -> str:
        """Démarre une session de groupe (Staged Bundle) en statut 'building'."""
        b_id = f"bundle_{uuid.uuid4().hex[:10]}"
        clean_title = title.strip() or "Nouveau Bundle"
        clean_exp = explanation.strip()

        with db.atomic():
            StagedBundleModel.create(
                bundle_id=b_id,
                title=clean_title,
                explanation=clean_exp,
                status="building",
                total_steps=0,
                current_step=1,
                created_at=datetime.datetime.now(),
            )

        cls._active_bundles[b_id] = StagedOverlay(bundle_id=b_id)
        cls._current_bundle_id = b_id
        logger.info("Session de bundle ouverte : %s ('%s')", b_id, clean_title)
        return b_id

    @classmethod
    def get_active_bundle_id(cls) -> str | None:
        """Retourne l'identifiant du bundle actif en cours de construction."""
        return cls._current_bundle_id

    @classmethod
    def get_active_bundle(cls) -> StagedBundleModel | None:
        """Retourne l'instance du bundle actif en cours de construction."""
        if not cls._current_bundle_id:
            return None
        return StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == cls._current_bundle_id)

    @classmethod
    def get_active_overlay(cls, bundle_id: str | None = None) -> StagedOverlay | None:
        """Retourne l'overlay virtuel du bundle spécifié ou du bundle actif."""
        target_id = bundle_id or cls._current_bundle_id
        if not target_id:
            return None
        return cls._active_bundles.get(target_id)

    @classmethod
    def commit_bundle(cls, bundle_id: str) -> dict[str, Any]:
        """Scelle un bundle au statut 'pending' et notifie l'IHM."""
        b_id = bundle_id.strip()
        bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == b_id)
        if not bundle:
            raise ValueError(f"Bundle '{b_id}' introuvable.")

        if bundle.status != "building":
            raise ValueError(f"Le bundle '{b_id}' ne peut pas être scellé (statut actuel: '{bundle.status}').")

        if bundle.total_steps < 1:
            raise ValueError(f"Le bundle '{b_id}' ne contient aucune étape et ne peut pas être scellé.")

        with db.atomic():
            bundle.status = "pending"
            bundle.created_at = datetime.datetime.now()
            bundle.save()

        if cls._current_bundle_id == b_id:
            cls._current_bundle_id = None

        logger.info("Bundle scellé avec succès : %s ('%s', %d étapes)", bundle.bundle_id, bundle.title, bundle.total_steps)

        cls._notify_bundle_staged(
            bundle_id=bundle.bundle_id,
            title=bundle.title,
            total_steps=bundle.total_steps,
            details={
                "bundle_id": bundle.bundle_id,
                "title": bundle.title,
                "explanation": bundle.explanation,
                "total_steps": bundle.total_steps,
            },
        )

        return {
            "status": "staged",
            "bundle_id": bundle.bundle_id,
            "title": bundle.title,
            "total_steps": bundle.total_steps,
        }

    @classmethod
    def abort_bundle(cls, bundle_id: str) -> bool:
        """Supprime le bundle en cours et toutes ses étapes."""
        b_id = bundle_id.strip()
        bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == b_id)
        if not bundle:
            return False

        with db.atomic():
            StagedPatchModel.delete().where(StagedPatchModel.bundle == bundle).execute()
            bundle.delete_instance()

        cls._active_bundles.pop(b_id, None)
        if cls._current_bundle_id == b_id:
            cls._current_bundle_id = None

        logger.info("Bundle %s annulé et supprimé.", b_id)
        return True

    @classmethod
    def reject_bundle_step(cls, bundle_id: str, step_order: int, reason: str = "") -> dict[str, Any]:
        """Arrêt en cascade (Fail-Fast Reject) : rejette l'étape courante et toutes les suivantes."""
        b_id = bundle_id.strip()
        bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == b_id)
        if not bundle:
            return {"status": "error", "message": f"Bundle '{b_id}' introuvable."}

        with db.atomic():
            patches_to_reject = list(StagedPatchModel.select().where((StagedPatchModel.bundle == bundle) & (StagedPatchModel.step_order >= step_order) & (StagedPatchModel.status == "pending")))
            for p in patches_to_reject:
                p.status = "rejected"
                p.save()

            rejected_count = len(patches_to_reject)

            applied_count = StagedPatchModel.select().where((StagedPatchModel.bundle == bundle) & (StagedPatchModel.status == "applied")).count()
            pending_count = StagedPatchModel.select().where((StagedPatchModel.bundle == bundle) & (StagedPatchModel.status == "pending")).count()

            if pending_count == 0:
                bundle.status = "applied" if (applied_count == bundle.total_steps and bundle.total_steps > 0) else ("partial" if applied_count > 0 else "rejected")
            else:
                bundle.status = "partial" if (applied_count > 0 or rejected_count > 0) else "pending"
            bundle.save()

        logger.info(
            "Fail-Fast Reject sur bundle %s (étape >= %d) : %d étapes rejetées. Raison: %s",
            b_id,
            step_order,
            rejected_count,
            reason,
        )
        return {
            "status": "rejected",
            "bundle_id": b_id,
            "rejected_steps_count": rejected_count,
            "reason": reason,
        }

    @classmethod
    def apply_bundle_step(cls, bundle_id: str, step_order: int) -> dict[str, Any]:
        """Applique l'étape ordonnée spécifiée du bundle et met à jour l'avancement."""
        b_id = bundle_id.strip()
        bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == b_id)
        if not bundle:
            return {"status": "error", "message": f"Bundle '{b_id}' introuvable."}

        patch = StagedPatchModel.get_or_none((StagedPatchModel.bundle == bundle) & (StagedPatchModel.step_order == step_order))
        if not patch:
            return {"status": "error", "message": f"Étape {step_order} introuvable dans le bundle '{b_id}'."}

        res = cls.apply_staged_patch(patch.patch_id)
        if res.get("status") == "applied":
            bundle.current_step = step_order + 1
            all_applied = not StagedPatchModel.select().where((StagedPatchModel.bundle == bundle) & (StagedPatchModel.status != "applied")).exists()
            if all_applied:
                bundle.status = "applied"
                bundle.applied_at = datetime.datetime.now()
            bundle.save()
        return res

    @classmethod
    def apply_bundle_all(cls, bundle_id: str) -> dict[str, Any]:
        """Applique l'intégralité des étapes restantes du bundle sous transaction atomique SQLite unique."""
        b_id = bundle_id.strip()
        bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == b_id)
        if not bundle:
            return {"status": "error", "message": f"Bundle '{b_id}' introuvable."}

        patches = list(StagedPatchModel.select().where((StagedPatchModel.bundle == bundle) & (StagedPatchModel.status == "pending")).order_by(StagedPatchModel.step_order.asc()))

        if not patches:
            return {"status": "error", "message": f"Aucune étape en attente à appliquer dans le bundle '{b_id}'."}

        applied_count = 0
        terminal_count = StagedPatchModel.select().where((StagedPatchModel.bundle == bundle) & (StagedPatchModel.status.in_(("aborted", "rejected")))).count()
        with db.atomic() as txn:
            for p in patches:
                res = cls.apply_staged_patch(p.patch_id)
                if res.get("status") != "applied":
                    txn.rollback()
                    return {
                        "status": "error",
                        "message": f"Échec application étape #{p.step_order} ({p.patch_id}) : {res.get('message')}",
                        "failed_step": p.step_order,
                        "patch_id": p.patch_id,
                    }
                applied_count += 1

            bundle.status = "partial" if terminal_count else "applied"
            bundle.applied_at = datetime.datetime.now()
            bundle.current_step = bundle.total_steps + 1
            bundle.save()

        return {
            "status": "partial" if terminal_count else "applied",
            "bundle_id": b_id,
            "applied_steps_count": applied_count,
            "aborted_or_rejected_steps_count": terminal_count,
        }

    @classmethod
    def get_staged_pending_operations(cls, bundle_id: str = "") -> dict[str, Any]:
        """Consulte les propositions d'opérations et bundles en attente."""
        b_id = bundle_id.strip()
        if b_id:
            bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == b_id)
            if not bundle:
                return {"status": "error", "message": f"Bundle '{b_id}' introuvable."}
            patches = list(StagedPatchModel.select().where(StagedPatchModel.bundle == bundle).order_by(StagedPatchModel.step_order.asc()))
            overlay = cls.get_active_overlay(bundle.bundle_id)
            return {
                "status": "success",
                "bundle": {
                    "bundle_id": bundle.bundle_id,
                    "title": bundle.title,
                    "explanation": bundle.explanation,
                    "status": bundle.status,
                    "total_steps": bundle.total_steps,
                    "current_step": bundle.current_step,
                },
                "steps": [
                    {
                        "patch_id": p.patch_id,
                        "step_order": p.step_order,
                        "patch_type": p.patch_type,
                        "status": p.status,
                        "payload": staged_payload_of(p),
                    }
                    for p in patches
                ],
                "overlay": overlay.to_dict() if overlay else None,
            }

        bundles = list(StagedBundleModel.select().where(StagedBundleModel.status.in_(["building", "pending"])).order_by(StagedBundleModel.created_at.desc()))
        standalone_patches = list(StagedPatchModel.select().where(StagedPatchModel.bundle.is_null(), StagedPatchModel.status == "pending").order_by(StagedPatchModel.created_at.asc()))
        return {
            "status": "success",
            "active_bundle_id": cls._current_bundle_id,
            "bundles": [
                {
                    "bundle_id": b.bundle_id,
                    "title": b.title,
                    "explanation": b.explanation,
                    "status": b.status,
                    "total_steps": b.total_steps,
                    "current_step": b.current_step,
                }
                for b in bundles
            ],
            "standalone_patches": [
                {
                    "patch_id": p.patch_id,
                    "patch_type": p.patch_type,
                    "status": p.status,
                    "payload": staged_payload_of(p),
                }
                for p in standalone_patches
            ],
        }

    @classmethod
    def _notify_bundle_staged(cls, bundle_id: str, title: str, total_steps: int, details: dict[str, Any]) -> None:
        """Déclenche la notification de scellement d'un staged bundle."""
        try:
            from ankiforge.utils.event_bus import MCPBundleStagedEvent, event_bus

            event_bus.publish(
                MCPBundleStagedEvent(
                    bundle_id=bundle_id,
                    title=title,
                    total_steps=total_steps,
                    details=details,
                )
            )
        except Exception as e:
            logger.debug("Erreur publication event_bus MCPBundleStagedEvent : %s", e)

        try:
            from ankiforge.services.ai.mcp_server import _notify_mcp_bundle_staged

            _notify_mcp_bundle_staged(
                {
                    "bundle_id": bundle_id,
                    "title": title,
                    "total_steps": total_steps,
                    **details,
                }
            )
        except Exception as e:
            logger.debug("Erreur notification listeners MCP bundle staged : %s", e)

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

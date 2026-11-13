"""Registre persistant pour la gestion des patchs chirurgicaux (Two-Phase Commit)."""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import Any

from ankidraft.database.models import (
    NoteModel,
    NoteVersionModel,
    StagedBundleModel,
    StagedPatchModel,
    db,
)
from ankidraft.services.ai.patch_appliers import get_patch_applier

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

        # Notification systématique vers l'IHM (y compris pendant la construction du bundle)
        details_enriched = dict(payload)
        if bundle_obj:
            details_enriched["bundle_id"] = bundle_obj.bundle_id
        cls._notify_staged_patch(
            patch_id=p_id,
            patch_type=patch_type,
            target_id=target_id,
            title=str(payload.get("title") or f"Proposition — {patch_type} #{target_id}"),
            details=details_enriched,
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

        if not isinstance(diff_data, dict):
            diff_data = {}

        applier = get_patch_applier(patch.patch_type)
        if not applier:
            return {"status": "error", "message": f"Type de patch non supporté : '{patch.patch_type}'."}

        return applier.apply(patch, diff_data, notify_mutation=cls._notify_mutation)

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
            patch.reason = reason or ""
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
        cls._notify_bundle_staged(
            bundle_id=b_id,
            title=clean_title,
            total_steps=0,
            status="building",
        )
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
            status="pending",
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
    def abort_bundle(cls, bundle_id: str, reason: str = "") -> bool:
        """Marque le bundle et ses étapes en cours comme annulés sans les supprimer physiquement."""
        b_id = bundle_id.strip()
        bundle = StagedBundleModel.get_or_none(StagedBundleModel.bundle_id == b_id)
        if not bundle:
            return False

        with db.atomic():
            StagedPatchModel.update(status="aborted").where((StagedPatchModel.bundle == bundle) & (StagedPatchModel.status == "pending")).execute()
            bundle.status = "aborted"
            bundle.explanation = f"{bundle.explanation}\n[Abort: {reason}]".strip() if reason else bundle.explanation
            bundle.save()

        cls._active_bundles.pop(b_id, None)
        if cls._current_bundle_id == b_id:
            cls._current_bundle_id = None

        logger.info("Bundle %s marqué comme annulé (aborted).", b_id)
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
    def _notify_bundle_staged(cls, bundle_id: str, title: str, total_steps: int, status: str = "pending", details: dict[str, Any] | None = None) -> None:
        """Déclenche la notification de scellement d'un staged bundle."""
        details = details or {}
        try:
            from ankidraft.utils.event_bus import MCPBundleStagedEvent, event_bus

            event_bus.publish(
                MCPBundleStagedEvent(
                    bundle_id=bundle_id,
                    title=title,
                    total_steps=total_steps,
                    status=status,
                    details=details,
                )
            )
        except Exception as e:
            logger.debug("Erreur publication event_bus MCPBundleStagedEvent : %s", e)

        try:
            from ankidraft.services.ai.mcp_server import _notify_mcp_bundle_staged

            _notify_mcp_bundle_staged(
                {
                    "bundle_id": bundle_id,
                    "title": title,
                    "total_steps": total_steps,
                    "status": status,
                    **details,
                }
            )
        except Exception as e:
            logger.debug("Erreur notification listeners MCP bundle staged : %s", e)

    @classmethod
    def _notify_mutation(cls, mutation_type: str, target_id: int, details: dict[str, Any]) -> None:
        """Déclenche la notification sur le bus d'événements si disponible."""
        try:
            from ankidraft.services.ai.mcp_server import _notify_mcp_mutation

            _notify_mcp_mutation({"type": mutation_type, "target_id": target_id, **details})
        except Exception as e:
            logger.debug("Erreur notification mutation patch : %s", e)

    @classmethod
    def _notify_staged_patch(cls, patch_id: str, patch_type: str, target_id: int, title: str, details: dict[str, Any]) -> None:
        """Déclenche la notification de création de patch staged sur le bus d'événements et vers MCP."""
        try:
            from ankidraft.utils.event_bus import MCPPatchStagedEvent, event_bus

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
            from ankidraft.services.ai.mcp_server import _notify_mcp_patch_staged

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

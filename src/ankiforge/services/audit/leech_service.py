"""Service de diagnostic et détection des cartes sangsues (Leeches) pour AnkiForge (ADR 0019).

Gère le filtrage dual (tag officiel Anki 'leech' et rechutes répétées) et la préparation
des métriques FSRS pour la restructuration via le Linter Wozniak.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteVersionModel,
)
from ankiforge.utils.tags import parse_note_tags

logger = logging.getLogger(__name__)


class LeechService:
    """Service d'analyse et d'extraction des cartes sangsues pour l'Atelier d'Audit et le cockpit SRS."""

    @classmethod
    def get_leech_cards(
        cls,
        deck_id: int | None = None,
        include_high_lapses: bool = False,
        lapse_threshold: int = 4,
    ) -> list[dict[str, Any]]:
        """Récupère la liste ordonnée des cartes sangsues selon la politique ADR 0019.

        Args:
            deck_id: Identifiant optionnel du paquet pour restreindre la recherche.
            include_high_lapses: Si True, inclut aussi les cartes dont lapses >= lapse_threshold
                                 même si elles ne portent pas encore le tag 'leech'.
            lapse_threshold: Seuil d'échecs pour le mode de détection préventif (défaut: 4).

        Returns:
            Liste des cartes sangsues ordonnée par sévérité
                                  (lapses décroissant, puis stability croissante).
        """
        try:
            query = (
                CardModel.select(CardModel, NoteModel, DeckModel)
                .join(NoteModel, on=(CardModel.note == NoteModel.id))
                .switch(CardModel)
                .join(DeckModel, on=(CardModel.deck == DeckModel.id))
                .where((NoteModel.status != "archived") | (NoteModel.status.is_null()))
                .where(CardModel.lapses > 0)
            )

            if deck_id is not None:
                query = query.where(CardModel.deck == deck_id)

            # Pré-filtrage SQL pour minimiser les cartes rapatriées en mémoire
            condition = NoteModel.tags.contains("leech") if not include_high_lapses else (NoteModel.tags.contains("leech") | (CardModel.lapses >= lapse_threshold))
            query = query.where(condition)

            query = query.order_by(CardModel.lapses.desc(), CardModel.stability.asc())

            cards = list(query)
            if not cards:
                return []

            # Préchargement des versions actives pour éviter les requêtes N+1
            note_ids = list({c.note_id for c in cards})
            active_versions = {
                v.note.id: v
                for v in NoteVersionModel.select().where(
                    (NoteVersionModel.note.in_(note_ids)) & (NoteVersionModel.is_active == True)  # noqa: E712
                )
            }

            results: list[dict[str, Any]] = []
            for card in cards:
                note = card.note
                parsed_tags = parse_note_tags(note.tags)
                is_leech_tagged = any(t.lower() == "leech" for t in parsed_tags)
                card_lapses = int(getattr(card, "lapses", 0) or 0)
                is_high_lapses = card_lapses >= lapse_threshold
                if card_lapses <= 0:
                    continue

                # Validation fine de la condition duale (évite les faux positifs sur 'leechcraft', etc.)
                if not include_high_lapses and not is_leech_tagged:
                    continue
                if include_high_lapses and not (is_leech_tagged or is_high_lapses):
                    continue

                active_v = active_versions.get(note.id)
                content_dict: dict[str, Any] = {}
                if active_v and active_v.content:
                    try:
                        content_dict = json.loads(str(active_v.content))
                    except Exception:
                        content_dict = {"Recto": str(active_v.content)}

                # Extraction des extraits recto / verso
                front_text = str(content_dict.get("Recto") or content_dict.get("Front") or content_dict.get("Texte") or content_dict.get("Text") or content_dict.get("question") or "").strip()

                back_text = str(content_dict.get("Verso") or content_dict.get("Back") or content_dict.get("reponse") or content_dict.get("Réponse") or "").strip()

                # Libellé lisible de la face/template
                tmpl_idx = int(getattr(card, "template_index", 0) or 0)
                face_name = f"Carte {tmpl_idx + 1}"
                if tmpl_idx == 0:
                    face_name = "Recto → Verso"
                elif tmpl_idx == 1:
                    face_name = "Verso → Recto"

                deck_obj = getattr(card, "deck", None)
                deck_name = deck_obj.name if deck_obj else "Sans paquet"

                results.append(
                    {
                        "card_id": card.id,
                        "note_id": note.id,
                        "deck_id": getattr(card, "deck_id", 0),
                        "deck_name": deck_name,
                        "template_index": tmpl_idx,
                        "face_name": face_name,
                        "lapses": card_lapses,
                        "ivl": int(getattr(card, "ivl", 0) or 0),
                        "reps": int(getattr(card, "reps", 0) or 0),
                        "stability": float(getattr(card, "stability", 0.0) or 0.0),
                        "difficulty": float(getattr(card, "difficulty", 0.0) or 0.0),
                        "retrievability": float(getattr(card, "retrievability", 0.0) or 0.0),
                        "is_suspended": bool(getattr(card, "is_suspended", False)),
                        "is_leech_tagged": is_leech_tagged,
                        "is_high_lapses": is_high_lapses,
                        "front_snippet": front_text[:120] + ("..." if len(front_text) > 120 else ""),
                        "back_snippet": back_text[:120] + ("..." if len(back_text) > 120 else ""),
                        "full_content": content_dict,
                        "note_tags": parsed_tags,
                    }
                )

            return results
        except Exception as e:
            logger.error("Erreur lors de la récupération des cartes sangsues : %s", e)
            return []

    @classmethod
    def count_leeches(
        cls,
        deck_id: int | None = None,
        include_high_lapses: bool = False,
        lapse_threshold: int = 4,
    ) -> int:
        """Compte rapidement le nombre de sangsues correspondant aux critères."""
        return len(
            cls.get_leech_cards(
                deck_id=deck_id,
                include_high_lapses=include_high_lapses,
                lapse_threshold=lapse_threshold,
            )
        )

    @classmethod
    def generate_split_proposal(
        cls,
        note_id: int,
        subcards: list[dict[str, Any]] | None = None,
        explanation: str = "",
    ) -> dict[str, Any]:
        """Prépare une proposition de scission atomique sous forme de StagedPatch (Two-Phase Commit, ADR 0019)."""
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        note = NoteModel.get_or_none(NoteModel.id == note_id)
        if not note:
            return {"status": "error", "message": f"Note #{note_id} introuvable."}

        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
        orig_content = active_v.content if active_v else "{}"

        try:
            orig_dict = json.loads(orig_content) if isinstance(orig_content, str) else orig_content
        except Exception:
            orig_dict = {"Recto": str(orig_content)}

        if subcards is None:
            r = str(orig_dict.get("Recto") or orig_dict.get("Front") or "")
            v = str(orig_dict.get("Verso") or orig_dict.get("Back") or "")
            extra = str(orig_dict.get("Champ Annexe Extra") or orig_dict.get("Extra") or "")
            subcards = [
                {
                    "Recto": f"Partie 1 : {r[:60]}",
                    "Verso": f"Élément clé 1 : {v[:60]}",
                    "Champ Annexe Extra": extra,
                },
                {
                    "Recto": f"Partie 2 : {r[60:120]}",
                    "Verso": f"Élément clé 2 : {v[60:120]}",
                    "Champ Annexe Extra": extra,
                },
            ]

        expl = explanation or f"Scission en {len(subcards)} cartes atomiques (Règle d'atomicité Wozniak)."
        patch_diff = {
            "type": "split",
            "note_id": note.id,
            "title": f"Proposition de Scission Atomique — Note #{note.id}",
            "original": orig_dict,
            "modified": subcards,
            "explanation": expl,
        }

        patch = StagedPatchRegistry.create_patch(
            patch_type="split",
            target_id=note.id,
            original_version_id=active_v.id if active_v else None,
            diff_payload=patch_diff,
        )

        return {
            "status": "staged_diff",
            "patch_id": patch.patch_id,
            "type": "split",
            "note_id": note.id,
            "title": f"Proposition de Scission Atomique — Note #{note.id}",
            "original": orig_dict,
            "modified": subcards,
            "explanation": expl,
            "metadata": {"note_id": note.id, "patch_id": patch.patch_id},
        }

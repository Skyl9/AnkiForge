"""Service de maintenance et d'hygiène en masse des notes, cartes et modèles AnkiForge.

Fournit des opérations atomiques et contrôlées (avec Two-Phase Commit pour les mutations larges) :
- Nettoyage et assainissement du HTML inline sur les champs de notes.
- Pose, suppression et remplacement de tags en masse via l'écrivain canonique.
- Suppression sécurisée de types de note inutilisés (0 note).
- Déplacement de cartes physiques entre paquets et sous-paquets hiérarchiques.
- Détection et suppression des cartes à front vide (Empty Cards).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
from ankiforge.utils.anki_renderer import _is_empty, render_card_text
from ankiforge.utils.c_bridge import levenshtein_distance
from ankiforge.utils.hierarchy import descendants_prefix
from ankiforge.utils.tags import (
    is_provenance_tag,
    parse_note_tags,
    serialize_note_tags,
)

logger = logging.getLogger(__name__)


@dataclass
class TagFrequency:
    """Occurrences d'un tag au sein de la collection."""

    tag: str
    count: int


@dataclass
class TagCluster:
    """Grappe de tags similaires (différences de casse ou proximité Levenshtein)."""

    cluster_id: str
    cluster_type: Literal["case", "levenshtein"]
    canonical_tag: str
    tags: list[TagFrequency]
    total_notes_count: int


@dataclass
class TagClustersReport:
    """Rapport d'analyse taxonomique des grappes de tags détectées."""

    case_clusters: list[TagCluster] = field(default_factory=list)
    levenshtein_clusters: list[TagCluster] = field(default_factory=list)
    total_clusters_count: int = 0
    total_notes_impacted: int = 0
    inspected_tags_count: int = 0
    inspected_notes_count: int = 0


@dataclass
class TagMergePlan:
    """Plan de fusion pour une grappe : tags sources et tag cible canonique."""

    tags_to_merge: list[str]
    target_tag: str


@dataclass
class TagMergeResult:
    """Résultat de l'exécution de la fusion en masse de tags."""

    success: bool
    merged_clusters_count: int = 0
    modified_notes_count: int = 0
    modified_note_ids: list[int] = field(default_factory=list)
    error_message: str | None = None


def parse_id_list(val: Any) -> list[int]:
    """Parse une collection d'identifiants (liste Python, entier unique, chaîne JSON ou liste séparée par virgules)."""

    if val is None:
        return []
    if isinstance(val, list):
        return [int(x) for x in val if str(x).strip()]
    if isinstance(val, int):
        return [val]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [int(x) for x in parsed if str(x).strip()]
            except Exception:
                pass
        return [int(x.strip()) for x in s.replace("[", "").replace("]", "").split(",") if x.strip()]
    return []


def parse_str_list(val: Any) -> list[str]:
    """Parse une collection de chaînes (liste Python, chaîne JSON ou liste séparée par virgules)."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                pass
        return [x.strip() for x in s.replace("[", "").replace("]", "").split(",") if x.strip()]
    return []


def clean_field_html(
    text: str,
    strip_tags: list[str] | None = None,
    strip_all_html: bool = False,
) -> str:
    """Nettoie le HTML inline d'un champ de note tout en préservant le contenu essentiel.

    - Si strip_all_html=True : supprime toutes les balises HTML sauf clozes, KaTeX et sons.
    - Sinon : supprime les styles inline, attributs parasites, balises <script>, <style>,
      <font>, spans vides ou sans style, tout en conservant les balises de structure saines.
    """
    if not text:
        return ""

    s = str(text)

    # 1. Mode suppression totale du HTML
    if strip_all_html:
        # Masquer temporairement les clozes, sons et blocs mathématiques
        placeholders: dict[str, str] = {}
        counter = 0

        def _sub_token(token: str) -> str:
            nonlocal counter
            key = f"___AF_PLACEHOLDER_{counter}___"
            counter += 1
            placeholders[key] = token
            return key

        # Clozes
        s = re.sub(r"\{\{c\d+::[\s\S]*?\}\}", lambda m: _sub_token(m.group(0)), s)
        # Sons
        s = re.sub(r"\[sound:[^\]]+\]", lambda m: _sub_token(m.group(0)), s, flags=re.IGNORECASE)
        # Math LaTeX
        s = re.sub(r"(\\\[[\s\S]*?\\\]|\\\(.*?\\\)|\$\$[\s\S]*?\$\$|(?<!\\)\$(?!\s).*?(?<!\s)\$)", lambda m: _sub_token(m.group(0)), s)

        s = re.sub(r"<[^>]+>", "", s)
        s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        s = re.sub(r"[ \t]+", " ", s).strip()

        for k, v in placeholders.items():
            s = s.replace(k, v)
        return s

    # 2. Mode nettoyage de styles inline
    # Supprimer les balises dangereuses ou de style interne
    s = re.sub(r"<(script|style|iframe)[^>]*>[\s\S]*?</\1>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<!--[\s\S]*?-->", "", s)

    # Supprimer les balises spécifiques si demandées
    if strip_tags:
        for t in strip_tags:
            t_clean = t.strip().lower()
            if t_clean:
                s = re.sub(rf"</?{re.escape(t_clean)}\b[^>]*>", "", s, flags=re.IGNORECASE)

    # Retirer les attributs de style inline, couleur, police et alignement
    s = re.sub(r"""\s*\b(style|color|face|size|lang|dir)\s*=\s*(["']).*?\2""", "", s, flags=re.IGNORECASE)
    s = re.sub(r"""\s*\b(style|color|face|size|lang|dir)\s*=\s*[^\s>]+""", "", s, flags=re.IGNORECASE)

    # Nettoyer class="..." sauf si elle contient cloze
    def _clean_class_attr(match: re.Match[str]) -> str:
        attr_val = match.group(0)
        if "cloze" in attr_val.lower():
            return attr_val
        return ""

    s = re.sub(r"""\s*\bclass\s*=\s*(["']).*?\1""", _clean_class_attr, s, flags=re.IGNORECASE)

    s = re.sub(r"</?font\b[^>]*>", "", s, flags=re.IGNORECASE)

    # Déballer les spans vides ou devenus sans attributs <span >...</span>
    for _ in range(4):
        prev = s
        s = re.sub(r"<span\s*>([\s\S]*?)</span>", r"\1", s, flags=re.IGNORECASE)
        if s == prev:
            break

    for _ in range(3):
        prev = s
        s = re.sub(r"<(p|div|span|b|i|u|strong|em)\b[^>]*>\s*</\1>", "", s, flags=re.IGNORECASE)
        s = re.sub(r"<p>\s*&nbsp;\s*</p>", "", s, flags=re.IGNORECASE)
        s = re.sub(r"<div>\s*&nbsp;\s*</div>", "", s, flags=re.IGNORECASE)
        if s == prev:
            break

    s = re.sub(r"(<br\s*/?>\s*){3,}", "<br><br>", s, flags=re.IGNORECASE)

    return s.strip()


class BulkHygieneService:
    """Service appliquant les règles d'hygiène en masse (HTML, tags, modèles, cartes)."""

    @classmethod
    def sanitize_notes_html(
        cls,
        note_ids: Sequence[int],
        strip_tags: list[str] | None = None,
        strip_all_html: bool = False,
        force_apply: bool = False,
        stage_threshold: int = 5,
    ) -> dict[str, Any]:
        """Nettoie le HTML inline des champs d'un lot de notes.

        Si le nombre de notes modifiées dépasse stage_threshold et que force_apply est faux,
        l'opération est enregistrée sous forme de StagedPatch (Two-Phase Commit).
        """
        if not note_ids:
            return {"status": "error", "message": "Aucun identifiant de note fourni."}

        notes = list(NoteModel.select().where(NoteModel.id.in_(list(note_ids))))
        if not notes:
            return {"status": "error", "message": "Aucune note correspondante trouvée."}

        diffs: list[dict[str, Any]] = []

        for note in notes:
            active_v = NoteVersionModel.get_or_none(note=note, is_active=True)
            if not active_v:
                active_v = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

            if not active_v or not active_v.content:
                continue

            try:
                content = json.loads(active_v.content)
                if not isinstance(content, dict):
                    content = {"Front": str(active_v.content)}
            except Exception:
                content = {"Front": str(active_v.content)}

            modified = False
            new_content: dict[str, str] = {}
            for k, v in content.items():
                old_val = str(v)
                cleaned_val = clean_field_html(old_val, strip_tags=strip_tags, strip_all_html=strip_all_html)
                new_content[str(k)] = cleaned_val
                if cleaned_val != old_val:
                    modified = True

            if modified:
                diffs.append(
                    {
                        "note_id": note.id,
                        "before": content,
                        "after": new_content,
                    }
                )

        if not diffs:
            return {
                "status": "no_change",
                "modified_count": 0,
                "message": "Aucune modification nécessaire : les champs sont déjà sains.",
            }

        # Two-Phase Commit si mutation large
        if len(diffs) > stage_threshold and not force_apply:
            patch = StagedPatchRegistry.create_patch(
                patch_type="bulk_html_sanitize",
                target_id=0,
                diff_payload={
                    "type": "bulk_html_sanitize",
                    "note_ids": [d["note_id"] for d in diffs],
                    "diffs": diffs,
                    "title": f"Nettoyage HTML en masse ({len(diffs)} notes)",
                    "explanation": f"Suppression des styles inline et balises superflues sur {len(diffs)} note(s).",
                },
            )
            return {
                "status": "staged_diff",
                "patch_id": patch.patch_id,
                "type": "bulk_html_sanitize",
                "modified_count": len(diffs),
                "total_inspected": len(notes),
                "diffs": diffs,
                "message": (f"Nettoyage HTML préparé pour {len(diffs)} note(s). Enregistré sous le patch {patch.patch_id} (Two-Phase Commit). Appliquez avec preview_and_apply_patch."),
            }

        # Application directe sous transaction atomique
        applied_ids: list[int] = []
        with db.atomic():
            for d in diffs:
                nid = d["note_id"]
                target_note = next((n for n in notes if n.id == nid), None)
                if target_note:
                    target_note.add_version(d["after"], source="mcp_sanitize_html")
                    applied_ids.append(nid)

        logger.info("BulkHygieneService: %d notes nettoyées directement.", len(applied_ids))
        cls._notify_mutation("sanitize_fields_html", 0, {"note_ids": applied_ids})

        return {
            "status": "applied",
            "modified_count": len(applied_ids),
            "modified_note_ids": applied_ids,
            "message": f"{len(applied_ids)} note(s) nettoyée(s) avec succès.",
        }

    @classmethod
    def set_tags_bulk(
        cls,
        note_ids: Sequence[int],
        tags: str | Sequence[str] | set[str] | None,
        mode: str = "add",
        allow_remove_provenance_tags: bool = False,
    ) -> dict[str, Any]:
        """Applique des tags sur un lot de notes en passant impérativement par l'écrivain canonique.

        Modes supportés :
        - 'add' : ajoute les nouveaux tags sans supprimer les existants.
        - 'remove' : retire les tags spécifiés (protège les tags de provenance sauf si allow_remove_provenance_tags=True).
        - 'replace' : remplace les tags existants par les nouveaux (en conservant les tags de provenance).
        """
        if not note_ids:
            return {"status": "error", "message": "Aucun identifiant de note fourni."}

        clean_input_tags = parse_note_tags(tags)
        if not clean_input_tags and mode in ("add", "remove"):
            return {"status": "error", "message": "Aucun tag valide fourni pour l'opération."}

        notes = list(NoteModel.select().where(NoteModel.id.in_(list(note_ids))))
        if not notes:
            return {"status": "error", "message": "Aucune note correspondante trouvée."}

        modified_ids: list[int] = []
        with db.atomic():
            for note in notes:
                current_tags = parse_note_tags(note.tags)
                if mode == "add":
                    new_tags = list(current_tags)
                    for t in clean_input_tags:
                        if t not in new_tags:
                            new_tags.append(t)
                elif mode == "remove":
                    new_tags = []
                    for t in current_tags:
                        if t in clean_input_tags:
                            if is_provenance_tag(t) and not allow_remove_provenance_tags:
                                new_tags.append(t)
                        else:
                            new_tags.append(t)
                elif mode == "replace":
                    prov_tags = [t for t in current_tags if is_provenance_tag(t)] if not allow_remove_provenance_tags else []
                    new_tags = list(prov_tags)
                    for t in clean_input_tags:
                        if t not in new_tags:
                            new_tags.append(t)
                else:
                    return {"status": "error", "message": f"Mode inconnu '{mode}'. Utilisez 'add', 'remove' ou 'replace'."}

                if new_tags != current_tags:
                    note.tags = serialize_note_tags(new_tags)
                    note.save(only=[NoteModel.tags])
                    modified_ids.append(note.id)

            # Synchronisation de la couverture pour les notes modifiées
            for nid in modified_ids:
                n_obj = next((n for n in notes if n.id == nid), None)
                if n_obj:
                    try:
                        from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                        CoverageAlignmentService.sync_note_coverage(n_obj)
                    except Exception as e:
                        logger.debug("Coverage sync skipped for note %d: %s", nid, e)

        logger.info("BulkHygieneService.set_tags_bulk: %d notes modifiées (mode=%s, tags=%s).", len(modified_ids), mode, clean_input_tags)
        cls._notify_mutation("set_tags_bulk", 0, {"note_ids": modified_ids, "tags": clean_input_tags, "mode": mode})

        return {
            "status": "success",
            "modified_count": len(modified_ids),
            "note_ids": modified_ids,
            "tags": clean_input_tags,
            "mode": mode,
            "message": f"Tags mis à jour avec succès sur {len(modified_ids)} note(s).",
        }

    @classmethod
    def delete_unused_note_type(
        cls,
        name: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Supprime un type de note uniquement s'il n'est utilisé par aucune note (garde-fou référentiel).

        Si name='all_unused' ou '*', supprime tous les modèles ayant 0 note rattachée.
        Exige confirm=True pour valider la suppression définitive.
        """
        name_clean = name.strip()
        if not name_clean:
            return {"status": "error", "message": "Nom de modèle invalide."}

        if name_clean in ("all_unused", "*"):
            all_types = list(NoteTypeModel.select())
            unused: list[NoteTypeModel] = []
            for nt in all_types:
                count = NoteModel.select().where(NoteModel.note_type == nt).count()
                if count == 0:
                    unused.append(nt)

            if not unused:
                return {"status": "no_op", "count": 0, "message": "Aucun modèle inutilisé trouvé."}

            if len(all_types) - len(unused) < 1:
                # Conserver au moins 1 modèle
                unused = unused[:-1]
                if not unused:
                    return {"status": "error", "message": "Impossible de supprimer : au moins un modèle doit être conservé dans la collection."}

            if not confirm:
                return {
                    "status": "confirmation_required",
                    "count": len(unused),
                    "unused_models": [nt.name for nt in unused],
                    "message": (f"{len(unused)} modèle(s) à 0 note détecté(s) : {', '.join(nt.name for nt in unused)}. Définissez confirm=True pour valider la suppression définitive."),
                }

            deleted_names = []
            with db.atomic():
                for nt in unused:
                    deleted_names.append(nt.name)
                    nt.delete_instance()

            logger.info("BulkHygieneService: %d modèles inutilisés supprimés : %s", len(deleted_names), deleted_names)
            cls._notify_mutation("delete_unused_note_types", 0, {"deleted_models": deleted_names})
            return {
                "status": "deleted",
                "count": len(deleted_names),
                "deleted_models": deleted_names,
                "message": f"{len(deleted_names)} modèle(s) inutilisé(s) supprimé(s) avec succès.",
            }

        target_nt = NoteTypeModel.get_or_none(NoteTypeModel.name == name_clean)
        if not target_nt and name_clean.isdigit():
            target_nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(name_clean))

        if not target_nt:
            return {"status": "error", "message": f"Type de note '{name_clean}' introuvable."}

        notes_count = NoteModel.select().where(NoteModel.note_type == target_nt).count()
        if notes_count > 0:
            return {
                "status": "error",
                "message": (f"Impossible de supprimer le modèle '{target_nt.name}' : {notes_count} note(s) y sont rattachées. Migrez d'abord ces notes (ex: via change_note_type)."),
            }

        total_models = NoteTypeModel.select().count()
        if total_models <= 1:
            return {
                "status": "error",
                "message": f"Impossible de supprimer le modèle '{target_nt.name}' : c'est le seul modèle restant dans la collection.",
            }

        if not confirm:
            return {
                "status": "confirmation_required",
                "name": target_nt.name,
                "id": target_nt.id,
                "message": f"Le type de note '{target_nt.name}' (0 note) sera définitivement supprimé. Définissez confirm=True pour valider.",
            }

        nt_name = target_nt.name
        nt_id = target_nt.id
        with db.atomic():
            target_nt.delete_instance()

        logger.info("BulkHygieneService: modèle inutilisé '%s' (#%d) supprimé.", nt_name, nt_id)
        cls._notify_mutation("delete_note_type", nt_id, {"note_type_name": nt_name})

        return {
            "status": "deleted",
            "name": nt_name,
            "id": nt_id,
            "message": f"Type de note '{nt_name}' supprimé avec succès.",
        }

    @classmethod
    def move_cards_to_deck(
        cls,
        card_ids: Sequence[int],
        deck: str | int,
    ) -> dict[str, Any]:
        """Déplace un lot de cartes physiques vers un paquet ou sous-paquet hiérarchique ('Parent::Enfant')."""
        if not card_ids:
            return {"status": "error", "message": "Aucun identifiant de carte fourni."}

        target_deck: DeckModel | None = None
        if isinstance(deck, int) or (isinstance(deck, str) and deck.strip().isdigit()):
            target_deck = DeckModel.get_or_none(DeckModel.id == int(deck))
        elif isinstance(deck, str):
            deck_name = deck.strip()
            if not deck_name:
                return {"status": "error", "message": "Nom de paquet cible vide."}
            target_deck = DeckRepository().get_or_create_deck_hierarchical(deck_name)

        if not target_deck:
            return {"status": "error", "message": f"Paquet cible '{deck}' introuvable ou impossible à créer."}

        cards = list(CardModel.select().where(CardModel.id.in_(list(card_ids))))
        if not cards:
            return {"status": "error", "message": "Aucune carte valide trouvée pour les identifiants fournis."}

        valid_ids = [c.id for c in cards]
        with db.atomic():
            updated_count = CardModel.update(deck=target_deck).where(CardModel.id.in_(valid_ids)).execute()

        logger.info("BulkHygieneService.move_cards_to_deck: %d cartes déplacées vers '%s' (#%d).", updated_count, target_deck.name, target_deck.id)
        cls._notify_mutation("move_cards", target_deck.id, {"card_ids": valid_ids, "target_deck": target_deck.name, "target_deck_id": target_deck.id})

        return {
            "status": "success",
            "moved_count": updated_count,
            "card_ids": valid_ids,
            "target_deck": target_deck.name,
            "target_deck_id": target_deck.id,
            "message": f"{updated_count} carte(s) déplacée(s) vers le paquet '{target_deck.name}'.",
        }

    @classmethod
    def list_empty_cards(
        cls,
        deck_name: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Identifie les cartes physiques dont le recto (question) est vide."""
        query = CardModel.select(CardModel, NoteModel, DeckModel).join(DeckModel).switch(CardModel).join(NoteModel)
        if deck_name:
            target_deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
            if not target_deck:
                return {"status": "error", "message": f"Paquet '{deck_name}' introuvable."}
            query = query.where(CardModel.deck == target_deck)

        all_cards = list(query)
        empty_cards: list[dict[str, Any]] = []

        for card in all_cards:
            note = card.note
            if not note:
                empty_cards.append({"card_id": card.id, "note_id": None, "deck_name": card.deck.name if card.deck else "", "template_index": card.template_index, "reason": "Note manquante"})
                continue

            active_v = NoteVersionModel.get_or_none(note=note, is_active=True)
            if not active_v:
                active_v = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()

            if not active_v or not active_v.content:
                empty_cards.append({"card_id": card.id, "note_id": note.id, "deck_name": card.deck.name if card.deck else "", "template_index": card.template_index, "reason": "Contenu de note vide"})
                continue

            try:
                content_dict = json.loads(active_v.content) if isinstance(active_v.content, str) else active_v.content
                if not isinstance(content_dict, dict):
                    content_dict = {"Front": str(active_v.content)}
            except Exception:
                content_dict = {"Front": str(active_v.content)}

            nt = note.note_type
            templates: list[dict[str, Any]] = []
            if nt and nt.templates:
                try:
                    parsed_tmpls = json.loads(nt.templates)
                    if isinstance(parsed_tmpls, list):
                        templates = parsed_tmpls
                except Exception:
                    pass

            tmpl_idx = card.template_index
            if 0 <= tmpl_idx < len(templates):
                tmpl = templates[tmpl_idx]
                qfmt = str(tmpl.get("qfmt", ""))
                tmpl_name = str(tmpl.get("name", f"Carte {tmpl_idx + 1}"))
                rendered_q = render_card_text(qfmt, content_dict, template_index=tmpl_idx, is_recto=True)
                if _is_empty(rendered_q) or not rendered_q.strip():
                    empty_cards.append(
                        {
                            "card_id": card.id,
                            "note_id": note.id,
                            "deck_name": card.deck.name if card.deck else "",
                            "template_index": tmpl_idx,
                            "template_name": tmpl_name,
                            "reason": "Front vide après substitution du gabarit",
                        }
                    )
            else:
                empty_cards.append(
                    {
                        "card_id": card.id,
                        "note_id": note.id,
                        "deck_name": card.deck.name if card.deck else "",
                        "template_index": tmpl_idx,
                        "template_name": f"Gabarit inconnu #{tmpl_idx}",
                        "reason": "Index de gabarit hors limite",
                    }
                )

        eff_limit = max(1, min(limit, 500))
        eff_offset = max(0, offset)
        paginated = empty_cards[eff_offset : eff_offset + eff_limit]

        return {
            "status": "success",
            "total_empty_cards": len(empty_cards),
            "offset": eff_offset,
            "limit": eff_limit,
            "count": len(paginated),
            "empty_cards": paginated,
        }

    @classmethod
    def delete_empty_cards(
        cls,
        card_ids: Sequence[int] | None = None,
        deck_name: str = "",
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Supprime les cartes physiques ayant un recto vide.

        Si card_ids n'est pas fourni, détecte automatiquement toutes les cartes vides
        (filtrées par deck_name si précisé).
        Exige confirm=True pour valider la suppression définitive.
        """
        if card_ids is not None and len(card_ids) > 0:
            target_ids = list(card_ids)
        else:
            list_res = cls.list_empty_cards(deck_name=deck_name, limit=10000, offset=0)
            if list_res.get("status") == "error":
                return list_res
            empty_list = list_res.get("empty_cards", [])
            target_ids = [c["card_id"] for c in empty_list]

        if not target_ids:
            return {
                "status": "no_op",
                "deleted_count": 0,
                "card_ids": [],
                "message": "Aucune carte vide trouvée à supprimer.",
            }

        if not confirm:
            return {
                "status": "confirmation_required",
                "empty_cards_count": len(target_ids),
                "card_ids": target_ids,
                "message": (f"{len(target_ids)} carte(s) vide(s) identifiée(s). Définissez confirm=True pour valider la suppression définitive."),
            }

        with db.atomic():
            deleted_count = CardModel.delete().where(CardModel.id.in_(target_ids)).execute()

        logger.info("BulkHygieneService.delete_empty_cards: %d cartes vides supprimées.", deleted_count)
        cls._notify_mutation("delete_empty_cards", 0, {"card_ids": target_ids, "deleted_count": deleted_count})

        return {
            "status": "deleted",
            "deleted_count": deleted_count,
            "card_ids": target_ids,
            "message": f"{deleted_count} carte(s) vide(s) supprimée(s) avec succès.",
        }

    @classmethod
    def analyze_tag_clusters(
        cls,
        note_ids: Sequence[int] | None = None,
        deck_id: int | None = None,
        include_levenshtein: bool = True,
    ) -> TagClustersReport:
        """Analyse la collection pour détecter les grappes de tags sensibles à la casse ou proches selon Levenshtein.

        Exclut rigoureusement les tags de traçabilité documentaire (is_provenance_tag)
        et le tag système ankiforge_generated.

        Args:
            note_ids: Périmètre restreint d'identifiants de notes (None pour toute la collection).
            deck_id: Identifiant d'un paquet racine (inclut automatiquement ses sous-paquets).
            include_levenshtein: Indique si la détection par distance de Levenshtein doit être exécutée.

        Returns:
            Rapport détaillé des grappes trouvées.
        """
        target_note_ids: set[int] | None = None

        if deck_id is not None and deck_id != -1:
            selected_deck = DeckModel.get_or_none(DeckModel.id == deck_id)
            if selected_deck:
                matching_decks = list(DeckModel.select().where((DeckModel.id == selected_deck.id) | DeckModel.name.startswith(descendants_prefix(selected_deck.name))))
                deck_notes = {c.note_id for c in CardModel.select(CardModel.note_id).where(CardModel.deck.in_(matching_decks))}
                target_note_ids = deck_notes
            else:
                target_note_ids = set()

        if note_ids is not None:
            target_note_ids = target_note_ids.intersection(set(note_ids)) if target_note_ids is not None else set(note_ids)

        if target_note_ids is not None:
            if not target_note_ids:
                return TagClustersReport(
                    case_clusters=[],
                    levenshtein_clusters=[],
                    total_clusters_count=0,
                    total_notes_impacted=0,
                    inspected_tags_count=0,
                    inspected_notes_count=0,
                )
            notes = list(NoteModel.select(NoteModel.id, NoteModel.tags).where(NoteModel.id.in_(list(target_note_ids))))
        else:
            notes = list(NoteModel.select(NoteModel.id, NoteModel.tags))

        tag_notes_map: dict[str, set[int]] = {}

        tag_counts: dict[str, int] = {}

        for note in notes:
            for t in parse_note_tags(note.tags):
                if is_provenance_tag(t) or t.strip().lower() == "ankiforge_generated":
                    continue
                tag_notes_map.setdefault(t, set()).add(note.id)
                tag_counts[t] = tag_counts.get(t, 0) + 1

        # 1. Regroupement insensible à la casse
        case_groups: dict[str, list[str]] = {}
        for tag in tag_counts:
            norm_key = unicodedata.normalize("NFC", tag).casefold()
            case_groups.setdefault(norm_key, []).append(tag)

        assigned_tags: set[str] = set()
        case_clusters: list[TagCluster] = []
        cluster_counter = 0

        for _norm_key, variants in sorted(case_groups.items()):
            if len(variants) > 1:
                # Élection canonique : fréquence max descendante, repli minuscules, ordre alphabétique
                variants_sorted = sorted(variants, key=lambda t: (-tag_counts[t], t.casefold() != t, t))
                canonical = variants_sorted[0]
                cluster_notes: set[int] = set()
                for v in variants_sorted:
                    cluster_notes.update(tag_notes_map[v])
                    assigned_tags.add(v)
                cluster_counter += 1
                case_clusters.append(
                    TagCluster(
                        cluster_id=f"case_{cluster_counter}",
                        cluster_type="case",
                        canonical_tag=canonical,
                        tags=[TagFrequency(tag=v, count=tag_counts[v]) for v in variants_sorted],
                        total_notes_count=len(cluster_notes),
                    )
                )

        # 2. Regroupement par distance de Levenshtein (graphe en étoile centré sur le plus fréquent)
        levenshtein_clusters: list[TagCluster] = []
        if include_levenshtein:
            cand_tags = [t for t in tag_counts if t not in assigned_tags and len(unicodedata.normalize("NFC", t)) >= 4]
            # Tri par fréquence décroissante pour faire du mot le plus représenté le centre de l'étoile
            cand_tags.sort(key=lambda t: (-tag_counts[t], t))

            used_in_levenshtein: set[str] = set()

            for pivot in cand_tags:
                if pivot in used_in_levenshtein:
                    continue
                pivot_norm = unicodedata.normalize("NFC", pivot)
                pivot_len = len(pivot_norm)
                max_dist = 1 if pivot_len <= 7 else 2

                matches: list[str] = []
                for other in cand_tags:
                    if other == pivot or other in used_in_levenshtein:
                        continue
                    other_norm = unicodedata.normalize("NFC", other)
                    other_len = len(other_norm)
                    if abs(pivot_len - other_len) > max_dist:
                        continue
                    d = levenshtein_distance(pivot_norm, other_norm)
                    if d <= max_dist:
                        matches.append(other)

                if matches:
                    cluster_members = [pivot] + matches
                    for m in cluster_members:
                        used_in_levenshtein.add(m)
                    cluster_counter += 1
                    cluster_notes = set()
                    for m in cluster_members:
                        cluster_notes.update(tag_notes_map[m])
                    levenshtein_clusters.append(
                        TagCluster(
                            cluster_id=f"lev_{cluster_counter}",
                            cluster_type="levenshtein",
                            canonical_tag=pivot,
                            tags=[TagFrequency(tag=m, count=tag_counts[m]) for m in cluster_members],
                            total_notes_count=len(cluster_notes),
                        )
                    )

        all_impacted_notes: set[int] = set()
        for c in case_clusters + levenshtein_clusters:
            for tf in c.tags:
                all_impacted_notes.update(tag_notes_map.get(tf.tag, set()))

        return TagClustersReport(
            case_clusters=case_clusters,
            levenshtein_clusters=levenshtein_clusters,
            total_clusters_count=len(case_clusters) + len(levenshtein_clusters),
            total_notes_impacted=len(all_impacted_notes),
            inspected_tags_count=len(tag_counts),
            inspected_notes_count=len(notes),
        )

    @classmethod
    def apply_tag_merges(
        cls,
        merges: Sequence[TagMergePlan],
        note_ids: Sequence[int] | None = None,
        deck_id: int | None = None,
    ) -> TagMergeResult:
        """Applique les fusions de tags planifiées sous une transaction atomique.

        Garantit la déduplication des tags sur chaque note et la préservation stricte
        des tags de traçabilité documentaire.

        Args:
            merges: Liste des plans de fusion.
            note_ids: Périmètre optionnel d'identifiants de notes à modifier.
            deck_id: Identifiant optionnel d'un paquet à restreindre.

        Returns:
            Rapport d'exécution.
        """
        if not merges:
            return TagMergeResult(success=True)

        replacement_map: dict[str, str] = {}
        for plan in merges:
            target = plan.target_tag.strip()
            if not target:
                continue
            for src in plan.tags_to_merge:
                src_clean = src.strip()
                if src_clean and src_clean != target:
                    replacement_map[src_clean] = target

        if not replacement_map:
            return TagMergeResult(success=True)

        target_note_ids: set[int] | None = None

        if deck_id is not None and deck_id != -1:
            selected_deck = DeckModel.get_or_none(DeckModel.id == deck_id)
            if selected_deck:
                matching_decks = list(DeckModel.select().where((DeckModel.id == selected_deck.id) | DeckModel.name.startswith(descendants_prefix(selected_deck.name))))
                deck_notes = {c.note_id for c in CardModel.select(CardModel.note_id).where(CardModel.deck.in_(matching_decks))}
                target_note_ids = deck_notes
            else:
                target_note_ids = set()

        if note_ids is not None:
            target_note_ids = target_note_ids.intersection(set(note_ids)) if target_note_ids is not None else set(note_ids)

        if target_note_ids is not None and not target_note_ids:
            return TagMergeResult(success=True)

        modified_ids: list[int] = []
        try:
            with db.atomic():
                all_notes = list(NoteModel.select().where(NoteModel.id.in_(list(target_note_ids)))) if target_note_ids is not None else list(NoteModel.select())

                for note in all_notes:
                    current_tags = parse_note_tags(note.tags)
                    new_tags: list[str] = []
                    has_mutation = False
                    for t in current_tags:
                        if is_provenance_tag(t) or t.strip().lower() == "ankiforge_generated":
                            if t not in new_tags:
                                new_tags.append(t)
                        elif t in replacement_map:
                            target_t = replacement_map[t]
                            if target_t not in new_tags:
                                new_tags.append(target_t)
                            has_mutation = True
                        else:
                            if t not in new_tags:
                                new_tags.append(t)

                    if has_mutation and new_tags != current_tags:
                        note.tags = serialize_note_tags(new_tags)
                        note.save(only=[NoteModel.tags])
                        modified_ids.append(note.id)

                for nid in modified_ids:
                    target_note = next((n for n in all_notes if n.id == nid), None)
                    if target_note:
                        try:
                            from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                            CoverageAlignmentService.sync_note_coverage(target_note)
                        except Exception as err:
                            logger.debug("Coverage sync skipped for note %d: %s", nid, err)

            logger.info("BulkHygieneService.apply_tag_merges: %d note(s) modifiée(s) pour %d fusion(s).", len(modified_ids), len(merges))
            cls._notify_mutation("merge_tags", 0, {"modified_count": len(modified_ids), "merges_count": len(merges)})

            return TagMergeResult(
                success=True,
                merged_clusters_count=len(merges),
                modified_notes_count=len(modified_ids),
                modified_note_ids=modified_ids,
            )
        except Exception as e:
            logger.error("BulkHygieneService.apply_tag_merges erreur : %s", e)
            return TagMergeResult(
                success=False,
                error_message=str(e),
            )

    @classmethod
    def _notify_mutation(cls, mutation_type: str, target_id: int, details: dict[str, Any]) -> None:
        """Déclenche la notification sur le bus d'événements MCP si disponible."""
        try:
            from ankiforge.services.ai.mcp_server import _notify_mcp_mutation

            _notify_mcp_mutation({"type": mutation_type, "target_id": target_id, **details})
        except Exception as e:
            logger.debug("BulkHygieneService notification mutation: %s", e)

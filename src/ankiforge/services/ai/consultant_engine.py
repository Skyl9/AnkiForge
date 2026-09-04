"""
Moteur IA Autonome pour le Consultant AnkiForge.

- Boucle autonome d'outils avec streaming granularisé (Token-by-Token, Outils).
- Outils de diagnostic et contrôle qualité (Linter Wozniak, Similarité Levenshtein, Smart Coverage).
- Garde-fous et Staging : Proposition de Diffs sans mutation directe de la BDD SQLite.
- Mémoire de session multi-tours et compaction dynamique de contexte (ContextCompactor).
- Support de l'interruption (Cancellation Token).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from collections.abc import AsyncGenerator
from typing import Any

from peewee import fn

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.services.ai.flexible_service import AIManager, OpenAICompatibleProvider
from ankiforge.services.ai.linter import WozniakLinterEngine
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.plugins.api import MCPHooksAPI
from ankiforge.services.tools.tool_service import ToolService
from ankiforge.utils.c_bridge import get_similarity

logger = logging.getLogger(__name__)


def robust_json_loads(text: Any) -> Any:
    r"""
    Décode une chaîne JSON de manière ultra-résistante face aux anti-slashs LaTeX
    non échappés (ex: \Sigma, \delta, \frac, \alpha, \[, \], etc.) et aux retours chariots bruts.
    """
    if not isinstance(text, str):
        return text

    clean = text.strip()
    if not clean:
        return {}

    # 1. Essai direct standard (permet de préserver les \uXXXX unicode natifs)
    try:
        return json.loads(clean)
    except Exception:
        pass

    # 2. Essai en mode non strict
    try:
        return json.loads(clean, strict=False)
    except Exception:
        pass

    # 3. Réparation ciblée des anti-slashs LaTeX (si json.loads standard a échoué)
    def _fix_latex_backslashes(s: str) -> str:
        # Ne pas toucher à \uXXXX (unicode hex à 4 chiffres)
        res = re.sub(r"(?<!\\)\\(?!u[0-9a-fA-F]{4})([a-zA-Z]{2,})", r"\\\\\1", s)
        # Doubler les \ devant les symboles mathématiques et délimiteurs (ex: \[, \], \{, \}, \$, \_, \^, \(, \), \ )
        res = re.sub(r'(?<!\\)\\([^a-zA-Z0-9"\\/])', r"\\\\\1", res)
        # Doubler les \ isolés devant une lettre (ex: \d, \a, \b, \f, \s, etc.)
        res = re.sub(r"(?<!\\)\\(?!u[0-9a-fA-F]{4})([a-zA-Z0-9])", r"\\\\\1", res)
        return res

    try:
        repaired = _fix_latex_backslashes(clean)
        return json.loads(repaired, strict=False)
    except Exception:
        pass

    # 4. Remplacement global de tous les \ isolés sauf devant " ou \
    try:
        repaired_all = re.sub(r'(?<!\\)\\(?!["\\])', r"\\\\", clean)
        return json.loads(repaired_all, strict=False)
    except Exception:
        pass

    # 5. Fallback vers ast.literal_eval pour les structures Python
    try:
        import ast

        return ast.literal_eval(clean)
    except Exception:
        pass

    raise ValueError(f"Impossible de parser le JSON : {clean[:120]}...")


# =====================================================================
# GESTIONNAIRE D'OUTILS ET CONTRÔLE QUALITÉ POUR LE CONSULTANT
# =====================================================================


class ConsultantToolRegistry:
    """
    Exécuteur d'outils in-process sécurisé pour le Consultant IA.
    Les modifications de cartes sont proposées sous forme de Staged Diffs avec validation humaine (Garde-Fou).
    """

    @staticmethod
    def audit_deck_wozniak(deck_name: str) -> str:
        """
        Effectue un audit de qualité Wozniak complet sur un paquet (20 règles de formulation, atomicité, interférences).
        """
        try:
            deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
            if not deck:
                return f"Erreur : Le paquet '{deck_name}' n'a pas été trouvé."

            report = WozniakLinterEngine.audit_deck(deck_id=deck.id)
            total_notes = report.get("total_notes", 0)
            flagged = report.get("notes_flagged", 0)
            score = report.get("score_global", 100)
            categories = report.get("categories", {})

            cat_summary = []
            for c_id, c_data in categories.items():
                c_name = c_data.get("name", c_id)
                c_count = c_data.get("count", 0)
                if c_count > 0:
                    cat_summary.append(f"  • {c_name} : {c_count} anomalies détectées")

            suggestions = report.get("suggestions_sample", [])
            sug_lines = []
            for s in suggestions[:4]:
                sug_lines.append(f"  - Note #{s.get('id')} : {s.get('rule_name')} (Conseil: {s.get('recommendation', '')[:70]})")

            return (
                f"🛡️ Rapport d'Audit Qualité Wozniak — Paquet '{deck.name}' :\n"
                f"- Score de conformité global : {score}/100\n"
                f"- Notes analysées : {total_notes} (dont {flagged} nécessitant une révision)\n"
                f"- Répartition des anomalies par catégorie :\n" + ("\n".join(cat_summary) if cat_summary else "  (Aucune anomalie majeure)") + "\n"
                "- Exemples de cartes prioritaires à corriger :\n" + ("\n".join(sug_lines) if sug_lines else "  (Toutes les cartes respectent les standards)")
            )
        except Exception as e:
            logger.error("Erreur audit_deck_wozniak : %s", e)
            return f"Erreur lors de l'audit Wozniak du paquet : {e}"

    @staticmethod
    def audit_card_wozniak(note_id: int) -> str:
        """
        Analyse chirurgicale d'une carte spécifique au regard des 20 règles de Piotr Wozniak.
        """
        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id)
            if not note:
                return f"Erreur : La note #{note_id} n'existe pas."

            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            if not active_v or not active_v.content:
                return f"Note #{note_id} sans contenu actif."

            try:
                data = json.loads(active_v.content)
            except Exception:
                data = {"Front": active_v.content}

            front = str(data.get("Front", data.get("Recto", data.get("question", ""))))
            back = str(data.get("Back", data.get("Verso", data.get("reponse", ""))))

            # Analyse des heuristiques Wozniak
            issues = []
            score = 100

            # 1. Règle d'atomicité (longueur excessive)
            word_count_front = len(front.split())
            word_count_back = len(back.split())
            if word_count_front > 25:
                issues.append("Règle #4 (Atomicité) : La question est trop verbeuse (>25 mots).")
                score -= 25
            if word_count_back > 35:
                issues.append("Règle #4 (Atomicité) : La réponse contient trop de détails (>35 mots). Envisager une scission.")
                score -= 30

            # 2. Règle de structure (listes à puces)
            if "\n-" in back or "\n*" in back or "<ul" in back or "<ol" in back:
                issues.append("Règle #4 (Minimum Information) : Présence d'une liste dans la réponse (privilégier plusieurs cartes atomiques).")
                score -= 20

            # 3. Règle d'interférence
            if len(front) > 0 and len(back) > 0 and front.lower() == back.lower():
                issues.append("Règle #6 (Clarté) : Question et réponse identiques.")
                score -= 40

            return (
                f"🔬 Audit Wozniak de la Note #{note.id} :\n"
                f"- Modèle : {note.note_type.name if note.note_type else 'Inconnu'}\n"
                f"- Score Qualité : {max(0, score)}/100\n"
                f"- Recto : {front[:80]}...\n"
                f"- Verso : {back[:80]}...\n"
                f"- Diagnostic :\n" + ("\n".join(f"  ⚠️ {iss}" for iss in issues) if issues else "  ✅ Parfait respect des principes d'atomicité et de clarté.")
            )
        except Exception as e:
            logger.error("Erreur audit_card_wozniak : %s", e)
            return f"Erreur lors de l'audit de la note : {e}"

    @staticmethod
    def find_duplicate_cards(deck_name: str = "", threshold: float = 0.75) -> str:
        """
        Détecte les cartes doublons ou quasi-doublons dans un paquet via l'extension C Levenshtein.
        """
        try:
            query = NoteModel.select().join(CardModel).distinct()
            if deck_name:
                deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
                if deck:
                    query = query.where(CardModel.deck == deck)

            notes = list(query.limit(80))
            if len(notes) < 2:
                return "Pas assez de cartes pour une recherche de doublons."

            note_texts: list[tuple[int, str]] = []
            for n in notes:
                v = n.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if v and v.content:
                    try:
                        d = json.loads(v.content)
                        txt = d.get("Front", d.get("Recto", v.content))
                    except Exception:
                        txt = v.content
                    note_texts.append((n.id, str(txt).strip()))

            duplicates = []
            for i in range(len(note_texts)):
                for j in range(i + 1, len(note_texts)):
                    id1, txt1 = note_texts[i]
                    id2, txt2 = note_texts[j]
                    sim = get_similarity(txt1, txt2)
                    if sim >= threshold:
                        duplicates.append((id1, id2, sim, txt1[:50], txt2[:50]))

            if not duplicates:
                return f"✅ Aucun doublon détecté avec un seuil de similarité de {threshold * 100:.0f}%."

            lines = [f"⚠️ {len(duplicates)} paires de cartes doublons détectées (Seuil {threshold * 100:.0f}%) :"]
            for id1, id2, sim, t1, t2 in duplicates[:8]:
                lines.append(f"  • Note #{id1} vs Note #{id2} ({sim * 100:.1f}% similaire) :\n    1: {t1}\n    2: {t2}")

            return "\n".join(lines)
        except Exception as e:
            logger.error("Erreur find_duplicate_cards : %s", e)
            return f"Erreur lors de la recherche de doublons : {e}"

    @staticmethod
    def find_cards_by_content(query: str, deck_name: str = "", limit: int = 8) -> str:
        """Recherche des cartes par mot-clé dans leur question/réponse pour retrouver facilement leur note_id."""
        try:
            q_db = NoteModel.select().join(CardModel).distinct()
            if deck_name:
                deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
                if deck:
                    q_db = q_db.where(CardModel.deck == deck)

            clean_query = query.strip().lower()
            matching_notes = []

            for note in q_db.limit(100):
                v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if not v or not v.content:
                    continue

                content_lower = v.content.lower()
                keywords = [k for k in clean_query.split() if len(k) > 2]
                if clean_query in content_lower or (keywords and any(k in content_lower for k in keywords)):
                    try:
                        d = json.loads(v.content)
                    except Exception:
                        d = {"Front": v.content}
                    card_rel = note.cards.first()
                    d_name = card_rel.deck.name if card_rel and card_rel.deck else "Sans paquet"
                    matching_notes.append(
                        {
                            "note_id": note.id,
                            "paquet": d_name,
                            "tags": note.tags,
                            "champs": d,
                        }
                    )
                    if len(matching_notes) >= limit:
                        break

            if not matching_notes:
                return f"Aucune carte trouvée pour la recherche '{query}' dans le paquet '{deck_name or 'tous'}'. Utilise get_cards_by_deck_or_tag pour lister les cartes disponibles."

            return f"🔍 {len(matching_notes)} cartes trouvées pour '{query}' :\n" + json.dumps(matching_notes, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur find_cards_by_content : %s", e)
            return f"Erreur recherche cartes : {e}"

    @staticmethod
    def propose_card_refactor(note_id: int, new_fields_json: str, explanation: str = "") -> str:
        """
        Garde-fou : Propose une modification de carte sous forme de Diff sans l'écrire immédiatement en BDD.
        L'utilisateur visualisera le diff et validera l'application dans l'inspecteur.
        """
        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id) if note_id and note_id > 0 else None
            new_dict = robust_json_loads(new_fields_json) if isinstance(new_fields_json, str) else new_fields_json

            # Fallback : chercher par ressemblance de question si note_id est manquant
            if not note and isinstance(new_dict, dict):
                front_hint = str(new_dict.get("Front", new_dict.get("Recto", ""))).strip()
                if front_hint:
                    for cand_note in NoteModel.select().order_by(NoteModel.id.desc()).limit(50):
                        v = cand_note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                        if v and v.content and (front_hint[:20].lower() in v.content.lower() or front_hint in v.content):
                            note = cand_note
                            break

            if not note:
                return f"Erreur : La note #{note_id} n'a pas été trouvée. Utilise l'outil find_cards_by_content(query='...') ou get_cards_by_deck_or_tag pour trouver l'ID exact de la note."

            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            orig_content = active_v.content if active_v else "{}"

            try:
                orig_dict = robust_json_loads(orig_content)
            except Exception:
                orig_dict = {"Front": orig_content}

            nt = note.note_type
            model_name = nt.name if nt else "Inconnu"
            fields_schema = []
            if nt and nt.fields_schema:
                try:
                    fields_schema = robust_json_loads(nt.fields_schema)
                except Exception:
                    fields_schema = [nt.fields_schema]

            staged_payload = {
                "status": "staged_diff",
                "type": "card",
                "note_id": note.id,
                "model_name": model_name,
                "fields_schema": fields_schema,
                "title": f"Proposition de Refactorisation — Note #{note.id} ({model_name})",
                "original": orig_dict,
                "modified": new_dict,
                "explanation": explanation or "Amélioration de la clarté et concision.",
                "metadata": {"note_id": note.id, "model_name": model_name},
            }

            return json.dumps(staged_payload, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur propose_card_refactor : %s", e)
            return f"Erreur lors de la préparation du diff de refactorisation : {e}"

    @staticmethod
    def propose_card_split(note_id: int, new_cards_json: str, explanation: str = "") -> str:
        """
        Garde-fou : Propose de scinder une carte dense en plusieurs cartes atomiques sans écriture directe.
        """
        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id)
            if not note:
                return f"Erreur : La note #{note_id} n'a pas été trouvée."

            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            orig_content = active_v.content if active_v else "{}"

            try:
                orig_dict = robust_json_loads(orig_content)
            except Exception:
                orig_dict = {"Front": orig_content}

            new_cards = robust_json_loads(new_cards_json) if isinstance(new_cards_json, str) else new_cards_json

            staged_payload = {
                "status": "staged_diff",
                "type": "split",
                "note_id": note.id,
                "title": f"Proposition de Scission Atomique — Note #{note.id}",
                "original": orig_dict,
                "modified": new_cards,
                "explanation": explanation or f"Scission en {len(new_cards)} cartes atomiques (Règle d'atomicité Wozniak).",
            }

            return json.dumps(staged_payload, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur propose_card_split : %s", e)
            return f"Erreur lors de la préparation de la scission : {e}"

    @staticmethod
    def list_note_types() -> str:
        """Liste tous les modèles de cartes (Note Types) enregistrés dans la collection avec leurs champs et statistiques."""
        try:
            models = list(NoteTypeModel.select())
            if not models:
                return "Aucun modèle de carte trouvé dans la collection."

            res = []
            for m in models:
                fields = []
                if m.fields_schema:
                    try:
                        fields = robust_json_loads(m.fields_schema)
                    except Exception:
                        fields = [m.fields_schema]

                templates = []
                if m.templates:
                    try:
                        templates = robust_json_loads(m.templates)
                    except Exception:
                        templates = []

                notes_count = NoteModel.select().where(NoteModel.note_type == m).count()
                res.append(
                    {
                        "id": m.id,
                        "nom": m.name,
                        "description": m.description or "",
                        "champs": fields,
                        "nombre_templates": len(templates),
                        "nombre_notes_rattachees": notes_count,
                    }
                )

            return "🎨 Modèles de cartes (Note Types) enregistrés :\n" + json.dumps(res, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur list_note_types : %s", e)
            return f"Erreur lors de la récupération des modèles : {e}"

    @staticmethod
    def get_note_type_details(note_type_name: str) -> str:
        """Retourne la définition complète d'un modèle de carte (champs, templates HTML Recto/Verso, CSS)."""
        try:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.name == note_type_name.strip())
            if not nt:
                return f"Erreur : Le modèle de carte '{note_type_name}' n'a pas été trouvé. Utilise list_note_types() pour voir les modèles disponibles."

            fields = []
            if nt.fields_schema:
                try:
                    fields = robust_json_loads(nt.fields_schema)
                except Exception:
                    fields = [nt.fields_schema]

            templates = []
            if nt.templates:
                try:
                    templates = robust_json_loads(nt.templates)
                except Exception:
                    templates = []

            notes_count = NoteModel.select().where(NoteModel.note_type == nt).count()

            sample_note = NoteModel.select().where(NoteModel.note_type == nt).order_by(NoteModel.id.desc()).first()
            sample_content = {}
            if sample_note:
                v = sample_note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if v and v.content:
                    try:
                        sample_content = robust_json_loads(v.content)
                    except Exception:
                        sample_content = {"Front": v.content}

            detail = {
                "id": nt.id,
                "nom": nt.name,
                "description": nt.description or "",
                "schema_champs": fields,
                "templates_cartes": templates,
                "css_style": nt.css_style or "/* Aucun style CSS personnalisé */",
                "nombre_notes_utilisant_ce_modele": notes_count,
                "exemple_note_actuelle": sample_content,
            }
            return f"🎨 Détails complets du Modèle '{nt.name}' :\n" + json.dumps(detail, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur get_note_type_details : %s", e)
            return f"Erreur lors de la récupération des détails du modèle : {e}"

    @staticmethod
    def propose_note_type_refactor(
        note_type_name: str,
        new_fields_schema_json: str = "",
        new_css: str = "",
        new_templates_json: str = "",
        new_description: str = "",
        explanation: str = "",
    ) -> str:
        """Garde-fou : Propose une modification structurelle d'un modèle de carte (CSS, templates, champs, description)."""
        try:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.name == note_type_name.strip())
            if not nt:
                return f"Erreur : Le modèle de carte '{note_type_name}' n'a pas été trouvé."

            orig_fields = robust_json_loads(nt.fields_schema) if nt.fields_schema else ["Front", "Back"]
            orig_templates = robust_json_loads(nt.templates) if nt.templates else []
            orig_css = nt.css_style or ""
            orig_desc = nt.description or ""

            orig_dict = {
                "nom": nt.name,
                "description": orig_desc,
                "fields_schema": orig_fields,
                "templates": orig_templates,
                "css_style": orig_css,
            }

            mod_dict = dict(orig_dict)
            if new_fields_schema_json:
                mod_dict["fields_schema"] = robust_json_loads(new_fields_schema_json)
            if new_css:
                mod_dict["css_style"] = new_css
            if new_templates_json:
                mod_dict["templates"] = robust_json_loads(new_templates_json)
            if new_description:
                mod_dict["description"] = new_description

            staged_payload = {
                "status": "staged_diff",
                "type": "model",
                "note_type_name": nt.name,
                "note_type_id": nt.id,
                "title": f"Proposition d'Évolution de Modèle — '{nt.name}'",
                "original": orig_dict,
                "modified": mod_dict,
                "explanation": explanation or "Mise à niveau du modèle de cartes (champs / CSS / templates).",
                "metadata": {"note_type_name": nt.name, "note_type_id": nt.id},
            }
            return json.dumps(staged_payload, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur propose_note_type_refactor : %s", e)
            return f"Erreur lors de la préparation de la refactorisation de modèle : {e}"

    @staticmethod
    def propose_css_tune(note_type_name: str, css_snippet: str, selector: str = "") -> str:
        """
        Garde-fou : Propose un ajustement CSS pour un modèle de carte sans modification directe en BDD.
        """
        try:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.name == note_type_name.strip())
            if not nt:
                return f"Erreur : Le modèle '{note_type_name}' n'existe pas."

            current_css = nt.css_style or "/* Aucun style */"
            snippet = css_snippet.strip()
            if selector and not snippet.startswith(selector):
                snippet = f"{selector} {{\n  {snippet}\n}}"

            staged_payload = {
                "status": "staged_diff",
                "type": "css",
                "title": f"Proposition de Style CSS — Modèle '{nt.name}'",
                "original": current_css,
                "modified": current_css + f"\n\n/* Consultant IA */\n{snippet}",
                "metadata": {"note_type_name": nt.name, "snippet": snippet},
            }

            return json.dumps(staged_payload, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur propose_css_tune : %s", e)
            return f"Erreur lors de la préparation du diff CSS : {e}"

    @staticmethod
    def query_peewee(sql_query: str) -> str:
        """Exécute une requête SQL SELECT en lecture seule sur la base SQLite."""
        sql_clean = sql_query.strip()
        forbidden = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "ATTACH", "DETACH"]
        if any(re.search(rf"\b{kw}\b", sql_clean, re.IGNORECASE) for kw in forbidden):
            return "Erreur : Seules les requêtes SELECT (lecture seule) sont autorisées par mesure de sécurité."

        try:
            from ankiforge.database.base import db

            cursor = db.execute_sql(sql_clean)
            results = cursor.fetchall()

            if not results:
                return "Aucun résultat trouvé."

            columns = [col[0] for col in cursor.description] if cursor.description else []
            formatted_lines = [f"Colonnes : {', '.join(columns)}"]
            for row in results[:40]:
                formatted_lines.append(f"- {row}")

            if len(results) > 40:
                formatted_lines.append(f"... ({len(results) - 40} résultats supplémentaires masqués)")

            return "\n".join(formatted_lines)
        except Exception as e:
            return f"Erreur SQL : {e}"

    @staticmethod
    def get_deck_stats(deck_name: str) -> str:
        """Calcule les statistiques SRS d'un paquet Anki (total, révisions, oublis, sangsues)."""
        try:
            deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
            if not deck:
                return f"Erreur : Le paquet '{deck_name}' n'a pas été trouvé."

            total_cards = CardModel.select().where(CardModel.deck == deck).count()
            avg_reps = CardModel.select(fn.AVG(CardModel.reps)).where(CardModel.deck == deck).scalar() or 0.0
            total_lapses = CardModel.select(fn.SUM(CardModel.lapses)).where(CardModel.deck == deck).scalar() or 0
            leeches = CardModel.select().where((CardModel.deck == deck) & (CardModel.lapses >= 4)).count()

            return (
                f"📊 Statistiques du Paquet '{deck.name}' :\n"
                f"- Nombre total de cartes : {total_cards}\n"
                f"- Nombre moyen de révisions : {float(avg_reps):.1f}\n"
                f"- Nombre total d'oublis (lapses) : {total_lapses}\n"
                f"- Cartes sangsues (≥ 4 oublis) : {leeches} cartes critiques\n"
            )
        except Exception as e:
            return f"Erreur lors du calcul des statistiques : {e}"

    @staticmethod
    def get_collection_panorama_360() -> str:
        """Fournit une vision 360° globale de la collection Anki (paquets, cartes, sangsues, santé globale)."""
        try:
            total_decks = DeckModel.select().count()
            total_cards = CardModel.select().count()
            total_notes = NoteModel.select().count()
            total_docs = DocumentModel.select().count()
            total_leeches = CardModel.select().where(CardModel.lapses >= 4).count()

            decks = list(DeckModel.select().order_by(DeckModel.name.asc()))
            deck_summaries = []
            for d in decks[:15]:
                cnt = CardModel.select().where(CardModel.deck == d).count()
                lapses = CardModel.select(fn.SUM(CardModel.lapses)).where(CardModel.deck == d).scalar() or 0
                deck_summaries.append(f"  • {d.name} : {cnt} cartes (oublis: {lapses})")

            recent_notes = list(NoteModel.select().order_by(NoteModel.id.desc()).limit(5))
            recent_ids = [str(n.id) for n in recent_notes]

            return (
                f"🌐 Panorama 360° de la Collection AnkiForge :\n"
                f"- Total Paquets : {total_decks}\n"
                f"- Total Notes : {total_notes}\n"
                f"- Total Cartes : {total_cards}\n"
                f"- Cartes Sangsues globales (lapses ≥ 4) : {total_leeches}\n"
                f"- Documents Sources indexés : {total_docs}\n"
                f"- Répartition des principaux paquets :\n" + ("\n".join(deck_summaries) if deck_summaries else "  (Aucun paquet)") + "\n"
                f"- Dernières notes créées (IDs) : {', '.join(recent_ids) if recent_ids else 'Aucune'}\n"
            )
        except Exception as e:
            logger.error("Erreur get_collection_panorama_360 : %s", e)
            return f"Erreur lors de la génération du panorama 360° : {e}"

    @staticmethod
    def inspect_deck_deep_scan(deck_name: str) -> str:
        """Effectue une analyse approfondie d'un paquet spécifique (intervalles, sangsues, modèles)."""
        try:
            deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
            if not deck:
                return f"Erreur : Le paquet '{deck_name}' n'existe pas."

            cards = list(CardModel.select().where(CardModel.deck == deck))
            total_cards = len(cards)
            if total_cards == 0:
                return f"Le paquet '{deck.name}' ne contient aucune carte."

            # Distribution des intervalles
            learning = sum(1 for c in cards if (getattr(c, "ivl", 0) or 0) <= 1)
            young = sum(1 for c in cards if 1 < (getattr(c, "ivl", 0) or 0) < 21)
            mature = sum(1 for c in cards if (getattr(c, "ivl", 0) or 0) >= 21)

            # Top sangsues
            leeches = sorted([c for c in cards if (c.lapses or 0) > 0], key=lambda c: c.lapses or 0, reverse=True)[:5]
            leech_details = []
            for lc in leeches:
                note = lc.note
                v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                snippet = v.content[:80] if v and v.content else f"Note #{note.id}"
                leech_details.append(f"  - Note #{note.id} ({lc.lapses} oublis, intervalle: {getattr(lc, 'ivl', 0)}j) : {snippet}")

            return (
                f"🔬 Deep Scan du Paquet '{deck.name}' ({total_cards} cartes) :\n"
                f"- Apprentissage (≤ 1j) : {learning} ({learning / total_cards * 100:.1f}%)\n"
                f"- Jeunes (2-20j) : {young} ({young / total_cards * 100:.1f}%)\n"
                f"- Matures (≥ 21j) : {mature} ({mature / total_cards * 100:.1f}%)\n"
                f"- Top cartes sangsues à refactoriser :\n" + ("\n".join(leech_details) if leech_details else "  (Aucune sangsue détectée)")
            )
        except Exception as e:
            logger.error("Erreur inspect_deck_deep_scan : %s", e)
            return f"Erreur lors du scan approfondi : {e}"

    @staticmethod
    def get_note_full_profile_360(note_id: int) -> str:
        """Génère le profil complet 360° d'une note (cartes physiques, modèle, historique Time Machine, stats SRS, templates)."""
        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id)
            if not note:
                return f"Erreur : La note #{note_id} n'a pas été trouvée."

            active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            total_versions = note.versions.count()

            nt = note.note_type
            nt_name = nt.name if nt else "Inconnu"
            fields_schema = []
            templates = []
            if nt:
                if nt.fields_schema:
                    try:
                        fields_schema = robust_json_loads(nt.fields_schema)
                    except Exception:
                        fields_schema = [nt.fields_schema]
                if nt.templates:
                    try:
                        templates = robust_json_loads(nt.templates)
                    except Exception:
                        templates = []

            cards = list(note.cards)
            cards_info = []
            for c in cards:
                d_name = c.deck.name if c.deck else "Sans paquet"
                t_idx = getattr(c, "template_index", 0)
                t_name = f"Template #{t_idx}"
                if templates and 0 <= t_idx < len(templates) and isinstance(templates[t_idx], dict):
                    t_name = templates[t_idx].get("name", t_name)

                cards_info.append(
                    f"  • Carte #{c.id} (Template: '{t_name}' [idx {t_idx}], Paquet: '{d_name}', "
                    f"Rév: {c.reps or 0}, Oublis: {c.lapses or 0}, Intervalle: {getattr(c, 'ivl', 0)}j, "
                    f"Stabilité: {getattr(c, 'stability', 0.0):.1f}, Difficulté: {getattr(c, 'difficulty', 0.0):.1f})"
                )

            content_parsed = active_v.content if active_v else "{}"
            try:
                content_obj = robust_json_loads(content_parsed)
                formatted_content = json.dumps(content_obj, ensure_ascii=False, indent=2)
            except Exception:
                formatted_content = str(content_parsed)

            return (
                f"📋 Profil 360° de la Note #{note.id} :\n"
                f"- GUID : {note.guid}\n"
                f"- Modèle de note : '{nt_name}' (Schéma des champs requis : {json.dumps(fields_schema, ensure_ascii=False)})\n"
                f"- Tags : {note.tags}\n"
                f"- Statut : {note.status}\n"
                f"- Historique Time Machine : {total_versions} versions enregistrées\n"
                f"- Cartes physiques générées par ce modèle ({len(cards)}) :\n" + ("\n".join(cards_info) if cards_info else "  (Aucune carte)") + "\n"
                f"- Contenu actif actuel de la note (champs dynamiques) :\n{formatted_content}\n"
                f"- Style CSS du modèle :\n{nt.css_style if nt and nt.css_style else '/* Aucun CSS personnalisé */'}\n"
            )
        except Exception as e:
            logger.error("Erreur get_note_full_profile_360 : %s", e)
            return f"Erreur lors de la récupération du profil de note : {e}"

    @staticmethod
    def get_cards_by_deck_or_tag(deck_name: str = "", tag: str = "", limit: int = 15) -> str:
        """Récupère une liste de cartes selon leur paquet ou tag."""
        try:
            query = NoteModel.select().join(CardModel).distinct()
            if deck_name:
                deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
                if deck:
                    query = query.where(CardModel.deck == deck)
            if tag:
                query = query.where(NoteModel.tags.contains(tag.strip()))

            notes = list(query.limit(min(limit, 30)))
            if not notes:
                return "Aucune carte trouvée pour ces critères."

            res_list = []
            for n in notes:
                active_v = NoteVersionModel.get_or_none(note=n, is_active=True)
                content: Any = {}
                if active_v and active_v.content:
                    try:
                        content = robust_json_loads(active_v.content)
                    except Exception:
                        content = {"raw": active_v.content}
                res_list.append(
                    {
                        "note_id": n.id,
                        "modele": n.note_type.name if n.note_type else "Inconnu",
                        "tags": n.tags,
                        "champs": content,
                    }
                )
            return f"🎴 {len(res_list)} notes trouvées :\n" + json.dumps(res_list, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Erreur de récupération des cartes : {e}"

    @staticmethod
    def search_attached_documents(query: str, document_title: str = "", top_k: int = 4) -> str:
        """Recherche sémantique ciblée dans les documents attachés via RAGService (FAISS / Chunks)."""
        try:
            from ankiforge.services.ai.rag_service import RAGService

            doc_query = DocumentModel.select()
            if document_title:
                doc_query = doc_query.where(DocumentModel.title.contains(document_title.strip()))

            docs = list(doc_query)
            if not docs:
                return f"Aucun document trouvé pour la recherche '{document_title}'."

            llm_config = LLMConfigModel.select().first()
            if not llm_config:
                return "Erreur : Aucun modèle LLM configuré pour le RAG."

            rag = RAGService(llm_config)
            snippets = []
            for d in docs[:3]:
                results = rag.search(str(d.id), query, top_k=top_k)
                for r in results:
                    txt = getattr(r, "page_content", getattr(r, "text", str(r)))
                    snippets.append(f"📄 [{d.title}] : {txt}")

            if not snippets:
                return "Aucun passage pertinent trouvé dans les documents pour cette requête."

            return "Extrait documentaire RAG :\n\n" + "\n---\n".join(snippets[:top_k])
        except Exception as e:
            logger.error("Erreur search_attached_documents : %s", e)
            return f"Erreur lors de la recherche documentaire : {e}"

    @staticmethod
    def analyze_coverage_gaps(deck_name: str, document_title: str = "") -> str:
        """Analyse de couverture (Smart Coverage) : compare les cartes d'un paquet avec un document source pour lister les lacunes."""
        try:
            deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
            if not deck:
                return f"Erreur : Paquet '{deck_name}' introuvable."

            doc_query = DocumentModel.select()
            if document_title:
                doc_query = doc_query.where(DocumentModel.title.contains(document_title.strip()))
            doc = doc_query.first()
            if not doc:
                return "Erreur : Document source introuvable pour l'analyse de couverture."

            card_texts = []
            for c in CardModel.select().where(CardModel.deck == deck):
                note = c.note
                v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                if v and v.content:
                    card_texts.append(v.content.lower())

            deck_vocab = " ".join(card_texts)
            doc_content = getattr(doc, "content", "") or ""
            doc_paragraphs = [p.strip() for p in doc_content.split("\n\n") if len(p.strip()) > 40]

            missing_sections = []
            for p in doc_paragraphs[:20]:
                words = [w for w in re.findall(r"\b\w{5,}\b", p.lower()) if w not in ["cette", "après", "comme", "avoir", "faire", "entre"]]
                matched = sum(1 for w in words if w in deck_vocab)
                coverage = matched / len(words) if words else 1.0
                if coverage < 0.35:
                    missing_sections.append(f"  • Notion peu/non couverte : {p[:110]}...")

            return (
                f"📊 Rapport de Couverture Smart Coverage :\n"
                f"- Paquet : '{deck.name}'\n"
                f"- Document source : '{doc.title}'\n"
                f"- Paragraphes analysés : {len(doc_paragraphs)}\n"
                f"- Lacunes identifiées :\n" + ("\n".join(missing_sections[:6]) if missing_sections else "  ✅ Le paquet semble couvrir exhaustivement les concepts du document.")
            )
        except Exception as e:
            logger.error("Erreur analyze_coverage_gaps : %s", e)
            return f"Erreur analyse de couverture : {e}"

    @staticmethod
    def execute_python_tool(tool_name: str, args_json: str = "{}") -> str:
        """Exécute un outil Python déterministe depuis ToolService."""
        try:
            parsed_args = json.loads(args_json) if isinstance(args_json, str) else args_json
            state = PipelineRunState(initial_prompt="Consultant Execution")
            res = ToolService.execute_tool(tool_name, state=state, args=parsed_args)
            return json.dumps(res, ensure_ascii=False, default=str)
        except Exception as e:
            return f"Erreur lors de l'exécution de l'outil Python '{tool_name}' : {e}"


# =====================================================================
# SPÉCIFICATIONS DES OUTILS POUR L'API OPENAI / LLM
# =====================================================================

DEFAULT_CONSULTANT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "audit_deck_wozniak",
            "description": "Exécute un audit qualité ergonomique complet d'un paquet selon les 20 règles de Piotr Wozniak (atomicité, redondance, formulation).",
            "parameters": {
                "type": "object",
                "properties": {"deck_name": {"type": "string", "description": "Nom exact du paquet à auditer"}},
                "required": ["deck_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audit_card_wozniak",
            "description": "Analyse de qualité détaillée d'une note spécifique avec calcul de score et identification des violations de règles.",
            "parameters": {
                "type": "object",
                "properties": {"note_id": {"type": "integer", "description": "ID de la note à analyser"}},
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_duplicate_cards",
            "description": "Détecte les cartes doublons ou formulées de manière quasi-identique dans un paquet via distance Levenshtein.",
            "parameters": {
                "type": "object",
                "properties": {
                    "deck_name": {"type": "string", "description": "Nom du paquet (optionnel)"},
                    "threshold": {"type": "number", "description": "Seuil de similarité entre 0.0 et 1.0 (défaut: 0.75)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_card_refactor",
            "description": "Propose une modification ou reformulation d'une note avec affichage d'un Diff comparatif pour validation humaine avant enregistrement en BDD.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "ID de la note cible"},
                    "new_fields_json": {"type": "string", "description": 'Nouveaux champs au format JSON (ex: {"Front": "Question", "Back": "Réponse"})'},
                    "explanation": {"type": "string", "description": "Raison de la proposition"},
                },
                "required": ["note_id", "new_fields_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_card_split",
            "description": "Propose de scinder une note surchargée en plusieurs cartes atomiques avec Diff comparatif pour validation humaine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "ID de la note originale à scinder"},
                    "new_cards_json": {"type": "string", "description": 'Tableau JSON des nouvelles cartes atomiques (ex: [{"Front": "Q1", "Back": "R1"}, ...])'},
                    "explanation": {"type": "string", "description": "Raison de la scission"},
                },
                "required": ["note_id", "new_cards_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_css_tune",
            "description": "Propose un ajustement CSS pour un modèle de carte avec aperçu live avant enregistrement en BDD.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type_name": {"type": "string", "description": "Nom du modèle de carte"},
                    "css_snippet": {"type": "string", "description": "Snippet CSS à appliquer"},
                    "selector": {"type": "string", "description": "Sélecteur CSS optionnel"},
                },
                "required": ["note_type_name", "css_snippet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_note_types",
            "description": "Liste tous les modèles de cartes (Note Types) enregistrés dans la collection avec leurs champs et statistiques.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_note_type_details",
            "description": "Consulte la structure complète d'un modèle de carte (champs requis, templates HTML Recto/Verso, CSS et exemple de note).",
            "parameters": {
                "type": "object",
                "properties": {"note_type_name": {"type": "string", "description": "Nom exact du modèle de carte"}},
                "required": ["note_type_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_note_type_refactor",
            "description": "Propose une évolution ou refactorisation d'un modèle de carte (nouveaux champs, templates HTML, CSS, description) avec Garde-Fou Diff pour validation humaine.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type_name": {"type": "string", "description": "Nom du modèle de carte"},
                    "new_fields_schema_json": {"type": "string", "description": 'Nouveau schéma des champs en JSON (ex: ["Front", "Back", "Audio"]) (optionnel)'},
                    "new_css": {"type": "string", "description": "Nouveau CSS complet du modèle (optionnel)"},
                    "new_templates_json": {"type": "string", "description": 'Nouveaux templates HTML en JSON (ex: [{"name": "Card 1", "qfmt": "...", "afmt": "..."}]) (optionnel)'},
                    "new_description": {"type": "string", "description": "Nouvelle description ou directives d'usage (optionnel)"},
                    "explanation": {"type": "string", "description": "Raison de l'évolution du modèle"},
                },
                "required": ["note_type_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_collection_panorama_360",
            "description": "Donne une vue panoramique 360° de la collection (paquets, cartes, sangsues, documents et dernières modifications).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_deck_deep_scan",
            "description": "Analyse en profondeur un paquet (distribution des intervalles, cartes sangsues avec laps élevés).",
            "parameters": {
                "type": "object",
                "properties": {"deck_name": {"type": "string", "description": "Nom exact du paquet à analyser"}},
                "required": ["deck_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_note_full_profile_360",
            "description": "Obtient le profil complet 360° d'une note (champs, historique Time Machine, stats de rétention des cartes, tags).",
            "parameters": {
                "type": "object",
                "properties": {"note_id": {"type": "integer", "description": "ID de la note"}},
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_peewee",
            "description": "Exécute une requête SQL SELECT (lecture seule) sur SQLite pour analyser des données spécifiques.",
            "parameters": {
                "type": "object",
                "properties": {"sql_query": {"type": "string", "description": "Requête SQL SELECT valide"}},
                "required": ["sql_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_deck_stats",
            "description": "Récupère les statistiques SRS d'un paquet Anki (nombre de cartes, révisions moyennes, oublis, sangsues).",
            "parameters": {
                "type": "object",
                "properties": {"deck_name": {"type": "string", "description": "Nom exact du paquet"}},
                "required": ["deck_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cards_by_deck_or_tag",
            "description": "Récupère un lot de cartes filtrées par nom de paquet ou par tag.",
            "parameters": {
                "type": "object",
                "properties": {
                    "deck_name": {"type": "string", "description": "Nom du paquet (optionnel)"},
                    "tag": {"type": "string", "description": "Tag recherché (optionnel)"},
                    "limit": {"type": "integer", "description": "Nombre max de cartes (défaut: 15)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_cards_by_content",
            "description": "Recherche des cartes par mot-clé dans leur question/réponse pour retrouver rapidement leur note_id et contenu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Mot-clé ou extrait de texte recherché dans la carte"},
                    "deck_name": {"type": "string", "description": "Nom du paquet (optionnel)"},
                    "limit": {"type": "integer", "description": "Nombre max de résultats (défaut: 8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_attached_documents",
            "description": "Recherche sémantique ciblée dans les documents attachés via RAGService (FAISS).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Requête de recherche textuelle"},
                    "document_title": {"type": "string", "description": "Titre du document (optionnel)"},
                    "top_k": {"type": "integer", "description": "Nombre de passages à extraire (défaut: 4)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_coverage_gaps",
            "description": "Compare le contenu d'un paquet de cartes avec un document source pour identifier les notions non couvertes (Smart Coverage).",
            "parameters": {
                "type": "object",
                "properties": {
                    "deck_name": {"type": "string", "description": "Nom du paquet à comparer"},
                    "document_title": {"type": "string", "description": "Titre du document source"},
                },
                "required": ["deck_name"],
            },
        },
    },
]


def extract_tool_call_from_text(content_text: str) -> tuple[bool, str, dict[str, Any]]:
    """
    Extrait de manière robuste un appel d'outil explicite formaté en JSON ou en action ReAct.
    Ne doit PAS intercepter les simples propositions de cartes destinées à l'utilisateur.
    """
    if not content_text:
        return False, "", {}

    # 1. Format Markdown explicite : ```json {"tool": "...", "args": {...}} ``` ou {"action": "..."}
    matches = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content_text)
    for m in matches:
        try:
            parsed = robust_json_loads(m.strip())
            if isinstance(parsed, dict):
                if "tool" in parsed:
                    args_val = parsed.get("args", {})
                    return True, str(parsed["tool"]), args_val if isinstance(args_val, dict) else {}
                if "action" in parsed:
                    act_in = parsed.get("action_input", parsed.get("args", {}))
                    return True, str(parsed["action"]), act_in if isinstance(act_in, dict) else {}
        except Exception as err:
            logger.debug("Tentative de parsing JSON markdown d'outil échouée : %s", err)

    # 2. Format JSON brut explicite {"tool": "...", "args": {...}}
    tool_match = re.search(
        r'\{\s*"(?:tool|action)"\s*:\s*"([^"]+)"\s*,\s*"(?:args|action_input|arguments)"\s*:\s*(\{[\s\S]*?\})\s*\}',
        content_text,
    )
    if tool_match:
        t_name = tool_match.group(1).strip()
        try:
            t_args = robust_json_loads(tool_match.group(2))
            return True, t_name, t_args if isinstance(t_args, dict) else {}
        except Exception as err:
            logger.debug("Tentative de parsing JSON brut d'outil échouée : %s", err)

    # 3. Format texte ReAct classique : Action: nom_outil \n Action Input: {...}
    act_match = re.search(r"Action\s*:\s*([a-zA-Z0-9_]+)\s*\n\s*Action\s*Input\s*:\s*(\{[\s\S]*?\})", content_text, re.IGNORECASE)
    if act_match:
        t_name = act_match.group(1).strip()
        try:
            t_args = robust_json_loads(act_match.group(2).strip())
            return True, t_name, t_args if isinstance(t_args, dict) else {}
        except Exception:
            return True, t_name, {}

    return False, "", {}


# =====================================================================
# CLASSE PRINCIPALE : CONSULTANTENGINE (MOTEUR AUTONOME SANS FAUSSES PENSÉES)
# =====================================================================


class ConsultantEngine:
    """
    Moteur IA autonome pour le Consultant AnkiForge avec exécution d'outils de qualité et garde-fous de diffs.
    """

    def __init__(
        self,
        llm_config: LLMConfigModel | None = None,
        persona: PersonaModel | None = None,
        ai_provider: LLMProvider | None = None,
    ) -> None:
        self.llm_config = llm_config
        self.persona = persona
        self.ai_provider = ai_provider

        if self.ai_provider is None and llm_config is not None:
            try:
                self.ai_provider = AIManager.create_provider_from_config(llm_config)
            except Exception as e:
                logger.warning("Erreur lors de la création du provider IA : %s", e)

    def _execute_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> tuple[str, bool]:
        """Exécute l'outil demandé in-process et renvoie (observation, is_error)."""
        try:
            if tool_name == "audit_deck_wozniak":
                deck = tool_args.get("deck_name", "")
                return ConsultantToolRegistry.audit_deck_wozniak(deck), False
            elif tool_name == "audit_card_wozniak":
                n_id = int(tool_args.get("note_id", 0))
                return ConsultantToolRegistry.audit_card_wozniak(n_id), False
            elif tool_name == "find_duplicate_cards":
                deck = tool_args.get("deck_name", "")
                threshold = float(tool_args.get("threshold", 0.75))
                return ConsultantToolRegistry.find_duplicate_cards(deck, threshold), False
            elif tool_name == "propose_card_refactor":
                n_id = int(tool_args.get("note_id", 0))
                nf_json = tool_args.get("new_fields_json", "{}")
                expl = tool_args.get("explanation", "")
                return ConsultantToolRegistry.propose_card_refactor(n_id, nf_json, expl), False
            elif tool_name == "propose_card_split":
                n_id = int(tool_args.get("note_id", 0))
                nc_json = tool_args.get("new_cards_json", "[]")
                expl = tool_args.get("explanation", "")
                return ConsultantToolRegistry.propose_card_split(n_id, nc_json, expl), False
            elif tool_name == "propose_css_tune":
                nt_name = tool_args.get("note_type_name", "")
                css = tool_args.get("css_snippet", "")
                selector = tool_args.get("selector", "")
                return ConsultantToolRegistry.propose_css_tune(nt_name, css, selector), False
            elif tool_name == "list_note_types":
                return ConsultantToolRegistry.list_note_types(), False
            elif tool_name == "get_note_type_details":
                nt_name = tool_args.get("note_type_name") or tool_args.get("name") or ""
                return ConsultantToolRegistry.get_note_type_details(nt_name), False
            elif tool_name == "propose_note_type_refactor":
                nt_name = tool_args.get("note_type_name", "")
                n_fields = tool_args.get("new_fields_schema_json", "")
                n_css = tool_args.get("new_css", "")
                n_tpl = tool_args.get("new_templates_json", "")
                n_desc = tool_args.get("new_description", "")
                expl = tool_args.get("explanation", "")
                return ConsultantToolRegistry.propose_note_type_refactor(nt_name, n_fields, n_css, n_tpl, n_desc, expl), False
            elif tool_name == "get_collection_panorama_360":
                return ConsultantToolRegistry.get_collection_panorama_360(), False
            elif tool_name == "inspect_deck_deep_scan":
                deck = tool_args.get("deck_name") or tool_args.get("name") or ""
                return ConsultantToolRegistry.inspect_deck_deep_scan(deck), False
            elif tool_name == "get_note_full_profile_360":
                n_id = int(tool_args.get("note_id", 0))
                return ConsultantToolRegistry.get_note_full_profile_360(n_id), False
            elif tool_name == "query_peewee":
                sql = tool_args.get("sql_query") or tool_args.get("query") or ""
                return ConsultantToolRegistry.query_peewee(sql), False
            elif tool_name == "get_deck_stats":
                deck = tool_args.get("deck_name") or tool_args.get("name") or ""
                return ConsultantToolRegistry.get_deck_stats(deck), False
            elif tool_name == "get_cards_by_deck_or_tag":
                deck = tool_args.get("deck_name", "")
                tag = tool_args.get("tag", "")
                limit = int(tool_args.get("limit", 15))
                return ConsultantToolRegistry.get_cards_by_deck_or_tag(deck, tag, limit), False
            elif tool_name == "find_cards_by_content":
                query = tool_args.get("query", "")
                deck = tool_args.get("deck_name", "")
                limit = int(tool_args.get("limit", 8))
                return ConsultantToolRegistry.find_cards_by_content(query, deck, limit), False
            elif tool_name == "search_attached_documents":
                query = tool_args.get("query", "")
                doc_title = tool_args.get("document_title", "")
                top_k = int(tool_args.get("top_k", 4))
                return ConsultantToolRegistry.search_attached_documents(query, doc_title, top_k), False
            elif tool_name == "analyze_coverage_gaps":
                deck = tool_args.get("deck_name", "")
                doc_title = tool_args.get("document_title", "")
                return ConsultantToolRegistry.analyze_coverage_gaps(deck, doc_title), False
            elif tool_name == "execute_python_tool":
                t_name = tool_args.get("tool_name", "")
                args_json = tool_args.get("args_json", "{}")
                return ConsultantToolRegistry.execute_python_tool(t_name, args_json), False
            elif tool_name in MCPHooksAPI.get_registered_tools():
                plugin_tool = MCPHooksAPI.get_registered_tools()[tool_name]
                handler = plugin_tool["handler"]
                res = handler(**tool_args) if isinstance(tool_args, dict) else handler(tool_args)
                return str(res) if not isinstance(res, str) else res, False
            else:
                state = PipelineRunState(initial_prompt="Consultant Fallback")
                res = ToolService.execute_tool(tool_name, state=state, args=tool_args)
                return json.dumps(res, ensure_ascii=False, default=str), False
        except Exception as e:
            logger.exception("Erreur exécution outil %s : %s", tool_name, e)
            return f"Erreur lors de l'exécution de l'outil '{tool_name}' : {e}", True

    async def chat_stream(
        self,
        user_query: str,
        history: list[dict[str, Any]] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Générateur asynchrone exécutant l'agent avec streaming fluide token-by-token et mémoire multi-tours.
        """
        persona_prompt = "Tu es un Consultant IA expert en analyse de rétention Anki, diagnostic de collection et formulation de cartes ergonomiques (20 règles de Piotr Wozniak)."
        if self.persona and hasattr(self.persona, "system_prompt") and self.persona.system_prompt:
            persona_prompt = f"Tu es l'agent '{self.persona.name}'. Instructions système :\n{self.persona.system_prompt}\n"

        system_prompt = f"""{persona_prompt}
Tu es connecté en direct aux outils de la base de données AnkiForge :

### OUTILS DISPONIBLES :
- `get_collection_panorama_360()`: Vue panoramique 360° de la collection (paquets, cartes, sangsues, documents).
- `get_deck_stats(deck_name: str)`: Statistiques SRS d'un paquet.
- `inspect_deck_deep_scan(deck_name: str)`: Analyse des intervalles et du top des cartes sangsues.
- `audit_deck_wozniak(deck_name: str)`: Audit ergonomique Wozniak complet d'un paquet (20 règles, atomicité).
- `audit_card_wozniak(note_id: int)`: Audit chirurgical d'une note selon les 20 règles de Piotr Wozniak.
- `find_duplicate_cards(deck_name: str, threshold: float)`: Détection de doublons via distance Levenshtein.
- `find_cards_by_content(query: str, deck_name: str, limit: int)`: Retrouve facilement le `note_id` et le contenu exact d'une carte par mot-clé dans sa question/réponse.
- `get_cards_by_deck_or_tag(deck_name: str, tag: str, limit: int)`: Récupération des cartes d'un paquet ou d'un tag avec leurs IDs et modèles.
- `get_note_full_profile_360(note_id: int)`: Profil complet 360° d'une note (modèle, champs requis, cartes physiques, historique Time Machine, CSS, stats SRS).
- `list_note_types()`: Liste tous les modèles de cartes (Note Types) enregistrés avec leurs champs et statistiques.
- `get_note_type_details(note_type_name: str)`: Structure complète d'un modèle (champs requis, templates HTML, CSS, exemple).
- `propose_note_type_refactor(...)`: Propose une évolution de modèle de cartes (champs, CSS, templates) avec Garde-Fou.
- `propose_css_tune(note_type_name: str, css_snippet: str)`: Propose un ajustement CSS avec aperçu live.
- `propose_card_refactor(note_id: int, new_fields_json: str, explanation: str)`: Propose une reformulation de carte avec Diff.
- `propose_card_split(note_id: int, new_cards_json: str, explanation: str)`: Propose de scinder une note en cartes atomiques.
- `search_attached_documents(query: str, document_title: str, top_k: int)`: Recherche sémantique RAG (FAISS).
- `analyze_coverage_gaps(deck_name: str, document_title: str)`: Détection des lacunes (Smart Coverage).
- `query_peewee(sql_query: str)`: Requête SQL SELECT (lecture seule) directe sur SQLite.
- `execute_python_tool(tool_name: str, args_json: str)`: Exécute un outil Python déterministe.

### RÈGLES D'OR SUR LES MODÈLES DE CARTES :
1. Les champs des cartes dépendent du modèle (`fields_schema`). Consulte `get_note_full_profile_360` ou `get_note_type_details`.
2. Tu peux consulter les modèles via `list_note_types` et `get_note_type_details`.
3. Tu peux faire évoluer un modèle (CSS, templates, nouveaux champs) via `propose_note_type_refactor` ou `propose_css_tune`.

### MODE D'APPEL DES OUTILS :
1. Utilise les appels d'outils natifs (tool_calling) si ton API le supporte.
2. Sinon, écris un bloc JSON explicite :
```json
{{"tool": "nom_outil", "args": {{"arg1": "valeur1"}}}}
```
3. N'hésite pas à appeler `find_cards_by_content` ou `get_cards_by_deck_or_tag` pour retrouver l'ID exact des cartes avant de les refactoriser.
4. Les formules et commandes LaTeX (`\\Sigma`, `\\delta`, `\\frac{...}{...}`, `\\[ ... \\]`, etc.) sont parfaitement supportées dans les champs.
"""  # nosec B608

        # Construction de l'historique conversationnel multi-tours
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        if history:
            for h in history:
                if h.get("role") in ("user", "assistant", "tool"):
                    messages.append(h)

        messages.append({"role": "user", "content": user_query})

        max_steps = 25
        final_answer = ""
        tool_call_history: list[str] = []

        for step in range(1, max_steps + 1):
            if cancel_event and cancel_event.is_set():
                yield {"type": "cancelled", "content": "Opération interrompue par l'utilisateur."}
                return

            # Compaction in-flight transparente si la conversation dépasse le seuil
            messages = ContextCompactor.compact_in_flight(messages, max_tokens=20000, keep_last_turns=3)

            content_text = ""
            tool_calls_detected: list[tuple[str, dict[str, Any], str | None]] = []

            # 1. Appel via OpenAICompatibleProvider (avec support des tool calls natifs)
            if isinstance(self.ai_provider, OpenAICompatibleProvider) and hasattr(self.ai_provider, "client"):
                try:
                    response = self.ai_provider.client.chat.completions.create(
                        model=self.ai_provider.model_name,
                        messages=messages,  # type: ignore[arg-type]
                        tools=DEFAULT_CONSULTANT_TOOLS,  # type: ignore[arg-type]
                        temperature=0.1,
                    )
                    resp_msg = response.choices[0].message
                    content_text = resp_msg.content or ""

                    # Extraction d'une véritable pensée si le modèle en émet (ex: DeepSeek-R1 / thinking models)
                    reasoning = getattr(resp_msg, "reasoning_content", None)
                    if reasoning:
                        yield {"type": "thought", "step": step, "content": str(reasoning), "is_running": False}

                    if resp_msg.tool_calls:
                        messages.append(resp_msg)  # type: ignore[arg-type]

                        for tc in resp_msg.tool_calls:
                            tc_func = getattr(tc, "function", tc)
                            t_name = getattr(tc_func, "name", "unknown")
                            raw_args = getattr(tc_func, "arguments", "{}")
                            try:
                                t_args = robust_json_loads(raw_args) if isinstance(raw_args, str) else raw_args
                                if not isinstance(t_args, dict):
                                    t_args = {}
                            except Exception:
                                t_args = {}
                            tool_calls_detected.append((t_name, t_args, getattr(tc, "id", None)))

                except Exception as e:
                    logger.warning("Appel client OpenAI direct échoué, repli vers generate(): %s", e)

            # 2. Repli vers generate()
            if not tool_calls_detected and not content_text and self.ai_provider is not None:
                try:
                    history_lines = []
                    for m in messages:
                        r = m.get("role", "user")
                        c = m.get("content", "")
                        if r == "system":
                            continue
                        history_lines.append(f"[{r.upper()}]: {c}")

                    conversation_text = "\n\n".join(history_lines)
                    content_text = self.ai_provider.generate(
                        system_prompt=system_prompt,
                        user_prompt=conversation_text,
                        response_format="text",
                    )
                except Exception as e:
                    logger.warning("Erreur generate provider : %s", e)
                    yield {"type": "text", "content": f"⚠️ Erreur de communication avec l'IA : {e}"}
                    break

            # 3. Extraction d'éventuels blocs <think> réels
            if content_text and "<think>" in content_text and "</think>" in content_text:
                think_match = re.search(r"<think>([\s\S]*?)</think>", content_text)
                if think_match:
                    real_thought = think_match.group(1).strip()
                    yield {"type": "thought", "step": step, "content": real_thought, "is_running": False}
                    content_text = re.sub(r"<think>[\s\S]*?</think>", "", content_text).strip()

            # 4. Parsing de secours JSON
            if not tool_calls_detected and content_text:
                is_json_tool, manual_tool, manual_args = extract_tool_call_from_text(content_text)
                if is_json_tool:
                    tool_calls_detected.append((manual_tool, manual_args, None))

            # 5. Exécution des outils avec streaming
            if tool_calls_detected:
                for t_name, t_args, call_id in tool_calls_detected:
                    if cancel_event and cancel_event.is_set():
                        yield {"type": "cancelled", "content": "Opération interrompue."}
                        return

                    yield {"type": "tool_start", "step": step, "tool": t_name, "args": t_args}

                    try:
                        call_sig = f"{t_name}:{json.dumps(t_args, sort_keys=True)}"
                    except Exception:
                        call_sig = f"{t_name}:{str(t_args)}"

                    if tool_call_history.count(call_sig) >= 2:
                        logger.warning("Détection de boucle répétitive ReAct sur l'outil '%s' : interruption du cycle", t_name)
                        observation = (
                            f"⚠️ Avertissement boucle d'outils : L'outil '{t_name}' a déjà été invoqué avec ces paramètres exacts. "
                            f"Ne rappelle pas cet outil et formule directement ta réponse finale d'analyse pour l'utilisateur."
                        )
                        is_err = False
                    else:
                        observation, is_err = self._execute_tool_call(t_name, t_args)
                        tool_call_history.append(call_sig)

                    logger.info("Étape %d - Outil '%s' exécuté (is_error: %s)", step, t_name, is_err)

                    yield {"type": "tool_result", "step": step, "tool": t_name, "result": observation, "is_error": is_err}

                    if call_id:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "name": t_name,
                                "content": observation,
                            }
                        )
                    else:
                        messages.append({"role": "assistant", "content": content_text})
                        messages.append({"role": "user", "content": f"[Observation de l'outil '{t_name}'] :\n{observation}\n\nDonne ta réponse finale ou invoque un autre outil si nécessaire."})
            else:
                # Réponse finale textuelle obtenue — Streaming par petits blocs pour réactivité instantanée
                final_answer = content_text
                chunks = re.findall(r"\S+|\s+", final_answer)
                stream_batch = []
                for chunk in chunks:
                    if cancel_event and cancel_event.is_set():
                        yield {"type": "cancelled", "content": "Opération interrompue."}
                        return
                    stream_batch.append(chunk)
                    if len(stream_batch) >= 4 or "\n" in chunk:
                        delta = "".join(stream_batch)
                        yield {"type": "text_delta", "delta": delta}
                        stream_batch.clear()
                        await asyncio.sleep(0.01)

                if stream_batch:
                    yield {"type": "text_delta", "delta": "".join(stream_batch)}

                yield {"type": "text", "content": final_answer}
                break

        # Compaction post-tâche et suggestions proactives
        _, next_steps = ContextCompactor.compact_post_task(messages)
        yield {"type": "finished", "content": final_answer, "next_steps": next_steps}

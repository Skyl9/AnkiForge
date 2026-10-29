"""Moteur de Linter IA Wozniak, Diagnostic des Sources & Suivi Financier Jetons / FSRS pour AnkiForge.

Raccordement dynamique à la base de données Peewee ORM (NoteModel, DeckModel, NoteVersionModel).
"""

import json
import logging
import re
from typing import Any

from ankiforge.database.models import NoteModel, NoteVersionModel
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.c_bridge import get_similarity

logger = logging.getLogger(__name__)


_LATEX_COMMAND_RE = re.compile(r"\\([a-zA-Z]+)")
_CLOZE_RE = re.compile(r"\{\{c\d+::")
_INTERFERENCE_SIMILARITY_THRESHOLD = 0.85

_CATEGORY_PENALTY = {
    "cat-atomicite": 7,
    "cat-katex": 5,
    "cat-cloze": 6,
    "cat-interference": 3,
}


def _strip_math_delimiters(text: str) -> str:
    """Retire les régions mathématique KaTeX ($$...$$ puis $...$) pour n'examiner que le texte hors formule."""
    without_display = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
    return re.sub(r"\$[^\$]+\$", " ", without_display)


def category_score(items_count: int, category: str) -> int:
    """Score d'une catégorie selon les pénalités du contrat Wozniak (identique à audit_deck).

    Source unique de vérité des pénalités : cat-atomicite ×7, cat-katex ×5, cat-cloze ×6,
    cat-interférence ×3.
    """
    return max(0, 100 - items_count * _CATEGORY_PENALTY.get(category, 7))


def score_global_from_categories(categories: dict[str, dict[str, Any]]) -> int:
    """Reconstitue le score_global du contrat à partir des catégories (moyenne des scores catégoriels)."""
    if not categories:
        return 100
    total = sum(category_score(len(cat.get("items", [])), cat_id) for cat_id, cat in categories.items())
    return int(total / len(categories))


def normalize_linter_suggestion(
    raw_sug: Any,
    original_content: dict[str, Any] | None = None,
    rule_name: str = "",
) -> dict[str, str]:
    """Normalise universellement toute suggestion de correction émise par l'IA ou le cache.

    Garantit la présence systématique des 5 champs clés : NoteType, Recto, Verso, Champ Annexe Extra, Tags.
    """
    if isinstance(raw_sug, str):
        try:
            parsed = json.loads(raw_sug)
            raw_sug = parsed if isinstance(parsed, dict) else {"Recto": str(raw_sug), "Verso": ""}
        except json.JSONDecodeError:
            raw_sug = {"Recto": str(raw_sug), "Verso": ""}

    if not isinstance(raw_sug, dict):
        raw_sug = {}

    orig = original_content or {}
    orig_recto = orig.get("Recto") or orig.get("Front") or orig.get("Texte") or orig.get("Text") or ""
    orig_verso = orig.get("Verso") or orig.get("Back") or ""
    orig_extra = orig.get("Champ Annexe Extra") or orig.get("Extra") or orig.get("Remarques extra") or ""
    orig_tags = orig.get("Tags") or "#linter-corrigé"

    # Mappings de synonymes
    recto = raw_sug.get("Recto") or raw_sug.get("Front") or raw_sug.get("question") or raw_sug.get("Question") or raw_sug.get("Texte") or raw_sug.get("Text") or raw_sug.get("q") or orig_recto
    verso = (
        raw_sug.get("Verso")
        or raw_sug.get("Back")
        or raw_sug.get("reponse")
        or raw_sug.get("Réponse")
        or raw_sug.get("Response")
        or raw_sug.get("Answer")
        or raw_sug.get("answer")
        or raw_sug.get("r")
        or orig_verso
    )
    extra = raw_sug.get("Champ Annexe Extra") or raw_sug.get("Extra") or raw_sug.get("extra") or raw_sug.get("Remarques extra") or raw_sug.get("context") or raw_sug.get("Contexte") or orig_extra
    tags = raw_sug.get("Tags") or orig_tags
    if "#linter" not in str(tags):
        tags = f"{tags} #linter-corrigé"

    note_type = raw_sug.get("NoteType") or orig.get("NoteType") or "AnkiForge-Basic"

    # Si c'est une liste de cartes atomiques ou multi-cartes
    subcards = raw_sug.get("subcards") or raw_sug.get("cartes_atomiques")
    if isinstance(subcards, list) and subcards:
        subcard_rectos = []
        subcard_versos = []
        for i, sc in enumerate(subcards, 1):
            if isinstance(sc, dict):
                r = sc.get("Recto") or sc.get("Front") or sc.get("question") or f"Sous-carte #{i}"
                v = sc.get("Verso") or sc.get("Back") or sc.get("reponse") or ""
                subcard_rectos.append(f"{i}. {r}")
                subcard_versos.append(f"{i}. {v}")
        recto = " | ".join(subcard_rectos) if subcard_rectos else recto
        verso = " | ".join(subcard_versos) if subcard_versos else verso
        note_type = f"{note_type} ({len(subcards)} Cartes Atomiques)"

    return {
        "NoteType": str(note_type),
        "Recto": str(recto),
        "Verso": str(verso),
        "Champ Annexe Extra": str(extra),
        "Tags": str(tags),
    }


class WozniakLinterEngine:
    """Moteur d'évaluation ergonomique Wozniak à 20 règles raccordé dynamiquement aux notes Peewee."""

    @staticmethod
    def audit_deck(deck_id: int | None = None, enable_cloze_audit: bool = True) -> dict[str, Any]:
        """Analyse dynamiquement les notes du paquet sélectionné (ou toutes les notes) et retourne un rapport d'audit structuré par catégorie."""
        notes_with_version = []
        try:
            from ankiforge.database.models import CardModel

            query = NoteModel.select()
            if deck_id:
                query = query.join(CardModel, on=(NoteModel.id == CardModel.note_id)).where(CardModel.deck_id == deck_id).distinct()

            for note in query:
                active_ver = NoteVersionModel.get_or_none(note=note, is_active=True)
                content = {}
                if active_ver and active_ver.content:
                    try:
                        content = json.loads(active_ver.content)
                    except Exception:
                        content = {"Text": str(active_ver.content)}

                notes_with_version.append(
                    {
                        "id": note.id,
                        "note_type": note.note_type.name if note.note_type else "AnkiForge-Basic",
                        "tags": note.tags or "#general",
                        "recto": content.get("Recto", content.get("Text", "")),
                        "verso": content.get("Verso", ""),
                        "extra": content.get("Champ Annexe Extra", content.get("Extra", "")),
                    }
                )
        except Exception as e:
            logger.warning("Note: Analyse BDD Peewee différée ou fallback: %s", e)

        # Catégories réelles
        cat_atomicite_items = WozniakLinterEngine._detect_atomicite_issues(notes_with_version)
        cat_katex_items = WozniakLinterEngine._detect_katex_issues(notes_with_version)
        cat_cloze_items = WozniakLinterEngine._detect_cloze_issues(notes_with_version) if enable_cloze_audit else []
        cat_interference_items = WozniakLinterEngine._detect_interference_issues(notes_with_version)

        score_atomicite = category_score(len(cat_atomicite_items), "cat-atomicite")
        score_katex = category_score(len(cat_katex_items), "cat-katex")
        score_cloze = category_score(len(cat_cloze_items), "cat-cloze") if enable_cloze_audit else 100
        score_interference = category_score(len(cat_interference_items), "cat-interference")

        score_global = score_global_from_categories(
            {
                "cat-atomicite": {"items": cat_atomicite_items},
                "cat-katex": {"items": cat_katex_items},
                "cat-cloze": {"items": cat_cloze_items},
                "cat-interference": {"items": cat_interference_items},
            }
        )
        logger.info(
            "Audit Wozniak calculé : %d notes analysées, Score global: %d/100 (atomicité: %d, katex: %d, cloze: %d, interférence: %d)",
            len(notes_with_version),
            score_global,
            score_atomicite,
            score_katex,
            score_cloze,
            score_interference,
        )

        return {
            "score_global": score_global,
            "enable_cloze_audit": enable_cloze_audit,
            "categories": {
                "cat-atomicite": {
                    "score": score_atomicite,
                    "count": len(cat_atomicite_items),
                    "title": "Atomicité & Restructuration",
                    "subtitle": f"{len(cat_atomicite_items)} cartes complexes ou surchargées",
                    "color": DesignTokens.COLOR_RED_TEXT,
                    "items": cat_atomicite_items,
                },
                "cat-katex": {
                    "score": score_katex,
                    "count": len(cat_katex_items),
                    "title": "Formules & Clarté",
                    "subtitle": f"{len(cat_katex_items)} formules avec Live Preview KaTeX",
                    "color": DesignTokens.COLOR_PURPLE_TEXT,
                    "items": cat_katex_items,
                },
                "cat-cloze": {
                    "score": score_cloze,
                    "count": len(cat_cloze_items),
                    "title": "Questions Univoques Q/R",
                    "subtitle": f"{len(cat_cloze_items)} conversions Cloze → Q/R",
                    "color": DesignTokens.COLOR_YELLOW_TEXT,
                    "items": cat_cloze_items,
                },
                "cat-interference": {
                    "score": score_interference,
                    "count": len(cat_interference_items),
                    "title": "Désambiguïsation & Non-Interférence",
                    "subtitle": f"{len(cat_interference_items)} désambiguïsations contextuelles",
                    "color": DesignTokens.COLOR_BLUE_TEXT,
                    "items": cat_interference_items,
                },
            },
        }

    @staticmethod
    def _detect_atomicite_issues(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = []
        # Aucune carte factice n'est générée quand la base est vide : on retourne [].
        for n in notes:
            text = n["recto"] + " " + n["verso"]
            if len(text.split()) > 40 or "," in n["recto"]:
                items.append(
                    {
                        "card_id": n["id"],
                        "title": f"Carte #{n['id']} · {n['recto'][:30]}...",
                        "badge": "Surcharge Atomicité détectée",
                        "badge_color": DesignTokens.COLOR_RED_TEXT,
                        "schema": "atomic_split",
                        "original": n,
                        "proposal_summary": "PROPOSITION MCP : DÉCOUPE ATOMIQUE",
                        "proposal": {
                            "NoteType": "AnkiForge-Basic (Multi-cartes)",
                            "Recto": f"Reformulation univoque de : {n['recto'][:40]}",
                            "Verso": f"Réponse concise : {n['verso'][:40]}",
                            "Champ Annexe Extra": n["extra"],
                            "Tags": n["tags"] + " #atomic",
                        },
                    }
                )
        return items

    @staticmethod
    def _detect_katex_issues(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for n in notes:
            text = n["recto"] + " " + n["verso"]
            # Délimiteurs KaTeX non appariés (nombre de $ impair).
            if text.count("$") % 2 != 0:
                items.append(
                    {
                        "card_id": n["id"],
                        "title": f"Carte #{n['id']} · {n['recto'][:30]}...",
                        "badge": "Délimiteurs KaTeX non appariés",
                        "badge_color": DesignTokens.COLOR_RED_TEXT,
                        "schema": "katex_unbalanced",
                        "original": n,
                        "proposal_summary": "PROPOSITION MCP : FERMER LES DELIMITERS KATEX",
                        "proposal": {
                            "NoteType": "AnkiForge-Basic",
                            "Recto": n["recto"],
                            "Verso": n["verso"],
                            "Champ Annexe Extra": n["extra"],
                            "Tags": n["tags"] + " #katex",
                        },
                    }
                )
                continue
            # Commandes LaTeX utilisées hors mode mathématique (hors $...$ et $$...$$).
            hors_formule = _strip_math_delimiters(text)
            if _LATEX_COMMAND_RE.search(hors_formule):
                items.append(
                    {
                        "card_id": n["id"],
                        "title": f"Carte #{n['id']} · {n['recto'][:30]}...",
                        "badge": "Formule KaTeX non délimitée",
                        "badge_color": DesignTokens.COLOR_PURPLE_TEXT,
                        "schema": "katex_undelimited",
                        "original": n,
                        "proposal_summary": "PROPOSITION MCP : ENCAPSULER LA FORMULE KATEX",
                        "proposal": {
                            "NoteType": "AnkiForge-Basic",
                            "Recto": n["recto"],
                            "Verso": n["verso"],
                            "Champ Annexe Extra": n["extra"],
                            "Tags": n["tags"] + " #katex",
                        },
                    }
                )
        return items

    @staticmethod
    def _detect_cloze_issues(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for n in notes:
            if _CLOZE_RE.search(n["recto"]) or _CLOZE_RE.search(n["verso"]):
                items.append(
                    {
                        "card_id": n["id"],
                        "title": f"Carte #{n['id']} · {n['recto'][:30]}...",
                        "badge": "Cloze sur une note de type Basic",
                        "badge_color": DesignTokens.COLOR_YELLOW_TEXT,
                        "schema": "cloze_to_qr",
                        "original": n,
                        "proposal_summary": "PROPOSITION MCP : CONVERTIR LE CLOZE EN QUESTION/REPONSE",
                        "proposal": {
                            "NoteType": "AnkiForge-Basic (Q/R directes)",
                            "Recto": n["recto"],
                            "Verso": n["verso"],
                            "Champ Annexe Extra": n["extra"],
                            "Tags": n["tags"] + " #cloze",
                        },
                    }
                )
        return items

    @staticmethod
    def _detect_interference_issues(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for i in range(len(notes)):
            for j in range(i + 1, len(notes)):
                sim = get_similarity(notes[i]["recto"], notes[j]["recto"])
                if sim >= _INTERFERENCE_SIMILARITY_THRESHOLD:
                    items.append(
                        {
                            "card_id": notes[j]["id"],
                            "title": f"Cartes #{notes[i]['id']} & #{notes[j]['id']} · interférence",
                            "badge": "Interférence sémantique entre deux cartes",
                            "badge_color": DesignTokens.COLOR_BLUE_TEXT,
                            "schema": "interference",
                            "original": notes[j],
                            "proposal_summary": "PROPOSITION MCP : DESAMBIGUISER LE CONTEXTE",
                            "proposal": {
                                "NoteType": "AnkiForge-Basic (Désambiguïsée)",
                                "Recto": notes[j]["recto"],
                                "Verso": notes[j]["verso"],
                                "Champ Annexe Extra": notes[j]["extra"],
                                "Tags": notes[j]["tags"] + " #disambiguation",
                            },
                        }
                    )
        return items


class TokenSrsFinancialService:
    """Service d'analyse financière des jetons consommés et de répartition de maturité des cartes."""

    @staticmethod
    def get_financial_summary(deck_id: int | None = None) -> dict[str, Any]:
        """Retourne le bilan financier des jetons consommés et la répartition de maturité des cartes."""
        from peewee import fn

        from ankiforge.database.models import CardModel, TokenUsageModel

        query = CardModel.select()
        if deck_id is not None:
            query = query.where(CardModel.deck_id == deck_id)
        total_cards = query.count()

        maturing_cards = query.where(CardModel.ivl > 21).count()
        new_cards = query.where(CardModel.ivl == 0).count()
        learning_cards = query.where((CardModel.ivl > 0) & (CardModel.ivl <= 21)).count()

        # Token usage aggregation (périmètre global : TokenUsageModel n'est pas lié à un paquet,
        # le numérateur de coût reste donc global pour rester cohérent avec le dénominateur).
        total_spent = TokenUsageModel.select(fn.SUM(TokenUsageModel.estimated_cost_usd)).scalar() or 0.0
        total_tokens = TokenUsageModel.select(fn.SUM(TokenUsageModel.total_tokens)).scalar() or 0

        total_cards_all = CardModel.select().count()

        avg_cost = total_spent / total_cards_all if total_cards_all > 0 else 0.0

        # Models usage
        models_query = TokenUsageModel.select(TokenUsageModel.model_id, fn.SUM(TokenUsageModel.estimated_cost_usd).alias("cost"), fn.SUM(TokenUsageModel.total_tokens).alias("tokens")).group_by(
            TokenUsageModel.model_id
        )

        colors = ["#4285F4", "#10a37f", "#c084fc", "#f59e0b"]
        models_list = []
        for i, mq in enumerate(models_query):
            mq_cost = float(getattr(mq, "cost", 0.0) or 0.0)
            mq_tokens = int(getattr(mq, "tokens", 0) or 0)
            pct = (mq_cost / total_spent * 100) if total_spent > 0 else 0
            models_list.append(
                {
                    "name": str(mq.model_id),
                    "cost_usd": mq_cost,
                    "tokens": mq_tokens,
                    "pct": pct,
                    "color": colors[i % len(colors)],
                }
            )

        if not models_list:
            models_list = [
                {
                    "name": "Aucun Modèle API Utilisé",
                    "cost_usd": 0.0,
                    "tokens": 0,
                    "pct": 0.0,
                    "color": "var(--color-blue)",
                }
            ]

        # Add Local model manually since it's zero cost
        models_list.append(
            {
                "name": "Modèles Locaux (Marker PDF & Whisper AI)",
                "cost_usd": 0.0,
                "tokens": 0,
                "pct": 0.0,
                "color": "var(--color-green)",
            }
        )

        # Task Breakdown
        task_query = TokenUsageModel.select(TokenUsageModel.task_type, fn.SUM(TokenUsageModel.estimated_cost_usd).alias("cost")).group_by(TokenUsageModel.task_type)

        tasks_breakdown = []
        for i, tq in enumerate(task_query):
            tq_cost = float(getattr(tq, "cost", 0.0) or 0.0)
            pct = (tq_cost / total_spent * 100) if total_spent > 0 else 0
            tasks_breakdown.append({"task": str(tq.task_type), "cost_usd": tq_cost, "pct": pct, "color": colors[i % len(colors)]})

        if not tasks_breakdown:
            tasks_breakdown = [
                {"task": "1. Reformulation & Génération Wozniak", "cost_usd": 0.0, "pct": 0.0, "color": "var(--accent-primary)"},
                {"task": "2. Extraction & Structure Sources (PDF/Web)", "cost_usd": 0.0, "pct": 0.0, "color": "var(--color-blue)"},
                {"task": "3. Audit Linter Ergonomique & Live KaTeX", "cost_usd": 0.0, "pct": 0.0, "color": "#c084fc"},
            ]

        avg_cost = total_spent / total_cards_all if total_cards_all > 0 else 0.0

        return {
            "total_spent_usd": total_spent,
            "avg_cost_per_card_usd": avg_cost,
            "tokens_consumed": total_tokens,
            "maturing_cards": maturing_cards,
            "total_cards": total_cards,
            "models": models_list,
            "tasks_breakdown": tasks_breakdown,
            "maturity_distribution": {
                "new": new_cards,
                "learning": learning_cards,
                "maturing": maturing_cards,
            },
        }

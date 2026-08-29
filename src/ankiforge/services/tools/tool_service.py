"""Service de gestion et d'exécution des Outils Python déterministes pour le Moteur DAG et le Consultant IA.

- Fournit des outils natifs haute performance (Nettoyeur HTML/LaTeX, Déduplication Levenshtein, Valideur JSON, Métriques).
- Permet l'enregistrement, l'édition et l'exécution dynamique de scripts personnalisés stockés en base SQLite.
- Expose des interfaces prêtes pour les agents et le protocole MCP.
"""

import datetime
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from ankiforge.database.models import PythonToolModel, db
from ankiforge.services.ai.state import PipelineRunState

logger = logging.getLogger(__name__)


# =====================================================================
# IMPLÉMENTATIONS DES OUTILS NATIFS (BUILT-IN TOOLS)
# =====================================================================


def tool_clean_html_latex(state: PipelineRunState, args: dict[str, Any] | None = None) -> Any:
    """Nettoie le HTML et harmonise les délimiteurs mathématiques LaTeX sur les cartes ou le texte généré."""
    cards = state.get_variable("generated_cards")
    cleaned_count = 0

    def _clean_text(text: str) -> str:
        if not text:
            return ""
        # 1. Harmoniser les délimiteurs LaTeX $$ ... $$ -> \[ ... \]
        text = re.sub(r"\$\$(.+?)\$\$", r"\\[\1\\]", text, flags=re.DOTALL)
        # 2. Harmoniser $ ... $ -> \( ... \) (sans capturer les prix comme 10$)
        text = re.sub(r"(?<!\\)\$(?!\s)(.+?)(?<!\s)\$", r"\\(\1\\)", text)
        # 3. Supprimer les balises dangereuses ou parasites
        text = re.sub(r"<(script|style|iframe)[^>]*>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # 4. Normaliser les espaces consécutifs et balises vides
        text = re.sub(r"<p>\s*</p>", "", text)
        text = re.sub(r"<div>\s*</div>", "", text)
        return text.strip()

    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict):
                for field, val in card.items():
                    if isinstance(val, str):
                        card[field] = _clean_text(val)
                cleaned_count += 1
        state.set_variable("generated_cards", cards)
        logger.info("[Tool:clean_html_latex] %d cartes nettoyées et harmonisées.", cleaned_count)
        return {"status": "success", "cleaned_cards": cleaned_count}

    # Si pas de liste de cartes, traiter last_output
    last_out = state.get_variable("last_output")
    if isinstance(last_out, str):
        cleaned_out = _clean_text(last_out)
        state.set_variable("last_output", cleaned_out)
        return {"status": "success", "result": cleaned_out}

    return {"status": "skipped", "reason": "No cards or text to clean"}


def tool_deduplicate_levenshtein(state: PipelineRunState, args: dict[str, Any] | None = None) -> Any:
    """Élimine les doublons ou quasi-doublons parmi les cartes générées via calcul de similarité."""
    cards = state.get_variable("generated_cards")
    if not isinstance(cards, list) or len(cards) <= 1:
        return {"status": "skipped", "reason": "Not enough cards to deduplicate"}

    threshold = float(args.get("threshold", 0.85)) if args else 0.85

    def _similarity_ratio(s1: str, s2: str) -> float:
        """Calcul de ratio de similarité rapide (Jaccard sur n-grammes de mots)."""
        w1 = set(re.findall(r"\w+", s1.lower()))
        w2 = set(re.findall(r"\w+", s2.lower()))
        if not w1 or not w2:
            return 0.0
        intersection = len(w1.intersection(w2))
        union = len(w1.union(w2))
        return intersection / float(union) if union > 0 else 0.0

    unique_cards: list[dict] = []
    removed_count = 0

    for card in cards:
        if not isinstance(card, dict):
            continue
        front = str(card.get("Front") or card.get("front") or card.get("recto") or list(card.values())[0] if card else "")
        is_dup = False
        for seen in unique_cards:
            seen_front = str(seen.get("Front") or seen.get("front") or seen.get("recto") or list(seen.values())[0] if seen else "")
            sim = _similarity_ratio(front, seen_front)
            if sim >= threshold:
                is_dup = True
                removed_count += 1
                break
        if not is_dup:
            unique_cards.append(card)

    state.set_variable("generated_cards", unique_cards)
    logger.info("[Tool:deduplicate_levenshtein] %d doublons supprimés (seuil=%.2f).", removed_count, threshold)
    return {"status": "success", "removed_duplicates": removed_count, "remaining_cards": len(unique_cards)}


def tool_validate_json_schema(state: PipelineRunState, args: dict[str, Any] | None = None) -> Any:
    """Valide et extrait strictement une liste de dictionnaires depuis les sorties brutes de l'IA."""
    raw_output = state.get_variable("last_output")
    extracted_cards: list[dict] = []

    if isinstance(raw_output, dict) and "cards" in raw_output and isinstance(raw_output["cards"], list):
        extracted_cards = [c for c in raw_output["cards"] if isinstance(c, dict)]
    elif isinstance(raw_output, list):
        extracted_cards = [c for c in raw_output if isinstance(c, dict)]
    elif isinstance(raw_output, str):
        # Tenter d'extraire un bloc JSON via regex
        m = re.search(r"```json\s*(.*?)\s*```", raw_output, flags=re.DOTALL)
        candidate = m.group(1) if m else raw_output
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "cards" in parsed:
                extracted_cards = [c for c in parsed["cards"] if isinstance(c, dict)]
            elif isinstance(parsed, list):
                extracted_cards = [c for c in parsed if isinstance(c, dict)]
        except Exception as e:
            logger.debug("Extraction JSON schema échouée: %s", e)

    if extracted_cards:
        state.set_variable("generated_cards", extracted_cards)
        return {"status": "success", "valid_cards_count": len(extracted_cards)}

    return {"status": "error", "message": "Impossible de valider un schéma de cartes JSON valide."}


def tool_compute_metrics(state: PipelineRunState, args: dict[str, Any] | None = None) -> Any:
    """Calcule des métriques statistiques sur les cartes et le contenu traité."""
    cards = state.get_variable("generated_cards", [])
    total_words = 0
    total_cards = len(cards) if isinstance(cards, list) else 0

    if isinstance(cards, list):
        for c in cards:
            if isinstance(c, dict):
                for v in c.values():
                    if isinstance(v, str):
                        total_words += len(v.split())

    avg_words = (total_words / total_cards) if total_cards > 0 else 0.0
    metrics = {
        "total_cards": total_cards,
        "total_words": total_words,
        "average_words_per_card": round(avg_words, 1),
    }
    state.set_variable("pipeline_metrics", metrics)
    return metrics


# Dictionnaire des outils natifs enregistrés
BUILTIN_TOOL_CALLABLES: dict[str, Callable[[PipelineRunState, dict[str, Any] | None], Any]] = {
    "clean_html_latex": tool_clean_html_latex,
    "deduplicate_cards_levenshtein": tool_deduplicate_levenshtein,
    "validate_json_schema": tool_validate_json_schema,
    "compute_stats_and_metrics": tool_compute_metrics,
}

BUILTIN_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "clean_html_latex",
        "display_name": "🧹 Nettoyeur HTML & Formules LaTeX",
        "description": "Harmonise les délimiteurs mathématiques LaTeX (\\(..\\), \\[..\\]) et nettoie les balises parasites.",
        "code": """def run(state):\n    from ankiforge.services.tools.tool_service import tool_clean_html_latex\n    return tool_clean_html_latex(state)""",
    },
    {
        "name": "deduplicate_cards_levenshtein",
        "display_name": "🔍 Déduplication de Cartes (Levenshtein)",
        "description": "Détecte et élimine automatiquement les flashcards redondantes ou quasi-identiques.",
        "code": """def run(state):\n    from ankiforge.services.tools.tool_service import tool_deduplicate_levenshtein\n    return tool_deduplicate_levenshtein(state)""",
    },
    {
        "name": "validate_json_schema",
        "display_name": "🛡️ Validation & Réparation de Schéma JSON",
        "description": "Extrait et valide strictement le format des flashcards depuis les sorties textuelles de l'IA.",
        "code": """def run(state):\n    from ankiforge.services.tools.tool_service import tool_validate_json_schema\n    return tool_validate_json_schema(state)""",
    },
    {
        "name": "compute_stats_and_metrics",
        "display_name": "📊 Calculateur de Statistiques & Métriques",
        "description": "Analyse le nombre de mots, la concision et la densité des cartes générées.",
        "code": """def run(state):\n    from ankiforge.services.tools.tool_service import tool_compute_metrics\n    return tool_compute_metrics(state)""",
    },
]


# =====================================================================
# SERVICE CENTRAL DE GESTION DES OUTILS (ToolService)
# =====================================================================


class ToolService:
    """Service centralisé pour la découverte, création, mise à jour et exécution des outils Python."""

    @classmethod
    def seed_builtin_tools(cls) -> None:
        """Enregistre ou met à jour les outils built-in dans la base SQLite."""
        try:
            with db.atomic():
                for def_tool in BUILTIN_TOOL_DEFINITIONS:
                    tool, created = PythonToolModel.get_or_create(
                        name=def_tool["name"],
                        defaults={
                            "display_name": def_tool["display_name"],
                            "description": def_tool["description"],
                            "code": def_tool["code"],
                            "is_builtin": True,
                        },
                    )
                    if not created and tool.is_builtin:
                        tool.display_name = def_tool["display_name"]
                        tool.description = def_tool["description"]
                        tool.code = def_tool["code"]
                        tool.save()
        except Exception as e:
            logger.warning("Erreur seed_builtin_tools: %s", e)

    @classmethod
    def list_tools(cls) -> list[PythonToolModel]:
        """Retourne la liste de tous les outils disponibles (natifs et personnalisés)."""
        cls.seed_builtin_tools()
        try:
            return list(PythonToolModel.select().order_by(PythonToolModel.is_builtin.desc(), PythonToolModel.name.asc()))
        except Exception as e:
            logger.warning("Erreur list_tools: %s", e)
            return []

    @classmethod
    def get_tool(cls, name: str) -> PythonToolModel | None:
        """Récupère un outil par son nom identifiant."""
        return PythonToolModel.get_or_none(PythonToolModel.name == name)

    @classmethod
    def create_or_update_tool(
        cls,
        name: str,
        display_name: str,
        description: str,
        code: str,
        is_builtin: bool = False,
    ) -> PythonToolModel:
        """Crée ou met à jour un outil Python personnalisé."""
        tool = PythonToolModel.get_or_none(PythonToolModel.name == name)
        if tool:
            tool.display_name = display_name
            tool.description = description
            tool.code = code
            tool.save()
            logger.info("Outil Python '%s' mis à jour.", name)
            return tool
        else:
            new_tool = PythonToolModel.create(
                name=name,
                display_name=display_name,
                description=description,
                code=code,
                is_builtin=is_builtin,
                created_at=datetime.datetime.now(),
            )
            logger.info("Outil Python '%s' créé avec succès.", name)
            return new_tool

    @classmethod
    def delete_tool(cls, name: str) -> bool:
        """Supprime un outil personnalisé (les built-in sont protégés)."""
        tool = PythonToolModel.get_or_none(PythonToolModel.name == name)
        if tool:
            if tool.is_builtin:
                raise ValueError("Impossible de supprimer un outil natif (built-in).")
            tool.delete_instance()
            return True
        return False

    @classmethod
    def execute_tool(cls, tool_name: str, state: PipelineRunState, args: dict[str, Any] | None = None) -> Any:
        """
        Exécute un outil par son nom sur l'état du pipeline.
        Cherche d'abord dans les fonctions natives, puis dans les scripts personnalisés de la base SQLite.
        """
        # 1. Appel direct si fonction native déclarée
        if tool_name in BUILTIN_TOOL_CALLABLES:
            return BUILTIN_TOOL_CALLABLES[tool_name](state, args)

        # 2. Recherche en base Peewee
        tool = cls.get_tool(tool_name)
        if not tool:
            msg = f"Outil Python '{tool_name}' non trouvé dans le registre."
            logger.warning(msg)
            return {"status": "error", "error": msg}

        # 3. Exécution dynamique sécurisée du script Python
        local_scope: dict[str, Any] = {}
        global_scope: dict[str, Any] = {
            "state": state,
            "args": args or {},
            "json": json,
            "re": re,
            "datetime": datetime,
            "logging": logging,
            "logger": logging.getLogger(f"custom_tool.{tool_name}"),
        }

        try:
            exec(str(tool.code), global_scope, local_scope)  # nosec B102
            run_fn = local_scope.get("run") or global_scope.get("run")

            if callable(run_fn):
                result = run_fn(state)
                return result
            else:
                msg = f"Le script de l'outil '{tool_name}' doit définir une fonction 'def run(state):'."
                logger.error(msg)
                return {"status": "error", "error": msg}
        except Exception as e:
            logger.exception("Erreur lors de l'exécution de l'outil '%s': %s", tool_name, e)
            return {"status": "error", "error": str(e)}

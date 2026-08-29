"""
Moteur IA Autonome ReAct & MCP pour le Consultant AnkiForge.

- Boucle ReAct (Thought ➔ Action ➔ Observation ➔ Response) multi-étapes.
- Registre unifié d'outils MCP in-process (Peewee + Outils Python ToolService).
- Support unifié de tous les fournisseurs (OpenAI, Ollama, Groq, Gemini, Anthropic, MockProvider).
- Analyse robuste des appels d'outils (appels de fonctions natifs et blocs JSON textuels).
- Émission structurée d'événements (Réflexion, Appel d'Outil, Observation, Réponse Finale).
"""

import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from peewee import fn

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
    db,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.flexible_service import AIManager, OpenAICompatibleProvider
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.plugins.api import MCPHooksAPI
from ankiforge.services.tools.tool_service import ToolService

logger = logging.getLogger(__name__)


# =====================================================================
# GESTIONNAIRE D'OUTILS DIRECTS IN-PROCESS POUR LE CONSULTANT
# =====================================================================


class ConsultantToolRegistry:
    """Exécuteur d'outils MCP in-process sécurisé pour le Consultant IA."""

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
                        content = json.loads(active_v.content)
                    except Exception:
                        content = {"raw": active_v.content}
                res_list.append({"note_id": n.id, "tags": n.tags, "fields": content})

            return json.dumps(res_list, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Erreur de récupération des cartes : {e}"

    @staticmethod
    def update_card_model_css(note_type_name: str, css_rule: str) -> str:
        """Injecte des règles CSS dans le modèle de carte NoteTypeModel."""
        try:
            nt = NoteTypeModel.get_or_none(NoteTypeModel.name == note_type_name.strip())
            if not nt:
                return f"Erreur : Le modèle '{note_type_name}' n'existe pas."

            with db.atomic():
                nt.css_style = (nt.css_style or "") + f"\n\n/* Ajouté par le Consultant IA */\n{css_rule}"
                nt.save()
            return f"Succès : Le style CSS du modèle '{nt.name}' a été enrichi avec succès !"
        except Exception as e:
            return f"Erreur lors de la mise à jour CSS : {e}"

    @staticmethod
    def execute_python_tool(tool_name: str, args_json: str = "{}") -> str:
        """Exécute un outil Python déterministe depuis ToolService."""
        try:
            parsed_args = json.loads(args_json) if isinstance(args_json, str) else args_json
            state = PipelineRunState(initial_prompt="Consultant IA Execution")
            res = ToolService.execute_tool(tool_name, state=state, args=parsed_args)
            return json.dumps(res, ensure_ascii=False, default=str)
        except Exception as e:
            return f"Erreur lors de l'exécution de l'outil Python '{tool_name}' : {e}"

    @staticmethod
    def list_available_tools() -> str:
        """Liste tous les outils disponibles pour le consultant."""
        tools_info = [
            "- query_peewee: Requête SQL de lecture seule sur les paquets et cartes.",
            "- get_deck_stats: Statistiques SRS et sangsues sur un paquet.",
            "- get_cards_by_deck_or_tag: Recherche de cartes par deck ou tag.",
            "- update_card_model_css: Ajout de style CSS sur un NoteType.",
            "- execute_python_tool: Exécute un outil Python déterministe enregistré.",
        ]
        try:
            for t in ToolService.list_tools():
                tools_info.append(f"- PythonTool:{t.name} ({t.display_name}) : {t.description}")
        except Exception as err:
            logger.debug("Remarque lors du listage des outils pour Consultant : %s", err)
        return "\n".join(tools_info)


# =====================================================================
# SPÉCIFICATIONS DES OUTILS POUR L'API OPENAI / MCP
# =====================================================================

DEFAULT_CONSULTANT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_peewee",
            "description": "Exécute une requête SQL SELECT sur la base SQLite pour compter ou analyser des cartes, paquets ou personas.",
            "parameters": {
                "type": "object",
                "properties": {"sql_query": {"type": "string", "description": "Requête SQL SELECT valide (ex: SELECT count(*) FROM cardmodel;)"}},
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
            "name": "update_card_model_css",
            "description": "Met à jour et enrichit le style CSS d'un modèle de carte (NoteTypeModel).",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_type_name": {"type": "string", "description": "Nom du modèle de note"},
                    "css_rule": {"type": "string", "description": "Code CSS à ajouter"},
                },
                "required": ["note_type_name", "css_rule"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_python_tool",
            "description": "Exécute un outil Python utilitaire (clean_html_latex, deduplicate_cards_levenshtein, validate_json_schema, compute_stats_and_metrics).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "Nom de l'outil Python"},
                    "args_json": {"type": "string", "description": "Arguments de l'outil sous forme d'objet JSON sérialisé"},
                },
                "required": ["tool_name"],
            },
        },
    },
]


def extract_tool_call_from_text(content_text: str) -> tuple[bool, str, dict[str, Any]]:
    """Extrait de manière robuste un appel d'outil formaté en JSON dans une réponse textuelle."""
    if not content_text:
        return False, "", {}

    # 1. Matcher les blocs de code markdown ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content_text)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict) and "tool" in parsed:
                return True, str(parsed["tool"]), parsed.get("args", {})
        except Exception as err:
            logger.debug("Tentative de parsing JSON markdown d'outil échouée : %s", err)

    # 2. Matcher un JSON brut avec clé "tool"
    tool_match = re.search(r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*(\{[\s\S]*?\})\s*\}', content_text)
    if tool_match:
        t_name = tool_match.group(1)
        try:
            t_args = json.loads(tool_match.group(2))
            return True, t_name, t_args
        except Exception as err:
            logger.debug("Tentative de parsing JSON brut d'outil échouée : %s", err)

    # 3. Chercher de la première accolade '{' à la dernière '}'
    start_idx = content_text.find("{")
    end_idx = content_text.rfind("}")
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        try:
            candidate = content_text[start_idx : end_idx + 1]
            parsed = json.loads(candidate)
            if isinstance(parsed, dict) and "tool" in parsed:
                return True, str(parsed["tool"]), parsed.get("args", {})
        except Exception as err:
            logger.debug("Tentative de parsing candidate JSON d'outil échouée : %s", err)

    return False, "", {}


# =====================================================================
# CLASSE PRINCIPALE : CONSULTANTENGINE (MOTEUR REACT)
# =====================================================================


class ConsultantEngine:
    """
    Moteur IA autonome pour le Consultant — Orchestre la boucle ReAct (Thought ➔ Action ➔ Observation).
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
            if tool_name == "query_peewee":
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
            elif tool_name == "update_card_model_css":
                nt_name = tool_args.get("note_type_name", "")
                css = tool_args.get("css_rule", "")
                return ConsultantToolRegistry.update_card_model_css(nt_name, css), False
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
                # Tentative d'exécution directe via ToolService
                state = PipelineRunState(initial_prompt="Consultant Fallback")
                res = ToolService.execute_tool(tool_name, state=state, args=tool_args)
                return json.dumps(res, ensure_ascii=False, default=str), False
        except Exception as e:
            logger.exception("Erreur exécution outil %s : %s", tool_name, e)
            return f"Erreur lors de l'exécution de l'outil '{tool_name}' : {e}", True

    async def chat_stream(self, user_query: str) -> AsyncGenerator[dict[str, Any], None]:
        """
        Générateur asynchrone exécutant la boucle ReAct.
        Émet des dictionnaires structurés :
          - {"type": "thought", "step": N, "content": "..."}
          - {"type": "tool_start", "step": N, "tool": "...", "args": {...}}
          - {"type": "tool_result", "step": N, "tool": "...", "result": "...", "is_error": bool}
          - {"type": "text", "content": "..."}
          - {"type": "finished", "content": "..."}
        """
        persona_prompt = "Tu es un Consultant IA expert en analyse de rétention Anki, diagnostic de collection et modèles de cartes."
        if self.persona and hasattr(self.persona, "system_prompt") and self.persona.system_prompt:
            persona_prompt = f"Tu es l'agent '{self.persona.name}'. Instructions système :\n{self.persona.system_prompt}\n"

        system_prompt = f"""{persona_prompt}
Tu es connecté en direct à la base de données AnkiForge via les outils MCP ci-dessous :

### OUTILS MCP DISPONIBLES :
1. `query_peewee(sql_query: str)`: Exécute une requête SQL SELECT (lecture seule) sur SQLite.
   - Tables : `deckmodel`, `cardmodel`, `notemodel`, `notetypemodel`, `personas`, `pipelines`, `documents`.
   - Exemples : "SELECT count(*) FROM cardmodel;", "SELECT name FROM deckmodel;"
2. `get_deck_stats(deck_name: str)`: Calcule les statistiques d'un paquet (total cartes, révisions moyennes, oublis, sangsues).
3. `get_cards_by_deck_or_tag(deck_name: str, tag: str, limit: int)`: Inspecte un lot de cartes.
4. `update_card_model_css(note_type_name: str, css_rule: str)`: Ajoute du style CSS à un modèle de cartes.
5. `execute_python_tool(tool_name: str, args_json: str)`: Exécute un outil Python déterministe.

### RÈGLE D'UTILISATION DES OUTILS :
Quand une question porte sur les données de l'utilisateur (cartes, paquets, sangsues, stats), INVOQUE DIRECTEMENT un outil !
Si ton client ne gère pas les appels de fonctions natifs, renvoie UNIQUEMENT ce bloc JSON :
```json
{{
    "tool": "nom_de_l_outil",
    "args": {{
        "nom_argument": "valeur"
    }}
}}
```
"""  # nosec B608
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ]

        max_steps = 6
        final_answer = ""
        logger.info(
            "Démarrage de session Consultant IA (Max étapes: %d, Provider: %s)",
            max_steps,
            type(self.ai_provider).__name__ if self.ai_provider else "None",
        )

        for step in range(1, max_steps + 1):
            yield {"type": "thought", "step": step, "content": f"Analyse de la requête et planification ReAct (Étape {step}/{max_steps})..."}

            content_text = ""
            tool_calls_detected: list[tuple[str, dict[str, Any], str | None]] = []

            # 1. Tentative d'appel via le client OpenAI natif s'il est disponible
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

                    if resp_msg.tool_calls:
                        messages.append(resp_msg)  # type: ignore[arg-type]

                        for tc in resp_msg.tool_calls:
                            tc_func = getattr(tc, "function", tc)
                            t_name = getattr(tc_func, "name", "unknown")
                            raw_args = getattr(tc_func, "arguments", "{}")
                            try:
                                t_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                            except Exception:
                                t_args = {}
                            tool_calls_detected.append((t_name, t_args, getattr(tc, "id", None)))

                except Exception as e:
                    logger.warning("Appel client OpenAI direct échoué, repli vers generate(): %s", e)

            # 2. Repli vers ai_provider.generate(...) si aucun appel natif n'a été fait
            if not tool_calls_detected and not content_text and self.ai_provider is not None:
                try:
                    # Construire le prompt conversationnel
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

            # 3. Vérifier si un outil a été demandé dans le texte JSON
            if not tool_calls_detected and content_text:
                is_json_tool, manual_tool, manual_args = extract_tool_call_from_text(content_text)
                if is_json_tool:
                    tool_calls_detected.append((manual_tool, manual_args, None))

            # 4. Exécuter les outils s'il y en a
            if tool_calls_detected:
                for t_name, t_args, call_id in tool_calls_detected:
                    yield {"type": "tool_start", "step": step, "tool": t_name, "args": t_args}

                    observation, is_err = self._execute_tool_call(t_name, t_args)
                    logger.info("Étape %d/%d - Outil '%s' exécuté (is_error: %s)", step, max_steps, t_name, is_err)

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
                        messages.append({"role": "user", "content": f"[Observation de l'outil MCP '{t_name}'] :\n{observation}\n\nDonne ta réponse finale ou invoque un autre outil si nécessaire."})
            else:
                # Réponse finale textuelle obtenue !
                final_answer = content_text
                yield {"type": "text", "content": final_answer}
                break

        logger.info("Session Consultant IA achevée avec succès.")
        yield {"type": "finished", "content": final_answer}

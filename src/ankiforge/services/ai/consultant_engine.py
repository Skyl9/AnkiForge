import json
import logging
import sys
import os
from typing import AsyncGenerator, Any, cast

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.flexible_service import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class ConsultantEngine:
    """Moteur IA autonome pour le Consultant."""

    def __init__(self, llm_config: LLMConfigModel, persona: Any = None):
        self.llm_config = llm_config
        self.persona = persona

        provider_name = str(llm_config.provider).lower() if llm_config.provider else "openai"
        base_url = "https://api.openai.com/v1"
        if provider_name == "ollama":
            base_url = "http://localhost:11434/v1"
        elif provider_name == "groq":
            base_url = "https://api.groq.com/openai/v1"
        elif provider_name == "gemini":
            base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

        self.provider = OpenAICompatibleProvider(
            base_url=base_url,
            model_name=str(llm_config.model_id) if llm_config.model_id else "default",
            api_key=str(llm_config.api_key) if llm_config.api_key else "dummy_key",
        )
        # On pointe vers notre serveur MCP local
        server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")
        self.server_params = StdioServerParameters(command=sys.executable, args=[server_path])

    async def chat_stream(self, user_query: str) -> AsyncGenerator[str, None]:
        """
        Boucle ReAct basique. Se connecte au serveur MCP, récupère les outils,
        et orchestre la réflexion LLM et l'exécution d'outils (Tool Calling).
        """
        async with stdio_client(self.server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. Initialiser la connexion MCP
                await session.initialize()

                # 2. Récupérer les outils disponibles
                tools_result = await session.list_tools()
                tools_list = tools_result.tools

                # Formater les outils pour le LLM au format OpenAI
                openai_tools: list[Any] = []
                tools_description_lines = []
                for t in tools_list:
                    schema = t.inputSchema if hasattr(t, "inputSchema") else getattr(t, "input_schema", {})
                    openai_tools.append({"type": "function", "function": {"name": t.name, "description": t.description, "parameters": schema}})
                    tools_description_lines.append(f"- {t.name}: {t.description}\n  Schéma: {json.dumps(schema)}")

                tools_description = "\n".join(tools_description_lines)

                persona_prompt = "Tu es un Agent Data Analyst ultra-technique connecté en direct à une base de données."
                if self.persona and hasattr(self.persona, "system_prompt") and self.persona.system_prompt:
                    persona_prompt = f"Tu es l'agent nommé '{self.persona.name}'. Ton rôle est défini comme suit :\n{self.persona.system_prompt}\n"

                # nosec B608 car c'est un prompt envoyé à l'IA, pas une vraie requête exécutée ici
                system_prompt = f"""{persona_prompt}
Ton UNIQUE but est de récupérer des données réelles et factuelles en utilisant tes outils si nécessaire, et de répondre en respectant ta personnalité.
Ne propose JAMAIS de créer des cartes ou des flashcards (même si le projet s'appelle AnkiForge) SAUF si on te le demande explicitement.

Voici les outils disponibles :
{tools_description}

RÈGLE ABSOLUE DE SURVIE :
Tu ne possèdes AUCUNE donnée en mémoire. Dès que l'utilisateur pose une question sur les données, TU DOIS OBLIGATOIREMENT appeler l'outil SQL `query_peewee`. 
Ne donne jamais la commande SQL directement à l'utilisateur, c'est à TOI de l'exécuter via l'outil.

INFO SCHÉMA : Les tables principales sont `personas` (les agents IA), `pipelines`, `deckmodel`, `notemodel`, `cardmodel`, `llm_configs`. N'utilise jamais "personamodel", utilise `personas`.

RÈGLE D'AUTO-CORRECTION :
Si l'outil te renvoie une "Erreur" (ex: table inexistante, syntaxe SQL incorrecte), NE RÉPONDS PAS à l'utilisateur ! 
Tu dois immédiatement faire un NOUVEL APPEL D'OUTIL avec la requête corrigée. Tu as le droit de faire jusqu'à 10 tentatives.

Si ton client API ne supporte pas l'appel natif d'outils, tu dois renvoyer UNIQUEMENT un bloc JSON valide avec cette structure exacte :
```json
{{
    "tool": "nom_de_l_outil",
    "args": {{
        "nom_argument": "valeur"
    }}
}}
```

EXEMPLE D'APPEL (pour "Combien d'agents y a-t-il ?") :
```json
{{
    "tool": "query_peewee",
    "args": {{
        "sql_query": "SELECT count(*) FROM agents;"
    }}
}}
```

Répète après moi : "Je n'inventerai aucune donnée. Je n'écrirai pas de flashcard. J'appellerai toujours mon outil JSON."
"""  # nosec B608
                messages: list[Any] = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_query}]

                max_steps = 5
                for _ in range(max_steps):
                    # Génération via le LLM avec le support natif des outils (OpenAI / Ollama)
                    response = self.provider.client.chat.completions.create(model=self.provider.model_name, messages=messages, tools=openai_tools, temperature=0.0)

                    response_message = response.choices[0].message

                    if response_message.tool_calls:
                        messages.append(response_message)  # Ajouter l'appel d'outil à l'historique

                        for tool_call in response_message.tool_calls:
                            try:
                                tc = cast(Any, tool_call)
                                tool_name = getattr(tc.function, "name", str(getattr(tc, "name", "")))
                                tool_args = json.loads(getattr(tc.function, "arguments", "{}"))
                            except Exception:
                                tool_name = "unknown"
                                tool_args = {}

                            yield f"🔄 J'utilise l'outil `{tool_name}` (Natif)...\n"

                            try:
                                result = await session.call_tool(tool_name, arguments=tool_args)
                                observation = "\n".join([r.text for r in result.content if r.type == "text"])
                                yield "✅ Résultat obtenu.\n"
                            except Exception as e:
                                observation = f"Erreur de l'outil : {e}"
                                yield "❌ Erreur avec l'outil.\n"

                            messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": observation})
                    else:
                        # Fallback pour les modèles locaux qui renvoient du texte (JSON manuel) au lieu d'un appel natif
                        content_text = response_message.content or ""
                        is_manual_tool_call = False
                        tool_name = ""
                        tool_args = {}

                        import re

                        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content_text, re.DOTALL)
                        if match:
                            clean_json = match.group(1).strip()
                        else:
                            clean_json = content_text.strip()

                        try:
                            parsed = json.loads(clean_json)
                            if not isinstance(parsed, dict) or "tool" not in parsed:
                                parsed = None
                        except Exception:
                            parsed = None

                        if not parsed:
                            # Sécurité 3 : Chercher la première accolade ouverte et la dernière fermée
                            start = content_text.find("{")
                            end = content_text.rfind("}")
                            if start != -1 and end != -1 and start < end:
                                try:
                                    parsed = json.loads(content_text[start : end + 1])
                                    if not isinstance(parsed, dict) or "tool" not in parsed:
                                        parsed = None
                                except Exception as parse_err:
                                    logger.debug("Échec du fallback de parsing JSON de la dernière chance: %s", parse_err)

                        if parsed and "tool" in parsed:
                            is_manual_tool_call = True
                            tool_name = parsed.get("tool", "")
                            tool_args = parsed.get("args", {})
                        else:
                            # Ce n'est pas un JSON valide ou ça a échoué.
                            pass

                        if is_manual_tool_call:
                            yield f"🔄 J'utilise l'outil `{tool_name}` (Manuel)...\n"
                            try:
                                result = await session.call_tool(tool_name, arguments=tool_args)
                                observation = "\n".join([r.text for r in result.content if r.type == "text"])
                                yield "✅ Résultat obtenu.\n"
                            except Exception as e:
                                observation = f"Erreur de l'outil : {e}"
                                yield "❌ Erreur avec l'outil.\n"

                            messages.append({"role": "assistant", "content": content_text})
                            messages.append({"role": "user", "content": f"Résultat de l'outil:\n{observation}\nDonne ta réponse finale."})
                        else:
                            # C'est la réponse finale !
                            if content_text:
                                yield content_text
                            break

        yield "\n\n(Consultation terminée)"

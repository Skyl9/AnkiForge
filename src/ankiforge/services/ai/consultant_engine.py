import json
import logging
import sys
import os
from typing import AsyncGenerator, Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.flexible_service import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


class ConsultantEngine:
    """
    Le Consultant est un agent ReAct (Reason & Act) qui résout des problèmes complexes
    en dialoguant avec le Serveur MCP d'AnkiForge pour obtenir des informations et
    agir sur la base de données de l'utilisateur.
    """

    def __init__(self, llm_config: LLMConfigModel):
        self.llm_config = llm_config
        self.provider = OpenAICompatibleProvider(
            base_url=llm_config.api_base,
            model_name=llm_config.model_name,
            api_key=llm_config.api_key or "dummy_key",
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

                # Formater les outils pour le LLM (ReAct textuel très basique pour Ollama/OpenAI standard)
                tools_description = "\n".join([f"- {t.name}: {t.description}\n  Schéma: {json.dumps(t.inputSchema)}" for t in tools_list])

                system_prompt = f"""Tu es l'Assistant Consultant AnkiForge. 
Tu peux utiliser les outils suivants pour aider l'utilisateur :
{tools_description}

Si tu dois utiliser un outil, renvoie STRICTEMENT ce format JSON (et rien d'autre) :
{{"tool": "nom_de_l_outil", "args": {{"arg1": "val1"}}}}

Si tu as la réponse finale, réponds normalement en texte.
"""

                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_query}]

                max_steps = 5
                for _ in range(max_steps):
                    # Génération via le LLM (ici on triche un peu en utilisant generate() qui est conçu pour du texte)
                    # Dans une vraie implémentation, on utiliserait le paramètre `tools` natif d'OpenAI.
                    # Mais pour la flexibilité (Ollama), le parsing JSON manuel ReAct est robuste.
                    response_text = self.provider.client.chat.completions.create(model=self.provider.model_name, messages=messages, temperature=0.0).choices[0].message.content

                    # Vérifier si c'est un appel d'outil (basé sur le format JSON demandé)
                    is_tool_call = False
                    tool_call_data: dict[str, Any] = {}
                    try:
                        if response_text:
                            parsed = json.loads(response_text)
                            if isinstance(parsed, dict) and "tool" in parsed and "args" in parsed:
                                is_tool_call = True
                                tool_call_data = parsed
                    except Exception as parse_error:
                        logger.debug("Le LLM n'a pas renvoyé de JSON valide pour l'outil: %s", parse_error)

                    if is_tool_call:
                        tool_name = str(tool_call_data.get("tool", ""))
                        tool_args = tool_call_data.get("args", {})
                        yield f"🔄 J'utilise l'outil `{tool_name}`...\n"

                        try:
                            # 3. Exécuter l'outil via le client MCP !
                            result = await session.call_tool(tool_name, arguments=tool_args)
                            observation = "\n".join([r.text for r in result.content if r.type == "text"])
                            yield "✅ Résultat obtenu.\n"
                        except Exception as e:
                            observation = f"Erreur lors de l'exécution de l'outil : {e}"
                            yield "❌ Erreur avec l'outil.\n"

                        # Ajouter l'observation dans l'historique pour le LLM
                        messages.append({"role": "assistant", "content": response_text})
                        messages.append({"role": "user", "content": f"Résultat de l'outil:\n{observation}\nMaintenant donne ta réponse finale ou utilise un autre outil."})

                    else:
                        # C'est la réponse finale !
                        yield response_text
                        break

        yield "\n\n(Consultation terminée)"

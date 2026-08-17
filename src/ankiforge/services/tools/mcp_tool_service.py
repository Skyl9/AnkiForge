"""Interface MCP (Model Context Protocol) exposant la gestion des Outils Python pour le Consultant IA."""

import logging
from typing import Any, Dict, List, Optional

from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.tools.tool_service import ToolService

logger = logging.getLogger(__name__)


class MCPToolService:
    """Expose les capacités de création et de gestion d'outils Python au Consultant IA via MCP."""

    @classmethod
    def list_available_tools(cls) -> List[Dict[str, Any]]:
        """Liste tous les outils Python (natifs et personnalisés) disponibles dans la Forge."""
        tools = ToolService.list_tools()
        return [
            {
                "name": t.name,
                "display_name": t.display_name,
                "description": t.description,
                "is_builtin": t.is_builtin,
                "code_snippet": t.code[:150] + "..." if len(t.code) > 150 else t.code,
            }
            for t in tools
        ]

    @classmethod
    def get_tool_code(cls, tool_name: str) -> Dict[str, Any]:
        """Récupère le code source complet d'un outil Python."""
        tool = ToolService.get_tool(tool_name)
        if not tool:
            return {"status": "error", "message": f"Outil '{tool_name}' non trouvé."}
        return {
            "status": "success",
            "name": tool.name,
            "display_name": tool.display_name,
            "description": tool.description,
            "code": tool.code,
            "is_builtin": tool.is_builtin,
        }

    @classmethod
    def create_or_update_tool(
        cls,
        name: str,
        display_name: str,
        description: str,
        python_code: str,
    ) -> Dict[str, Any]:
        """
        Permet au Consultant IA de concevoir ou mettre à jour un outil Python réutilisable.
        Le script doit contenir 'def run(state):'.
        """
        # Vérification syntaxique préalable
        if "def run(" not in python_code:
            return {
                "status": "error",
                "message": "Le script Python doit impérativement définir une fonction 'def run(state):'.",
            }

        try:
            compile(python_code, "<custom_tool>", "exec")
        except SyntaxError as e:
            return {"status": "error", "message": f"Erreur de syntaxe Python : {e}"}

        tool = ToolService.create_or_update_tool(
            name=name.strip(),
            display_name=display_name.strip(),
            description=description.strip(),
            code=python_code,
            is_builtin=False,
        )

        return {
            "status": "success",
            "message": f"Outil '{tool.display_name}' ({tool.name}) enregistré avec succès !",
            "tool_id": tool.id,
        }

    @classmethod
    def test_tool_execution(
        cls,
        tool_name: str,
        sample_cards: Optional[List[dict]] = None,
        sample_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simule l'exécution d'un outil sur des données échantillons."""
        state = PipelineRunState(initial_prompt="Test Consultant IA")
        if sample_cards:
            state.set_variable("generated_cards", sample_cards)
        if sample_text:
            state.set_variable("last_output", sample_text)
            state.set_variable("text_source", sample_text)

        result = ToolService.execute_tool(tool_name, state)
        return {
            "tool_name": tool_name,
            "result": result,
            "modified_cards": state.get_variable("generated_cards"),
            "modified_last_output": state.get_variable("last_output"),
        }

import pytest

from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.tools.mcp_tool_service import MCPToolService
from ankiforge.services.tools.tool_service import (
    ToolService,
    tool_clean_html_latex,
    tool_compute_metrics,
    tool_deduplicate_levenshtein,
    tool_validate_json_schema,
)


@pytest.fixture(autouse=True)
def init_tools(mock_db):
    ToolService.seed_builtin_tools()


def test_tool_clean_html_latex():
    state = PipelineRunState(initial_prompt="Test")
    state.set_variable(
        "generated_cards",
        [
            {"Front": "Calculer $$x^2 + y^2$$ et $z$", "Back": "<p>Résultat :</p><script>alert(1)</script> 42"},
        ],
    )
    res = tool_clean_html_latex(state)
    assert res["status"] == "success"
    cards = state.get_variable("generated_cards")
    assert "\\[x^2 + y^2\\]" in cards[0]["Front"]
    assert "\\(z\\)" in cards[0]["Front"]
    assert "<script>" not in cards[0]["Back"]
    assert "42" in cards[0]["Back"]


def test_tool_deduplicate_levenshtein():
    state = PipelineRunState(initial_prompt="Test")
    state.set_variable(
        "generated_cards",
        [
            {"Front": "Quelle est la capitale de la France ?", "Back": "Paris"},
            {"Front": "Quelle est la capitale de la France ?", "Back": "Paris (doublon)"},
            {"Front": "Quelle est la vitesse de la lumière ?", "Back": "300 000 km/s"},
        ],
    )
    res = tool_deduplicate_levenshtein(state)
    assert res["status"] == "success"
    assert res["removed_duplicates"] == 1
    assert len(state.get_variable("generated_cards")) == 2


def test_tool_validate_json_schema():
    state = PipelineRunState(initial_prompt="Test")
    raw_markdown = 'Voici les cartes demandées :\n```json\n[{"Front": "Question 1", "Back": "Réponse 1"}]\n```'
    state.set_variable("last_output", raw_markdown)
    res = tool_validate_json_schema(state)
    assert res["status"] == "success"
    assert res["valid_cards_count"] == 1
    assert state.get_variable("generated_cards")[0]["Front"] == "Question 1"


def test_tool_compute_metrics():
    state = PipelineRunState(initial_prompt="Test")
    state.set_variable(
        "generated_cards",
        [
            {"Front": "Mot un deux", "Back": "Trois quatre cinq"},
        ],
    )
    metrics = tool_compute_metrics(state)
    assert metrics["total_cards"] == 1
    assert metrics["total_words"] == 6


def test_custom_tool_execution_and_mcp():
    # 1. Le Consultant IA crée un outil personnalisé via MCP
    code = """def run(state):
    state.set_variable("custom_tag", "Mathématiques-Avancées")
    return {"status": "ok"}
"""
    mcp_res = MCPToolService.create_or_update_tool(
        name="custom_tagger",
        display_name="Tagueur Personnalisé",
        description="Ajoute un tag custom",
        python_code=code,
    )
    assert mcp_res["status"] == "success"

    # 2. Exécution de l'outil personnalisé
    state = PipelineRunState(initial_prompt="Test DAG")
    exec_res = ToolService.execute_tool("custom_tagger", state)
    assert exec_res == {"status": "ok"}
    assert state.get_variable("custom_tag") == "Mathématiques-Avancées"

    # 3. Listing des outils via MCP
    tools = MCPToolService.list_available_tools()
    names = [t["name"] for t in tools]
    assert "custom_tagger" in names
    assert "clean_html_latex" in names

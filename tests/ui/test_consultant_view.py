import pytest
import json
import uuid
from typing import Any

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
from ankiforge.services.ai.consultant_engine import ConsultantToolRegistry
from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.views.consultant_view import (
    ChatMessageWidget,
    ConsultantView,
    ThoughtStepWidget,
    ToolCallWidget,
)


class MockReActProvider(LLMProvider):
    """Simule un LLM exécutant un appel d'outil MCP au tour 1 puis formulant sa réponse finale au tour 2."""

    def __init__(self):
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        self.call_count += 1
        if self.call_count == 1:
            return json.dumps(
                {
                    "tool": "get_deck_stats",
                    "args": {"deck_name": "Deck Cardio Test"},
                }
            )
        return "Analyse terminée : Le paquet 'Deck Cardio Test' est en excellente santé."


def test_consultant_view_initialization(qtbot):
    """Vérifie l'initialisation du Consultant IA et le message d'accueil."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    assert view is not None
    assert view.chat_messages_layout.count() >= 2  # Stretch + Welcome message


def test_consultant_view_context_attachment(qtbot):
    """Vérifie l'attachement dynamique de paquets et documents au contexte actif."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Cardio {uid}")
    doc = DocumentModel.create(title=f"Doc Cardiologie {uid}", content="Contenu de test anatomie.")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    # Attacher le deck et le document
    view._attach_context(f"deck_{deck.id}")
    view._attach_context(f"doc_{doc.id}")

    assert len(view.active_context) == 2
    assert f"deck_{deck.id}" in view.active_context
    assert f"doc_{doc.id}" in view.active_context

    # Vérification des données construites
    ctx_data = view._build_context_data()
    assert len(ctx_data["documents"]) == 1
    assert ctx_data["documents"][0]["titre"] == f"Doc Cardiologie {uid}"
    assert len(ctx_data["paquets"]) == 1
    assert ctx_data["paquets"][0]["nom"] == f"Deck Cardio {uid}"

    # Réinitialisation de la mémoire
    view._on_clear_memory()
    assert len(view.active_context) == 0


def test_consultant_view_quick_prompts(qtbot):
    """Vérifie le fonctionnement des suggestions rapides de prompts."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._on_quick_prompt_clicked("🔍 Trouver les cartes doublons")
    assert view.chat_input.toPlainText() == "Trouver les cartes doublons"


def test_consultant_view_persona_scope_filtering(qtbot):
    """Vérifie que seuls les personas MCP et universels apparaissent dans le menu Consultant (pas les pipelines purs)."""
    uid = uuid.uuid4().hex[:6]
    p_pipe = PersonaModel.create(name=f"Agent Pipe Pure {uid}", persona_type="pipeline", system_prompt="Pipeline only")
    p_mcp = PersonaModel.create(name=f"Agent MCP Only {uid}", persona_type="mcp", system_prompt="MCP only")
    p_univ = PersonaModel.create(name=f"Agent Univ {uid}", persona_type="universal", system_prompt="Universal")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    combo_texts = [view.persona_combo.itemText(i) for i in range(view.persona_combo.count())]
    assert any(p_mcp.name in t for t in combo_texts)
    assert any(p_univ.name in t for t in combo_texts)
    assert not any(p_pipe.name in t for t in combo_texts)


@pytest.mark.slow
@pytest.mark.integration
def test_consultant_react_mcp_worker_execution(qtbot):
    """Vérifie le cycle complet du worker ReAct : appel d'outil MCP puis réponse finale."""
    DeckModel.create(name="Deck Cardio Test")
    persona = PersonaModel.create(name="Consultant Test", system_prompt="Tu es un analyste", persona_type="mcp")
    cfg = LLMConfigModel.create(provider="mock", model_id="mock_react", display_name="Mock ReAct")

    mock_provider = MockReActProvider()
    worker = ConsultantWorker(
        llm_config=cfg,
        persona=persona,
        instruction="Quelles sont les statistiques du paquet Deck Cardio Test ?",
        ai_provider=mock_provider,
    )

    tools_called = []
    thoughts_emitted = []
    final_responses = []

    worker.tool_call_emitted.connect(lambda t_name, args, res, is_err: tools_called.append(t_name))
    worker.thought_emitted.connect(lambda step, th: thoughts_emitted.append(step))
    worker.finished_signal.connect(lambda text: final_responses.append(text))

    with qtbot.waitSignal(worker.finished_signal, timeout=5000):
        worker.start()

    assert len(thoughts_emitted) >= 1
    assert "get_deck_stats" in tools_called
    assert len(final_responses) == 1
    assert "Deck Cardio Test" in final_responses[0]


def test_consultant_tool_registry_execution():
    """Vérifie l'exécution in-process des outils MCP et de base de données."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck SRS {uid}")
    nt = NoteTypeModel.create(
        name=f"NoteType SRS {uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style=".card { color: black; }",
    )
    note = NoteModel.create(guid=f"guid_{uid}", note_type=nt, tags="srs_test")
    NoteVersionModel.create(note=note, content='{"Front": "Q1", "Back": "R1"}', is_active=True)
    CardModel.create(note=note, deck=deck, reps=5, lapses=2)

    # 1. query_peewee
    sql_res = ConsultantToolRegistry.query_peewee(f"SELECT name FROM deckmodel WHERE id = {deck.id};")
    assert f"Deck SRS {uid}" in sql_res

    # 2. get_deck_stats
    stats = ConsultantToolRegistry.get_deck_stats(deck.name)
    assert "Nombre total de cartes : 1" in stats
    assert "Nombre moyen de révisions : 5.0" in stats

    # 3. get_cards_by_deck_or_tag
    cards_json = ConsultantToolRegistry.get_cards_by_deck_or_tag(deck_name=deck.name)
    assert "srs_test" in cards_json

    # 4. update_card_model_css
    css_res = ConsultantToolRegistry.update_card_model_css(nt.name, ".custom-cloze { color: #8b5cf6; }")
    assert "Succès" in css_res
    reloaded_nt = NoteTypeModel.get_by_id(nt.id)
    assert ".custom-cloze" in reloaded_nt.css_style

    # 5. execute_python_tool
    py_res = ConsultantToolRegistry.execute_python_tool(
        "clean_html_latex",
        args_json=json.dumps({"test": "value"}),
    )
    assert "status" in py_res


def test_consultant_react_widgets_and_actions(qtbot):
    """Vérifie le rendu des widgets ReAct (ThoughtStepWidget, ToolCallWidget, ChatMessageWidget)."""
    # 1. Thought widget
    th = ThoughtStepWidget(step=1, thought_text="Planification de la requête SQL...")
    qtbot.addWidget(th)
    assert th.lbl_content.isHidden()
    th._toggle_content()
    assert not th.lbl_content.isHidden()

    # 2. ToolCall widget
    tc = ToolCallWidget(tool_name="query_peewee", args_json='{"query": "SELECT 1;"}', result_str="Colonnes: 1\n- (1,)", is_error=False)
    qtbot.addWidget(tc)
    assert tc.details_box.isHidden()
    tc._toggle_details()
    assert not tc.details_box.isHidden()

    # 3. Chat message avec CSS détecté et import 1-clic
    msg_with_css = "Voici le style généré :\n```css\n.card.dark-mode { background: #1e1e2e; }\n```"
    chat_msg = ChatMessageWidget(
        sender="AnkiForge AI",
        text=msg_with_css,
        is_user=False,
        thoughts=[(1, "Analyse du besoin de style")],
        tool_calls=[("update_card_model_css", "{}", "Succès", False)],
    )
    qtbot.addWidget(chat_msg)
    assert chat_msg is not None

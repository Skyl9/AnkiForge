import json
import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from ankiforge.database.models import (
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.views.consultant_view import (
    ChatMessageWidget,
    ConsultantChatInput,
    ConsultantView,
)
from ankiforge.ui.views.consultant_view.view import extract_card_proposal_from_text


class MockReActProvider(LLMProvider):
    """Simule un LLM exécutant un appel d'outil au tour 1 puis formulant sa réponse avec réflexion au tour 2."""

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
        return "<think>Analyse des statistiques complétée.</think>Analyse terminée : Le paquet 'Deck Cardio Test' est en excellente santé."


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
    assert len(ctx_data["paquets"]) == 1

    # Supprimer un contexte via _remove_context
    view._remove_context(f"deck_{deck.id}")
    assert len(view.active_context) == 1
    assert f"doc_{doc.id}" in view.active_context


def test_consultant_view_working_scope_persists_on_send(qtbot, monkeypatch):
    """Vérifie que le Working Scope reste persistant et ancré après l'envoi d'un message."""
    from ankiforge.services.workers.consultant_worker import ConsultantWorker

    monkeypatch.setattr(ConsultantWorker, "start", lambda self: None)

    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Neuro {uid}")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._attach_context(f"deck_{deck.id}")
    assert len(view.active_context) == 1
    assert f"deck_{deck.id}" not in view.committed_context

    view.chat_input.setPlainText("Analyse ce paquet s'il te plaît.")
    view._on_send_clicked()

    # Le Working Scope est ancré (committed)
    assert len(view.active_context) == 1
    assert f"deck_{deck.id}" in view.active_context
    assert f"deck_{deck.id}" in view.committed_context

    # Une source envoyée ne peut plus être retirée en cours de discussion
    view._remove_context(f"deck_{deck.id}")
    assert len(view.active_context) == 1

    # Réinitialisation de session libère le contexte
    view._on_clear_memory()
    assert len(view.active_context) == 0
    assert len(view.committed_context) == 0


def test_consultant_view_uncommitted_source_can_be_removed(qtbot):
    """Vérifie qu'un paquet ajouté par erreur mais NON envoyé peut être retiré librement sans exception."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Erreur {uid}")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._attach_context(f"deck_{deck.id}")
    assert len(view.active_context) == 1
    assert f"deck_{deck.id}" not in view.committed_context

    # Retrait immédiat avant envoi de message
    view._remove_context(f"deck_{deck.id}")
    assert len(view.active_context) == 0


def test_extract_card_proposal_from_text():
    """Vérifie l'extraction robuste de propositions de cartes depuis du JSON brut en texte markdown."""
    response_with_json = """
    Voici ma proposition d'amélioration pour la Note #42 :
    ```json
    {
      "Front": "Quelle est la fonction du myocarde ?",
      "Back": "Assurer la contraction musculaire cardiaque pour pomper le sang."
    }
    ```
    """
    prop = extract_card_proposal_from_text(response_with_json, user_query="Peux-tu améliorer la note #42 ?")
    assert prop is not None
    assert prop.get("status") == "staged_diff"
    assert prop.get("note_id") == 42
    assert "myocarde" in prop.get("modified", {}).get("Front", "")


def test_consultant_view_json_response_triggers_diff(qtbot):
    """Vérifie qu'une réponse IA contenant un JSON de carte met à jour le Workspace Inspector."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"NT_Diff_{uid}", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid=f"g_diff_{uid}", note_type=nt)
    NoteVersionModel.create(note=note, version_number=1, content='{"Front": "Question originale"}', is_active=True)

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    ai_response = f"""
    Voici la version optimisée pour la Note #{note.id} :
    ```json
    {{
      "Front": "Question considérablement améliorée",
      "Back": "Réponse claire et concise"
    }}
    ```
    """

    view._on_ai_response(ai_response)

    # Le workspace inspector doit avoir reçu la proposition et activé le garde-fou
    assert "En attente" in view.workspace_inspector.status_badge.text()
    assert view.workspace_inspector.btn_apply.isEnabled()


def test_consultant_view_quick_prompts(qtbot):
    """Vérifie que le clic sur un quick prompt injecte le texte attendu."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._on_quick_prompt_clicked("Audit Wozniak")
    assert "Wozniak" in view.chat_input.toPlainText()

    view._on_quick_prompt_clicked("Panorama 360°")
    assert "panorama 360°" in view.chat_input.toPlainText().lower()


def test_consultant_view_slash_commands(qtbot):
    """Vérifie l'exécution des commandes slash locales."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    # Test /help
    res_help = view._handle_slash_command("/help")
    assert res_help is True

    # Test /clear
    view.active_context.append("deck_1")
    res_clear = view._handle_slash_command("/clear")
    assert res_clear is True
    assert len(view.active_context) == 0

    # Test /compact
    res_compact = view._handle_slash_command("/compact")
    assert res_compact is True


def test_consultant_view_send_button_mode(qtbot):
    """Vérifie la bascule du bouton d'envoi vers le bouton stop."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._set_send_button_mode(is_running=True)
    assert "Stop" in view.btn_send.toolTip()

    view._set_send_button_mode(is_running=False)
    assert "Envoyer" in view.btn_send.toolTip()


def test_consultant_view_persona_scope_filtering(qtbot):
    """Vérifie que seuls les personas MCP et Universels sont chargés dans la combo."""
    uid = uuid.uuid4().hex[:6]
    p_mcp = PersonaModel.create(name=f"MCP Agent {uid}", system_prompt="mcp prompt", persona_type="mcp")
    p_univ = PersonaModel.create(name=f"Universal Agent {uid}", system_prompt="univ prompt", persona_type="universal")
    p_pipe = PersonaModel.create(name=f"Pipeline Agent {uid}", system_prompt="pipe prompt", persona_type="pipeline")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    combo_texts = [view.persona_combo.itemText(i) for i in range(view.persona_combo.count())]
    assert any(p_mcp.name in t for t in combo_texts)
    assert any(p_univ.name in t for t in combo_texts)
    assert not any(p_pipe.name in t for t in combo_texts)


@pytest.mark.slow
@pytest.mark.integration
def test_consultant_react_mcp_worker_execution(qtbot):
    """Vérifie le cycle complet du worker avec streaming et outils."""
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
    worker.thought_emitted.connect(lambda step, th, is_run: thoughts_emitted.append(step))
    worker.finished_signal.connect(lambda text: final_responses.append(text))

    with qtbot.waitSignal(worker.finished_signal, timeout=5000):
        worker.start()

    assert len(thoughts_emitted) >= 1
    assert "get_deck_stats" in tools_called
    assert len(final_responses) == 1
    assert "Deck Cardio Test" in final_responses[0]


def test_consultant_worker_cancellation(qtbot):
    """Vérifie l'annulation d'un worker en cours d'exécution."""
    worker = ConsultantWorker(instruction="Long running prompt")
    assert not worker.is_cancelled()
    worker.cancel()
    assert worker.is_cancelled()


def test_chat_message_widget_streaming(qtbot):
    """Vérifie l'accumulation en streaming du texte et des outils dans ChatMessageWidget."""
    msg = ChatMessageWidget(sender="AnkiForge AI", text="", is_user=False)
    qtbot.addWidget(msg)

    # 1. Ajout de pensée
    msg.add_or_update_thought(1, "Analyse de la requête", is_running=True)
    assert 1 in msg._thought_widgets

    # 2. Ajout d'outil en cours
    msg.add_tool_start("query_peewee", '{"sql": "SELECT 1;"}')
    assert len(msg._tool_widgets) == 1
    assert msg._tool_widgets[0].is_running

    # 3. Résultat de l'outil
    msg.update_tool_result("query_peewee", "1 row found", is_error=False)
    assert not msg._tool_widgets[0].is_running

    # 4. Streaming de texte
    msg.append_text_chunk("Voici ")
    msg.append_text_chunk("la réponse finale.")
    assert msg.raw_text == "Voici la réponse finale."

    # 5. Finalisation
    msg.mark_as_finished()
    assert not msg.is_streaming


def test_chat_message_widget_cancellation(qtbot):
    """Vérifie l'affichage de l'état interrompu."""
    msg = ChatMessageWidget(sender="AnkiForge AI", text="", is_user=False)
    qtbot.addWidget(msg)
    msg.mark_as_cancelled()
    assert not msg.is_streaming


def test_consultant_chat_input_slash_typing_and_events(qtbot):
    """Vérifie la frappe d'un slash, la détection du préfixe et l'absence de crash."""
    input_edit = ConsultantChatInput()
    qtbot.addWidget(input_edit)

    # 1. Taper "/"
    qtbot.keyClicks(input_edit, "/")
    trigger, prefix = input_edit.textUnderCursor()
    assert trigger == "/"
    assert prefix == ""

    # 2. Taper "p"
    qtbot.keyClicks(input_edit, "p")
    trigger, prefix = input_edit.textUnderCursor()
    assert trigger == "/"
    assert prefix == "p"

    # 3. Activation de la complétion pour /panorama
    input_edit._on_completion_activated("slash", "/panorama")
    assert input_edit.toPlainText() == "/panorama"

    # 4. Test envoi avec Enter (sans Shift)
    send_signals = []
    input_edit.send_requested.connect(lambda: send_signals.append(True))
    event_enter = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    input_edit.keyPressEvent(event_enter)
    assert len(send_signals) == 1


def test_consultant_view_diff_signals_and_inspector_activation(qtbot):
    """Vérifie que le signal diff_inspect_requested bascule l'onglet sur l'Inspecteur et charge le patch."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    patch = {
        "title": "Optimisation Note #42",
        "type": "card",
        "original": {"Front": "Q"},
        "modified": {"Front": "Q modifiée"},
        "metadata": {"note_id": 42},
    }

    # Émettre le signal d'inspection
    view._on_diff_inspect_requested(patch)

    # Le workspace inspector a bien reçu la proposition
    assert view.workspace_inspector.status_badge.text() != "En veille"


def test_consultant_view_diff_applied_updates_metrics(qtbot):
    """Vérifie que l'application d'un patch inline incrémente le compteur de cartes modifiées."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    assert view.modified_cards_count == 0
    view._on_workspace_action_applied("Patch appliqué")

    assert view.modified_cards_count == 1
    assert view.lbl_cards_modified.text() == "1"


def test_consultant_view_source_double_click_removal(qtbot):
    """Vérifie que le double-clic sur un élément de sources_list le retire du contexte."""
    deck = DeckModel.create(name=f"Deck DblClick {uuid.uuid4().hex[:4]}")
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._attach_context(f"deck_{deck.id}")
    assert len(view.active_context) == 1
    assert view.sources_list.count() == 1

    item = view.sources_list.item(0)
    view._on_source_item_double_clicked(item)

    assert len(view.active_context) == 0


def test_consultant_view_revert_updates_metrics(qtbot):
    """Vérifie que l'annulation (revert) décrémente le compteur de cartes modifiées."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._on_workspace_action_applied("Patch appliqué")
    assert view.modified_cards_count == 1

    view._on_workspace_action_reverted("Patch annulé")
    assert view.modified_cards_count == 0
    assert view.lbl_cards_modified.text() == "0"


def test_consultant_view_attach_and_prompt(qtbot):
    """Vérifie que attach_and_prompt pré-remplit le contexte et le champ texte."""
    deck = DeckModel.create(name=f"Deck Prompt {uuid.uuid4().hex[:4]}")
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view.attach_and_prompt(f"deck_{deck.id}", "Optimise ce deck")
    assert f"deck_{deck.id}" in view.active_context
    assert view.chat_input.toPlainText() == "Optimise ce deck"


def test_consultant_session_persistence_and_restart(qtbot):
    """Vérifie que lors d'un redémarrage, une session existante est fidèlement restaurée avec pensées et sans welcome parasite."""
    import datetime

    from ankiforge.database.models import ConsultantMessageModel, ConsultantSessionModel

    uid = uuid.uuid4().hex[:6]
    session = ConsultantSessionModel.create(
        title=f"Session Cardio Test {uid}",
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
    )

    # Créer un message utilisateur
    ConsultantMessageModel.create(
        session=session,
        role="user",
        content="Analyse cette carte cardio",
        tokens_used=15,
        created_at=datetime.datetime.now(),
    )

    # Créer un message assistant avec thoughts et tool_calls
    thoughts_json = json.dumps([[1, "Vérification de l'atomicité Wozniak"]])
    tool_calls_json = json.dumps([["audit_card_wozniak", '{"note_id": 1}', "Violation Règle 4", False]])
    staged_diff = {
        "status": "staged_diff",
        "title": "Scission de carte",
        "type": "card",
        "original": "Contenu long",
        "modified": "Contenu scindé",
    }

    ConsultantMessageModel.create(
        session=session,
        role="assistant",
        content="Voici ma proposition de découpage.",
        thoughts=thoughts_json,
        tool_calls_json=tool_calls_json,
        staged_diffs_json=json.dumps(staged_diff),
        tokens_used=120,
        created_at=datetime.datetime.now(),
    )

    # Initialisation de la vue : elle doit restaurer cette session comme active
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    # Basculer explicitement sur la session créée
    view.view_model.switch_session(session.id)

    # Vérifications :
    # 1. Exactement 2 messages restaurés (pas de message de bienvenue parasite !)
    assert len(view.view_model.messages) == 2

    # 2. Le nombre de widgets dans le layout correspond aux 2 messages + stretch
    # (chat_messages_layout contient les messages + 1 stretch à la fin)
    assert view.chat_messages_layout.count() == 3

    # 3. Le second message a bien restauré ses thoughts et tool_calls
    second_widget = view.chat_messages_layout.itemAt(1).widget()
    assert isinstance(second_widget, ChatMessageWidget)
    assert len(second_widget._thought_widgets) == 1
    assert len(second_widget._tool_widgets) == 1
    assert second_widget._thought_widgets[1].lbl_content.text() == "Vérification de l'atomicité Wozniak"


def test_consultant_session_sidebar_filtering_and_actions(qtbot):
    """Vérifie la recherche et les interactions dans la sidebar des discussions."""
    from ankiforge.database.models import ConsultantSessionModel

    uid = uuid.uuid4().hex[:6]
    s1 = ConsultantSessionModel.create(title=f"Cardiologie {uid}")
    s2 = ConsultantSessionModel.create(title=f"Neurologie {uid}")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    sidebar = view.session_sidebar
    sidebar.set_sessions([s1, s2], active_id=s1.id)

    # Recherche filtrante
    sidebar.search_input.setText("Neuro")
    assert sidebar.list_widget.count() == 1

    # Effacer le filtre
    sidebar.search_input.setText("")
    assert sidebar.list_widget.count() == 2

    # Toggle sidebar
    assert not sidebar.isHidden()
    view._toggle_sidebar()
    assert sidebar.isHidden()
    view._toggle_sidebar()
    assert not sidebar.isHidden()


def test_chat_message_widget_accordion_toggle(qtbot):
    """Vérifie le fonctionnement de l'accordéon rétractable des pensées ReAct."""
    msg = ChatMessageWidget(
        sender="AnkiForge AI",
        text="Voici la réponse.",
        is_user=False,
        thoughts=[(1, "Étape 1")],
        tool_calls=[("get_deck_stats", "{}", "OK", False)],
    )
    qtbot.addWidget(msg)

    # Au départ (message finalisé), l'accordéon est replié
    assert not msg.steps_wrapper.isHidden()
    assert msg.steps_container.isHidden()

    # Clic sur le bouton de l'accordéon pour le déplier
    msg._toggle_steps_visibility()
    assert not msg.steps_container.isHidden()

    # Second clic pour le replier
    msg._toggle_steps_visibility()
    assert msg.steps_container.isHidden()


def test_context_hub_widget_token_estimation_and_sources(qtbot):
    """Vérifie le calcul des tokens estimés et l'affichage des sources dans ContextHubWidget."""
    from ankiforge.ui.views.consultant_view.widgets.context_hub_widget import ContextHubWidget

    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Hub Test {uid}")
    doc = DocumentModel.create(title=f"Cours Cardio {uid}", content="Ceci est un long cours de médecine sur le myocarde et la circulation sanguine.")

    hub = ContextHubWidget()
    qtbot.addWidget(hub)

    # Au départ, aucune source
    assert not hub.empty_state_lbl.isHidden()
    assert hub._sources_tokens == 0

    # Connexion de sources au working scope
    hub.set_context_sources([f"deck_{deck.id}", f"doc_{doc.id}"])

    assert hub.empty_state_lbl.isHidden()
    assert len(hub.active_context) == 2
    assert hub.sources_layout.count() == 2
    assert hub._sources_tokens > 0
    assert "tokens" in hub.lbl_token_usage_total.text()


def test_slash_command_context_displays_breakdown(qtbot):
    """Vérifie que la commande /context affiche le diagnostic détaillé de la fenêtre de contexte."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Slash Test {uid}")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._attach_context(f"deck_{deck.id}")

    # Exécution de la commande slash /context
    handled = view._handle_slash_command("/context")
    assert handled is True

    # Vérifier qu'un message de diagnostic a été ajouté au chat
    last_item = view.chat_messages_layout.itemAt(view.chat_messages_layout.count() - 2)
    assert last_item is not None
    last_widget = last_item.widget()
    assert isinstance(last_widget, ChatMessageWidget)
    assert "Diagnostic de la Fenêtre d'Attention" in last_widget.msg_body.text()
    assert "Ventilation détaillée" in last_widget.msg_body.text()


def test_context_hub_committed_locking_and_uncommitted_removal(qtbot, monkeypatch):
    """Vérifie le verrouillage des sources engagées et la suppression des sources libres dans le Hub."""
    from ankiforge.services.workers.consultant_worker import ConsultantWorker

    monkeypatch.setattr(ConsultantWorker, "start", lambda self: None)

    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Hub Lock {uid}")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    # 1. Source non encore envoyée : non verrouillée
    view._attach_context(f"deck_{deck.id}")
    hub = view.context_hub
    assert len(hub.active_context) == 1
    assert hub.sources_layout.count() == 1
    first_card = hub.sources_layout.itemAt(0).widget()
    assert not first_card.is_committed

    # 2. Envoi d'un message : la source devient ancrée (committed)
    view.chat_input.setPlainText("Bonjour")
    view._on_send_clicked()

    assert f"deck_{deck.id}" in view.committed_context
    first_card_committed = hub.sources_layout.itemAt(0).widget()
    assert first_card_committed.is_committed


def test_context_uncommitted_safe_mouse_clicks(qtbot):
    """Vérifie que les clics physiques de suppression sur badge et carte s'exécutent sans exception."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton

    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Click Test {uid}")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    # 1. Clic souris sur le badge au-dessus de l'input
    view._attach_context(f"deck_{deck.id}")
    assert len(view.active_context) == 1
    badge = view.mentions_layout.itemAt(0).widget()
    qtbot.mouseClick(badge, Qt.MouseButton.LeftButton)
    qtbot.wait(50)

    # Le badge a été supprimé sans erreur C++
    assert len(view.active_context) == 0

    # 2. Clic souris sur le bouton de la carte dans le Hub
    view._attach_context(f"deck_{deck.id}")
    assert len(view.active_context) == 1
    hub_card = view.context_hub.sources_layout.itemAt(0).widget()
    # Le dernier widget dans la carte est le bouton del
    btn_del = hub_card.findChild(QPushButton)
    assert btn_del is not None
    qtbot.mouseClick(btn_del, Qt.MouseButton.LeftButton)
    qtbot.wait(50)

    assert len(view.active_context) == 0


def test_consultant_view_open_in_editor_navigation(qtbot):
    """Vérifie que la demande d'ouverture dans l'éditeur émet request_navigation('edition', {'note_id': id})."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.request_navigation, timeout=1000) as blocker:
        view._on_open_in_editor_requested(42)

    assert blocker.args == ["edition", {"note_id": 42}]

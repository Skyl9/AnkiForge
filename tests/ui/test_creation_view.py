import json
import uuid
from typing import Any

import pytest

from ankiforge.database.models import (
    DeckModel,
    LLMConfigModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.ui.dialogs.human_validation_dialog import HumanValidationDialog
from ankiforge.ui.views.creation_view import CreationView


class DummyCreationProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        return json.dumps(
            {
                "cards": [
                    {"Front": "Qu'est-ce que le DAG ?", "Back": "Un graphe orienté acyclique."},
                    {"Front": "Rôle du Copilote ?", "Back": "Validation humaine interactive."},
                ]
            }
        )


class DummyCreationAIManager:
    def create_provider_from_config(self, config: Any) -> LLMProvider:
        return DummyCreationProvider()


@pytest.mark.ui
def test_creation_view_creation(qtbot, mock_db):
    """Vérifie l'instanciation de base de la vue de création."""
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None


@pytest.mark.slow
@pytest.mark.ui
def test_creation_view_dag_generation_flow(qtbot, mock_db):
    """Vérifie le déclenchement asynchrone de la génération DAG et la réception des cartes."""

    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Test {uid}")
    nt = NoteTypeModel.create(
        name=f"Modèle Test {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card { font-family: arial; }",
    )
    pipe = PipelineModel.create(name=f"Pipeline Test DAG {uid}")
    persona = PersonaModel.create(name=f"Créateur {uid}", system_prompt="Créer cartes", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_type="LLM_PROMPT", step_order=1)

    LLMConfigModel.create(provider="mock", model_id=f"dummy_{uid}", display_name=f"Mock IA {uid}")

    ai_mgr = DummyCreationAIManager()

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    # Sélectionner le pipeline et le moteur dans les combos de l'IHM
    for i in range(view.pipeline_combo.count()):
        if view.pipeline_combo.itemData(i) and getattr(view.pipeline_combo.itemData(i), "id", None) == pipe.id:
            view.pipeline_combo.setCurrentIndex(i)
            break

    for i in range(view.engine_combo.count()):
        data = view.engine_combo.itemData(i)
        if data and getattr(data, "model_id", "") == f"dummy_{uid}":
            view.engine_combo.setCurrentIndex(i)
            break

    # Déclencher la génération asynchrone
    view._on_generate(text_source="Texte source sur le DAG et le Copilote", source_title="Test Document")

    # Attendre que le thread termine la génération et mette à jour le tableau
    qtbot.waitUntil(lambda: view.results_table.rowCount() == 2, timeout=6000)

    assert len(view.generated_cards) == 2
    assert view.generated_cards[0]["Front"] == "Qu'est-ce que le DAG ?"
    assert view.generated_cards[0]["Back"] == "Un graphe orienté acyclique."
    assert view.results_table.rowCount() == 2

    view.thread_pool.waitForDone(2000)


@pytest.mark.ui
def test_human_validation_dialog(qtbot, mock_db):
    """Vérifie le fonctionnement de la modale HumanValidationDialog."""
    from ankiforge.services.ai.state import PipelineRunState

    state = PipelineRunState()
    state.set_variable("last_output", {"concepts_cles": ["Concept 1", "Concept 2"]})
    state.set_variable("human_validation_config", {"human_title": "Pause Personnalisée", "human_message": "Veuillez valider."})

    dlg = HumanValidationDialog(state=state)
    qtbot.addWidget(dlg)

    assert "Concept 1" in dlg.editor.toPlainText()

    # Tester le formateur JSON
    dlg.editor.setPlainText('{"concepts_cles":["A","B"]}')
    dlg._format_json()
    assert "\n" in dlg.editor.toPlainText()

    # Modifier le texte et valider
    dlg.editor.setPlainText('{"concepts_cles": ["Concept 1 Modifié"]}')
    dlg._on_validate_clicked()

    assert state.get_variable("last_output") == {"concepts_cles": ["Concept 1 Modifié"]}
    assert state.get_variable("map_items") == ["Concept 1 Modifié"]


@pytest.mark.ui
def test_creation_view_cancellation(qtbot, mock_db):
    """Vérifie l'annulation propre de la génération dans CreationView."""
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)

    view._on_cancel_generation()
    assert view.orchestrator is None or view.orchestrator._is_cancelled

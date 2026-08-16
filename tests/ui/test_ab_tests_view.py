import json
import uuid
from typing import Any

from ankiforge.database.models import (
    LLMConfigModel,
    NoteTypeModel,
    PersonaModel,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.ui.views.ab_tests_view import ABTestsView


class DummyABProviderA(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        return json.dumps(
            {
                "cards": [
                    {"Front": "Question Branche A", "Back": "Réponse Branche A"},
                ]
            }
        )


class DummyABProviderB(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        return json.dumps(
            {
                "cards": [
                    {"Front": "Question Branche B", "Back": "Réponse Branche B"},
                ]
            }
        )


class DummyABManager:
    def __init__(self, cfg_a_id: int):
        self.cfg_a_id = cfg_a_id

    def create_provider_from_config(self, config: Any) -> LLMProvider:
        if config and getattr(config, "id", None) == self.cfg_a_id:
            return DummyABProviderA()
        return DummyABProviderB()


class DummySingleABManager:
    def create_provider_from_config(self, config: Any) -> LLMProvider:
        return DummyABProviderA()


def test_ab_tests_view_engine_comparison(qtbot):
    """Vérifie le test A/B en Mode 0 : Comparer deux Moteurs IA."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"NoteType AB {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card { font-family: arial; }",
    )

    persona = PersonaModel.create(name=f"Agent Commun {uid}", system_prompt="Prompt Commun", output_format="json")

    cfg_a = LLMConfigModel.create(provider="mock_a", model_id=f"model_a_{uid}", display_name=f"Model A {uid}")
    LLMConfigModel.create(provider="mock_b", model_id=f"model_b_{uid}", display_name=f"Model B {uid}")

    ai_mgr = DummyABManager(cfg_a_id=cfg_a.id)

    view = ABTestsView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.refresh_data()

    # Mode 0 : Comparer deux moteurs
    view.mode_combo.setCurrentIndex(0)

    idx_ea = view.engine_a_combo.findText(f"Model A {uid}")
    if idx_ea != -1:
        view.engine_a_combo.setCurrentIndex(idx_ea)

    idx_eb = view.engine_b_combo.findText(f"Model B {uid}")
    if idx_eb != -1:
        view.engine_b_combo.setCurrentIndex(idx_eb)

    idx_p = view.persona_combo.findText(str(persona.name))
    if idx_p != -1:
        view.persona_combo.setCurrentIndex(idx_p)

    # Lancer le test A/B
    view.source_text_edit.setPlainText("Texte d'évaluation comparatif Moteurs A/B.")
    view._on_run_ab_test()

    # Attendre que les deux branches asynchrones terminent
    qtbot.waitUntil(lambda: view.btn_run.isEnabled() is True, timeout=7000)

    assert len(view.cards_a) == 1
    assert view.cards_a[0]["Front"] == "Question Branche A"
    assert len(view.cards_b) == 1
    assert view.cards_b[0]["Front"] == "Question Branche B"


def test_ab_tests_view_prompt_comparison(qtbot):
    """Vérifie le test A/B en Mode 1 : Comparer deux Prompts."""
    uid = uuid.uuid4().hex[:6]
    NoteTypeModel.create(
        name=f"NoteType Prompt {uid}",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"}]',
        css_style=".card { font-family: arial; }",
    )

    PersonaModel.create(name=f"Agent Simple {uid}", system_prompt="Prompt Simple", output_format="json")
    PersonaModel.create(name=f"Agent Complexe {uid}", system_prompt="Prompt Complexe", output_format="json")

    LLMConfigModel.create(provider="mock", model_id=f"model_{uid}", display_name=f"Model Global {uid}")

    ai_mgr = DummySingleABManager()

    view = ABTestsView(ai_manager=ai_mgr)
    qtbot.addWidget(view)

    view.refresh_data()

    # Mode 1 : Comparer deux prompts
    view.mode_combo.setCurrentIndex(1)
    assert not view.persona_a_combo.isHidden()
    assert not view.persona_b_combo.isHidden()

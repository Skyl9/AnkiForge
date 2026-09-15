"""
Unit tests for ConsultantViewModel.
"""

from __future__ import annotations

from ankiforge.repositories.persona_repository import PersonaRepository
from ankiforge.repositories.setting_repository import SettingRepository
from ankiforge.ui.viewmodels.consultant_viewmodel import ConsultantViewModel
from ankiforge.utils.event_bus import AppEventBus


def test_consultant_viewmodel_chat_and_thoughts() -> None:
    bus = AppEventBus()
    persona_repo = PersonaRepository()
    setting_repo = SettingRepository()

    vm = ConsultantViewModel(
        persona_repo=persona_repo,
        setting_repo=setting_repo,
        bus=bus,
    )

    # Personas and LLMs
    persona = persona_repo.create_persona("AI Coach", "You assist students.")
    llm = persona_repo.create_llm_config("Claude 3.5", "anthropic", "claude-3-5")

    vm.load_data()
    assert vm.selected_persona is not None
    assert vm.selected_persona.id == persona.id
    assert vm.selected_llm_config is not None
    assert vm.selected_llm_config.id == llm.id

    # Messages
    user_msg = vm.add_user_message("Can you help optimize this card?")
    assert user_msg["role"] == "user"
    assert len(vm.messages) == 1

    # Thoughts and tool calls
    vm.record_thought(1, "Analyzing card content...")
    vm.record_tool_call("query_peewee", "select * from cards", result="[1, 2]", is_done=True)
    assert len(vm.current_thoughts) == 1
    assert len(vm.current_tool_calls) == 1

    # Assistant response
    assistant_msg = vm.add_assistant_message("Here is the simplified version.")
    assert assistant_msg["role"] == "assistant"
    assert len(assistant_msg["thoughts"]) == 1
    assert len(assistant_msg["tool_calls"]) == 1
    assert len(vm.current_thoughts) == 0
    assert len(vm.current_tool_calls) == 0

    # Metrics
    tokens_before = vm.used_tokens_count
    vm.update_metrics(tokens_delta=150, cards_delta=1)
    assert vm.used_tokens_count == tokens_before + 150
    assert vm.modified_cards_count == 1

    # Clear chat
    vm.clear_chat()
    assert len(vm.messages) == 0

    vm.dispose()

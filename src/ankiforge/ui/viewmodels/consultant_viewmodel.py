"""
ViewModel for AI Consultant Chat, ReAct Thought Engine, and Tool Execution.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import LLMConfigModel, PersonaModel
from ankiforge.repositories.persona_repository import PersonaRepository
from ankiforge.repositories.setting_repository import SettingRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import AppEventBus

logger = logging.getLogger(__name__)


class ConsultantViewModel(BaseViewModel):
    """Encapsulates state and reactive logic for AI Consultant ReAct chat and tool telemetry."""

    data_loaded = Signal()
    message_added = Signal(dict)
    thought_added = Signal(int, str)
    tool_call_added = Signal(str, str, str, bool)
    tool_call_completed = Signal(str, str)
    stats_updated = Signal(int, int)
    thinking_changed = Signal(bool)

    def __init__(
        self,
        persona_repo: PersonaRepository | None = None,
        setting_repo: SettingRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._persona_repo = persona_repo or PersonaRepository()
        self._setting_repo = setting_repo or SettingRepository()

        self._personas: list[PersonaModel] = []
        self._selected_persona: PersonaModel | None = None
        self._llm_configs: list[LLMConfigModel] = []
        self._selected_llm_config: LLMConfigModel | None = None

        self._messages: list[dict[str, Any]] = []
        self._current_thoughts: list[tuple[int, str]] = []
        self._current_tool_calls: list[tuple[str, str, str, bool]] = []
        self._is_thinking: bool = False
        self._used_tokens_count: int = 0
        self._modified_cards_count: int = 0

    @property
    def personas(self) -> list[PersonaModel]:
        return self._personas

    @property
    def selected_persona(self) -> PersonaModel | None:
        return self._selected_persona

    @property
    def llm_configs(self) -> list[LLMConfigModel]:
        return self._llm_configs

    @property
    def selected_llm_config(self) -> LLMConfigModel | None:
        return self._selected_llm_config

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self._messages

    @property
    def current_thoughts(self) -> list[tuple[int, str]]:
        return self._current_thoughts

    @property
    def current_tool_calls(self) -> list[tuple[str, str, str, bool]]:
        return self._current_tool_calls

    @property
    def is_thinking(self) -> bool:
        return self._is_thinking

    @property
    def used_tokens_count(self) -> int:
        return self._used_tokens_count

    @property
    def modified_cards_count(self) -> int:
        return self._modified_cards_count

    def load_data(self) -> None:
        """Load available personas and LLM engine configurations."""
        try:
            self._personas = self._persona_repo.get_all_personas()
            self._llm_configs = self._persona_repo.get_all_llm_configs()

            if self._personas and (self._selected_persona is None or self._selected_persona not in self._personas):
                self.select_persona_by_id(self._personas[0].id)

            if self._llm_configs and (self._selected_llm_config is None or self._selected_llm_config not in self._llm_configs):
                self.select_llm_config_by_id(self._llm_configs[0].id)

            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load consultant data: {e}")

    def select_persona_by_id(self, persona_id: int) -> None:
        """Select persona by ID."""
        persona = self._persona_repo.get_persona_by_id(persona_id)
        if persona:
            self._selected_persona = persona

    def select_llm_config_by_id(self, config_id: int) -> None:
        """Select LLM configuration by ID."""
        config = self._persona_repo.get_llm_config_by_id(config_id)
        if config:
            self._selected_llm_config = config

    def set_thinking(self, thinking: bool) -> None:
        """Update thinking state."""
        self._is_thinking = thinking
        self.thinking_changed.emit(thinking)

    def add_user_message(self, text: str) -> dict[str, Any]:
        """Record and emit a user message."""
        msg = {"role": "user", "text": text}
        self._messages.append(msg)
        self.message_added.emit(msg)
        return msg

    def add_assistant_message(
        self,
        text: str,
        thoughts: list[tuple[int, str]] | None = None,
        tool_calls: list[tuple[str, str, str, bool]] | None = None,
    ) -> dict[str, Any]:
        """Record and emit an assistant message with optional thoughts and tool calls."""
        msg = {
            "role": "assistant",
            "text": text,
            "thoughts": thoughts or list(self._current_thoughts),
            "tool_calls": tool_calls or list(self._current_tool_calls),
        }
        self._messages.append(msg)
        self.message_added.emit(msg)
        self._current_thoughts.clear()
        self._current_tool_calls.clear()
        return msg

    def record_thought(self, iteration: int, thought: str) -> None:
        """Record an incremental thought step."""
        self._current_thoughts.append((iteration, thought))
        self.thought_added.emit(iteration, thought)

    def record_tool_call(self, tool_name: str, args: str, result: str = "", is_done: bool = False) -> None:
        """Record an incremental tool invocation."""
        self._current_tool_calls.append((tool_name, args, result, is_done))
        self.tool_call_added.emit(tool_name, args, result, is_done)

    def update_metrics(self, tokens_delta: int, cards_delta: int) -> None:
        """Update session tokens and cards modified count."""
        self._used_tokens_count += tokens_delta
        self._modified_cards_count += cards_delta
        self.stats_updated.emit(self._used_tokens_count, self._modified_cards_count)

    def clear_chat(self) -> None:
        """Clear message history and current scratchpad."""
        self._messages.clear()
        self._current_thoughts.clear()
        self._current_tool_calls.clear()

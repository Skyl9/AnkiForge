"""
ViewModel for AI Consultant Chat, Persistent Sessions, and Tool Execution.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import (
    ConsultantMessageModel,
    ConsultantSessionModel,
    LLMConfigModel,
    PersonaModel,
    db,
)
from ankiforge.repositories.persona_repository import PersonaRepository
from ankiforge.repositories.setting_repository import SettingRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import AppEventBus

logger = logging.getLogger(__name__)


class ConsultantViewModel(BaseViewModel):
    """Encapsulates state, session persistence, and reactive logic for AI Consultant chat."""

    data_loaded = Signal()
    session_changed = Signal(object)
    sessions_list_updated = Signal(list)
    message_added = Signal(dict)
    thought_added = Signal(int, str, bool)
    tool_call_added = Signal(str, str, str, bool)
    tool_call_completed = Signal(str, str)
    stats_updated = Signal(int, int)
    thinking_changed = Signal(bool)
    next_steps_updated = Signal(list)
    workspace_preview_updated = Signal(dict)

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

        self._current_session: ConsultantSessionModel | None = None
        self._sessions: list[ConsultantSessionModel] = []
        self._messages: list[dict[str, Any]] = []
        self._conversation_history: list[dict[str, Any]] = []
        self._current_thoughts: list[tuple[int, str]] = []
        self._current_tool_calls: list[tuple[str, str, str, bool]] = []
        self._next_steps: list[str] = []
        self._workspace_state: dict[str, Any] = {}
        self._is_thinking: bool = False
        self._used_tokens_count: int = 0
        self._modified_cards_count: int = 0

    @property
    def current_session(self) -> ConsultantSessionModel | None:
        return self._current_session

    @property
    def sessions(self) -> list[ConsultantSessionModel]:
        return self._sessions

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
    def conversation_history(self) -> list[dict[str, Any]]:
        return self._conversation_history

    @property
    def current_thoughts(self) -> list[tuple[int, str]]:
        return self._current_thoughts

    @property
    def current_tool_calls(self) -> list[tuple[str, str, str, bool]]:
        return self._current_tool_calls

    @property
    def next_steps(self) -> list[str]:
        return self._next_steps

    @property
    def workspace_state(self) -> dict[str, Any]:
        return self._workspace_state

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
        """Load available personas, LLM engine configurations, and persistent chat sessions."""
        try:
            self._personas = self._persona_repo.get_all_personas()
            self._llm_configs = self._persona_repo.get_all_llm_configs()

            if self._personas and (self._selected_persona is None or self._selected_persona not in self._personas):
                self.select_persona_by_id(self._personas[0].id)

            if self._llm_configs and (self._selected_llm_config is None or self._selected_llm_config not in self._llm_configs):
                self.select_llm_config_by_id(self._llm_configs[0].id)

            self.load_sessions()
            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load consultant data: {e}")

    def load_sessions(self) -> list[ConsultantSessionModel]:
        """Loads all chat sessions from SQLite, sorted by most recent."""
        try:
            self._sessions = list(ConsultantSessionModel.select().order_by(ConsultantSessionModel.updated_at.desc()).limit(30))
            if not self._sessions:
                self.create_new_session("Nouvelle Session")
            elif self._current_session is None:
                self.switch_session(self._sessions[0].id)

            self.sessions_list_updated.emit(self._sessions)
            return self._sessions
        except Exception as e:
            logger.warning("Erreur chargement sessions consultant : %s", e)
            return []

    def create_new_session(self, title: str = "Nouvelle Session") -> ConsultantSessionModel:
        """Creates a fresh chat session and sets it as active."""
        try:
            with db.atomic():
                session = ConsultantSessionModel.create(
                    title=title,
                    persona=self._selected_persona,
                    created_at=datetime.datetime.now(),
                    updated_at=datetime.datetime.now(),
                )
            self._current_session = session
            self._sessions.insert(0, session)
            self.clear_chat()
            self.session_changed.emit(session)
            self.sessions_list_updated.emit(self._sessions)
            return session
        except Exception as e:
            logger.error("Erreur création session consultant : %s", e)
            raise

    def switch_session(self, session_id: int) -> None:
        """Switches active session and loads its persistent message history."""
        try:
            session = ConsultantSessionModel.get_or_none(ConsultantSessionModel.id == session_id)
            if not session:
                return

            self._current_session = session
            self.clear_chat()

            # Load messages from SQLite
            msgs = list(ConsultantMessageModel.select().where(ConsultantMessageModel.session == session).order_by(ConsultantMessageModel.created_at.asc()))
            for m in msgs:
                self._conversation_history.append({"role": m.role, "content": m.content})
                msg_dict = {
                    "role": m.role,
                    "text": m.content,
                    "thoughts": json.loads(m.thoughts) if m.thoughts else [],
                    "tool_calls": json.loads(m.tool_calls_json) if m.tool_calls_json else [],
                    "staged_diff": json.loads(m.staged_diffs_json) if m.staged_diffs_json else None,
                }
                self._messages.append(msg_dict)
                self._used_tokens_count += m.tokens_used

            self.session_changed.emit(session)
        except Exception as e:
            logger.error("Erreur switch session consultant : %s", e)

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

    def set_next_steps(self, next_steps: list[str]) -> None:
        """Update proactive next steps suggestions."""
        self._next_steps = list(next_steps)
        self.next_steps_updated.emit(self._next_steps)

    def update_workspace_preview(self, state_dict: dict[str, Any]) -> None:
        """Update workspace live inspector preview data (diffs, KaTeX, cards)."""
        self._workspace_state = dict(state_dict)
        self.workspace_preview_updated.emit(self._workspace_state)

    def add_user_message(self, text: str) -> dict[str, Any]:
        """Record, persist in SQLite, and emit a user message."""
        msg = {"role": "user", "text": text}
        self._messages.append(msg)
        self._conversation_history.append({"role": "user", "content": text})

        # Persister en BDD SQLite
        if self._current_session:
            try:
                # Renommer la session si c'est le premier message
                if len(self._messages) == 1 and self._current_session.title == "Nouvelle Session":
                    short_title = text[:32] + ("..." if len(text) > 32 else "")
                    self._current_session.title = short_title
                    self._current_session.save()
                    self.sessions_list_updated.emit(self._sessions)

                with db.atomic():
                    ConsultantMessageModel.create(
                        session=self._current_session,
                        role="user",
                        content=text,
                        tokens_used=int(len(text.split()) * 1.3),
                        created_at=datetime.datetime.now(),
                    )
                    self._current_session.updated_at = datetime.datetime.now()
                    self._current_session.save()
            except Exception as e:
                logger.debug("Remarque sauvegarde message utilisateur : %s", e)

        self.message_added.emit(msg)
        return msg

    def add_assistant_message(
        self,
        text: str,
        thoughts: list[tuple[int, str]] | None = None,
        tool_calls: list[tuple[str, str, str, bool]] | None = None,
        staged_diff: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record, persist in SQLite, and emit an assistant message."""
        msg = {
            "role": "assistant",
            "text": text,
            "thoughts": thoughts or list(self._current_thoughts),
            "tool_calls": tool_calls or list(self._current_tool_calls),
            "staged_diff": staged_diff,
        }
        self._messages.append(msg)
        self._conversation_history.append({"role": "assistant", "content": text})

        tokens = int(len(text.split()) * 1.3) + 100
        self._used_tokens_count += tokens

        # Persister en BDD SQLite
        if self._current_session:
            try:
                with db.atomic():
                    ConsultantMessageModel.create(
                        session=self._current_session,
                        role="assistant",
                        content=text,
                        thoughts=json.dumps(msg["thoughts"], ensure_ascii=False) if msg["thoughts"] else None,
                        tool_calls_json=json.dumps(msg["tool_calls"], ensure_ascii=False) if msg["tool_calls"] else None,
                        staged_diffs_json=json.dumps(staged_diff, ensure_ascii=False) if staged_diff else None,
                        tokens_used=tokens,
                        created_at=datetime.datetime.now(),
                    )
                    self._current_session.updated_at = datetime.datetime.now()
                    self._current_session.save()
            except Exception as e:
                logger.debug("Remarque sauvegarde message assistant : %s", e)

        self.message_added.emit(msg)
        self._current_thoughts.clear()
        self._current_tool_calls.clear()
        return msg

    def record_thought(self, iteration: int, thought: str, is_running: bool = False) -> None:
        """Record or update an incremental thought step."""
        found = False
        for idx, (step, _) in enumerate(self._current_thoughts):
            if step == iteration:
                self._current_thoughts[idx] = (iteration, thought)
                found = True
                break
        if not found:
            self._current_thoughts.append((iteration, thought))
        self.thought_added.emit(iteration, thought, is_running)

    def record_tool_call(self, tool_name: str, args: str, result: str = "", is_done: bool = False, is_error: bool = False) -> None:
        """Record or update an incremental tool invocation."""
        found = False
        for idx in range(len(self._current_tool_calls) - 1, -1, -1):
            t_name, t_args, t_res, _ = self._current_tool_calls[idx]
            if t_name == tool_name and not t_res:
                self._current_tool_calls[idx] = (tool_name, args or t_args, result, is_error)
                found = True
                break
        if not found:
            self._current_tool_calls.append((tool_name, args, result, is_error))
        self.tool_call_added.emit(tool_name, args, result, is_done)

    def update_metrics(self, tokens_delta: int, cards_delta: int) -> None:
        """Update session tokens and cards modified count."""
        self._used_tokens_count += tokens_delta
        self._modified_cards_count += cards_delta
        self.stats_updated.emit(self._used_tokens_count, self._modified_cards_count)

    def clear_chat(self) -> None:
        """Clear message history and current scratchpad."""
        self._messages.clear()
        self._conversation_history.clear()
        self._current_thoughts.clear()
        self._current_tool_calls.clear()
        self._next_steps.clear()
        self._workspace_state.clear()
        self._used_tokens_count = 0
        self.stats_updated.emit(self._used_tokens_count, self._modified_cards_count)

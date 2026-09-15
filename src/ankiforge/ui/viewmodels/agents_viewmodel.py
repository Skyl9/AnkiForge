"""
ViewModel for AI Agents, Personas, and System Prompts Management.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaFolderModel,
    PersonaModel,
)
from ankiforge.repositories.persona_repository import PersonaRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import (
    AppEventBus,
    PersonaCreatedEvent,
    PersonaDeletedEvent,
    PersonaUpdatedEvent,
)

logger = logging.getLogger(__name__)


class AgentsViewModel(BaseViewModel):
    """Encapsulates state and reactive logic for Persona editing and versioning."""

    data_loaded = Signal()
    persona_selected = Signal(object)
    personas_list_updated = Signal(list)
    folders_list_updated = Signal(list)

    def __init__(
        self,
        persona_repo: PersonaRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._persona_repo = persona_repo or PersonaRepository()

        self._folders: list[PersonaFolderModel] = []
        self._personas: list[PersonaModel] = []
        self._selected_persona: PersonaModel | None = None
        self._llm_configs: list[LLMConfigModel] = []

    @property
    def folders(self) -> list[PersonaFolderModel]:
        return self._folders

    @property
    def personas(self) -> list[PersonaModel]:
        return self._personas

    @property
    def selected_persona(self) -> PersonaModel | None:
        return self._selected_persona

    @property
    def llm_configs(self) -> list[LLMConfigModel]:
        return self._llm_configs

    def load_data(self) -> None:
        """Load persona folders, personas and engine configs."""
        try:
            self._folders = self._persona_repo.get_all_folders()
            self._personas = self._persona_repo.get_all_personas()
            self._llm_configs = self._persona_repo.get_all_llm_configs()

            self.folders_list_updated.emit(self._folders)
            self.personas_list_updated.emit(self._personas)

            if self._personas and (self._selected_persona is None or self._selected_persona not in self._personas):
                self.select_persona_by_id(self._personas[0].id)

            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load agents data: {e}")

    def select_persona_by_id(self, persona_id: int) -> None:
        """Select a persona."""
        persona = self._persona_repo.get_persona_by_id(persona_id)
        self._selected_persona = persona
        self.persona_selected.emit(persona)

    def create_persona(
        self,
        name: str,
        system_prompt: str,
        description: str | None = None,
        output_format: str = "json",
        persona_type: str = "pipeline",
    ) -> PersonaModel:
        """Create a new persona."""
        persona = self._persona_repo.create_persona(
            name=name,
            system_prompt=system_prompt,
            description=description,
            output_format=output_format,
            persona_type=persona_type,
        )
        self.publish_event(PersonaCreatedEvent(persona_id=persona.id, name=persona.name))
        self.load_data()
        self.select_persona_by_id(persona.id)
        return persona

    def update_persona(self, persona_id: int, **kwargs: Any) -> PersonaModel | None:
        """Update an existing persona."""
        updated = self._persona_repo.update_persona(persona_id, **kwargs)
        if updated:
            self.publish_event(PersonaUpdatedEvent(persona_id=persona_id, name=updated.name))
            self.load_data()
            self.select_persona_by_id(persona_id)
        return updated

    def delete_persona(self, persona_id: int) -> bool:
        """Delete a persona."""
        success = self._persona_repo.delete_persona(persona_id)
        if success:
            self.publish_event(PersonaDeletedEvent(persona_id=persona_id))
            if self._selected_persona and self._selected_persona.id == persona_id:
                self._selected_persona = None
                self.persona_selected.emit(None)
            self.load_data()
        return success

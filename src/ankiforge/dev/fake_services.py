"""Services factices pour le mode développeur."""

from __future__ import annotations

import json
from typing import Any

from ankiforge.dev.fake_data import (
    FakeDeck,
    FakeDocument,
    FakeNote,
    make_fake_decks,
    make_fake_documents,
    make_fake_notes,
)
from ankiforge.services.ai.base import LLMProvider


class FakeLLMProvider(LLMProvider):
    """Fournisseur LLM déterministe renvoyant des cartes factices."""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        return json.dumps({"cards": [{"Front": "Question factice", "Back": "Réponse factice"}]})


class FakeDeckRepository:
    """Dépôt factice de paquets (en mémoire)."""

    def __init__(self) -> None:
        self._decks: list[FakeDeck] = make_fake_decks()

    def list_all(self) -> list[FakeDeck]:
        return list(self._decks)

    def get(self, deck_id: int) -> FakeDeck | None:
        return next((d for d in self._decks if d.id == deck_id), None)


class FakeDocumentRepository:
    """Dépôt factice de documents (en mémoire)."""

    def __init__(self) -> None:
        self._documents: list[FakeDocument] = make_fake_documents()

    def list_all(self) -> list[FakeDocument]:
        return list(self._documents)

    def get(self, document_id: int) -> FakeDocument | None:
        return next((d for d in self._documents if d.id == document_id), None)


class FakeNoteRepository:
    """Dépôt factice de notes (en mémoire)."""

    def __init__(self) -> None:
        self._notes: list[FakeNote] = make_fake_notes()

    def list_all(self) -> list[FakeNote]:
        return list(self._notes)

    def get(self, note_id: int) -> FakeNote | None:
        return next((n for n in self._notes if n.id == note_id), None)

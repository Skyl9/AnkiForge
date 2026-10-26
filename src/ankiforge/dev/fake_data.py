"""Factories de données factices déterministes pour le mode développeur."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeDeck:
    id: int
    name: str
    parent: str | None = None


@dataclass
class FakeNoteType:
    id: int
    name: str
    fields: list[str] = field(default_factory=list)


@dataclass
class FakeNote:
    id: int
    note_type: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeDocument:
    id: int
    title: str
    page_count: int = 10


@dataclass
class FakePipeline:
    id: int
    name: str
    steps: list[str] = field(default_factory=list)


@dataclass
class FakePersona:
    id: int
    name: str
    role: str = ""


def make_fake_decks() -> list[FakeDeck]:
    return [
        FakeDeck(id=1, name="Default"),
        FakeDeck(id=2, name="Langues", parent=None),
        FakeDeck(id=3, name="Langues::Anglais", parent="Langues"),
    ]


def make_fake_note_types() -> list[FakeNoteType]:
    return [
        FakeNoteType(id=1, name="Basique", fields=["Recto", "Verso"]),
        FakeNoteType(id=2, name="Recto/Verso", fields=["Front", "Back", "Tags"]),
    ]


def make_fake_notes() -> list[FakeNote]:
    return [
        FakeNote(id=1, note_type="Basique", fields={"Recto": "Question", "Verso": "Réponse"}),
        FakeNote(id=2, note_type="Recto/Verso", fields={"Front": "Hello", "Back": "Bonjour"}),
    ]


def make_fake_documents() -> list[FakeDocument]:
    return [
        FakeDocument(id=1, title="Cours de statistiques", page_count=42),
        FakeDocument(id=2, title="Manuel d'anglais", page_count=120),
    ]


def make_fake_pipelines() -> list[FakePipeline]:
    return [
        FakePipeline(id=1, name="Extraction cartes", steps=["RAG", "LLM", "Validation"]),
        FakePipeline(id=2, name="Résumé", steps=["MAP_REDUCE"]),
    ]


def make_fake_personas() -> list[FakePersona]:
    return [
        FakePersona(id=1, name="Tuteur", role="Explique simplement"),
        FakePersona(id=2, name="Examinateur", role="Pose des questions"),
    ]


def make_fake_collection() -> dict[str, Any]:
    """Retourne un dictionnaire agrégé de données factices déterministes."""
    return {
        "decks": make_fake_decks(),
        "note_types": make_fake_note_types(),
        "notes": make_fake_notes(),
        "documents": make_fake_documents(),
        "pipelines": make_fake_pipelines(),
        "personas": make_fake_personas(),
    }

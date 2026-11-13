"""Paquet des dépôts d'AnkiForge (couche d'accès aux données).

Encapsule les requêtes Peewee ORM et garantit l'isolation des transactions.
"""

from __future__ import annotations

from ankidraft.repositories.audit_repository import AuditRepository
from ankidraft.repositories.base import BaseRepository
from ankidraft.repositories.deck_repository import DeckRepository
from ankidraft.repositories.document_repository import DocumentRepository
from ankidraft.repositories.note_repository import NoteRepository
from ankidraft.repositories.persona_repository import PersonaRepository
from ankidraft.repositories.pipeline_repository import PipelineRepository
from ankidraft.repositories.setting_repository import SettingRepository

__all__ = [
    "BaseRepository",
    "NoteRepository",
    "DeckRepository",
    "AuditRepository",
    "DocumentRepository",
    "PipelineRepository",
    "PersonaRepository",
    "SettingRepository",
]

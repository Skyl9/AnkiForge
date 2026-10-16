"""Contrats de données immuables et sans dépendance Qt utilisés par le flux Batch."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class BatchTaskStatus(StrEnum):
    """Statuts du cycle de vie d'une tâche de traitement par lots."""

    QUEUED = "queued"
    RUNNING = "running"
    REVIEW = "review"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class BatchSourceBlock:
    """Page ou section Markdown lisible par l'utilisateur au sein d'une portée figée."""

    kind: Literal["page", "section", "document"]
    label: str
    content: str
    ordinal: int
    page_number: int | None = None
    heading_path: str | None = None
    source_id: int | None = None
    source_hash: str = ""
    #: Identifiant du ``DocumentChunkModel`` exact dont ce bloc est issu, lorsqu'il est connu.
    #: Sans lui, une partie multi-blocs ne pourrait pas se rattacher à un fragment précis.
    chunk_id: int | None = None

    def __post_init__(self) -> None:
        if not self.source_hash:
            object.__setattr__(self, "source_hash", content_hash(self.content))

    def as_dict(self) -> dict[str, Any]:
        """Sérialise le bloc source en dictionnaire prêt pour la persistance."""
        return {
            "kind": self.kind,
            "label": self.label,
            "content": self.content,
            "ordinal": self.ordinal,
            "page_number": self.page_number,
            "heading_path": self.heading_path,
            "source_id": self.source_id,
            "source_hash": self.source_hash,
            "chunk_id": self.chunk_id,
        }


@dataclass(frozen=True, slots=True)
class BatchScopeSnapshot:
    """Sélection de sources immuable servant d'unité d'exécution Batch."""

    document_id: int
    document_title: str
    selection_mode: str
    blocks: tuple[BatchSourceBlock, ...]
    scope_title: str
    range_str: str = ""
    content: str = ""
    scope_hash: str = ""

    def __post_init__(self) -> None:
        content = self.content or "\n\n".join(block.content for block in self.blocks)
        object.__setattr__(self, "content", content)
        if not self.scope_hash:
            payload = {
                "document_id": self.document_id,
                "selection_mode": self.selection_mode,
                "blocks": [block.as_dict() for block in self.blocks],
            }
            object.__setattr__(self, "scope_hash", stable_hash(payload))

    @property
    def is_empty(self) -> bool:
        """Indique si la sélection ne porte aucun contenu exploitable."""
        return not self.content.strip() or not self.blocks


@dataclass(frozen=True, slots=True)
class BatchGenerationConfig:
    """Paramètres de génération figés lors de la création d'une ligne de file d'attente."""

    pipeline_id: int
    pipeline_name: str
    llm_id: int
    llm_config: dict[str, Any]
    deck_id: int
    deck_name: str
    model_id: int
    model_name: str
    note_type_fields: tuple[str, ...]
    note_type_templates: tuple[dict[str, Any], ...] = ()
    auto_validation: bool = True
    use_vision: bool = False
    temperature: float = 0.7
    max_tokens: int = 16384
    strict_source_grounding: bool = True

    def identity_payload(self) -> dict[str, Any]:
        """Retourne la charge utile servant à calculer l'empreinte d'identité de la configuration."""
        return {
            "pipeline_id": self.pipeline_id,
            "llm_id": self.llm_id,
            "llm_config": self.llm_config,
            "deck_id": self.deck_id,
            "model_id": self.model_id,
            "note_type_fields": self.note_type_fields,
            "note_type_templates": self.note_type_templates,
            "auto_validation": self.auto_validation,
            "use_vision": self.use_vision,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "strict_source_grounding": self.strict_source_grounding,
        }


@dataclass(slots=True)
class BatchTaskSnapshot:
    """État de session mutable autour des snapshots immuables de portée et de configuration."""

    task_id: str
    scope: BatchScopeSnapshot
    config: BatchGenerationConfig
    task_index: int | None = None
    status: BatchTaskStatus = BatchTaskStatus.QUEUED
    attempt: int = 0
    cards: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def create(cls, scope: BatchScopeSnapshot, config: BatchGenerationConfig, task_index: int | None = None) -> BatchTaskSnapshot:
        """Construit une tâche dont l'identifiant dérive des empreintes de portée et de configuration."""
        identity = stable_hash({"scope": scope.scope_hash, "config": config.identity_payload()})
        return cls(task_id=identity, scope=scope, config=config, task_index=task_index)

    @property
    def pending_cards(self) -> list[dict[str, Any]]:
        """Cartes en attente de révision ou non encore explicitement rejetées."""
        return [c for c in self.cards if c.get("status") not in (BatchTaskStatus.REJECTED, "Rejetée")]

    @property
    def accepted_cards(self) -> list[dict[str, Any]]:
        """Cartes expressément validées par l'utilisateur."""
        return [c for c in self.cards if c.get("status") in (BatchTaskStatus.ACCEPTED, "Validée")]

    @property
    def rejected_cards(self) -> list[dict[str, Any]]:
        """Cartes rejetées lors du staging."""
        return [c for c in self.cards if c.get("status") in (BatchTaskStatus.REJECTED, "Rejetée")]

    def set_card_status(self, card_index: int, status: str) -> None:
        """Modifie le statut d'une carte spécifique."""
        if 0 <= card_index < len(self.cards):
            self.cards[card_index]["status"] = status

    def update_card_field(self, card_index: int, field_name: str, value: str) -> None:
        """Met à jour la valeur d'un champ de carte et marque la carte comme éditée."""
        if 0 <= card_index < len(self.cards):
            self.cards[card_index][field_name] = value
            self.cards[card_index]["user_edited"] = True

    def accept_all_cards(self) -> None:
        """Valide toutes les cartes de la tâche."""
        for card in self.cards:
            card["status"] = "Validée"
        self.status = BatchTaskStatus.ACCEPTED

    def reject_all_cards(self) -> None:
        """Rejette toutes les cartes de la tâche."""
        for card in self.cards:
            card["status"] = "Rejetée"
        self.status = BatchTaskStatus.REJECTED


def content_hash(content: str) -> str:
    """Calcule l'empreinte SHA-256 du contenu textuel fourni."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def stable_hash(value: Any) -> str:
    """Calcule une empreinte SHA-256 déterministe d'une valeur sérialisable en JSON."""
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

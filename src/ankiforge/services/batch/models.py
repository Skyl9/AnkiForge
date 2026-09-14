"""Qt-free, immutable data contracts used by the Batch workflow."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class BatchTaskStatus(StrEnum):
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
    """A user-readable page or Markdown section in a frozen scope."""

    kind: Literal["page", "section", "document"]
    label: str
    content: str
    ordinal: int
    page_number: int | None = None
    heading_path: str | None = None
    source_id: int | None = None
    source_hash: str = ""

    def __post_init__(self) -> None:
        if not self.source_hash:
            object.__setattr__(self, "source_hash", content_hash(self.content))

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "content": self.content,
            "ordinal": self.ordinal,
            "page_number": self.page_number,
            "heading_path": self.heading_path,
            "source_id": self.source_id,
            "source_hash": self.source_hash,
        }


@dataclass(frozen=True, slots=True)
class BatchScopeSnapshot:
    """Immutable source selection used as one Batch execution unit."""

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
        return not self.content.strip() or not self.blocks


@dataclass(frozen=True, slots=True)
class BatchGenerationConfig:
    """Generation settings captured when a queue row is created."""

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
    """Mutable session state around immutable scope and configuration snapshots."""

    task_id: str
    scope: BatchScopeSnapshot
    config: BatchGenerationConfig
    status: BatchTaskStatus = BatchTaskStatus.QUEUED
    attempt: int = 0
    cards: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @classmethod
    def create(cls, scope: BatchScopeSnapshot, config: BatchGenerationConfig) -> BatchTaskSnapshot:
        identity = stable_hash({"scope": scope.scope_hash, "config": config.identity_payload()})
        return cls(task_id=identity, scope=scope, config=config)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def stable_hash(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

"""Conversion of the generic document-scope dialog result to Batch scopes."""

from __future__ import annotations

from typing import Any, Literal

from ankiforge.services.batch.models import BatchScopeSnapshot, BatchSourceBlock


class BatchScopeError(ValueError):
    """Raised when a scope cannot be queued safely."""


def scope_from_dialog_result(document: Any, result: dict[str, Any]) -> BatchScopeSnapshot:
    """Build one immutable Batch scope without changing document state."""
    raw_blocks = result.get("chunks") or result.get("blocks") or []
    if not isinstance(raw_blocks, list):
        raise BatchScopeError("La portée sélectionnée est invalide.")

    mode = str(result.get("selection_mode") or "pages")
    blocks: list[BatchSourceBlock] = []
    for ordinal, raw in enumerate(raw_blocks):
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content") or "").strip()
        if not content:
            continue
        page_number = _optional_int(raw.get("page_number"))
        heading_path = _optional_text(raw.get("heading_path"))
        kind: Literal["page", "section", "document"] = "section" if mode in {"sections", "chapters"} or heading_path else "page"
        label = str(raw.get("title") or heading_path or (f"Page {page_number}" if page_number else f"Partie {ordinal + 1}"))
        blocks.append(
            BatchSourceBlock(
                kind=kind,
                label=label,
                content=content,
                ordinal=ordinal,
                page_number=page_number,
                heading_path=heading_path,
                source_id=_optional_int(raw.get("id")),
                source_hash=str(raw.get("content_hash") or ""),
            )
        )

    if not blocks:
        raise BatchScopeError("La portée sélectionnée est vide.")

    return BatchScopeSnapshot(
        document_id=int(document.id),
        document_title=str(document.title),
        selection_mode=mode,
        blocks=tuple(blocks),
        scope_title=str(result.get("scope_title") or f"Portée : {document.title}"),
        range_str=str(result.get("range_str") or ""),
    )


def _optional_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None

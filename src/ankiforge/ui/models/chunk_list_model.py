"""
Modèle de liste virtuel paginé pour l'explorateur de fragments RAG et les sections de cours (DocumentsView).
Gère la virtualisation des milliers de fragments de texte extraits de gros manuels PDF.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, Qt
import peewee

from ankiforge.database.models import DocumentChunkModel

logger = logging.getLogger(__name__)
_ROOT_INDEX = QModelIndex()


@dataclass
class ChunkItemData:
    """Structure mémoire compacte d'un fragment RAG."""

    chunk_id: int
    chunk_index: int
    heading_path: str
    content_preview: str
    page_number: Optional[int] = None
    similarity_score: Optional[float] = None
    is_indexed: bool = True
    raw_chunk: Optional[DocumentChunkModel] = None


class VirtualChunkListModel(QAbstractListModel):
    """
    Modèle de liste virtuel haute performance pour les fragments de documents.
    """

    CHUNK_SIZE: int = 50

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self._chunks: List[ChunkItemData] = []
        self._base_query: Optional[peewee.Query] = None
        self._total_count: int = 0

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._chunks)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._chunks):
            return None

        chunk = self._chunks[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            prefix = f"p.{chunk.page_number} " if chunk.page_number is not None else ""
            heading = f"[{chunk.heading_path}] " if chunk.heading_path else ""
            sim = f" (Similarité: {int(chunk.similarity_score * 100)}%)" if chunk.similarity_score is not None else ""
            return f"{prefix}{heading}{chunk.content_preview}{sim}"

        if role == Qt.ItemDataRole.UserRole:
            return chunk.raw_chunk

        if role == Qt.ItemDataRole.UserRole + 1:
            return chunk.chunk_id

        return None

    def canFetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> bool:
        if parent.isValid() or self._base_query is None:
            return False
        return len(self._chunks) < self._total_count

    def fetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> None:
        if parent.isValid() or self._base_query is None:
            return

        remainder = self._total_count - len(self._chunks)
        to_fetch = min(remainder, self.CHUNK_SIZE)
        if to_fetch <= 0:
            return

        offset = len(self._chunks)
        try:
            items = list(self._base_query.offset(offset).limit(to_fetch))
            new_chunks = self._convert_chunks(items)
            if new_chunks:
                self.beginInsertRows(QModelIndex(), offset, offset + len(new_chunks) - 1)
                self._chunks.extend(new_chunks)
                self.endInsertRows()
        except Exception as e:
            logger.warning("Erreur fetchMore VirtualChunkListModel: %s", e)

    def set_document_query(self, query: peewee.Query, total_count: Optional[int] = None) -> None:
        """Charge une requête Peewee de fragments DocumentChunkModel."""
        self.beginResetModel()
        self._base_query = query
        self._chunks.clear()
        try:
            self._total_count = total_count if total_count is not None else query.count()
        except Exception as e:
            logger.warning("Erreur calcul count dans VirtualChunkListModel: %s", e)
            self._total_count = 0
        self.endResetModel()

        if self._total_count > 0:
            self.fetchMore()

    def set_static_results(self, search_results: List[dict[str, Any]]) -> None:
        """Charge des résultats d'inférence ou de recherche sémantique en mémoire."""
        self.beginResetModel()
        self._base_query = None
        self._chunks.clear()
        self._total_count = len(search_results)

        for idx, res in enumerate(search_results):
            content = res.get("content", "")
            preview = content.replace("\n", " ")[:140] + ("..." if len(content) > 140 else "")
            item = ChunkItemData(
                chunk_id=res.get("id", idx),
                chunk_index=res.get("chunk_index", idx),
                heading_path=res.get("heading_path", ""),
                content_preview=preview,
                page_number=res.get("page_number"),
                similarity_score=res.get("similarity") or res.get("score"),
                raw_chunk=None,
            )
            self._chunks.append(item)

        self.endResetModel()

    def _convert_chunks(self, items: List[Any]) -> List[ChunkItemData]:
        results = []
        for c in items:
            content = str(getattr(c, "content", ""))
            preview = content.replace("\n", " ")[:140] + ("..." if len(content) > 140 else "")
            c_data = ChunkItemData(
                chunk_id=c.id,
                chunk_index=getattr(c, "chunk_index", 0),
                heading_path=str(getattr(c, "heading_path", "") or ""),
                content_preview=preview,
                page_number=getattr(c, "page_number", None),
                raw_chunk=c,
            )
            results.append(c_data)
        return results

    def get_chunk_at(self, row: int) -> Optional[ChunkItemData]:
        if 0 <= row < len(self._chunks):
            return self._chunks[row]
        return None

"""
Classe de base abstraite pour les modèles de table/liste Peewee paginés (Virtualisation Qt).
Implémente le protocole natif canFetchMore() / fetchMore() avec requêtes Peewee paginées
par blocs (limit/offset) pour garantir une empreinte mémoire constante et un défilement 60 FPS.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

import peewee
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex

logger = logging.getLogger(__name__)

T = TypeVar("T")
_ROOT_INDEX = QModelIndex()


class BasePaginatedPeeweeModel[T](QAbstractTableModel):
    """
    Modèle de table virtuel paginé générique connecté à Peewee ORM.

    Permet de charger des dizaines de milliers d'enregistrements à la demande
    par blocs configurables (ex: 100 éléments), sans jamais bloquer l'UI.
    """

    DEFAULT_CHUNK_SIZE: int = 100

    def __init__(
        self,
        query: peewee.Query | None = None,
        total_count: int | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        parent: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._chunk_size: int = max(10, chunk_size)
        self._base_query: peewee.Query | None = query
        self._total_count: int = total_count if total_count is not None else (query.count() if query is not None else 0)
        self._loaded_rows: list[T] = []

        if self._base_query is not None and self._total_count > 0:
            self._load_initial_batch()

    # --- Propriétés & Accesseurs ---

    @property
    def total_count(self) -> int:
        """Nombre total d'éléments disponibles dans la requête BDD."""
        return self._total_count

    @property
    def loaded_count(self) -> int:
        """Nombre d'éléments actuellement chargés en RAM."""
        return len(self._loaded_rows)

    @property
    def chunk_size(self) -> int:
        return self._chunk_size

    def get_row(self, row_idx: int) -> T | None:
        """Retourne l'objet à l'index spécifié si disponible."""
        if 0 <= row_idx < len(self._loaded_rows):
            return self._loaded_rows[row_idx]
        return None

    def get_all_loaded_rows(self) -> list[T]:
        """Retourne une copie de tous les éléments actuellement chargés."""
        return list(self._loaded_rows)

    # --- Cycle de vie de la Requête ---

    def set_query(
        self,
        query: peewee.Query,
        total_count: int | None = None,
        auto_fetch_first_batch: bool = True,
    ) -> None:
        """
        Réinitialise le modèle avec une nouvelle requête Peewee filtrée.
        """
        self.beginResetModel()
        self._base_query = query
        self._loaded_rows.clear()
        try:
            self._total_count = total_count if total_count is not None else query.count()
        except Exception as e:
            logger.warning("Erreur lors du calcul total_count dans BasePaginatedPeeweeModel: %s", e)
            self._total_count = 0
        self.endResetModel()

        if auto_fetch_first_batch and self._total_count > 0:
            self._load_initial_batch()

    def clear(self) -> None:
        """Vide le modèle."""
        self.beginResetModel()
        self._base_query = None
        self._total_count = 0
        self._loaded_rows.clear()
        self.endResetModel()

    def _load_initial_batch(self) -> None:
        """Charge le tout premier bloc d'éléments."""
        if self._base_query is None or self._total_count <= 0:
            return
        to_fetch = min(self._total_count, self._chunk_size)
        try:
            batch = list(self._base_query.limit(to_fetch))
            processed = self._process_batch(batch)
            if processed:
                self.beginInsertRows(_ROOT_INDEX, 0, len(processed) - 1)
                self._loaded_rows.extend(processed)
                self.endInsertRows()
        except Exception as e:
            logger.warning("Erreur lors du chargement initial du modèle paginé: %s", e)

    # --- Implémentation du Protocole de Virtualisation Qt (canFetchMore / fetchMore) ---

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._loaded_rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        if parent.isValid():
            return 0
        return 0

    def canFetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> bool:
        if parent.isValid() or self._base_query is None:
            return False
        return len(self._loaded_rows) < self._total_count

    def fetchMore(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> None:
        if parent.isValid() or self._base_query is None:
            return

        remainder = self._total_count - len(self._loaded_rows)
        items_to_fetch = min(remainder, self._chunk_size)
        if items_to_fetch <= 0:
            return

        offset = len(self._loaded_rows)
        try:
            batch = list(self._base_query.offset(offset).limit(items_to_fetch))
            if not batch:
                self._total_count = len(self._loaded_rows)
                return

            processed = self._process_batch(batch)
            if processed:
                first_row = offset
                last_row = offset + len(processed) - 1
                self.beginInsertRows(QModelIndex(), first_row, last_row)
                self._loaded_rows.extend(processed)
                self.endInsertRows()
        except Exception as e:
            logger.warning("Erreur lors du fetchMore dans BasePaginatedPeeweeModel: %s", e)

    # --- Méthodes à surcharger par les classes dérivées ---

    def _process_batch(self, raw_items: list[Any]) -> list[T]:
        """
        Hook de conversion et de préchargement des relations en lot.
        Par défaut, renvoie la liste brute.
        """
        return raw_items  # type: ignore[return-value]

"""Interface de base et abstractions pour les stratégies d'application de staged patches (ADR 0054)."""

from __future__ import annotations

import abc
from collections.abc import Callable
from typing import Any

from ankiforge.database.models import StagedPatchModel

NotifyMutationCallback = Callable[[str, int, dict[str, Any]], None]


class PatchApplierStrategy(abc.ABC):
    """Interface abstraite définissant le contrat d'application chirurgicale d'un staged patch."""

    @abc.abstractmethod
    def can_apply(self, patch_type: str) -> bool:
        """Détermine si cette stratégie prend en charge la variante de type de patch donnée."""
        ...

    @abc.abstractmethod
    def apply(
        self,
        patch: StagedPatchModel,
        diff_data: dict[str, Any],
        notify_mutation: NotifyMutationCallback | None = None,
    ) -> dict[str, Any]:
        """Applique chirurgicalement le patch en base de données et retourne le résultat de mutation."""
        ...

"""
ViewModel for Application Dashboard and Global KPIs Cockpit.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.repositories.audit_repository import AuditRepository
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.repositories.setting_repository import SettingRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import AppEventBus

logger = logging.getLogger(__name__)


class DashboardViewModel(BaseViewModel):
    """Encapsulates state and reactive computation of global application telemetry and KPIs."""

    data_loaded = Signal()
    kpis_updated = Signal(dict)

    def __init__(
        self,
        note_repo: NoteRepository | None = None,
        deck_repo: DeckRepository | None = None,
        audit_repo: AuditRepository | None = None,
        doc_repo: DocumentRepository | None = None,
        setting_repo: SettingRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._note_repo = note_repo or NoteRepository()
        self._deck_repo = deck_repo or DeckRepository()
        self._audit_repo = audit_repo or AuditRepository()
        self._doc_repo = doc_repo or DocumentRepository()
        self._setting_repo = setting_repo or SettingRepository()

        self._kpis: dict[str, Any] = {}

    @property
    def kpis(self) -> dict[str, Any]:
        return self._kpis

    def load_data(self) -> None:
        """Compute all global KPIs."""
        try:
            notes_count = self._note_repo.count_notes()
            cards_count = self._note_repo.count_cards()
            decks = self._deck_repo.get_all_decks()
            telemetry = self._setting_repo.get_total_token_usage_stats()
            audit_records = self._audit_repo.get_audit_records()
            anomalies = sum(1 for r in audit_records if not r.is_compliant)

            self._kpis = {
                "notes_count": notes_count,
                "cards_count": cards_count,
                "decks_count": len(decks),
                "anomalies_count": anomalies,
                "telemetry": telemetry,
            }
            self.kpis_updated.emit(self._kpis)
            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load dashboard KPIs: {e}")

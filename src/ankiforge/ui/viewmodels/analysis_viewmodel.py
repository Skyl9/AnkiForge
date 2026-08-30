"""
ViewModel for AI Analysis, Wozniak Linter, Gap Coverage, Duplicates, and Telemetry.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QObject, Signal

from ankiforge.database.models import (
    AuditRecordModel,
    DeckModel,
    DocumentModel,
    LinterRuleModel,
)
from ankiforge.repositories.audit_repository import AuditRepository
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.repositories.setting_repository import SettingRepository
from ankiforge.ui.viewmodels.base import BaseViewModel
from ankiforge.utils.event_bus import (
    AppEventBus,
    AuditCompletedEvent,
    AuditStartedEvent,
    LinterRuleToggledEvent,
)

logger = logging.getLogger(__name__)


class AnalysisViewModel(BaseViewModel):
    """Encapsulates state and reactive business logic for Wozniak audit, coverage, and duplicates."""

    data_loaded = Signal()
    audit_started = Signal()
    audit_completed = Signal(list, int)
    rule_toggled = Signal(int, bool)
    duplicates_updated = Signal(list)
    coverage_updated = Signal(dict)
    token_stats_updated = Signal(dict)

    def __init__(
        self,
        audit_repo: AuditRepository | None = None,
        note_repo: NoteRepository | None = None,
        deck_repo: DeckRepository | None = None,
        doc_repo: DocumentRepository | None = None,
        setting_repo: SettingRepository | None = None,
        bus: AppEventBus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(bus=bus, parent=parent)
        self._audit_repo = audit_repo or AuditRepository()
        self._note_repo = note_repo or NoteRepository()
        self._deck_repo = deck_repo or DeckRepository()
        self._doc_repo = doc_repo or DocumentRepository()
        self._setting_repo = setting_repo or SettingRepository()

        self._decks: list[DeckModel] = []
        self._selected_deck_id: int | None = None
        self._linter_rules: list[LinterRuleModel] = []
        self._audit_records: list[AuditRecordModel] = []
        self._anomalies_count: int = 0
        self._duplicates: list[dict[str, Any]] = []
        self._documents: list[DocumentModel] = []
        self._selected_doc_id: int | None = None
        self._coverage_stats: dict[str, Any] = {}
        self._token_stats: dict[str, Any] = {}

    @property
    def decks(self) -> list[DeckModel]:
        return self._decks

    @property
    def selected_deck_id(self) -> int | None:
        return self._selected_deck_id

    @property
    def linter_rules(self) -> list[LinterRuleModel]:
        return self._linter_rules

    @property
    def audit_records(self) -> list[AuditRecordModel]:
        return self._audit_records

    @property
    def anomalies_count(self) -> int:
        return self._anomalies_count

    @property
    def duplicates(self) -> list[dict[str, Any]]:
        return self._duplicates

    @property
    def documents(self) -> list[DocumentModel]:
        return self._documents

    @property
    def coverage_stats(self) -> dict[str, Any]:
        return self._coverage_stats

    @property
    def token_stats(self) -> dict[str, Any]:
        return self._token_stats

    def load_data(self) -> None:
        """Load initial rules, decks, documents and telemetry."""
        try:
            self._decks = self._deck_repo.get_all_decks()
            self._linter_rules = self._audit_repo.get_all_rules()
            self._documents = self._doc_repo.get_all_documents()
            self.load_audit_records()
            self.load_token_stats()
            self.data_loaded.emit()
        except Exception as e:
            self.set_error(f"Failed to load analysis data: {e}")

    def select_deck(self, deck_id: int | None) -> None:
        """Filter audit by deck."""
        self._selected_deck_id = deck_id
        self.load_audit_records()

    def toggle_rule(self, rule_id: int, is_active: bool) -> None:
        """Toggle active status for a linter rule."""
        success = self._audit_repo.toggle_rule(rule_id, is_active)
        if success:
            self._linter_rules = self._audit_repo.get_all_rules()
            self.publish_event(LinterRuleToggledEvent(rule_id=rule_id, is_active=is_active))
            self.rule_toggled.emit(rule_id, is_active)

    def create_rule(
        self,
        name: str,
        prompt_injection: str,
        category: str = "cat-atomicite",
        category_label: str = "Atomicité & Restructuration",
        description: str | None = None,
    ) -> LinterRuleModel:
        """Create a new custom linter rule."""
        rule = self._audit_repo.create_rule(
            name=name,
            prompt_injection=prompt_injection,
            category=category,
            category_label=category_label,
            description=description,
        )
        self._linter_rules = self._audit_repo.get_all_rules()
        return rule

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a linter rule."""
        success = self._audit_repo.delete_rule(rule_id)
        if success:
            self._linter_rules = self._audit_repo.get_all_rules()
        return success

    def load_audit_records(self) -> None:
        """Fetch audit records from repository."""
        self._audit_records = self._audit_repo.get_audit_records(deck_id=self._selected_deck_id)
        self._anomalies_count = sum(1 for r in self._audit_records if not r.is_compliant)
        self.audit_completed.emit(self._audit_records, self._anomalies_count)

    def clear_audit_records(self) -> None:
        """Clear audit history."""
        self._audit_repo.clear_audit_records(deck_id=self._selected_deck_id)
        self.load_audit_records()

    def notify_audit_started(self) -> None:
        """Notify audit start."""
        self.publish_event(AuditStartedEvent(deck_id=self._selected_deck_id))
        self.audit_started.emit()

    def notify_audit_completed(self, total_notes: int, anomalies_count: int) -> None:
        """Notify audit finished."""
        self.publish_event(
            AuditCompletedEvent(
                total_notes=total_notes,
                anomalies_count=anomalies_count,
                deck_id=self._selected_deck_id,
            )
        )
        self.load_audit_records()

    def ignore_duplicate(self, note_a_id: int, note_b_id: int) -> None:
        """Ignore a detected duplicate pair."""
        self._audit_repo.ignore_duplicate(note_a_id, note_b_id)
        self._duplicates = [
            d for d in self._duplicates if not ((d.get("note_a_id") == note_a_id and d.get("note_b_id") == note_b_id) or (d.get("note_a_id") == note_b_id and d.get("note_b_id") == note_a_id))
        ]
        self.duplicates_updated.emit(self._duplicates)

    def load_coverage(self, doc_id: int) -> None:
        """Calculate coverage for a document."""
        self._selected_doc_id = doc_id
        self._coverage_stats = self._doc_repo.get_coverage_stats(doc_id)
        self.coverage_updated.emit(self._coverage_stats)

    def load_token_stats(self) -> None:
        """Fetch total token consumption and costs."""
        self._token_stats = self._setting_repo.get_total_token_usage_stats()
        self.token_stats_updated.emit(self._token_stats)

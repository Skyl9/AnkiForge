"""
Unit tests for DashboardViewModel.
"""

from __future__ import annotations

from ankiforge.repositories.audit_repository import AuditRepository
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.repositories.setting_repository import SettingRepository
from ankiforge.ui.viewmodels.dashboard_viewmodel import DashboardViewModel
from ankiforge.utils.event_bus import AppEventBus


def test_dashboard_viewmodel_kpis() -> None:
    bus = AppEventBus()
    note_repo = NoteRepository()
    deck_repo = DeckRepository()
    audit_repo = AuditRepository()
    doc_repo = DocumentRepository()
    setting_repo = SettingRepository()

    vm = DashboardViewModel(
        note_repo=note_repo,
        deck_repo=deck_repo,
        audit_repo=audit_repo,
        doc_repo=doc_repo,
        setting_repo=setting_repo,
        bus=bus,
    )

    # Populate some data
    deck = deck_repo.create_deck("Philosophy")
    nt = note_repo.create_note_type("Basic", ["Front", "Back"], [])
    note_repo.create_note(nt, deck, {"Front": "Cogito ergo sum?"})

    setting_repo.record_token_usage("openai", "gpt-4o", 100, 50, 0.005)

    vm.load_data()
    assert vm.kpis["notes_count"] == 1
    assert vm.kpis["cards_count"] == 1
    assert vm.kpis["decks_count"] == 1
    assert vm.kpis["telemetry"]["total_tokens"] == 150

    vm.dispose()

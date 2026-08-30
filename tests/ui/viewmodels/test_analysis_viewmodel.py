"""
Unit tests for AnalysisViewModel.
"""

from __future__ import annotations

from ankiforge.repositories.audit_repository import AuditRepository
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.repositories.setting_repository import SettingRepository
from ankiforge.ui.viewmodels.analysis_viewmodel import AnalysisViewModel
from ankiforge.utils.event_bus import AppEventBus, LinterRuleToggledEvent


def test_analysis_viewmodel_operations() -> None:
    bus = AppEventBus()
    audit_repo = AuditRepository()
    note_repo = NoteRepository()
    deck_repo = DeckRepository()
    doc_repo = DocumentRepository()
    setting_repo = SettingRepository()

    vm = AnalysisViewModel(
        audit_repo=audit_repo,
        note_repo=note_repo,
        deck_repo=deck_repo,
        doc_repo=doc_repo,
        setting_repo=setting_repo,
        bus=bus,
    )

    # Initial data
    deck = deck_repo.create_deck("Medical")
    rule = audit_repo.create_rule(
        name="Minimum Information Principle",
        prompt_injection="Check card simplicity",
        is_active=True,
    )

    vm.load_data()
    assert len(vm.decks) == 1
    assert len(vm.linter_rules) == 1

    # Toggle rule & EventBus notification
    toggled_events: list = []
    bus.subscribe(LinterRuleToggledEvent, lambda e: toggled_events.append(e))

    vm.toggle_rule(rule.id, is_active=False)
    assert len(toggled_events) == 1
    assert toggled_events[0].is_active is False

    # Audit records
    nt = note_repo.create_note_type("Basic", ["Front", "Back"], [])
    note = note_repo.create_note(nt, deck, {"Front": "Q"}, source="ai")
    ver = note_repo.get_active_version(note)
    assert ver is not None

    audit_repo.create_or_update_audit_record(
        note=note,
        note_version=ver,
        is_compliant=False,
        rule_broken=rule.name,
        reason="Information too dense",
    )

    vm.load_audit_records()
    assert len(vm.audit_records) == 1
    assert vm.anomalies_count == 1

    # Clear records
    vm.clear_audit_records()
    assert len(vm.audit_records) == 0

    vm.dispose()

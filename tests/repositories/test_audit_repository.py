"""
Unit tests for AuditRepository.
"""

from __future__ import annotations

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.repositories.audit_repository import AuditRepository


def test_audit_repository_rules_and_records() -> None:
    repo = AuditRepository()

    # Rules
    rule1 = repo.create_rule(
        name="Rule 1: Atomicity",
        prompt_injection="Check that each card tests only one concept.",
        category="cat-atomicite",
        is_active=True,
    )
    rule2 = repo.create_rule(
        name="Rule 2: Cloze univocity",
        prompt_injection="Check that clozes are unambiguous.",
        category="cat-cloze",
        is_active=False,
    )

    assert repo.get_rule_by_id(rule1.id) is not None
    assert repo.get_rule_by_name("Rule 1: Atomicity") is not None
    assert len(repo.get_all_rules()) == 2
    assert len(repo.get_active_rules()) == 1

    # Toggle rule
    repo.toggle_rule(rule2.id, is_active=True)
    assert len(repo.get_active_rules()) == 2

    # Audit Records
    DeckModel.create(name="French")
    nt = NoteTypeModel.create(name="Basic", fields_schema="[]")
    note = NoteModel.create(note_type=nt, tags="test")
    ver = NoteVersionModel.create(note=note, version_number=1, content='{"Front":"Q"}', is_active=True)

    record = repo.create_or_update_audit_record(
        note=note,
        note_version=ver,
        is_compliant=False,
        rule_broken="Rule 1: Atomicity",
        reason="Contains multiple facts.",
        suggestion='{"Front":"Q1"}',
    )
    assert record is not None
    records = repo.get_audit_records()
    assert len(records) == 1
    assert records[0].is_compliant is False

    # Ignored duplicates
    note2 = NoteModel.create(note_type=nt, tags="test2")
    assert repo.is_duplicate_ignored(note.id, note2.id) is False
    repo.ignore_duplicate(note.id, note2.id)
    assert repo.is_duplicate_ignored(note.id, note2.id) is True
    assert repo.is_duplicate_ignored(note2.id, note.id) is True

    # Clear records
    repo.clear_audit_records()
    assert len(repo.get_audit_records()) == 0

from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import (
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.group_edit_service import (
    GroupEditOptions,
    GroupEditService,
)
from ankiforge.utils.tags import parse_note_tags

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_notes(mock_db):
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Model_{uid}",
        fields_schema=json.dumps(["Front", "Back", "Notes"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )

    n1 = NoteModel.create(
        guid=f"guid1_{uid}",
        note_type=nt,
        tags=json.dumps(["tagA", "doc:doc1", "section:intro"]),
    )
    NoteVersionModel.create(
        note=n1,
        content=json.dumps({"Front": "Question 1", "Back": "Answer 1", "Notes": "Tip 1"}),
        is_active=True,
    )

    n2 = NoteModel.create(
        guid=f"guid2_{uid}",
        note_type=nt,
        tags=json.dumps(["tagB", "doc:doc1"]),
    )
    NoteVersionModel.create(
        note=n2,
        content=json.dumps({"Front": "Question 2", "Back": "Answer 2", "Notes": "Tip 2"}),
        is_active=True,
    )

    n3 = NoteModel.create(
        guid=f"guid3_{uid}",
        note_type=nt,
        tags=json.dumps(["tagA", "tagC"]),
    )
    NoteVersionModel.create(
        note=n3,
        content=json.dumps({"Front": "Question 3", "Back": "Answer 3", "Notes": ""}),
        is_active=True,
    )

    return [n1, n2, n3]


def test_group_edit_add_tags(sample_notes):
    n1, n2, n3 = sample_notes
    opts = GroupEditOptions(tags_to_add=["nouvel_etiquette", "tagA"])
    res = GroupEditService.apply_group_edit([n1.id, n2.id], opts)

    assert res.success is True
    assert set(res.modified_note_ids) == {n1.id, n2.id}

    n1 = NoteModel.get_by_id(n1.id)
    n2 = NoteModel.get_by_id(n2.id)
    n3 = NoteModel.get_by_id(n3.id)

    tags1 = parse_note_tags(n1.tags)
    assert "nouvel_etiquette" in tags1
    assert "tagA" in tags1
    assert "doc:doc1" in tags1

    tags2 = parse_note_tags(n2.tags)
    assert "nouvel_etiquette" in tags2
    assert "tagA" in tags2
    assert "tagB" in tags2
    assert "doc:doc1" in tags2

    # n3 non modifiée
    tags3 = parse_note_tags(n3.tags)
    assert "nouvel_etiquette" not in tags3


def test_group_edit_remove_tags_preserves_provenance(sample_notes):
    n1, n2, n3 = sample_notes
    # Tentative de retirer tagA et le tag de provenance doc:doc1
    opts = GroupEditOptions(tags_to_remove=["tagA", "doc:doc1"])
    res = GroupEditService.apply_group_edit([n1.id, n2.id, n3.id], opts)

    assert res.success is True

    n1 = NoteModel.get_by_id(n1.id)
    tags1 = parse_note_tags(n1.tags)
    assert "tagA" not in tags1
    # doc:doc1 est un tag de provenance, protégé contre le retrait en masse
    assert "doc:doc1" in tags1
    assert "section:intro" in tags1

    n3 = NoteModel.get_by_id(n3.id)
    tags3 = parse_note_tags(n3.tags)
    assert "tagA" not in tags3
    assert "tagC" in tags3


def test_group_edit_field_replace(sample_notes):
    n1, n2, n3 = sample_notes
    opts = GroupEditOptions(
        field_name="Notes",
        field_action="replace",
        field_value="Note commune mise a jour",
    )
    res = GroupEditService.apply_group_edit([n1.id, n2.id], opts)

    assert res.success is True
    assert set(res.modified_note_ids) == {n1.id, n2.id}

    for note in [n1, n2]:
        v = NoteVersionModel.get_or_none(note=note, is_active=True)
        assert v is not None
        assert v.source == "batch_edit"
        parsed = json.loads(v.content)
        assert parsed["Notes"] == "Note commune mise a jour"

    # n3 inchangée
    v3 = NoteVersionModel.get_or_none(note=n3, is_active=True)
    assert v3 is not None
    assert json.loads(v3.content)["Notes"] == ""


def test_group_edit_field_append_and_prepend(sample_notes):
    n1, n2, _ = sample_notes
    # Prepend
    opts_prepend = GroupEditOptions(
        field_name="Back",
        field_action="prepend",
        field_value="[PREFIX]",
    )
    res1 = GroupEditService.apply_group_edit([n1.id], opts_prepend)
    assert res1.success is True

    v1 = NoteVersionModel.get_or_none(note=n1, is_active=True)
    assert v1 is not None
    assert json.loads(v1.content)["Back"] == "[PREFIX] Answer 1"

    # Append
    opts_append = GroupEditOptions(
        field_name="Back",
        field_action="append",
        field_value="[SUFFIX]",
    )
    res2 = GroupEditService.apply_group_edit([n1.id], opts_append)
    assert res2.success is True

    v1_after = NoteVersionModel.get_or_none(note=n1, is_active=True)
    assert v1_after is not None
    assert json.loads(v1_after.content)["Back"] == "[PREFIX] Answer 1 [SUFFIX]"


def test_group_edit_field_find_replace(sample_notes):
    n1, n2, _ = sample_notes
    opts = GroupEditOptions(
        field_name="Front",
        field_action="find_replace",
        find_text="Question",
        field_value="Exercice",
    )
    res = GroupEditService.apply_group_edit([n1.id, n2.id], opts)
    assert res.success is True

    for note, expected_num in [(n1, "1"), (n2, "2")]:
        v = NoteVersionModel.get_or_none(note=note, is_active=True)
        assert v is not None
        assert json.loads(v.content)["Front"] == f"Exercice {expected_num}"


def test_group_edit_atomic_rollback_on_error(sample_notes, monkeypatch):
    n1, n2, n3 = sample_notes

    # Forcer une exception sur la 2e note
    orig_add_version = NoteModel.add_version
    calls = 0

    def faulty_add_version(self, content, source="manual"):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Erreur BDD simulée")
        return orig_add_version(self, content, source=source)

    monkeypatch.setattr(NoteModel, "add_version", faulty_add_version)

    opts = GroupEditOptions(
        tags_to_add=["nouvel_echec"],
        field_name="Notes",
        field_action="replace",
        field_value="Ne doit pas persister",
    )

    res = GroupEditService.apply_group_edit([n1.id, n2.id], opts)
    assert res.success is False
    assert "Erreur BDD simulée" in (res.error_message or "")

    # Vérification du rollback complet (la première note n'a pas été modifiée)
    n1 = NoteModel.get_by_id(n1.id)
    assert "nouvel_echec" not in parse_note_tags(n1.tags)
    v1 = NoteVersionModel.get_or_none(note=n1, is_active=True)
    assert v1 is not None
    assert json.loads(v1.content)["Notes"] == "Tip 1"

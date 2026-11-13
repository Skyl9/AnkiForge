"""Tests unitaires et de couverture CRAP pour les stratégies PatchApplierStrategy (ADR 0054)."""

import json
from unittest.mock import MagicMock
from unittest.mock import patch as mock_patch

import pytest

from ankidraft.database.models import (
    DeckModel,
    NoteModel,
    NoteTypeModel,
    StagedPatchModel,
)
from ankidraft.services.ai.patch_appliers import (
    DeckPatchApplier,
    DelegatedStepPatchApplier,
    ModelPatchApplier,
    NoteCreatePatchApplier,
    NoteDeletePatchApplier,
    NoteSplitPatchApplier,
    NoteUpdatePatchApplier,
    TagPatchApplier,
    get_patch_applier,
)
from ankidraft.services.cards.note_type_service import NoteTypeService


@pytest.fixture
def test_deck(mock_db):
    return DeckModel.create(name="Default", description="Default test deck")


@pytest.fixture
def test_note_type(mock_db):
    return NoteTypeModel.create(
        name="Basic",
        fields_schema=json.dumps([{"name": "Front"}, {"name": "Back"}]),
        templates=json.dumps([{"name": "Card 1", "front": "{{Front}}", "back": "{{FrontSide}}<hr>{{Back}}"}]),
        css_style=".card { font-family: arial; }",
    )


@pytest.fixture
def test_note(test_deck, test_note_type):
    from ankidraft.services.cards.note_manager import NoteManager

    return NoteManager.create_note(
        note_type=test_note_type,
        deck=test_deck,
        content_dict={"Front": "Q1", "Back": "A1"},
        tags=["tag1"],
        source="unit_test",
    )


class TestGetPatchApplier:
    def test_lookup_strategies(self):
        assert isinstance(get_patch_applier("card"), NoteUpdatePatchApplier)
        assert isinstance(get_patch_applier("note_update"), NoteUpdatePatchApplier)
        assert isinstance(get_patch_applier("split"), NoteSplitPatchApplier)
        assert isinstance(get_patch_applier("css"), ModelPatchApplier)
        assert isinstance(get_patch_applier("note_type_create"), ModelPatchApplier)
        assert isinstance(get_patch_applier("note_create"), NoteCreatePatchApplier)
        assert isinstance(get_patch_applier("deck_create"), DeckPatchApplier)
        assert isinstance(get_patch_applier("tag_add"), TagPatchApplier)
        assert isinstance(get_patch_applier("note_delete"), NoteDeletePatchApplier)
        assert isinstance(get_patch_applier("empty_cards_delete"), NoteDeletePatchApplier)
        assert isinstance(get_patch_applier("pipeline_step_delegated"), DelegatedStepPatchApplier)
        assert get_patch_applier("unknown_type_xyz") is None


class TestNoteUpdatePatchApplier:
    def test_note_not_found(self, mock_db):
        patch = StagedPatchModel.create(
            patch_id="p1",
            patch_type="note_update",
            target_id=99999,
            diff_payload="{}",
            status="pending",
        )
        applier = NoteUpdatePatchApplier()
        res = applier.apply(patch, {})
        assert res["status"] == "error"
        assert "introuvable" in res["message"]

    def test_optimistic_conflict(self, test_note):
        active_v = test_note.versions.first()
        patch = StagedPatchModel.create(
            patch_id="p2",
            patch_type="note_update",
            target_id=test_note.id,
            original_version_id=active_v.id + 999,
            diff_payload="{}",
            status="pending",
        )
        applier = NoteUpdatePatchApplier()
        res = applier.apply(patch, {})
        assert res["status"] == "conflict"

    def test_successful_update_fields_and_tags(self, test_note):
        active_v = test_note.versions.first()
        patch = StagedPatchModel.create(
            patch_id="p3",
            patch_type="note_update",
            target_id=test_note.id,
            original_version_id=active_v.id,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "fields": {"Front": "Q1 Modified", "Back": "A1 Modified"},
            "tags_added": ["tag2"],
        }
        mock_cb = MagicMock()
        applier = NoteUpdatePatchApplier()
        res = applier.apply(patch, diff_data, notify_mutation=mock_cb)

        assert res["status"] == "applied"
        assert mock_cb.called
        saved_patch = StagedPatchModel.get_by_id(patch.id)
        assert saved_patch.status == "applied"


class TestNoteSplitPatchApplier:
    def test_note_not_found(self, mock_db):
        patch = StagedPatchModel.create(
            patch_id="p4",
            patch_type="split",
            target_id=99999,
            diff_payload="{}",
            status="pending",
        )
        applier = NoteSplitPatchApplier()
        res = applier.apply(patch, {})
        assert res["status"] == "error"

    def test_invalid_payload(self, test_note):
        patch = StagedPatchModel.create(
            patch_id="p5",
            patch_type="split",
            target_id=test_note.id,
            diff_payload="{}",
            status="pending",
        )
        applier = NoteSplitPatchApplier()
        res = applier.apply(patch, {"new_notes": []})
        assert res["status"] == "error"

    def test_successful_split(self, test_note):
        patch = StagedPatchModel.create(
            patch_id="p6",
            patch_type="split",
            target_id=test_note.id,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "new_cards": [
                {"fields": {"Front": "Part 1", "Back": "Resp 1"}, "tags": ["tagA"]},
                {"fields": {"Front": "Part 2", "Back": "Resp 2"}, "tags": ["tagB"]},
            ],
            "delete_original": True,
        }
        mock_cb = MagicMock()
        applier = NoteSplitPatchApplier()
        res = applier.apply(patch, diff_data, notify_mutation=mock_cb)

        assert res["status"] == "applied"
        assert len(res["created_note_ids"]) == 2
        assert mock_cb.called
        archived_orig = NoteModel.get_by_id(test_note.id)
        assert archived_orig.status == "archived"


class TestModelPatchApplier:
    def test_apply_css_modified_string(self, test_note_type):
        patch = StagedPatchModel.create(
            patch_id="p7",
            patch_type="css",
            target_id=test_note_type.id,
            diff_payload="{}",
            status="pending",
        )
        applier = ModelPatchApplier()
        res = applier.apply(patch, {"modified": ".new-css { color: red; }"})
        assert res["status"] == "applied"
        nt = NoteTypeModel.get_by_id(test_note_type.id)
        assert nt.css_style == ".new-css { color: red; }"

    def test_apply_css_snippet(self, test_note_type):
        patch = StagedPatchModel.create(
            patch_id="p8",
            patch_type="css_tune",
            target_id=test_note_type.id,
            diff_payload="{}",
            status="pending",
        )
        applier = ModelPatchApplier()
        res = applier.apply(patch, {"metadata": {"snippet": "/* custom snippet */"}})
        assert res["status"] == "applied"
        nt = NoteTypeModel.get_by_id(test_note_type.id)
        assert "/* custom snippet */" in (nt.css_style or "")

    def test_apply_model_update(self, test_note_type):
        patch = StagedPatchModel.create(
            patch_id="p9",
            patch_type="model",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "metadata": {"note_type_name": test_note_type.name},
            "modified": {
                "description": "Updated model description",
                "css_style": ".updated {}",
                "fields_schema": ["Front", "Back", "Extra"],
                "templates": [{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
            },
        }
        applier = ModelPatchApplier()
        res = applier.apply(patch, diff_data)
        assert res["status"] == "applied"
        nt = NoteTypeModel.get_by_id(test_note_type.id)
        assert nt.description == "Updated model description"
        assert "Extra" in nt.fields_schema

    def test_apply_note_type_create(self, mock_db):
        patch = StagedPatchModel.create(
            patch_id="p10",
            patch_type="note_type_create",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "name": "CustomBrandNewType",
            "fields_schema": ["Prompt", "Solution"],
            "templates": [{"name": "Default", "qfmt": "{{Prompt}}", "afmt": "{{Solution}}"}],
        }
        applier = ModelPatchApplier()
        res = applier.apply(patch, diff_data)
        assert res["status"] == "applied"
        created = NoteTypeModel.get_or_none(NoteTypeModel.name == "CustomBrandNewType")
        assert created is not None

    def test_apply_note_type_change(self, test_note):
        patch = StagedPatchModel.create(
            patch_id="p10b",
            patch_type="note_type_change",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "note_ids": [test_note.id],
            "target_model": "Basic",
        }
        with mock_patch.object(
            NoteTypeService,
            "change_note_type",
            return_value={
                "target_model_id": 1,
                "target_model_name": "Basic",
                "migrated_count": 1,
                "cards_preserved": 1,
                "cards_created": 0,
                "cards_deleted": 0,
                "warnings": [],
            },
        ):
            applier = ModelPatchApplier()
            res = applier.apply(patch, diff_data)
            assert res["status"] == "applied"
            assert res["count"] == 1

    def test_apply_html_sanitize(self, test_note):
        patch = StagedPatchModel.create(
            patch_id="p11",
            patch_type="html_sanitize",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        clean_content = json.dumps({"Front": "Sanitized Front", "Back": "Sanitized Back"})
        diff_data = {"diffs": [{"note_id": test_note.id, "after": clean_content}]}
        applier = ModelPatchApplier()
        res = applier.apply(patch, diff_data)
        assert res["status"] == "applied"
        assert res["count"] == 1


class TestNoteCreatePatchApplier:
    def test_single_create_success(self, test_deck, test_note_type):
        patch = StagedPatchModel.create(
            patch_id="p12",
            patch_type="note_create",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "deck_name": test_deck.name,
            "note_type_name": test_note_type.name,
            "fields": {"Front": "Single Q", "Back": "Single A"},
            "tags": ["single_tag"],
        }
        applier = NoteCreatePatchApplier()
        res = applier.apply(patch, diff_data)
        assert res["status"] == "applied"
        assert res["note_id"] > 0

    def test_batch_create_success(self, test_deck, test_note_type):
        patch = StagedPatchModel.create(
            patch_id="p13",
            patch_type="batch_note_create",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "default_deck": test_deck.name,
            "default_note_type": test_note_type.name,
            "notes": [
                {"fields": {"Front": "Batch Q1", "Back": "Batch A1"}},
                {"fields": {"Front": "Batch Q2", "Back": "Batch A2"}},
            ],
        }
        applier = NoteCreatePatchApplier()
        res = applier.apply(patch, diff_data)
        assert res["status"] == "applied"
        assert res["count"] == 2

    def test_batch_create_from_json_string(self, test_deck, test_note_type):
        patch = StagedPatchModel.create(
            patch_id="p13b",
            patch_type="batch_note_create",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        diff_data = {
            "default_deck": test_deck.name,
            "default_note_type": test_note_type.name,
            "notes": json.dumps(
                [
                    {"fields": {"Front": "String Q1", "Back": "String A1"}},
                ]
            ),
        }
        applier = NoteCreatePatchApplier()
        res = applier.apply(patch, diff_data)
        assert res["status"] == "applied"
        assert res["count"] == 1


class TestDeckPatchApplier:
    def test_deck_create_and_rename_and_delete(self, mock_db):
        applier = DeckPatchApplier()

        # 1. Create
        p_create = StagedPatchModel.create(
            patch_id="p14",
            patch_type="deck_create",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        res_create = applier.apply(p_create, {"deck_name": "OrigDeck", "description": "Desc"})
        assert res_create["status"] == "applied"
        deck_id = res_create["deck_id"]

        # 2. Rename
        p_rename = StagedPatchModel.create(
            patch_id="p15",
            patch_type="deck_rename",
            target_id=deck_id,
            diff_payload="{}",
            status="pending",
        )
        res_rename = applier.apply(p_rename, {"old_name": "OrigDeck", "new_name": "RenamedDeck"})
        assert res_rename["status"] == "applied"
        assert DeckModel.get_by_id(deck_id).name == "RenamedDeck"

        # 3. Delete
        p_delete = StagedPatchModel.create(
            patch_id="p16",
            patch_type="deck_delete",
            target_id=deck_id,
            diff_payload="{}",
            status="pending",
        )
        res_delete = applier.apply(p_delete, {"deck_name": "RenamedDeck"})
        assert res_delete["status"] == "applied"
        assert DeckModel.get_or_none(DeckModel.id == deck_id) is None


class TestTagPatchApplier:
    def test_tag_bulk_apply(self, test_note):
        patch = StagedPatchModel.create(
            patch_id="p17",
            patch_type="set_tags",
            target_id=test_note.id,
            diff_payload="{}",
            status="pending",
        )
        applier = TagPatchApplier()
        res = applier.apply(patch, {"note_ids": [test_note.id], "tags": ["new_tag"], "mode": "add"})
        assert res["status"] == "applied"


class TestNoteDeletePatchApplier:
    def test_delete_note_with_conflict(self, test_note):
        active_v = test_note.versions.first()
        patch = StagedPatchModel.create(
            patch_id="p18",
            patch_type="note_delete",
            target_id=test_note.id,
            original_version_id=active_v.id + 999,
            diff_payload="{}",
            status="pending",
        )
        applier = NoteDeletePatchApplier()
        res = applier.apply(patch, {"note_ids": [test_note.id]})
        assert res["status"] == "conflict"

    def test_delete_note_success(self, test_note):
        active_v = test_note.versions.first()
        patch = StagedPatchModel.create(
            patch_id="p19",
            patch_type="note_delete",
            target_id=test_note.id,
            original_version_id=active_v.id,
            diff_payload="{}",
            status="pending",
        )
        applier = NoteDeletePatchApplier()
        res = applier.apply(patch, {"note_ids": [test_note.id]})
        assert res["status"] == "applied"
        assert NoteModel.get_or_none(NoteModel.id == test_note.id) is None

    def test_empty_cards_delete(self, mock_db):
        patch = StagedPatchModel.create(
            patch_id="p20",
            patch_type="empty_cards_delete",
            target_id=0,
            diff_payload="{}",
            status="pending",
        )
        applier = NoteDeletePatchApplier()
        res = applier.apply(patch, {"card_ids": [99991, 99992]})
        assert res["status"] == "applied"


class TestDelegatedStepPatchApplier:
    def test_apply_delegated_step_success(self, mock_db):
        patch = StagedPatchModel.create(
            patch_id="p_delegated_1",
            patch_type="pipeline_step_delegated",
            step_order=1,
            diff_payload=json.dumps({"pipeline_id": 42, "step_order": 1}),
            status="pending",
        )
        callback_mock = MagicMock()
        applier = DelegatedStepPatchApplier()
        res = applier.apply(patch, {"pipeline_id": 42, "step_order": 1}, notify_mutation=callback_mock)

        assert res["status"] == "applied"
        assert res["patch_id"] == "p_delegated_1"
        assert patch.status == "applied"
        assert patch.applied_at is not None
        callback_mock.assert_called_once_with(
            "pipeline_step_delegated",
            patch.id,
            {"patch_id": "p_delegated_1", "step_order": 1, "pipeline_id": 42, "run_id": None},
        )

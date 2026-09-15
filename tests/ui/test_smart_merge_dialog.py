import pytest

from ankiforge.services.cards.import_manager import ConflictItem
from ankiforge.ui.dialogs.smart_merge_dialog import ConflictFieldRow, SmartMergeDialog


@pytest.fixture
def sample_conflict():
    return ConflictItem(
        note_id=42,
        guid="guid_xyz",
        note_type_name="Basic",
        local_content={"Front": "Capitale de France ?", "Back": "Paris (Local)"},
        incoming_content={"Front": "Capitale de la France ?", "Back": "Paris (Entrant)"},
        local_deck="Geographie::France",
        incoming_deck="Geographie::Europe",
        local_tags=["france", "v1"],
        incoming_tags=["europe", "v2"],
        similarity_score=85.0,
    )


def test_conflict_field_row(qtbot):
    row = ConflictFieldRow("Front", "Local Value", "Incoming Value")
    qtbot.addWidget(row)

    assert row.get_merged_value() == "Local Value"

    # Transfert incoming vers center
    row._copy_incoming_to_center()
    assert row.get_merged_value() == "Incoming Value"

    # Transfert local vers center
    row._copy_local_to_center()
    assert row.get_merged_value() == "Local Value"


def test_smart_merge_dialog_navigation_and_resolutions(qtbot, sample_conflict):
    conflicts = [
        sample_conflict,
        ConflictItem(
            note_id=43,
            guid="guid_abc",
            note_type_name="Basic",
            local_content={"Front": "Q2 Local", "Back": "A2 Local"},
            incoming_content={"Front": "Q2 Incoming", "Back": "A2 Incoming"},
            local_deck="Deck 1",
            incoming_deck="Deck 2",
            local_tags=[],
            incoming_tags=[],
            similarity_score=60.0,
        ),
    ]

    dialog = SmartMergeDialog(conflicts)
    qtbot.addWidget(dialog)

    assert dialog.lbl_page.text() == "1 / 2"
    assert "Capitale de France" in dialog.field_rows["Front"].get_merged_value()

    # Tout garder local pour le premier conflit
    dialog._on_keep_all_local()
    assert dialog.resolutions["guid_xyz"]["choice"] == "local"

    # Naviguer au conflit suivant
    dialog._on_next_conflict()
    assert dialog.lbl_page.text() == "2 / 2"
    assert "Q2 Local" in dialog.field_rows["Front"].get_merged_value()

    # Tout remplacer par entrant pour le second conflit
    dialog._on_keep_all_incoming()
    assert dialog.resolutions["guid_abc"]["choice"] == "incoming"

    # Validation
    dialog._on_confirm_merge()
    res = dialog.get_resolutions()
    assert res["guid_xyz"]["choice"] == "local"
    assert res["guid_abc"]["choice"] == "incoming"

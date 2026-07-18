from ankiforge.ui.widgets.time_machine_dialog import TimeMachineDialog
from ankiforge.database.models import NoteModel, NoteTypeModel


def test_time_machine_creation(qtbot, mock_db):
    note_type = NoteTypeModel.create(name="test", fields_schema="[]", templates="{}", css_style="")
    note = NoteModel.create(note_type=note_type, content_data="{}", guid="123")
    dialog = TimeMachineDialog(note=note)
    qtbot.addWidget(dialog)
    assert dialog is not None

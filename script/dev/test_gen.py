files = {
    "tests/ui/test_edition_view.py": """import pytest
from ankiforge.ui.views.edition_view import EditionTab

def test_edition_view_creation(qtbot):
    view = EditionTab()
    qtbot.addWidget(view)
    assert view is not None
""",
    "tests/ui/test_consultant_view.py": """import pytest
from ankiforge.ui.views.consultant_view import ConsultantTab

def test_consultant_view_creation(qtbot):
    view = ConsultantTab(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None
""",
    "tests/ui/test_batch_views.py": """import pytest
from ankiforge.ui.views.batch_view import BatchTab

def test_batch_views_creation(qtbot):
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None
""",
    "tests/ui/test_command_palette.py": """import pytest
from ankiforge.ui.widgets.command_palette import CommandPalette

def test_command_palette_creation(qtbot):
    widget = CommandPalette()
    qtbot.addWidget(widget)
    assert widget is not None
""",
    "tests/ui/test_settings_modal.py": """import pytest
from ankiforge.ui.widgets.settings_modal import SettingsModal

def test_settings_modal_creation(qtbot):
    modal = SettingsModal()
    qtbot.addWidget(modal)
    assert modal is not None
""",
    "tests/ui/test_time_machine.py": """import pytest
from ankiforge.ui.widgets.time_machine_dialog import TimeMachineDialog

def test_time_machine_creation(qtbot):
    dialog = TimeMachineDialog(note_id=1)
    qtbot.addWidget(dialog)
    assert dialog is not None
""",
}

for path, content in files.items():
    with open(path, "w") as f:
        f.write(content)

print("Created test files.")

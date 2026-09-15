"""
Tests UI pytest-qt pour les dialogues de modèles de cartes :
ModelExportDialog, ModelImportDialog et StarterPackDialog.
"""

import json
from pathlib import Path

from pytestqt.qtbot import QtBot

from ankiforge.database.models import (
    NoteTypeModel,
)
from ankiforge.ui.dialogs.model_export_dialog import ModelExportDialog
from ankiforge.ui.dialogs.model_import_dialog import ModelImportDialog
from ankiforge.ui.dialogs.starter_pack_dialog import StarterPackDialog


def test_model_export_dialog(qtbot: QtBot, tmp_path: Path):
    model = NoteTypeModel.create(
        name="Law Bar Exam",
        fields_schema=json.dumps(["Article", "Jurisprudence"]),
        templates=json.dumps([{"name": "Droit", "qfmt": "{{Article}}", "afmt": "{{Jurisprudence}}"}]),
        css_style=".law { color: #333; }",
    )

    dlg = ModelExportDialog(model=model)
    qtbot.addWidget(dlg)

    assert dlg.input_author.text() == "AnkiForge User"
    assert dlg.input_version.text() == "1.0.0"
    assert dlg.radio_bundle.isChecked()

    # Définir un chemin temporaire
    target_export = tmp_path / "law_exam.afmodel"
    dlg.dest_input.setText(str(target_export))

    # Déclencher l'export
    dlg._on_confirm_export()
    assert dlg.exported_file_path is not None
    assert dlg.exported_file_path.exists()


def test_model_import_dialog(qtbot: QtBot):
    model_data = {
        "name": "Physics Quantum",
        "fields_schema": ["Equation", "Constant", "Context"],
        "templates": [{"name": "Quantum 1", "qfmt": "{{Equation}}", "afmt": "{{Constant}}"}],
        "css_style": ".quantum { font-family: monospace; }",
        "metadata": {
            "author": "Einstein",
            "version": "1.0.0",
            "description": "Quantum mechanics basics",
            "tags": ["physics", "quantum"],
        },
        "demo_cards": [{"Equation": "E = mc^2", "Constant": "c = 3e8 m/s", "Context": "Special relativity"}],
    }

    dlg = ModelImportDialog(model_data=model_data)
    qtbot.addWidget(dlg)

    assert dlg.name_input.text() == "Physics Quantum"
    assert not dlg.collision_frame.isVisible()

    # Confirmer l'importation
    dlg._on_confirm_import()
    assert dlg.imported_model is not None
    assert dlg.imported_model.name == "Physics Quantum"

    # Vérifier que le modèle est en BDD
    in_db = NoteTypeModel.get_or_none(NoteTypeModel.name == "Physics Quantum")
    assert in_db is not None


def test_starter_pack_dialog(qtbot: QtBot):
    dlg = StarterPackDialog()
    qtbot.addWidget(dlg)

    # Vérifier qu'on peut installer un pack
    pack_data = {
        "id": "medical_qcm",
        "name": "Médical & QCM Interactif Test",
        "category": "Médecine",
        "author": "AnkiForge",
        "version": "1.0.0",
        "fields_schema": ["Question", "Reponse"],
        "templates": [{"name": "QCM", "qfmt": "{{Question}}", "afmt": "{{Reponse}}"}],
        "css_style": "",
    }

    signal_received = []
    dlg.model_installed.connect(lambda model_id: signal_received.append(model_id))

    dlg._on_install_pack(pack_data)
    assert len(signal_received) == 1
    installed_model = NoteTypeModel.get_by_id(signal_received[0])
    assert installed_model.name == "Médical & QCM Interactif Test"

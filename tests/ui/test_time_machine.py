"""
Tests unitaires pour la Machine à Remonter le Temps (Time Machine) et le Diff.
"""

import json
import uuid

import pytest

from ankiforge.database.models import NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.ui.widgets.time_machine_dialog import DiffViewerWidget, TimeMachineDialog


@pytest.mark.ui
def test_time_machine_dialog_loading_versions(qtbot, mock_db):
    """Vérifie le chargement des versions dans TimeMachineDialog et le calcul du diff."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Model TM {uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style=".card {}",
    )
    note = NoteModel.create(guid=f"tm_{uid}", note_type=nt)

    # v1
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Capitale de France ?", "Back": "Lyon"}),
        source="initial",
        is_active=False,
    )
    # v2 (active)
    NoteVersionModel.create(
        note=note,
        version_number=2,
        content=json.dumps({"Front": "Capitale de la France ?", "Back": "Paris"}),
        source="manual",
        is_active=True,
    )

    dialog = TimeMachineDialog(note=note)
    qtbot.addWidget(dialog)

    assert dialog.version_list.count() == 2
    assert dialog.active_version is not None
    assert dialog.active_version.version_number == 2

    # Sélection de la version 1 (historique)
    dialog.version_list.setCurrentRow(1)
    assert dialog.btn_restore.isEnabled() is True

    # Sélection de la version 2 (active) -> bouton restaurer désactivé
    dialog.version_list.setCurrentRow(0)
    assert dialog.btn_restore.isEnabled() is False


@pytest.mark.ui
def test_time_machine_diff_viewer_html_generation(qtbot):
    """Vérifie la génération HTML du visualiseur de diff (rouge/vert)."""
    diff_viewer = DiffViewerWidget()
    qtbot.addWidget(diff_viewer)

    old_dict = {"Front": "Ancienne Question", "Back": "Ancienne Réponse"}
    cur_dict = {"Front": "Nouvelle Question", "Back": "Nouvelle Réponse"}

    diff_viewer.set_content_diff(old_dict, cur_dict)
    html = diff_viewer.toHtml()

    assert "Front" in html
    assert "Back" in html
    assert "COMPARAISON AVEC LA VERSION ACTUELLE" in html


@pytest.mark.ui
def test_time_machine_restore_version(qtbot, mock_db, monkeypatch):
    """Vérifie la restauration d'une ancienne version avec création de snapshot et émission de signal."""
    from PySide6.QtWidgets import QMessageBox

    # Simuler la réponse "Oui" à la confirmation de restauration
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Model TM Restore {uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style=".card {}",
    )
    note = NoteModel.create(guid=f"tm_res_{uid}", note_type=nt)

    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Version 1", "Back": "Réponse 1"}),
        source="initial",
        is_active=False,
    )
    NoteVersionModel.create(
        note=note,
        version_number=2,
        content=json.dumps({"Front": "Version 2", "Back": "Réponse 2"}),
        source="manual",
        is_active=True,
    )

    dialog = TimeMachineDialog(note=note)
    qtbot.addWidget(dialog)

    restored_signals = []
    dialog.version_restored.connect(lambda nid, c_dict: restored_signals.append((nid, c_dict)))

    # Sélectionner la v1 (2ème item dans la liste car ordre desc)
    dialog.version_list.setCurrentRow(1)
    dialog._restore_selected_version()

    assert len(restored_signals) == 1
    assert restored_signals[0][0] == note.id
    assert restored_signals[0][1]["Front"] == "Version 1"

    # Vérifier en BDD que la v3 a été créée et est active
    latest = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()
    assert latest is not None
    assert latest.version_number == 3
    assert latest.is_active is True
    assert "Version 1" in latest.content

"""
Tests d'interface graphique (pytest-qt) pour la modale PersonaHistoryDialog.
"""

from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox
from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.persona_version_service import PersonaVersionService
from ankiforge.ui.dialogs.persona_history_dialog import PersonaHistoryDialog


def test_persona_history_dialog_rendering(qtbot, mock_db):
    """Vérifie le chargement des versions dans la modale d'historique."""
    persona = PersonaModel.create(
        name="Auditeur Math",
        description="Auditeur pour formules KaTeX",
        system_prompt="Extrais les théorèmes.",
        output_format="json",
    )
    PersonaVersionService.create_snapshot(persona, "V1 Initial")

    persona.system_prompt = "Extrais les théorèmes et les lemmes."
    persona.save()
    PersonaVersionService.create_snapshot(persona, "V2 Lemmes", force=True)

    dlg = PersonaHistoryDialog(persona.id)
    qtbot.addWidget(dlg)

    assert dlg.version_list.count() == 2
    # La version sélectionnée par défaut est la plus récente (V2)
    assert dlg._selected_version is not None
    assert dlg._selected_version.version_number == 2
    assert dlg.btn_restore.isEnabled() is False  # Car active


def test_persona_history_dialog_selection_and_restore(qtbot, mock_db):
    """Vérifie la sélection d'une ancienne version et l'émission du signal de restauration."""
    persona = PersonaModel.create(
        name="Agent Rédaction",
        system_prompt="Version originale.",
        output_format="text",
    )
    v1 = PersonaVersionService.create_snapshot(persona, "V1")

    persona.system_prompt = "Version modifiée."
    persona.save()
    PersonaVersionService.create_snapshot(persona, "V2", force=True)

    dlg = PersonaHistoryDialog(persona.id)
    qtbot.addWidget(dlg)

    # Sélection de la version 1 (ligne index 1)
    dlg.version_list.setCurrentRow(1)
    assert dlg._selected_version is not None
    assert dlg._selected_version.id == v1.id
    assert dlg.btn_restore.isEnabled() is True

    # Simulation du clic sur Restaurer avec mock de confirmation
    restored_ids = []
    dlg.version_restored.connect(lambda pid: restored_ids.append(pid))

    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        dlg.btn_restore.click()

    assert len(restored_ids) == 1
    assert restored_ids[0] == persona.id

    # Vérification en base
    persona_reloaded = PersonaModel.get_by_id(persona.id)
    assert persona_reloaded.system_prompt == "Version originale."

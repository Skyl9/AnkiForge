"""Tests UI pour la boîte de dialogue de structuration IA de documents (AIDocumentStructureDialog)."""

from unittest.mock import MagicMock

from pytestqt.qtbot import QtBot

from ankiforge.database.models import DocumentModel
from ankiforge.services.markdown.ai_structurer import AIDocumentStructurer, StructuringProfile
from ankiforge.ui.views.documents_view.dialogs.ai_structure_dialog import AIDocumentStructureDialog
from ankiforge.ui.views.documents_view.view import DocumentsView


def test_ai_structure_dialog_initial_state(qtbot: QtBot) -> None:
    raw_text = "00:00 Bienvenue à ce cours sur l'astronomie.\n00:30 Nous allons voir la loi de gravitation : F = G * m1 * m2 / r^2."
    dialog = AIDocumentStructureDialog(doc_title="Astronomie", content=raw_text, parent=None)
    qtbot.addWidget(dialog)

    assert "Structurer avec l'IA" in dialog.windowTitle()
    assert "Astronomie" in dialog.windowTitle()
    assert dialog.txt_original.toPlainText() == raw_text
    assert dialog.txt_result.toPlainText() == ""
    assert not dialog.btn_apply_editor.isEnabled()
    assert not dialog.btn_save_copy.isEnabled()
    assert dialog.cb_profile.count() == 3
    assert dialog.cb_profile.currentData() == StructuringProfile.DIDACTIC


def test_ai_structure_dialog_finished_and_signals(qtbot: QtBot) -> None:
    raw_text = "Retranscription brute de test."
    dialog = AIDocumentStructureDialog(doc_title="Test Doc", content=raw_text, parent=None)
    qtbot.addWidget(dialog)

    # Simuler la complétion du traitement
    structured_output = "# Titre Structuré\n\n## [00:10] Introduction\n\nExplication claire avec terme en **gras** et formule $E = mc^2$."
    dialog._on_worker_finished(structured_output)

    assert dialog.txt_result.toPlainText() == structured_output
    assert dialog.btn_apply_editor.isEnabled()
    assert dialog.btn_save_copy.isEnabled()

    # Test émission du signal pour remplacement dans l'éditeur
    applied_results: list[str] = []
    dialog.structure_applied.connect(applied_results.append)
    dialog.btn_apply_editor.click()
    assert len(applied_results) == 1
    assert applied_results[0] == structured_output

    # Test émission du signal pour sauvegarde en copie
    copy_results: list[str] = []
    dialog.structure_saved_as_copy.connect(copy_results.append)
    dialog.btn_save_copy.click()
    assert len(copy_results) == 1
    assert copy_results[0] == structured_output


def test_ai_structure_dialog_worker_mock(qtbot: QtBot, monkeypatch: object) -> None:
    raw_text = "Retranscription courte."
    dialog = AIDocumentStructureDialog(doc_title="Cours Rapide", content=raw_text, parent=None)
    qtbot.addWidget(dialog)

    # Mock de AIDocumentStructurer.structure_document
    mock_struct = MagicMock(return_value="# Cours Rapide\n\nContenu restructuré avec succès.")
    monkeypatch.setattr(AIDocumentStructurer, "structure_document", mock_struct)

    # Lancement de la structuration
    dialog._on_start_structuring()
    assert dialog._worker is not None

    # Attendre que le thread se termine proprement avec qtbot
    with qtbot.waitSignal(dialog._worker.finished, timeout=3000):
        pass

    assert dialog.txt_result.toPlainText() == "# Cours Rapide\n\nContenu restructuré avec succès."
    assert dialog.btn_apply_editor.isEnabled()


def test_documents_view_ai_structure_integration(qtbot: QtBot) -> None:
    view = DocumentsView()
    qtbot.addWidget(view)

    assert hasattr(view, "btn_ai_structure")

    # Crée un document test
    doc = DocumentModel.create(
        title="Conférence Physique",
        content="Retranscription conférence sur la physique quantique.",
        file_type="txt",
    )
    view._current_doc_id = doc.id
    view.text_editor.set_content(doc.content)

    structured_text = "# Conférence Physique\n\n## 01:00 Principes\n\nContenu structuré."

    # Test 1 : Remplacement direct dans l'éditeur
    view._on_structure_applied_to_editor(structured_text)
    assert view.text_editor.get_content() == structured_text
    assert view._dirty is True

    # Test 2 : Enregistrement comme nouveau document (copie)
    initial_count = DocumentModel.select().count()
    view._on_structure_saved_as_copy(structured_text)
    assert DocumentModel.select().count() == initial_count + 1

    new_doc = DocumentModel.get(DocumentModel.title == "Conférence Physique (Structuré IA)")
    assert new_doc.content == structured_text
    assert new_doc.file_type == "md"

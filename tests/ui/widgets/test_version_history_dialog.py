import pytest
import json
from datetime import datetime
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QDialog

# Ajuste l'import selon ton architecture exacte
from ankiforge.ui.widgets.version_history_dialog import VersionHistoryDialog
from ankiforge.database.models import DeckModel, NoteTypeModel, NoteModel, NoteVersionModel


# --- FIXTURES ---

@pytest.fixture
def test_note():
    """
    Insère de vraies données dans la base de données en mémoire (mock_db).
    On respecte scrupuleusement les contraintes NOT NULL de models.py.
    """
    # 1. On crée les dépendances (clés étrangères)
    deck = DeckModel.create(name="Deck de Test")

    note_type = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Recto", "Verso"]),
        templates=json.dumps([]),
        css_style=""  # <-- REQUIS car pas de null=True dans ton modèle !
    )

    # 2. On crée la note
    note = NoteModel.create(
        guid="test-unique-guid-123",  # <-- REQUIS car pas de null=True !
        deck=deck,
        note_type=note_type
    )

    # 3. On crée l'ancienne version (v1)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Recto": "Chien", "Verso": "Doggo"}),  # "Doggo" était une erreur
        source="ai",
        is_active=False,
        created_at=datetime(2026, 1, 1, 10, 0)
    )

    # 4. On crée la version actuelle (v2)
    NoteVersionModel.create(
        note=note,
        version_number=2,
        content=json.dumps({"Recto": "Chien", "Verso": "Dog"}),  # Corrigé en "Dog"
        source="manual",
        is_active=True,
        created_at=datetime(2026, 1, 2, 12, 0)
    )

    return note


@pytest.fixture
def dialog(qtbot, test_note):
    """Crée le dialog en lui passant la vraie note de la BDD."""
    dialog = VersionHistoryDialog(note=test_note)
    qtbot.addWidget(dialog)
    return dialog


# --- TESTS ---

def test_dialog_initialization(dialog):
    """Vérifie que l'historique se charge bien au démarrage depuis la BDD."""
    assert dialog.list_versions.count() == 2

    # L'ordre est DESC, donc la v2 (Actuelle) est en haut
    item_active = dialog.list_versions.item(0)
    assert "v2 (Actuelle)" in item_active.text()

    # La version active étant sélectionnée par défaut, le bouton restaurer doit être grisé
    assert dialog.btn_restore.isEnabled() == False


def test_diff_html_generation(dialog):
    """Test unitaire isolé de l'algorithme de diff."""
    html = dialog.generate_diff_html(old_text="Doggo", new_text="Dog")

    # 1. Vérification d'une suppression partielle
    assert "text-decoration: line-through" in html  # Il y a bien une suppression
    assert "Dog" in html  # La partie commune est conservée
    assert ">go</span>" in html  # C'est spécifiquement "go" qui a été barré/supprimé

    # 2. Vérification d'un ajout
    html_add = dialog.generate_diff_html(old_text="Chat", new_text="Le Chat")
    assert "Le " in html_add  # Le nouveau texte est là
    assert "line-through" not in html_add  # Rien n'a été supprimé


def test_version_selection_updates_diff(dialog, qtbot):
    """Vérifie que cliquer sur une ancienne version met à jour l'écran de droite."""
    # On sélectionne la v1 (qui est à l'index 1 car on trie par ordre décroissant)
    dialog.list_versions.setCurrentRow(1)

    assert dialog.btn_restore.isEnabled() == True

    displayed_html = dialog.text_diff.toHtml()
    assert "Champ : Recto" in displayed_html
    assert "Identique" in displayed_html

    # On vérifie la présence du diff découpé par difflib
    assert "Dog" in displayed_html
    assert ">go</span>" in displayed_html


@patch('ankiforge.ui.widgets.version_history_dialog.QMessageBox.question')
@patch('ankiforge.ui.widgets.version_history_dialog.show_toast')
def test_restore_version_flow(mock_toast, mock_question, dialog, qtbot, test_note):
    """Vérifie que la restauration crée BIEN une nouvelle version dans la base de données."""

    # 1. On programme la popup pour qu'elle simule "Oui"
    mock_question.return_value = QMessageBox.StandardButton.Yes

    # 2. On sélectionne la v1 et on clique sur Restaurer
    dialog.list_versions.setCurrentRow(1)
    qtbot.mouseClick(dialog.btn_restore, Qt.MouseButton.LeftButton)

    # 3. Vérifications de l'UI
    mock_question.assert_called_once()
    mock_toast.assert_called_once()
    assert dialog.result() == QDialog.DialogCode.Accepted

    # 4. VÉRIFICATION DE LA BASE DE DONNÉES (La magie opère ici)

    # Il doit y avoir 3 versions maintenant
    assert test_note.versions.count() == 3

    # On récupère la nouvelle version active
    new_active_version = test_note.versions.where(NoteVersionModel.is_active == True).first()

    # Elle doit être la v3
    assert new_active_version.version_number == 3
    assert new_active_version.source == "manual"

    # Son contenu doit être celui de la v1 restaurée ("Doggo")
    content = json.loads(new_active_version.content)
    assert content["Verso"] == "Doggo"
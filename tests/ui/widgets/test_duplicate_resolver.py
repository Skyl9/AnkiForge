import pytest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QDialog

# Ajuste les imports selon ton architecture
from ankiforge.ui.widgets.duplicate_resolver import DuplicateResolverDialog
from ankiforge.database.models import DeckModel, NoteTypeModel, NoteModel, IgnoredDuplicateModel


# --- FIXTURES ---

@pytest.fixture
def mock_db_notes():
    """Prépare 4 notes réelles dans la BDD de test pour simuler 2 conflits."""
    deck = DeckModel.create(name="Deck de Conflits")
    note_type = NoteTypeModel.create(
        name="Basique",
        fields_schema='["Recto", "Verso"]',
        templates="[]",
        css_style=""
    )

    # Création de 4 notes (A vs B pour le conflit 1, C vs D pour le conflit 2)
    note_a = NoteModel.create(guid="guid-A", deck=deck, note_type=note_type)
    note_b = NoteModel.create(guid="guid-B", deck=deck, note_type=note_type)
    note_c = NoteModel.create(guid="guid-C", deck=deck, note_type=note_type)
    note_d = NoteModel.create(guid="guid-D", deck=deck, note_type=note_type)

    return note_a, note_b, note_c, note_d


@pytest.fixture
def conflicts_data(mock_db_notes):
    """Prépare la liste de conflits attendue par le Dialog."""
    note_a, note_b, note_c, note_d = mock_db_notes

    # Conflit 1: A vs B
    content_a = {"Recto": "Chien", "Verso": "Doggo"}
    content_b = {"Recto": "Chien", "Verso": "Dog"}

    # Conflit 2: C vs D (Totalement différents)
    content_c = {"Recto": "Chat", "Verso": "Cat"}
    content_d = {"Recto": "Chat", "Verso": "Kitten"}

    return [
        (note_a, content_a, note_b, content_b),
        (note_c, content_c, note_d, content_d)
    ]


@pytest.fixture
def dialog(qtbot, conflicts_data):
    """Initialise le Dialog avec les conflits."""
    dialog = DuplicateResolverDialog(conflicts=conflicts_data)
    qtbot.addWidget(dialog)
    return dialog


# --- TESTS ---

def test_generate_diff_html(dialog):
    """Test unitaire de l'algorithme de diff Rouge/Vert."""
    html_a, html_b = dialog.generate_diff_html("Doggo", "Dog")

    # html_a (Original) doit montrer "go" en rouge (supprimé)
    assert "Dog" in html_a
    assert "#5c1b1b" in html_a  # Couleur rouge
    assert ">go</span>" in html_a

    # html_b (Nouveau) ne doit plus contenir "go"
    assert "Dog" in html_b
    assert "go" not in html_b


def test_dialog_initialization_and_ui(dialog):
    """Vérifie que le premier conflit se charge correctement dans l'UI."""
    assert dialog.current_index == 0
    assert dialog.progress_bar.maximum() == 2
    assert "Conflit 1 sur 2" in dialog.lbl_status.text()

    # Le texte doit avoir été injecté
    html_left = dialog.text_left.toHtml()
    assert "Champ : Recto" in html_left
    assert "Identique" in html_left  # Car "Chien" == "Chien"

    # On vérifie les morceaux découpés par l'algorithme de diff
    assert "Dog" in html_left
    assert ">go</span>" in html_left


def test_keep_a_deletes_b(dialog, qtbot, mock_db_notes):
    """Vérifie que garder A supprime B de la BDD et passe au conflit suivant."""
    note_a, note_b, note_c, note_d = mock_db_notes

    # Action : Clic sur Garder A
    qtbot.mouseClick(dialog.btn_keep_a, Qt.MouseButton.LeftButton)

    # 1. Vérification BDD : B doit être détruite, A doit survivre
    assert NoteModel.get_or_none(id=note_a.id) is not None
    assert NoteModel.get_or_none(id=note_b.id) is None

    # 2. Vérification UI : On est passé au conflit 2
    assert dialog.current_index == 1
    assert "Conflit 2 sur 2" in dialog.lbl_status.text()


def test_keep_b_deletes_a(dialog, qtbot, mock_db_notes):
    """Vérifie que garder B supprime A de la BDD et passe au conflit suivant."""
    note_a, note_b, _, _ = mock_db_notes

    # Action : Clic sur Garder B
    qtbot.mouseClick(dialog.btn_keep_b, Qt.MouseButton.LeftButton)

    # Vérification BDD : A doit être détruite, B doit survivre
    assert NoteModel.get_or_none(id=note_a.id) is None
    assert NoteModel.get_or_none(id=note_b.id) is not None


def test_ignore_conflict_saves_to_db(dialog, qtbot, mock_db_notes):
    """Vérifie que le bouton Ignorer sauvegarde l'ID dans la table d'ignorés."""
    note_a, note_b, _, _ = mock_db_notes

    # Action : Clic sur Ignorer
    qtbot.mouseClick(dialog.btn_ignore, Qt.MouseButton.LeftButton)

    # Vérification BDD : Les deux notes existent toujours
    assert NoteModel.get_or_none(id=note_a.id) is not None
    assert NoteModel.get_or_none(id=note_b.id) is not None

    # Vérification BDD : Une entrée a été créée dans IgnoredDuplicateModel
    ignored_entry = IgnoredDuplicateModel.select().first()
    assert ignored_entry is not None
    # On vérifie l'ordre (le plus petit ID en premier)
    expected_id_1 = min(note_a.id, note_b.id)
    expected_id_2 = max(note_a.id, note_b.id)
    assert ignored_entry.note_a.id == expected_id_1
    assert ignored_entry.note_b.id == expected_id_2


@patch('ankiforge.ui.widgets.duplicate_resolver.QMessageBox.information')
def test_end_of_conflicts_closes_dialog(mock_info, dialog, qtbot):
    """Vérifie qu'à la fin de la liste, un message s'affiche et le dialog se ferme."""
    # On résout le conflit 1
    qtbot.mouseClick(dialog.btn_ignore, Qt.MouseButton.LeftButton)

    # On résout le conflit 2 (ce qui amène index >= len)
    qtbot.mouseClick(dialog.btn_ignore, Qt.MouseButton.LeftButton)

    # La messagebox doit être appelée
    mock_info.assert_called_once()

    # Le dialog doit être fermé (status Accepted)
    assert dialog.result() == QDialog.DialogCode.Accepted
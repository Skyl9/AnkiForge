import csv
from pathlib import Path
from unittest.mock import patch, MagicMock

from ankiforge.database.models import DeckModel, NoteTypeModel, NoteModel, CardModel
from ankiforge.services.cards.store_manager import StoreManager


def test_extract_pb_string():
    """Test du mini-décodeur Protobuf."""
    manager = StoreManager()

    # Octets représentant le tag (champ 1, type chaîne) et "Hello"
    fake_pb_data = b'\x0a\x05Hello'

    result = manager.extract_pb_string(fake_pb_data, target_field=1)
    assert result == "Hello"


def test_handle_txt_import(tmp_path):
    """Génère un fichier TSV à la volée et vérifie son importation."""
    manager = StoreManager()

    fake_txt = tmp_path / "test.txt"
    with open(fake_txt, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(["#separator:tab"])
        writer.writerow(["#html:true"])
        writer.writerow(["#tags column:5"])
        writer.writerow(["#notetype column:1"])
        writer.writerow(["#deck column:4"])
        # Format: Notetype, Recto, Verso, Deck, Tags
        writer.writerow(["Basique", "Chat", "Cat", "Langues::Anglais", "Vocabulaire"])

    manager.handle_txt(fake_txt)

    # Vérifications Base de Données (La base est déjà vierge grâce au conftest.py)
    assert DeckModel.select().count() == 2  # 'Langues' et 'Langues::Anglais'
    assert NoteTypeModel.select().count() == 1
    assert NoteModel.select().count() == 1

    note = NoteModel.get()
    assert note.note_type.name == "Basique"
    assert "Cat" in note.versions.first().content


@patch('ankiforge.services.cards.store_manager.sqlite3.connect')
@patch('zipfile.ZipFile')
def test_handle_apkg_mocked(mock_zip, mock_sqlite, tmp_path):
    """Simule l'extraction d'un apkg en mockant les interactions SQL."""
    manager = StoreManager()

    # 1. On mocke l'extraction ZIP (pour ne pas vraiment essayer de dézipper notre faux fichier)
    mock_zip_instance = MagicMock()
    mock_zip.return_value.__enter__.return_value = mock_zip_instance

    # 2. On mocke la base SQL Anki
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_sqlite.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # On simule les retours SQL de base (Decks et Models JSON format)
    mock_cursor.fetchone.side_effect = [
        ('{"1": {"id": 1, "name": "Mon Paquet"}}',),  # col.decks
        ('{"2": {"name": "Basic", "flds": [{"name": "Front"}], "tmpls": [], "css": ""}}',),  # col.models
    ]
    mock_cursor.fetchall.side_effect = [
        [(1, "guid1", 2, "Tag1", "Ceci est le recto")],  # notes
        [(1, 1, 1, 0)]  # cards
    ]

    # 3. Exécution avec de VRAIS faux fichiers
    fake_apkg = tmp_path / "fake.apkg"
    fake_apkg.touch()  # On crée physiquement le fichier sur le disque pour passer le premier check

    # On force StoreManager à utiliser notre tmp_path quand il crée son dossier temporaire d'extraction
    with patch('ankiforge.services.cards.store_manager.tempfile.TemporaryDirectory') as mock_temp:
        mock_temp.return_value.__enter__.return_value = str(tmp_path)

        # On crée physiquement la fausse base extraite pour passer le second check "if anki2_path.exists():"
        (tmp_path / "collection.anki2").touch()

        # Et on lance la machine !
        manager.store_collection(str(fake_apkg))

    # 4. Vérifications PEEWEE
    assert DeckModel.get(DeckModel.name == "Mon Paquet") is not None
    assert NoteTypeModel.get(NoteTypeModel.name == "Basic") is not None
    assert CardModel.select().count() == 1
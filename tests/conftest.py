# tests/conftest.py
import pytest
from peewee import SqliteDatabase
from src.database.models import DeckModel, NoteTypeModel, NoteModel, CardModel


@pytest.fixture(autouse=True)
def mock_db():
    """Cette base fantôme sera automatiquement utilisée pour TOUS les tests du projet."""
    test_db = SqliteDatabase(':memory:')
    models = [DeckModel, NoteTypeModel, NoteModel, CardModel]
    test_db.bind(models, bind_refs=False, bind_backrefs=False)

    test_db.connect()
    test_db.create_tables(models)

    yield test_db

    test_db.drop_tables(models)
    test_db.close()
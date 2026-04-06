# tests/conftest.py
import os

import pytest
from peewee import SqliteDatabase
from ankiforge.database.models import (DeckModel, NoteTypeModel, NoteModel, CardModel,
                 NoteVersionModel, AgentModel, PipelineModel,
                 PipelineStepModel, FolderModel, DocumentModel,
                 IgnoredDuplicateModel, LLMConfigModel, PromptModel)

os.environ["QT_QPA_PLATFORM"] = "offscreen"

@pytest.fixture(autouse=True)
def mock_db():
    """Cette base fantôme en RAM sera automatiquement utilisée pour TOUS les tests."""
    # On crée une base en mémoire (ultra-rapide, vidée à chaque test)
    test_db = SqliteDatabase(':memory:')

    # On liste TOUTES les tables de l'application
    models = [DeckModel, NoteTypeModel, NoteModel, CardModel, NoteVersionModel,
              AgentModel, PipelineModel, PipelineStepModel, FolderModel, DocumentModel,
              IgnoredDuplicateModel, LLMConfigModel, PromptModel]

    # On force Peewee à utiliser cette fausse base plutôt que le fichier .db réel
    test_db.bind(models, bind_refs=False, bind_backrefs=False)

    test_db.connect()
    test_db.execute_sql('PRAGMA foreign_keys = ON;')  # <-- INDISPENSABLE POUR TESTER LES CASCADES
    test_db.create_tables(models)

    yield test_db  # Le test s'exécute ici

    test_db.drop_tables(models)
    test_db.close()
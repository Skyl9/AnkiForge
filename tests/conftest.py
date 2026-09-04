# tests/conftest.py
import contextlib
import os

import pytest
from peewee import SqliteDatabase

from ankiforge.database.models import (
    AICacheModel,
    AuditRecordModel,
    CardModel,
    ConsultantMessageModel,
    ConsultantSessionModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    EmbeddingCacheModel,
    FolderModel,
    IgnoredDuplicateModel,
    LinterRuleModel,
    LLMConfigModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
    PersonaFolderModel,
    PersonaModel,
    PersonaVersionModel,
    PipelineModel,
    PipelineStepModel,
    PromptModel,
    PythonToolModel,
    SettingModel,
    TokenUsageModel,
    db,
)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-gpu --disable-software-rasterizer --offscreen --disable-dev-shm-usage"
os.environ["ANKIFORGE_MOCK_WEBENGINE"] = "1"


@pytest.fixture(autouse=True)
def mock_db():
    """Cette base fantôme en RAM sera automatiquement utilisée pour TOUS les tests."""
    # On crée une base en mémoire partagée entre threads pour supporter QThreadPool (isolée par worker xdist)
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "master")
    db_uri = f"file:memdb_test_{worker_id}?mode=memory&cache=shared"
    test_db = SqliteDatabase(db_uri, uri=True)
    db.init(db_uri, uri=True)

    # On liste TOUTES les tables de l'application
    models = [
        DeckModel,
        NoteTypeModel,
        NoteModel,
        CardModel,
        NoteVersionModel,
        PersonaFolderModel,
        PersonaModel,
        PersonaVersionModel,
        ConsultantSessionModel,
        ConsultantMessageModel,
        PipelineModel,
        PipelineStepModel,
        PythonToolModel,
        FolderModel,
        DocumentModel,
        DocumentPageModel,
        IgnoredDuplicateModel,
        LLMConfigModel,
        PromptModel,
        MediaModel,
        NoteVersionMediaModel,
        AICacheModel,
        DocumentChunkModel,
        NoteChunkLinkModel,
        EmbeddingCacheModel,
        LinterRuleModel,
        AuditRecordModel,
        SettingModel,
        TokenUsageModel,
    ]

    # On force Peewee à utiliser cette fausse base plutôt que le fichier .db réel
    test_db.bind(models, bind_refs=False, bind_backrefs=False)

    test_db.connect()
    test_db.execute_sql("PRAGMA foreign_keys = ON;")  # <-- INDISPENSABLE POUR TESTER LES CASCADES
    test_db.create_tables(models)

    yield test_db  # Le test s'exécute ici

    with contextlib.suppress(Exception):
        test_db.execute_sql("DROP TABLE IF EXISTS migratehistory;")
    test_db.drop_tables(models)
    test_db.close()


@pytest.fixture(autouse=True)
def cleanup_qt_widgets():
    """Nettoie les fenêtres et widgets Qt à la fin de chaque test."""
    yield
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication

    # 1. Attendre que les tâches en cours du QThreadPool terminent
    with contextlib.suppress(Exception):
        QThreadPool.globalInstance().waitForDone(3000)

    app = QApplication.instance()
    if app:
        for widget in list(app.allWidgets()):
            try:
                if widget.parent() is None:
                    widget.close()
                    widget.deleteLater()
            except Exception:
                pass
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    with contextlib.suppress(Exception):
        QThreadPool.globalInstance().waitForDone(1000)


def pytest_unconfigure(config):
    """S'assure d'une sortie propre sans crash C++ Chromium WebEngine en fin de tests."""
    import os
    import sys

    # Ne jamais appeler os._exit dans les workers xdist, sinon xdist considère le worker comme crashé
    if "PYTEST_XDIST_WORKER" in os.environ or "PYTEST_XDIST_TESTRUNUID" in os.environ or hasattr(config, "workerinput"):
        return

    sys.stdout.flush()
    sys.stderr.flush()
    exit_code = getattr(config, "exitstatus", 0)
    os._exit(exit_code)

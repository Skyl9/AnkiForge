# tests/conftest.py
import os

import pytest
from peewee import SqliteDatabase
from ankiforge.database.models import (
    AICacheModel,
    AuditRecordModel,
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
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


@pytest.fixture(autouse=True)
def mock_db():
    """Cette base fantôme en RAM sera automatiquement utilisée pour TOUS les tests."""
    # On crée une base en mémoire partagée entre threads pour supporter QThreadPool
    test_db = SqliteDatabase("file:memdb_test?mode=memory&cache=shared", uri=True)
    db.init("file:memdb_test?mode=memory&cache=shared", uri=True)

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
        PipelineModel,
        PipelineStepModel,
        PythonToolModel,
        FolderModel,
        DocumentModel,
        IgnoredDuplicateModel,
        LLMConfigModel,
        PromptModel,
        MediaModel,
        NoteVersionMediaModel,
        AICacheModel,
        DocumentChunkModel,
        NoteChunkLinkModel,
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

    try:
        test_db.execute_sql("DROP TABLE IF EXISTS migratehistory;")
    except Exception:
        pass
    test_db.drop_tables(models)
    test_db.close()


@pytest.fixture(autouse=True)
def cleanup_qt_widgets():
    """Nettoie les fenêtres et widgets Qt à la fin de chaque test."""
    yield
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
    from PySide6.QtWidgets import QApplication

    # 1. Attendre que les tâches en cours du QThreadPool terminent
    try:
        QThreadPool.globalInstance().waitForDone(3000)
    except Exception:
        pass

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

    try:
        QThreadPool.globalInstance().waitForDone(1000)
    except Exception:
        pass


def pytest_unconfigure(config):
    """S'assure d'une sortie propre sans crash C++ Chromium WebEngine en fin de tests."""
    import os

    exit_code = getattr(config, "exitstatus", 0)
    os._exit(exit_code)

# tests/conftest.py
import contextlib
import os
from collections.abc import Callable

import pytest
from peewee import SqliteDatabase

# Neutralise le trousseau OS durant les tests : aucun accès au Keychain/Credential
# Manager CI, et le code refuse alors toute persistance de clé en clair (sécurité).
with contextlib.suppress(Exception):
    import keyring
    from keyring.backends import fail

    keyring.set_keyring(fail.Keyring())

from ankiforge.database.models import (
    AICacheModel,
    AuditRecordModel,
    BatchRunModel,
    BatchTaskModel,
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
    JobModel,
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
    PipelineRunModel,
    PipelineStepModel,
    PromptModel,
    PythonToolModel,
    SettingModel,
    StagedPatchModel,
    TokenUsageModel,
    db,
)

# Keep CI's Xvfb/xcb backend when it is explicitly configured. Local headless
# runs still default to offscreen when no display backend was provided.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu --disable-software-rasterizer --offscreen --disable-dev-shm-usage")
os.environ.setdefault("ANKIFORGE_MOCK_WEBENGINE", "1")
os.environ.setdefault("ANKIFORGE_ENV", "testing")

# Document Marker typique (fixture partagée) : un sommaire dont les entrées sont
# balisées comme des titres Markdown, suivi du corps réel des chapitres sous les
# MÊMES titres — la collision à laquelle le ticket P1 s'applique.
MARKER_TOC_PAGINATED = "\n".join(
    [
        "{0}------------------------------------------------",
        "# Polycopié de Statistiques",
        "",
        "Page de couverture du polycopié.",
        "",
        "{1}------------------------------------------------",
        "# Sommaire",
        "",
        "## 1 - Introduction aux données",
        "",
        "## 2 - Statistiques descriptives",
        "",
        "## 3 - Probabilités",
        "",
        "{4}------------------------------------------------",
        "# 1 - Introduction aux données",
        "",
        "Une variable aléatoire est une fonction qui associe chaque issue d'une expérience "
        "aléatoire à une valeur numérique. Elle est décrite par une fonction de répartition "
        "croissante qui converge vers l'unité en l'infini du support.",
        "",
        "# 2 - Statistiques descriptives",
        "",
        "La moyenne arithmétique est la somme des valeurs divisée par le nombre d'observations. La variance mesure la dispersion autour de cette moyenne et l'écart-type en est la racine.",
    ]
)

# Même document sans les marqueurs de page : pour les consommateurs Markdown.
MARKER_TOC_PLAIN = (
    MARKER_TOC_PAGINATED.replace("{0}------------------------------------------------\n", "")
    .replace("{1}------------------------------------------------\n", "")
    .replace("{4}------------------------------------------------\n", "")
)


FORBIDDEN_GLYPHS = ("✅", "⚠️", "🛑", "⏭️", "🔀", "➡️", "↳", "📄", "📑", "📦")


@pytest.fixture
def contains_forbidden_glyph() -> Callable[[str], bool]:
    """Détecte les emojis et pictogrammes interdits dans un texte d'interface.

    La règle du dépôt est « icônes Phosphor, zéro emoji texte » (DESIGN.md). Ce contrôle
    est donc factorisé ici : deux copies de la même liste finiraient fatalement par
    diverger, et un test vert sur une liste incomplète ne prouve rien.
    """
    forbidden = tuple(FORBIDDEN_GLYPHS)

    def _contains(text: str) -> bool:
        return any(ch in text for ch in forbidden) or any(ord(ch) > 10000 for ch in text)

    return _contains


@pytest.fixture(scope="session")
def marker_toc_paginated() -> str:
    """Markdown Marker paginé dont le sommaire duplique les titres du corps de cours."""
    return MARKER_TOC_PAGINATED


@pytest.fixture(scope="session")
def marker_toc_plain() -> str:
    """Variante non paginée du même document (consommateurs Markdown)."""
    return MARKER_TOC_PLAIN


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
        PipelineRunModel,
        PipelineStepModel,
        PythonToolModel,
        BatchRunModel,
        BatchTaskModel,
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
        StagedPatchModel,
        JobModel,  # Ajouté pour aligner avec ALL_MODELS et éviter les tests cassés
    ]

    # On force Peewee à utiliser cette fausse base plutôt que le fichier .db réel
    test_db.bind(models, bind_refs=False, bind_backrefs=False)

    test_db.connect()
    test_db.execute_sql("PRAGMA foreign_keys = ON;")  # <-- INDISPENSABLE POUR TESTER LES CASCADES
    test_db.create_tables(models)
    with contextlib.suppress(Exception):
        test_db.execute_sql("""
            CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
                note_id UNINDEXED,
                deck_id UNINDEXED,
                fields_text,
                tags,
                tokenize = 'unicode61 remove_diacritics 2'
            );
        """)

    with contextlib.suppress(Exception):
        from ankiforge.utils.environment import get_app_qsettings

        get_app_qsettings().clear()
        # Les préférences d'apparence et de layout vivent dans le scope « obsidian ».
        get_app_qsettings("obsidian").clear()
    with contextlib.suppress(Exception):
        SettingModel.delete().where(SettingModel.key.startswith("profiles/")).execute()

    yield test_db  # Le test s'exécute ici

    with contextlib.suppress(Exception):
        from ankiforge.utils.environment import get_app_qsettings

        get_app_qsettings().clear()
        get_app_qsettings("obsidian").clear()
    with contextlib.suppress(Exception):
        SettingModel.delete().where(SettingModel.key.startswith("profiles/")).execute()
    with contextlib.suppress(Exception):
        test_db.execute_sql("DROP TABLE IF EXISTS note_fts;")
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

    with contextlib.suppress(Exception):
        from ankiforge.ui.widgets.toast import ToastManager

        ToastManager.get_instance().clear()

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

    with contextlib.suppress(Exception):
        from ankiforge.ui.style_engine import StyleEngine

        if StyleEngine._instance is not None:
            StyleEngine._instance.clear_custom_library()

    # Le cache de vignettes est un singleton de **processus**, et sa clé s'appuie sur
    # `media_id` : or chaque test repart d'une base neuve où le premier média porte
    # toujours l'id 1. Sans cette remise à zéro, la vignette rendue par un test était
    # servie telle quelle à un autre test dont la planche avait la même clé — un échec
    # qui ne se reproduisait qu'en-suite complète, jamais isolé.
    with contextlib.suppress(Exception):
        from ankiforge.ui.views.documents_view.widgets.album_thumbnails import GLOBAL_THUMBNAIL_CACHE

        GLOBAL_THUMBNAIL_CACHE.clear()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Garantit que 100% des tests possèdent au moins un marqueur primaire (unit, integration, ui)

    selon leur nature et leur emplacement, tout en respectant les marqueurs explicites.
    """
    unit_marker = pytest.mark.unit
    integration_marker = pytest.mark.integration
    ui_marker = pytest.mark.ui

    integration_specific_paths = {
        "tests/test_dag_audio_tts_step.py",
        "tests/test_tts_service.py",
        "tests/services/test_card_model_io.py",
        "tests/services/test_markdown_integration.py",
        "tests/services/test_persona_versioning.py",
        "tests/services/test_profile_content_transfer.py",
        "tests/services/test_profile_manager.py",
        "tests/services/test_reindex_service.py",
        "tests/services/test_settings_service.py",
        "tests/services/ai/test_ai_manager.py",
        "tests/services/ai/test_consultant_360_tools.py",
        "tests/services/ai/test_consultant_loop.py",
        "tests/services/ai/test_consultant_note_types.py",
        "tests/services/ai/test_dag_orchestrator.py",
        "tests/services/ai/test_dedicated_mcp_agents.py",
        "tests/services/ai/test_ia_consolidation.py",
        "tests/services/ai/test_mcp_doc_tools.py",
        "tests/services/ai/test_mcp_server_agents.py",
        "tests/services/ai/test_pricing_service.py",
        "tests/services/ai/test_vision_categories.py",
        "tests/services/rag/test_hybrid_retriever.py",
        "tests/services/rag/test_vector_manager.py",
        "tests/services/rag/test_vector_manager_cache.py",
        "tests/services/rag/test_visual_rag_service.py",
    }

    for item in items:
        existing_markers = {m.name for m in item.iter_markers()}
        has_primary = bool(existing_markers & {"unit", "integration", "ui"})

        if not has_primary:
            rel_path = os.path.relpath(str(item.fspath), str(config.rootdir)).replace("\\", "/")
            if "qtbot" in item.fixturenames or rel_path.startswith("tests/ui/") or "widget" in rel_path:
                item.add_marker(ui_marker)
            elif (
                rel_path.startswith("tests/database/")
                or rel_path.startswith("tests/repositories/")
                or rel_path.startswith("tests/services/workers/")
                or rel_path.startswith("tests/services/cards/")
                or rel_path.startswith("tests/services/audit/")
                or rel_path in integration_specific_paths
            ):
                item.add_marker(integration_marker)
            else:
                item.add_marker(unit_marker)


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

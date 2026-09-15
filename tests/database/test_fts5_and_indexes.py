"""Tests pour SQLite FTS5 plein-texte et l'optimisation des index B-Tree."""

import json
from unittest.mock import patch

from peewee import SqliteDatabase
from PySide6.QtCore import Qt

from ankiforge.database.models import (
    DeckModel,
    NoteTypeModel,
    db,
)
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.services.search.fts_service import (
    FTSService,
    clean_html,
    extract_fields_text,
    extract_tags_text,
    sanitize_fts5_query,
)
from ankiforge.ui.widgets.omnibox import Omnibox


def test_sanitize_fts5_query():
    """Vérifie la robustesse du sanitizer de requêtes FTS5 contre les erreurs de syntaxe."""
    # Requêtes standards avec as_prefix=True
    assert sanitize_fts5_query("mitochondrie cellule", as_prefix=True) == '"mitochondrie" "cellule"*'
    assert sanitize_fts5_query("mitochondrie", as_prefix=True) == '"mitochondrie"*'
    assert sanitize_fts5_query("mitochondrie", as_prefix=False) == '"mitochondrie"'

    # Caractères réservés FTS5
    assert sanitize_fts5_query("c++ (langage) : test*", as_prefix=True) == '"c++" "langage" "test"*'
    assert sanitize_fts5_query('not "or" and', as_prefix=True) == '"not" "or" "and"*'
    assert sanitize_fts5_query('::: *** () ""', as_prefix=True) == ""
    assert sanitize_fts5_query("   ", as_prefix=True) == ""


def test_clean_html_and_extractors():
    """Vérifie le stripping HTML et l'extraction de texte brut."""
    raw_html = "<p>Bonjour <b>le monde</b> &amp; les amis&nbsp;!</p>"
    assert clean_html(raw_html) == "Bonjour le monde & les amis !"

    json_dict = json.dumps({"Front": "<h1>La photosynthèse</h1>", "Back": "<p>Processus biochimique</p>"})
    assert extract_fields_text(json_dict) == "La photosynthèse Processus biochimique"

    json_list = json.dumps(["<h1>Titre</h1>", "<p>Contenu</p>"])
    assert extract_fields_text(json_list) == "Titre Contenu"

    # Extraction des tags
    assert extract_tags_text('["bio", "cellule"]') == "bio cellule"
    assert extract_tags_text("bio cellule") == "bio cellule"
    assert extract_tags_text(["bio", "cellule"]) == "bio cellule"


def test_fts_service_availability(mock_db: SqliteDatabase):
    """Vérifie que FTSService détecte correctement la disponibilité de note_fts."""
    assert FTSService.is_available() is True


def test_fts_sync_note_and_search_diacritics(mock_db: SqliteDatabase):
    """Vérifie l'insensibilité aux accents (remove_diacritics 2) dans note_fts."""
    deck = DeckModel.create(name="Biologie")
    nt = NoteTypeModel.create(name="Basic Bio", fields_schema="[]", templates="[]", css_style="")

    repo = NoteRepository()
    note = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "<b>Mémoire</b> à long terme", "Back": "Stockage permanent des données"},
        tags=["neuroscience", "cognition"],
    )

    # 1. Recherche sans accent trouve la note avec accent
    results_no_accent = FTSService.search("memoire")
    assert len(results_no_accent) == 1
    assert results_no_accent[0].note_id == note.id
    assert results_no_accent[0].deck_id == deck.id

    # 2. Recherche avec accent trouve la note
    results_with_accent = FTSService.search("mémoire")
    assert len(results_with_accent) == 1
    assert results_with_accent[0].note_id == note.id

    # 3. Recherche sur tag
    results_tag = FTSService.search("neuroscience")
    assert len(results_tag) == 1
    assert results_tag[0].note_id == note.id


def test_fts_prefix_and_bm25_ranking(mock_db: SqliteDatabase):
    """Vérifie la recherche par préfixe et le classement BM25."""
    deck = DeckModel.create(name="Informatique")
    nt = NoteTypeModel.create(name="Basic Dev", fields_schema="[]", templates="[]", css_style="")
    repo = NoteRepository()

    # Note 1 : mentionne python une seule fois
    note1 = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Python", "Back": "Langage de programmation"},
    )

    # Note 2 : mentionne python plusieurs fois (pertinence BM25 supérieure)
    note2 = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Python Python", "Back": "Python est le langage par excellence pour l'IA et Python scripts"},
    )

    # Recherche par préfixe "pyth"
    results = FTSService.search("pyth")
    assert len(results) == 2
    # La note 2 ayant une plus forte densité de terme doit être classée en premier (rank plus négatif)
    assert results[0].note_id == note2.id
    assert results[1].note_id == note1.id
    assert results[0].rank < results[1].rank


def test_fts_snippet_generation(mock_db: SqliteDatabase):
    """Vérifie la génération d'extraits surlignés avec balises <b>."""
    deck = DeckModel.create(name="Sciences")
    nt = NoteTypeModel.create(name="Basic Sci", fields_schema="[]", templates="[]", css_style="")
    repo = NoteRepository()

    note = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Mitochondrie", "Back": "Organite responsable de la respiration cellulaire"},
    )

    results = FTSService.search("respiration")
    assert len(results) == 1
    assert results[0].note_id == note.id
    assert "<b>respiration</b>" in results[0].snippet


def test_fts_crud_lifecycle_sync(mock_db: SqliteDatabase):
    """Vérifie la synchronisation FTS5 automatique lors des opérations CRUD."""
    deck = DeckModel.create(name="Histoire")
    nt = NoteTypeModel.create(name="Basic Hist", fields_schema="[]", templates="[]", css_style="")
    repo = NoteRepository()

    # 1. Create
    note = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Napoléon", "Back": "Empereur des Français"},
        tags=["france"],
    )
    assert len(FTSService.search("napoleon")) == 1

    # 2. Update content
    repo.update_note_content(
        note_id=note.id,
        fields_data={"Front": "Bonaparte", "Back": "Premier Consul"},
    )
    # L'ancien contenu ne doit plus matcher
    assert len(FTSService.search("empereur")) == 0
    # Le nouveau contenu doit matcher
    assert len(FTSService.search("bonaparte")) == 1

    # 3. Update tags
    repo.update_note_tags(note.id, ["empire", "corse"])
    assert len(FTSService.search("corse")) == 1

    # 4. Delete
    repo.delete_note(note.id)
    assert len(FTSService.search("bonaparte")) == 0


def test_note_repository_search_with_fts_and_filters(mock_db: SqliteDatabase):
    """Vérifie que NoteRepository.search_notes combine FTS5 avec les filtres flag et is:suspended."""
    deck = DeckModel.create(name="Physique")
    nt = NoteTypeModel.create(name="Basic Phy", fields_schema="[]", templates="[]", css_style="")
    repo = NoteRepository()

    note1 = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Thermodynamique", "Back": "Premier principe de Carnot"},
    )
    repo.set_note_flag(note1.id, 1)  # Red flag

    note2 = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Thermodynamique", "Back": "Second principe de Clausius"},
    )
    repo.set_note_flag(note2.id, 2)  # Orange flag
    repo.suspend_note(note2.id, True)

    # Recherche FTS combinée avec flag:red
    res_flag = repo.search_notes("thermodynamique flag:red")
    assert len(res_flag) == 1
    assert res_flag[0].id == note1.id

    # Recherche FTS combinée avec is:suspended
    res_susp = repo.search_notes("thermodynamique is:suspended")
    assert len(res_susp) == 1
    assert res_susp[0].id == note2.id

    # Recherche purement textuelle
    res_all = repo.search_notes("thermodynamique")
    assert len(res_all) == 2


def test_note_repository_search_fallback_when_fts_unavailable(mock_db: SqliteDatabase):
    """Vérifie le repli gracieux vers LIKE si FTS5 n'est pas disponible."""
    deck = DeckModel.create(name="Chimie")
    nt = NoteTypeModel.create(name="Basic Chim", fields_schema="[]", templates="[]", css_style="")
    repo = NoteRepository()

    note = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Atome", "Back": "Structure électronique"},
    )

    with patch.object(FTSService, "is_available", return_value=False):
        results = repo.search_notes("Atome")
        assert len(results) == 1
        assert results[0].id == note.id


def test_fts_rebuild(mock_db: SqliteDatabase):
    """Vérifie la réindexation complète via rebuild_fts."""
    deck = DeckModel.create(name="Maths")
    nt = NoteTypeModel.create(name="Basic Math", fields_schema="[]", templates="[]", css_style="")
    repo = NoteRepository()

    note = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Intégrale", "Back": "Calcul infinitésimal"},
    )

    # Vider manuellement la table FTS
    db.execute_sql("DELETE FROM note_fts;")
    assert len(FTSService.search("integrale")) == 0

    # Reconstruire l'index
    indexed_count = FTSService.rebuild_fts()
    assert indexed_count >= 1
    results = FTSService.search("integrale")
    assert len(results) == 1
    assert results[0].note_id == note.id


def test_omnibox_fts_search(qtbot, mock_db: SqliteDatabase):
    """Vérifie que l'Omnibox utilise FTS5 sans requêtes N+1."""
    deck = DeckModel.create(name="Littérature")
    nt = NoteTypeModel.create(name="Basic Lit", fields_schema="[]", templates="[]", css_style="")
    repo = NoteRepository()

    note = repo.create_note(
        note_type=nt,
        deck=deck,
        fields_data={"Front": "Victor Hugo", "Back": "Les Misérables"},
    )

    omnibox = Omnibox()
    qtbot.addWidget(omnibox)

    omnibox.search_bar.setText("victor")
    omnibox.perform_search()

    assert omnibox.results_list.count() >= 1
    item = omnibox.results_list.item(0)
    assert "[Carte]" in item.text()
    assert "Victor" in item.text() or "Hugo" in item.text()
    user_data = item.data(Qt.ItemDataRole.UserRole)
    assert user_data is not None
    assert user_data["id"] == note.id


def test_migration_030_and_perf_indexes(mock_db: SqliteDatabase):
    """Vérifie l'exécution de la migration 030, la présence des index et le rollback."""
    import importlib

    from peewee_migrate import Migrator

    mig_module = importlib.import_module("ankiforge.database.migrations.030_fts5_and_perf_indexes")
    migrator = Migrator(mock_db)

    # Exécution de migrate
    mig_module.migrate(migrator, mock_db, fake=False)

    # Vérifier la présence des index B-Tree
    cursor = mock_db.execute_sql("SELECT name FROM sqlite_master WHERE type='index';")
    indexes = {row[0] for row in cursor.fetchall()}
    assert "idx_note_chunk_link_chunk" in indexes
    assert "idx_card_deck_suspended" in indexes
    assert "idx_card_flags" in indexes
    assert "idx_audit_note_rule" in indexes

    # Vérifier la présence de la table virtuelle note_fts
    cursor = mock_db.execute_sql("SELECT name FROM sqlite_master WHERE type='table' AND name='note_fts';")
    assert cursor.fetchone() is not None

    # Test du rollback
    mig_module.rollback(migrator, mock_db, fake=False)
    cursor = mock_db.execute_sql("SELECT name FROM sqlite_master WHERE type='index';")
    indexes_after = {row[0] for row in cursor.fetchall()}
    assert "idx_note_chunk_link_chunk" not in indexes_after

    # Ré-appliquer pour laisser la base propre
    mig_module.migrate(migrator, mock_db, fake=False)

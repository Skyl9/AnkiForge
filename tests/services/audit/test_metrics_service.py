"""
Tests unitaires pour MetricsService (calcul des KPIs, agrégation 7 jours et diagnostics).
"""

from datetime import datetime, timedelta
import pytest
from ankiforge.database.models import (
    AuditRecordModel,
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    FolderModel,
    LinterRuleModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    TokenUsageModel,
    db,
)
from ankiforge.services.audit.metrics_service import MetricsService


@pytest.fixture(autouse=True)
def setup_test_db():
    models = [
        FolderModel,
        MediaModel,
        NoteModel,
        CardModel,
        DeckModel,
        NoteTypeModel,
        NoteVersionModel,
        DocumentModel,
        DocumentChunkModel,
        NoteChunkLinkModel,
        TokenUsageModel,
        LinterRuleModel,
        AuditRecordModel,
    ]
    db.bind(models)
    db.create_tables(models)
    yield
    db.drop_tables(models)


def test_wozniak_health_score_empty_db():
    res = MetricsService.get_wozniak_health_score()
    assert res["score"] == 100
    assert res["total_notes"] == 0
    assert res["issues_count"] == 0


def test_wozniak_health_score_with_issues():
    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basic", fields_schema=["Front", "Back"])
    n1 = NoteModel.create(deck=deck, note_type=nt, fields={"Front": "Q1", "Back": "A1"})
    v1 = NoteVersionModel.create(note=n1, version_number=1, fields={"Front": "Q1", "Back": "A1"})
    n2 = NoteModel.create(deck=deck, note_type=nt, fields={"Front": "Q2", "Back": "A2"})
    _v2 = NoteVersionModel.create(note=n2, version_number=1, fields={"Front": "Q2", "Back": "A2"})

    # Ajouter une violation sur n1
    AuditRecordModel.create(
        note=n1,
        note_version=v1,
        is_compliant=False,
        rule_broken="Atomicité",
        reason="La note contient plusieurs concepts.",
    )

    res = MetricsService.get_wozniak_health_score()
    assert res["total_notes"] == 2
    assert res["issues_count"] == 1
    assert res["compliant_count"] == 1
    assert res["score"] == 50


def test_smart_coverage_rate():
    doc = DocumentModel.create(title="Doc 1", file_type="pdf")
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, content="Chunk 1", content_hash="h1")
    _c2 = DocumentChunkModel.create(document=doc, chunk_index=1, content="Chunk 2", content_hash="h2")

    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basic", fields_schema=["Front", "Back"])
    note = NoteModel.create(deck=deck, note_type=nt)

    # Lier c1 à note
    NoteChunkLinkModel.create(note=note, chunk=c1)

    res = MetricsService.get_smart_coverage_rate()
    assert res["total_chunks"] == 2
    assert res["linked_chunks"] == 1
    assert res["unlinked_chunks"] == 1
    assert res["coverage"] == 50


def test_ai_telemetry():
    TokenUsageModel.create(
        provider="openai",
        model_id="gpt-4o",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        estimated_cost_usd=0.05,
    )
    TokenUsageModel.create(
        provider="anthropic",
        model_id="claude-3-5",
        prompt_tokens=200,
        completion_tokens=100,
        total_tokens=300,
        estimated_cost_usd=0.15,
    )

    res = MetricsService.get_ai_telemetry()
    assert res["calls_count"] == 2
    assert res["total_tokens"] == 450
    assert abs(res["total_cost_usd"] - 0.20) < 0.001


def test_7_days_activity():
    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basic", fields_schema=["Front", "Back"])
    note = NoteModel.create(deck=deck, note_type=nt, fields={"Front": "Q", "Back": "A"})

    now = datetime.now()
    # Création aujourd'hui (version 1)
    NoteVersionModel.create(
        note=note,
        version_number=1,
        fields={"Front": "Q"},
        source="manual",
        created_at=now,
    )
    # Modification hier (version 2)
    yesterday = now - timedelta(days=1)
    NoteVersionModel.create(
        note=note,
        version_number=2,
        fields={"Front": "Q edited"},
        source="manual",
        created_at=yesterday,
    )

    activity = MetricsService.get_7_days_activity()
    assert len(activity) == 7
    # Aujourd'hui est le dernier élément
    today_act = activity[-1]
    assert today_act["created"] >= 1
    # Hier est l'avant-dernier élément
    yesterday_act = activity[-2]
    assert yesterday_act["modified"] >= 1


def test_proactive_diagnostics_and_full_data():
    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basic", fields_schema=["Front", "Back"])
    n = NoteModel.create(deck=deck, note_type=nt, fields={"Front": "Q", "Back": "A"})
    v = NoteVersionModel.create(note=n, version_number=1, fields={"Front": "Q", "Back": "A"})

    AuditRecordModel.create(
        note=n,
        note_version=v,
        is_compliant=False,
        rule_broken="Atomicité",
        reason="Violation d'atomicité",
    )

    diagnostics = MetricsService.get_proactive_diagnostics()
    assert len(diagnostics) >= 1
    assert diagnostics[0]["type"] == "wozniak"
    assert diagnostics[0]["target_view"] == "analysis"
    assert diagnostics[0]["target_tab"] == "audit"

    full_data = MetricsService.get_full_dashboard_data()
    assert "kpis" in full_data
    assert "activity_7_days" in full_data
    assert "diagnostics" in full_data
    assert "recent_feed" in full_data
    assert "macro_activities" in full_data


def test_recent_macro_actions():
    deck = DeckModel.create(name="Médecine")
    nt = NoteTypeModel.create(name="Basic", fields_schema=["Front", "Back"])
    n1 = NoteModel.create(guid="guid-1", note_type=nt)
    CardModel.create(note=n1, deck=deck, ord=0)
    n2 = NoteModel.create(guid="guid-2", note_type=nt)
    CardModel.create(note=n2, deck=deck, ord=0)

    now = datetime.now()
    NoteVersionModel.create(note=n1, version_number=1, fields={"Front": "Q1"}, source="ai_generator", created_at=now)
    NoteVersionModel.create(note=n2, version_number=1, fields={"Front": "Q2"}, source="ai_generator", created_at=now)

    macros = MetricsService.get_recent_macro_actions(limit=5)
    assert len(macros) >= 1
    assert macros[0]["source"] == "ai_generator"
    assert macros[0]["count"] == 2
    assert "Génération IA" in macros[0]["title"]
    assert "Médecine" in macros[0]["subtitle"]

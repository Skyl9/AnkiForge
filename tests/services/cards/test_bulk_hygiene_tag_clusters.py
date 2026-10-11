from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel
from ankiforge.services.cards.bulk_hygiene_service import (
    BulkHygieneService,
    TagClustersReport,
    TagMergePlan,
    TagMergeResult,
)
from ankiforge.utils.tags import parse_note_tags


@pytest.fixture
def tag_hygiene_setup(mock_db):
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(
        name=f"Model_{uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    return {"deck": deck, "nt": nt}


def test_analyze_tag_clusters_case_grouping(tag_hygiene_setup):
    """Vérifie le regroupement strict insensible à la casse et l'élection de la forme la plus fréquente."""
    nt = tag_hygiene_setup["nt"]

    # 3 notes : anatomie apparaît 2 fois, Anatomie 1 fois, ANATOMIE 1 fois
    NoteModel.create(note_type=nt, tags='["anatomie", "physiologie"]')
    NoteModel.create(note_type=nt, tags='["anatomie", "vocabulaire"]')
    NoteModel.create(note_type=nt, tags='["Anatomie"]')
    NoteModel.create(note_type=nt, tags='["ANATOMIE"]')

    report = BulkHygieneService.analyze_tag_clusters(include_levenshtein=False)
    assert isinstance(report, TagClustersReport)
    assert len(report.case_clusters) == 1
    assert len(report.levenshtein_clusters) == 0

    cluster = report.case_clusters[0]
    assert cluster.cluster_type == "case"
    assert cluster.canonical_tag == "anatomie"  # La plus fréquente (2 occurrences)
    assert len(cluster.tags) == 3
    tag_names = {t.tag for t in cluster.tags}
    assert tag_names == {"anatomie", "Anatomie", "ANATOMIE"}
    assert cluster.total_notes_count == 4


def test_analyze_tag_clusters_levenshtein_thresholds(tag_hygiene_setup):
    """Vérifie le clustering Levenshtein, les seuils de longueur et l'exclusion des mots <= 3 caractères."""
    nt = tag_hygiene_setup["nt"]

    # Mots longs (len >= 8) : distance <= 2 autorisée
    NoteModel.create(note_type=nt, tags='["pharmacologie"]')
    NoteModel.create(note_type=nt, tags='["pharmacologie"]')
    NoteModel.create(note_type=nt, tags='["pharmacologies"]')  # distance 1
    NoteModel.create(note_type=nt, tags='["pharmacologiet"]')  # distance 1

    # Mots courts (len <= 3) : doivent être strictement ignorés même si distance == 1
    NoteModel.create(note_type=nt, tags='["dna"]')
    NoteModel.create(note_type=nt, tags='["rna"]')

    # Mots de longueur 4 à 7 : distance <= 1
    NoteModel.create(note_type=nt, tags='["nerf"]')
    NoteModel.create(note_type=nt, tags='["nerfs"]')

    report = BulkHygieneService.analyze_tag_clusters(include_levenshtein=True)
    assert len(report.case_clusters) == 0
    assert len(report.levenshtein_clusters) >= 2

    # Cluster pharmacologie
    pharma_cluster = next((c for c in report.levenshtein_clusters if c.canonical_tag == "pharmacologie"), None)
    assert pharma_cluster is not None
    pharma_tags = {t.tag for t in pharma_cluster.tags}
    assert "pharmacologie" in pharma_tags
    assert "pharmacologies" in pharma_tags

    # Cluster nerf
    nerf_cluster = next((c for c in report.levenshtein_clusters if c.canonical_tag == "nerf"), None)
    assert nerf_cluster is not None
    nerf_tags = {t.tag for t in nerf_cluster.tags}
    assert nerf_tags == {"nerf", "nerfs"}

    # Vérification que dna et rna ne forment AUCUN cluster
    dna_cluster = next((c for c in report.levenshtein_clusters if "dna" in [t.tag for t in c.tags]), None)
    assert dna_cluster is None


def test_analyze_tag_clusters_excludes_provenance_and_system_tags(tag_hygiene_setup):
    """Vérifie que les tags de provenance documentaire et ankiforge_generated sont exclus de toute analyse."""
    nt = tag_hygiene_setup["nt"]

    NoteModel.create(
        note_type=nt,
        tags='["doc:1", "source:cours_anatomie", "section:coeur", "page:10", "chunk:42", "ankiforge_generated", "Biologie"]',
    )
    NoteModel.create(
        note_type=nt,
        tags='["doc:2", "source:cours_anatomie_v2", "section:coeur", "page:11", "ankiforge_generated", "biologie"]',
    )

    report = BulkHygieneService.analyze_tag_clusters(include_levenshtein=True)
    assert len(report.case_clusters) == 1
    cluster = report.case_clusters[0]
    assert {t.tag for t in cluster.tags} == {"Biologie", "biologie"}

    # Aucun tag doc, source, section, page, chunk ou ankiforge_generated
    all_cluster_tags = [t.tag for c in report.case_clusters + report.levenshtein_clusters for t in c.tags]
    for tag in all_cluster_tags:
        assert not tag.startswith(("doc:", "source:", "section:", "page:", "chunk:"))
        assert tag != "ankiforge_generated"


def test_analyze_tag_clusters_scope_restriction(tag_hygiene_setup):
    """Vérifie la restriction de l'analyse à un sous-ensemble d'identifiants de notes."""
    nt = tag_hygiene_setup["nt"]

    n1 = NoteModel.create(note_type=nt, tags='["Cardiologie"]')
    n2 = NoteModel.create(note_type=nt, tags='["cardiologie"]')
    _ = NoteModel.create(note_type=nt, tags='["Neurologie"]')
    _ = NoteModel.create(note_type=nt, tags='["neurologie"]')

    # Restriction aux notes 1 et 2 uniquement

    report = BulkHygieneService.analyze_tag_clusters(note_ids=[n1.id, n2.id], include_levenshtein=False)
    assert len(report.case_clusters) == 1
    assert report.case_clusters[0].canonical_tag.lower() == "cardiologie"
    assert report.inspected_notes_count == 2


def test_apply_tag_merges_atomic(tag_hygiene_setup):
    """Vérifie la fusion atomique de tags avec déduplication et préservation de la provenance."""
    nt = tag_hygiene_setup["nt"]

    # Note 1 : porte Anatomie et doc:1
    n1 = NoteModel.create(note_type=nt, tags='["Anatomie", "doc:1", "examen"]')
    # Note 2 : porte déjà Anatomie ET anatomie (doit être dédupliquée vers anatomie)
    n2 = NoteModel.create(note_type=nt, tags='["Anatomie", "anatomie", "source:cours"]')
    # Note 3 : porte seulement anatomie (ne doit pas être modifiée)
    n3 = NoteModel.create(note_type=nt, tags='["anatomie"]')

    plan = TagMergePlan(
        tags_to_merge=["Anatomie", "ANATOMIE"],
        target_tag="anatomie",
    )

    result = BulkHygieneService.apply_tag_merges([plan])
    assert isinstance(result, TagMergeResult)
    assert result.success is True
    assert result.merged_clusters_count == 1
    assert result.modified_notes_count == 2
    assert set(result.modified_note_ids) == {n1.id, n2.id}

    # Relecture des notes
    n1_refreshed = NoteModel.get_by_id(n1.id)
    n2_refreshed = NoteModel.get_by_id(n2.id)
    n3_refreshed = NoteModel.get_by_id(n3.id)

    # Note 1 : Anatomie est devenue anatomie, doc:1 et examen préservés
    tags_1 = parse_note_tags(n1_refreshed.tags)
    assert "anatomie" in tags_1
    assert "Anatomie" not in tags_1
    assert "doc:1" in tags_1
    assert "examen" in tags_1

    # Note 2 : déduplication stricte vers un seul tag 'anatomie'
    tags_2 = parse_note_tags(n2_refreshed.tags)
    assert tags_2.count("anatomie") == 1
    assert "source:cours" in tags_2

    # Note 3 : inchangée
    tags_3 = parse_note_tags(n3_refreshed.tags)
    assert tags_3 == ["anatomie"]


def test_analyze_and_apply_tag_merges_with_deck_filter(mock_db):
    """Vérifie le filtrage par paquet racine et l'inclusion des sous-paquets hiérarchiques."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Model_Deck_{uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )

    deck_parent = DeckModel.create(name=f"Medecine_{uid}")
    deck_child = DeckModel.create(name=f"Medecine_{uid}::Cardio")
    deck_other = DeckModel.create(name=f"Histoire_{uid}")

    n1 = NoteModel.create(note_type=nt, tags='["cardiologie"]')
    CardModel.create(note=n1, deck=deck_parent, ord=0)

    n2 = NoteModel.create(note_type=nt, tags='["Cardiologie"]')
    CardModel.create(note=n2, deck=deck_child, ord=0)

    n3 = NoteModel.create(note_type=nt, tags='["Cardiologie", "histoire"]')
    CardModel.create(note=n3, deck=deck_other, ord=0)

    # 1. Analyse restreinte au paquet parent (doit inclure deck_parent et deck_child)
    report_med = BulkHygieneService.analyze_tag_clusters(deck_id=deck_parent.id, include_levenshtein=False)
    assert len(report_med.case_clusters) == 1
    cluster_med = report_med.case_clusters[0]
    assert cluster_med.canonical_tag == "cardiologie"
    assert cluster_med.total_notes_count == 2  # n1 et n2, n3 exclu !

    # 2. Analyse restreinte au paquet autre
    report_other = BulkHygieneService.analyze_tag_clusters(deck_id=deck_other.id, include_levenshtein=False)
    assert len(report_other.case_clusters) == 0  # Seulement 1 note avec ce tag dans ce paquet

    # 3. Application de la fusion restreinte au paquet parent
    plan = TagMergePlan(tags_to_merge=["Cardiologie"], target_tag="cardiologie")
    res = BulkHygieneService.apply_tag_merges([plan], deck_id=deck_parent.id)
    assert res.success is True
    assert res.modified_notes_count == 1
    assert res.modified_note_ids == [n2.id]

    # Vérification : n2 a été fusionné, n3 dans deck_other n'a pas été touché
    n2_ref = NoteModel.get_by_id(n2.id)
    n3_ref = NoteModel.get_by_id(n3.id)
    assert parse_note_tags(n2_ref.tags) == ["cardiologie"]
    assert "Cardiologie" in parse_note_tags(n3_ref.tags)

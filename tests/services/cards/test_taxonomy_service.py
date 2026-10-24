"""Tests d'intégration pour TaxonomyService (renommage hiérarchique, suppression, audit et réparations).

Conforme à l'ADR 0040 et au ticket Taxonomie et Normalisation.
"""

from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel
from ankiforge.services.cards.taxonomy_service import (
    TaxonomyAuditReport,
    TaxonomyRepairAction,
    TaxonomyService,
)
from ankiforge.utils.tags import parse_note_tags

pytestmark = pytest.mark.integration


@pytest.fixture
def taxo_setup(mock_db):
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_{uid}")
    nt = NoteTypeModel.create(
        name=f"Model_{uid}",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    return {"deck": deck, "nt": nt}


def test_rename_tag_with_subtag_propagation(taxo_setup) -> None:
    """Vérifie le renommage d'un tag avec propagation à toute la descendance ::."""
    nt = taxo_setup["nt"]
    n1 = NoteModel.create(note_type=nt, tags='["medecine", "urgent"]')
    n2 = NoteModel.create(note_type=nt, tags='["medecine::anatomie", "exam"]')
    n3 = NoteModel.create(note_type=nt, tags='["medecine::anatomie::coeur"]')
    n4 = NoteModel.create(note_type=nt, tags='["autre_matiere"]')

    result = TaxonomyService.rename_tag(
        old_tag="medecine",
        new_tag="sante",
        propagate_subtags=True,
    )

    assert result.success is True
    assert result.modified_notes_count == 3
    assert set(result.modified_note_ids) == {n1.id, n2.id, n3.id}

    n1 = NoteModel.get_by_id(n1.id)
    n2 = NoteModel.get_by_id(n2.id)
    n3 = NoteModel.get_by_id(n3.id)
    n4 = NoteModel.get_by_id(n4.id)

    assert parse_note_tags(n1.tags) == ["sante", "urgent"]
    assert parse_note_tags(n2.tags) == ["sante::anatomie", "exam"]
    assert parse_note_tags(n3.tags) == ["sante::anatomie::coeur"]
    assert parse_note_tags(n4.tags) == ["autre_matiere"]


def test_rename_tag_without_subtag_propagation(taxo_setup) -> None:
    """Vérifie le renommage strict d'un nœud sans propager aux sous-tags."""
    nt = taxo_setup["nt"]
    n1 = NoteModel.create(note_type=nt, tags='["medecine"]')
    n2 = NoteModel.create(note_type=nt, tags='["medecine::anatomie"]')

    result = TaxonomyService.rename_tag(
        old_tag="medecine",
        new_tag="sante",
        propagate_subtags=False,
    )

    assert result.success is True
    assert result.modified_notes_count == 1
    assert result.modified_note_ids == [n1.id]

    n1 = NoteModel.get_by_id(n1.id)
    n2 = NoteModel.get_by_id(n2.id)
    assert parse_note_tags(n1.tags) == ["sante"]
    assert parse_note_tags(n2.tags) == ["medecine::anatomie"]


def test_delete_tag_globally(taxo_setup) -> None:
    """Vérifie la suppression d'un tag dans toute la collection."""
    nt = taxo_setup["nt"]
    n1 = NoteModel.create(note_type=nt, tags='["chimie", "brouillon"]')
    n2 = NoteModel.create(note_type=nt, tags='["brouillon", "maths"]')
    n3 = NoteModel.create(note_type=nt, tags='["maths"]')

    result = TaxonomyService.delete_tag("brouillon")
    assert result.success is True
    assert result.modified_notes_count == 2
    assert set(result.modified_note_ids) == {n1.id, n2.id}

    n1 = NoteModel.get_by_id(n1.id)
    n2 = NoteModel.get_by_id(n2.id)
    n3 = NoteModel.get_by_id(n3.id)
    assert parse_note_tags(n1.tags) == ["chimie"]
    assert parse_note_tags(n2.tags) == ["maths"]
    assert parse_note_tags(n3.tags) == ["maths"]


def test_provenance_tag_safety_guard(taxo_setup) -> None:
    """Vérifie que la modification ou suppression d'un tag de provenance est bloquée sans confirmation explicite."""
    nt = taxo_setup["nt"]
    n1 = NoteModel.create(note_type=nt, tags='["doc:42", "source:manuel"]')

    # Renommage refusé sans allow_provenance
    res_rename = TaxonomyService.rename_tag("doc:42", "doc:99", allow_provenance=False)
    assert res_rename.success is False
    assert "provenance" in res_rename.error_message.lower()

    # Suppression refusée sans allow_provenance
    res_delete = TaxonomyService.delete_tag("doc:42", allow_provenance=False)
    assert res_delete.success is False
    assert "provenance" in res_delete.error_message.lower()

    # Avec allow_provenance=True, l'opération réussit
    res_delete_confirmed = TaxonomyService.delete_tag("doc:42", allow_provenance=True)
    assert res_delete_confirmed.success is True
    n1 = NoteModel.get_by_id(n1.id)
    assert parse_note_tags(n1.tags) == ["source:manuel"]


def test_audit_taxonomy_and_repairs(taxo_setup) -> None:
    """Vérifie la détection d'anomalies (espaces, segments vides) et leur réparation assistée."""
    nt = taxo_setup["nt"]
    n1 = NoteModel.create(note_type=nt, tags='["medecine generale", "valide"]')
    n2 = NoteModel.create(note_type=nt, tags='["::physique::"]')

    report = TaxonomyService.audit_taxonomy()
    assert isinstance(report, TaxonomyAuditReport)
    assert report.total_anomalies_count >= 2

    # Préparer les réparations :
    # 1. Remplacer 'medecine generale' par conversion en underscore 'medecine_generale'
    # 2. Nettoyer '::physique::' en 'physique'
    repairs = [
        TaxonomyRepairAction(
            old_tag="medecine generale",
            repair_mode="replace",
            target_tag="medecine_generale",
        ),
        TaxonomyRepairAction(
            old_tag="::physique::",
            repair_mode="replace",
            target_tag="physique",
        ),
    ]

    res_repair = TaxonomyService.apply_taxonomy_repairs(repairs)
    assert res_repair.success is True
    assert res_repair.repaired_tags_count == 2

    n1 = NoteModel.get_by_id(n1.id)
    n2 = NoteModel.get_by_id(n2.id)
    assert parse_note_tags(n1.tags) == ["medecine_generale", "valide"]
    assert parse_note_tags(n2.tags) == ["physique"]


def test_rename_and_delete_tag_deck_scope_restriction(taxo_setup) -> None:
    """Vérifie que la portée deck_id restreint strictement les notes modifiées."""
    deck1 = taxo_setup["deck"]
    deck2 = DeckModel.create(name="Deck_Autre")
    nt = taxo_setup["nt"]

    n1 = NoteModel.create(note_type=nt, tags='["commun"]')
    CardModel.create(note=n1, deck=deck1, card_type=0, queue=0)

    n2 = NoteModel.create(note_type=nt, tags='["commun"]')
    CardModel.create(note=n2, deck=deck2, card_type=0, queue=0)

    # Renommer 'commun' uniquement dans deck1
    res = TaxonomyService.rename_tag("commun", "specifique", deck_id=deck1.id)
    assert res.success is True
    assert res.modified_notes_count == 1
    assert res.modified_note_ids == [n1.id]

    n1 = NoteModel.get_by_id(n1.id)
    n2 = NoteModel.get_by_id(n2.id)
    assert parse_note_tags(n1.tags) == ["specifique"]
    assert parse_note_tags(n2.tags) == ["commun"]


def test_taxonomy_service_empty_collection(mock_db) -> None:
    """Vérifie que les opérations de taxonomie s'exécutent gracieusement sur une base vide."""
    # Renommer un tag sur une collection vide
    res_rename = TaxonomyService.rename_tag("introuvable", "cible")
    assert res_rename.success is True
    assert res_rename.modified_notes_count == 0

    # Supprimer un tag sur une collection vide
    res_delete = TaxonomyService.delete_tag("introuvable")
    assert res_delete.success is True
    assert res_delete.modified_notes_count == 0

    # Audit sur une collection vide
    report = TaxonomyService.audit_taxonomy()
    assert report.total_anomalies_count == 0
    assert report.total_notes_impacted == 0

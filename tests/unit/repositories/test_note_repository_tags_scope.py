"""Tests d'extraction et de portée des tags sur NoteRepository.

Vérifie l'extraction exhaustive sans troncation, le respect de la hiérarchie des paquets
et le support de tous les formats de tags (JSON et délimités par espaces).
"""

from __future__ import annotations

import json
import uuid

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
)
from ankiforge.repositories.note_repository import NoteRepository

pytestmark = pytest.mark.integration


def test_get_tags_for_scope_empty_database() -> None:
    repo = NoteRepository()
    assert repo.get_tags_for_scope(deck_id=None) == []
    assert repo.get_tags_for_scope(deck_id=999999) == []


def test_get_tags_for_scope_all_collection_no_truncation() -> None:
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"ModelScopeAll_{uid}", fields_schema='["Front", "Back"]')

    # Création de 520 notes pour s'assurer de dépasser le seuil historique de 500
    notes_data = []
    for i in range(520):
        notes_data.append(
            {
                "note_type": nt,
                "tags": json.dumps([f"tag_batch_{i // 100}", f"single_tag_{i}"]),
                "status": "new",
            }
        )

    NoteModel.insert_many(notes_data).execute()

    repo = NoteRepository()
    all_tags = repo.get_tags_for_scope(deck_id=None)

    # Vérification que le tag de la 519ème note est bien présent
    assert "single_tag_519" in all_tags
    assert "single_tag_0" in all_tags
    assert len(all_tags) == 520 + 6  # 520 singles + 6 batches (0 à 5)
    assert all_tags == sorted(all_tags)


def test_get_tags_for_scope_hierarchical_decks() -> None:
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(name=f"ModelHier_{uid}", fields_schema='["Front", "Back"]')

    deck_parent = DeckModel.create(name=f"Matiere_{uid}")
    deck_child = DeckModel.create(name=f"Matiere_{uid}::Physique")
    deck_subchild = DeckModel.create(name=f"Matiere_{uid}::Physique::Quantique")
    deck_other = DeckModel.create(name=f"Histoire_{uid}")

    # Note 1 dans parent
    n1 = NoteModel.create(note_type=nt, tags='["matiere_generale"]')
    CardModel.create(note=n1, deck=deck_parent, template_index=0)

    # Note 2 dans child avec tags Anki délimités par espaces
    n2 = NoteModel.create(note_type=nt, tags="mecanique optique")
    CardModel.create(note=n2, deck=deck_child, template_index=0)

    # Note 3 dans subchild
    n3 = NoteModel.create(note_type=nt, tags='["spin", "qubit"]')
    CardModel.create(note=n3, deck=deck_subchild, template_index=0)

    # Note 4 dans un autre deck non lié
    n4 = NoteModel.create(note_type=nt, tags='["napoleon", "revolution"]')
    CardModel.create(note=n4, deck=deck_other, template_index=0)

    repo = NoteRepository()

    # Portée deck parent avec descendants : doit inclure n1, n2, n3 mais pas n4
    tags_parent = repo.get_tags_for_scope(deck_id=deck_parent.id, include_descendants=True)
    assert sorted(tags_parent) == sorted(["matiere_generale", "mecanique", "optique", "qubit", "spin"])
    assert "napoleon" not in tags_parent

    # Portée deck child avec descendants : doit inclure n2, n3
    tags_child = repo.get_tags_for_scope(deck_id=deck_child.id, include_descendants=True)
    assert sorted(tags_child) == sorted(["mecanique", "optique", "qubit", "spin"])
    assert "matiere_generale" not in tags_child

    # Portée deck parent SANS descendants : uniquement n1
    tags_parent_strict = repo.get_tags_for_scope(deck_id=deck_parent.id, include_descendants=False)
    assert tags_parent_strict == ["matiere_generale"]

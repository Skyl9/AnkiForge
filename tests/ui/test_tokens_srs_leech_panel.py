"""
Tests UI headless pour le panneau de diagnostic des cartes sangsues dans AITokensSrsTab.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.ui.components.deck_select_window import ALL_DECKS_NODE_ID
from ankiforge.ui.views.analysis_view.tabs.tokens_srs_tab import AITokensSrsTab

pytestmark = pytest.mark.ui


def test_ai_tokens_srs_tab_leech_panel(qtbot: Any) -> None:
    deck1 = DeckModel.create(name="Mathématiques")
    deck2 = DeckModel.create(name="Histoire")
    nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Recto", "Verso"]))

    # Note 1 : tagguée 'leech' dans Deck 1
    n1 = NoteModel.create(note_type=nt, tags=json.dumps(["leech"]))
    NoteVersionModel.create(
        note=n1,
        version_number=1,
        content=json.dumps({"Recto": "Dérivée de ln(x) ?", "Verso": "1/x"}),
        is_active=True,
    )
    c1 = CardModel.create(note=n1, deck=deck1, lapses=6, stability=1.0, difficulty=6.0)

    # Note 2 : fort taux d'échecs (lapses=5) SANS tag 'leech' dans Deck 2
    n2 = NoteModel.create(note_type=nt, tags=json.dumps(["dates"]))
    NoteVersionModel.create(
        note=n2,
        version_number=1,
        content=json.dumps({"Recto": "Bataille de Marignan ?", "Verso": "1515"}),
        is_active=True,
    )
    c2 = CardModel.create(note=n2, deck=deck2, lapses=5, stability=1.5, difficulty=5.5)

    tab = AITokensSrsTab()
    qtbot.addWidget(tab)

    # 1. Vérification des éléments d'interface
    assert hasattr(tab, "table_leeches")
    assert tab.table_leeches.columnCount() == 9
    assert hasattr(tab, "cb_include_high_lapses")
    assert hasattr(tab, "spn_lapse_threshold")

    # 2. Mode strict (par défaut) : seule n1/c1 est listée
    tab.refresh_stats()
    assert tab.table_leeches.rowCount() == 1
    assert str(c1.id) in tab.table_leeches.item(0, 0).text()
    assert "Mathématiques" in tab.table_leeches.item(0, 1).text()
    assert "6" in tab.table_leeches.item(0, 3).text()

    # 3. Mode dual : cocher la case inclut aussi n2/c2
    tab.cb_include_high_lapses.setChecked(True)
    assert tab.table_leeches.rowCount() == 2

    # 4. Filtrage par paquet : sélectionner Deck 2
    tab.current_deck_id = deck2.id
    tab.refresh_stats()
    assert tab.table_leeches.rowCount() == 1
    assert str(c2.id) in tab.table_leeches.item(0, 0).text()
    assert "Histoire" in tab.table_leeches.item(0, 1).text()


def test_ai_tokens_srs_tab_relays_fsrs_projection_and_normalizes_all_decks(qtbot: Any) -> None:
    """L'onglet SRS relaie la projection FSRS et normalise le nœud virtuel « Tous les paquets »."""
    deck = DeckModel.create(name="Profil")
    nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Recto", "Verso"]))
    note = NoteModel.create(note_type=nt)
    CardModel.create(note=note, deck=deck, ivl=10)

    tab = AITokensSrsTab()
    qtbot.addWidget(tab)

    tab.refresh_stats()

    # 1. La projection FSRS est relayée au widget de courbe (source d'autorité unique).
    assert tab.retention_curve._available is True
    assert len(tab.retention_curve._checkpoints) == 4
    assert [c["day"] for c in tab.retention_curve._checkpoints] == [1, 3, 7, 14]

    # 2. Le nœud racine virtuel « Tous les paquets » (-1) se traduit par l'absence de filtre.
    tab._on_deck_selected(ALL_DECKS_NODE_ID, "Tous les paquets")
    assert tab.current_deck_id is None
    assert tab.retention_curve._available is True


def test_ai_tokens_srs_tab_empty_collection_and_refresh_theme(qtbot: Any) -> None:
    """Collection vide : état vide explicite ; le thème se propage au widget de courbe."""
    tab = AITokensSrsTab()
    qtbot.addWidget(tab)

    tab.refresh_stats()
    assert tab.retention_curve._available is False

    tab.refresh_theme(MagicMock(accent_primary="#123456", color_green="#10b981", text_primary="#ffffff", text_muted="#888888"))
    assert tab.retention_curve._accent == "#123456"
    assert tab.retention_curve._target_color == "#10b981"

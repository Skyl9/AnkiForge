"""
Test de non-régression pour l'exportation Anki avec drapeaux personnalisés (Critère d'acceptation 4) :
Vérifie que même si les libellés de drapeaux sont personnalisés dans le profil actif,
la valeur entière native Anki (1..7) est fidèlement préservée dans la table cards de l'archive .apkg.
"""

from __future__ import annotations

import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest

from ankiforge.database.models import (
    DeckModel,
)
from ankiforge.repositories.note_repository import NoteRepository
from ankiforge.services.cards.export_manager import ExportManager
from ankiforge.services.cards.flag_service import FlagService

pytestmark = pytest.mark.integration


def test_export_apkg_preserves_numeric_flags_with_custom_labels() -> None:
    """La personnalisation des libellés n'altère en rien l'intégrité de la valeur entière Anki 1..7 à l'export."""
    FlagService.reset_to_defaults()
    FlagService.set_flag_labels({1: "Vocabulaire Critique", 7: "Culture Générale"})

    repo = NoteRepository()
    export_mgr = ExportManager()

    deck = DeckModel.create(name="Deck::CustomFlagsExport")
    nt = repo.create_note_type("ModelCustomExport", ["Front", "Back"], [{"name": "C1"}])
    note = repo.create_note(nt, deck, {"Front": "Question Export", "Back": "Réponse Export"})

    cards = repo.get_cards_by_note(note.id)
    assert len(cards) >= 1
    # Assigner flag 1 (personnalisé en "Vocabulaire Critique")
    repo.set_card_flag(cards[0].id, 1)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "custom_flags_export.apkg"
        exported_count = export_mgr.export_package(
            output_path=out_path,
            deck_id=deck.id,
            status_filter="all",
            include_media=False,
            sync_flags_and_suspension_tags=True,
        )
        assert exported_count == 1
        assert out_path.exists()

        with zipfile.ZipFile(out_path, "r") as zf:
            zf.extract("collection.anki2", tmpdir)

        anki_db_path = Path(tmpdir) / "collection.anki2"
        conn = sqlite3.connect(str(anki_db_path))
        cur = conn.cursor()

        # Vérification formelle du champ flags dans SQLite Anki
        cur.execute("SELECT flags FROM cards")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 1  # Valeur entière Anki 1 préservée

        conn.close()

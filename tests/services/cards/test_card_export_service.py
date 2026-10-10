"""
Tests pour CardExportService (Export des cartes en texte ou JSON pour analyse rapide).
Valide la sérialisation, les formats (JSON, JSONL, Texte, Markdown),
l'inclusion de la provenance et le golden file déterministe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.card_export_service import CardExportService

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_export_data():
    """Crée un jeu de données de test avec notes, cartes, versions et traçabilité RAG."""
    deck_bio = DeckModel.create(name="Sciences::Biologie")
    deck_math = DeckModel.create(name="Sciences::Mathématiques")

    nt_basic = NoteTypeModel.create(
        name="Basique",
        fields_schema='["Recto", "Verso"]',
        templates='[{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"}]',
    )
    nt_cloze = NoteTypeModel.create(
        name="Texte à trous",
        fields_schema='["Texte", "Remarque"]',
        templates='[{"name": "Cloze", "qfmt": "{{cloze:Texte}}", "afmt": "{{cloze:Texte}}<br>{{Remarque}}"}]',
    )

    # Document et chunk pour la provenance
    doc = DocumentModel.create(title="Biologie Cellulaire", doc_type="pdf", total_pages=50)
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=3,
        heading_path="Chapitre 1 > Mitochondrie",
        page_number=12,
        content="La mitochondrie produit l'ATP.",
    )

    # Note 1 : Avec provenance liée et tag de provenance
    note1 = NoteModel.create(
        guid="guid_note_1",
        note_type=nt_basic,
        tags='["bio", "cellule", "doc:1", "page:12", "section:mitochondrie"]',
        status="new",
    )
    NoteVersionModel.create(
        note=note1,
        content=json.dumps({"Recto": "Rôle de la mitochondrie ?", "Verso": "Production d'ATP."}),
        is_active=True,
    )
    CardModel.create(note=note1, deck=deck_bio, flags=2, is_suspended=False)

    NoteChunkLinkModel.create(
        note=note1,
        chunk=chunk,
        resolution="exact",
    )

    # Note 2 : Cloze sans lien RAG explicite mais avec tags
    note2 = NoteModel.create(
        guid="guid_note_2",
        note_type=nt_cloze,
        tags='["maths", "algebre"]',
        status="modified",
    )
    NoteVersionModel.create(
        note=note2,
        content=json.dumps({"Texte": "Le théorème de {{c1::Pythagore}} : a² + b² = c²", "Remarque": "Triangle rectangle"}),
        is_active=True,
    )
    CardModel.create(note=note2, deck=deck_math, flags=0, is_suspended=True)

    return {
        "deck_bio": deck_bio,
        "deck_math": deck_math,
        "notes": [note1, note2],
        "doc": doc,
        "chunk": chunk,
    }


def test_extract_card_export_data_structure(sample_export_data):
    """Vérifie la structure complète des données extraites pour l'export."""
    notes = sample_export_data["notes"]
    service = CardExportService()

    data = service.extract_export_data(notes, include_ids=True)
    assert len(data) == 2

    card1 = data[0]
    assert card1["id"] == notes[0].id
    assert card1["guid"] == "guid_note_1"
    assert card1["deck"] == "Sciences::Biologie"
    assert card1["model"] == "Basique"
    assert card1["status"] == "new"
    assert card1["flags"] == 2
    assert card1["is_suspended"] is False
    assert card1["fields"] == {"Recto": "Rôle de la mitochondrie ?", "Verso": "Production d'ATP."}
    assert card1["tags"] == ["bio", "cellule", "doc:1", "page:12", "section:mitochondrie"]

    # Provenance
    prov1 = card1["provenance"]
    assert "tags" in prov1
    assert "sources" in prov1
    assert "doc:1" in prov1["tags"]
    assert len(prov1["sources"]) == 1
    src = prov1["sources"][0]
    assert src["document_title"] == "Biologie Cellulaire"
    assert src["heading_path"] == "Chapitre 1 > Mitochondrie"
    assert src["page_number"] == 12
    assert src["resolution"] == "exact"

    card2 = data[1]
    assert card2["deck"] == "Sciences::Mathématiques"
    assert card2["model"] == "Texte à trous"
    assert card2["is_suspended"] is True
    assert card2["fields"]["Texte"] == "Le théorème de {{c1::Pythagore}} : a² + b² = c²"
    assert card2["provenance"]["sources"] == []


def test_extract_card_export_data_without_ids(sample_export_data):
    """Vérifie que les IDs techniques peuvent être exclus pour un export anonymisé ou testable."""
    notes = sample_export_data["notes"]
    service = CardExportService()

    data = service.extract_export_data(notes, include_ids=False)
    assert len(data) == 2
    for card in data:
        assert "id" not in card
        assert "guid" not in card
        if card["provenance"]["sources"]:
            for src in card["provenance"]["sources"]:
                assert "document_id" not in src
                assert "chunk_id" not in src


def test_format_json(sample_export_data):
    """Vérifie la sérialisation JSON valide et lisible."""
    notes = sample_export_data["notes"]
    service = CardExportService()
    data = service.extract_export_data(notes, include_ids=False)

    json_str = service.format_json(data)
    parsed = json.loads(json_str)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["deck"] == "Sciences::Biologie"


def test_format_jsonl(sample_export_data):
    """Vérifie la sérialisation JSON Lines (1 objet par ligne)."""
    notes = sample_export_data["notes"]
    service = CardExportService()
    data = service.extract_export_data(notes, include_ids=False)

    jsonl_str = service.format_jsonl(data)
    lines = [line.strip() for line in jsonl_str.strip().split("\n") if line.strip()]
    assert len(lines) == 2
    line1 = json.loads(lines[0])
    line2 = json.loads(lines[1])
    assert line1["deck"] == "Sciences::Biologie"
    assert line2["deck"] == "Sciences::Mathématiques"


def test_format_text_blocks(sample_export_data):
    """Vérifie la génération de texte lisible avec une carte par bloc."""
    notes = sample_export_data["notes"]
    service = CardExportService()
    data = service.extract_export_data(notes, include_ids=True)

    text_output = service.format_text(data)
    assert "Sciences::Biologie" in text_output
    assert "Rôle de la mitochondrie ?" in text_output
    assert "Production d'ATP." in text_output
    assert "Sciences::Mathématiques" in text_output
    assert "Théorème de" in text_output or "théorème de" in text_output
    # Vérification des séparateurs de blocs
    assert "===" in text_output
    assert "---" in text_output


def test_format_markdown_blocks(sample_export_data):
    """Vérifie le formatage Markdown."""
    notes = sample_export_data["notes"]
    service = CardExportService()
    data = service.extract_export_data(notes, include_ids=True)

    md_output = service.format_markdown(data)
    assert "### Carte" in md_output or "## Carte" in md_output
    assert "**Paquet :** Sciences::Biologie" in md_output
    assert "**Modèle :** Basique" in md_output


def test_export_to_file(sample_export_data, tmp_path):
    """Vérifie l'écriture physique dans un fichier unique."""
    notes = sample_export_data["notes"]
    service = CardExportService()

    # JSON export
    json_path = tmp_path / "cards.json"
    count = service.export_to_file(notes, json_path, format_type="json")
    assert count == 2
    assert json_path.exists()
    assert len(json.loads(json_path.read_text(encoding="utf-8"))) == 2

    # TXT export
    txt_path = tmp_path / "cards.txt"
    count = service.export_to_file(notes, txt_path, format_type="text")
    assert count == 2
    assert txt_path.exists()
    assert "Biologie" in txt_path.read_text(encoding="utf-8")


def test_export_to_directory(sample_export_data, tmp_path):
    """Vérifie l'export sous forme d'un dossier avec un fichier par carte."""
    notes = sample_export_data["notes"]
    service = CardExportService()

    out_dir = tmp_path / "cards_folder"
    count = service.export_to_directory(notes, out_dir, format_type="json", include_ids=False)
    assert count == 2
    assert out_dir.is_dir()

    files = sorted(list(out_dir.glob("*.json")))
    assert len(files) == 2
    content_0 = json.loads(files[0].read_text(encoding="utf-8"))
    assert content_0["deck"] == "Sciences::Biologie"


def test_golden_file_deterministic(sample_export_data):
    """Vérifie la conformité exacte avec le golden file JSON sans IDs variables."""
    notes = sample_export_data["notes"]
    service = CardExportService()

    data = service.extract_export_data(notes, include_ids=False)
    actual_json = service.format_json(data)

    golden_path = Path(__file__).parents[2] / "fixtures" / "golden_data" / "golden_cards_export.json"
    golden_path.parent.mkdir(parents=True, exist_ok=True)

    # Si le fichier golden n'existe pas encore lors du premier run, on l'initialise
    if not golden_path.exists():
        golden_path.write_text(actual_json, encoding="utf-8")

    expected_json = golden_path.read_text(encoding="utf-8")
    assert json.loads(actual_json) == json.loads(expected_json)

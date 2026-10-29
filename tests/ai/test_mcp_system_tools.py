"""Tests d'intégration et unitaires pour les outils MCP système, SRS, export et sauvegarde.

Vérifie l'exportation autonome en .apkg à IDs stables, la manipulation des drapeaux et de
la suspension SRS, la correction d'OCR de planches sans altération d'image, et le déclenchement
d'instantanés manuels SQLite.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    DocumentPageModel,
    FolderModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry

pytestmark = pytest.mark.integration


def _extract_text(res: Any) -> str:
    """Helper canonique d'extraction de texte FastMCP conformément aux règles d'ingénierie."""
    return str(res.content[0].text) if hasattr(res, "content") and res.content else str(res)


@pytest.fixture
def sample_deck_with_cards(mock_db: Any) -> tuple[DeckModel, NoteModel, list[CardModel]]:
    """Crée un paquet de test avec une note et deux cartes physiques."""
    deck = DeckModel.create(name="Biologie Médicale")
    note_type = NoteTypeModel.create(
        name="Basique Biologie",
        fields_schema='["Front", "Back"]',
        templates='[{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
        css_style=".card { font-size: 14px; }",
    )
    note = NoteModel.create(
        note_type=note_type,
        guid="bio-guid-001",
        status="new",
        tags='["biologie", "cours"]',
    )
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps({"Front": "Qu'est-ce que l'hémoglobine ?", "Back": "Une protéine de transport d'oxygène."}),
        is_active=True,
    )
    card1 = CardModel.create(
        note=note,
        deck=deck,
        template_index=0,
        flags=0,
        is_suspended=False,
    )
    card2 = CardModel.create(
        note=note,
        deck=deck,
        template_index=1,
        flags=0,
        is_suspended=False,
    )
    return deck, note, [card1, card2]


@pytest.fixture
def sample_album_plate(mock_db: Any, tmp_path: Path) -> tuple[DocumentModel, DocumentPageModel, MediaModel]:
    """Crée un document album avec une planche et son média associé."""
    folder = FolderModel.create(name="Anatomie")
    doc = DocumentModel.create(
        title="Atlas d'Anatomie",
        content="",
        file_type="album",
        folder=folder,
    )
    media_file = tmp_path / "planche_coeur.png"
    media_file.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes")
    media = MediaModel.create(
        filename="planche_coeur.png",
        original_name="coeur.png",
        checksum="sha256_fake_heart",
        mime_type="image/png",
    )
    page = DocumentPageModel.create(
        document=doc,
        media=media,
        page_number=1,
        rotation=0,
        ocr_text="Ventricul gauch et artère aortique",
        status="ready",
    )
    return doc, page, media


# ── 1. Export .apkg ────────────────────────────────────────────────────────


def test_export_deck_apkg_success(sample_deck_with_cards: tuple[DeckModel, NoteModel, list[CardModel]], tmp_path: Path) -> None:
    """Vérifie l'exportation .apkg vers un chemin cible explicite."""
    deck, _, _ = sample_deck_with_cards
    target_apkg = tmp_path / "exports" / "test_bio.apkg"

    res_raw = MCPToolRegistry.export_deck_apkg(
        deck_name=deck.name,
        output_path=str(target_apkg),
        include_media=True,
    )
    data = json.loads(res_raw)

    assert data["status"] == "success"
    assert data["deck_name"] == deck.name
    assert data["exported_notes_count"] == 1
    assert data["output_path"] == str(target_apkg)
    assert target_apkg.exists()
    assert target_apkg.stat().st_size > 0


def test_export_deck_apkg_default_path(sample_deck_with_cards: tuple[DeckModel, NoteModel, list[CardModel]], tmp_path: Path) -> None:
    """Vérifie l'exportation .apkg avec chemin par défaut généré dans le profil actif."""
    deck, _, _ = sample_deck_with_cards

    with patch("ankiforge.services.ai.mcp_tool_registry.get_active_profile", return_value="test_profile"), patch("ankiforge.services.profile_manager.ProfileManager.PROFILES_DIR", tmp_path):
        res_raw = MCPToolRegistry.export_deck_apkg(deck_name=deck.name)
        data = json.loads(res_raw)

        assert data["status"] == "success"
        generated_path = Path(data["output_path"])
        assert generated_path.exists()
        assert generated_path.suffix == ".apkg"


def test_export_deck_apkg_unknown_deck() -> None:
    """Vérifie le rejet motivé si le paquet spécifié n'existe pas."""
    res_raw = MCPToolRegistry.export_deck_apkg(deck_name="Paquet Inexistant 404")
    data = json.loads(res_raw)
    assert data["status"] == "error"
    assert "introuvable" in data["message"].lower()


# ── 2. Drapeaux SRS (set_card_flag) ────────────────────────────────────────


def test_set_card_flag_success(sample_deck_with_cards: tuple[DeckModel, NoteModel, list[CardModel]]) -> None:
    """Vérifie l'attribution d'un drapeau sur toutes les cartes d'une note."""
    _, note, cards = sample_deck_with_cards

    # 1. Poser un drapeau rouge
    res_raw = MCPToolRegistry.set_card_flag(note_id=note.id, flag="red")
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["note_id"] == note.id
    assert data["flag"] == "red"
    assert data["flag_value"] == 1
    assert data["updated_cards_count"] == 2

    # Contrôle direct en base SQLite
    for card_id in [c.id for c in cards]:
        reloaded = CardModel.get_by_id(card_id)
        assert reloaded.flags == 1

    # 2. Réinitialiser à "none"
    res_reset = MCPToolRegistry.set_card_flag(note_id=note.id, flag="none")
    data_reset = json.loads(res_reset)
    assert data_reset["status"] == "success"
    assert data_reset["flag_value"] == 0

    for card_id in [c.id for c in cards]:
        reloaded = CardModel.get_by_id(card_id)
        assert reloaded.flags == 0


def test_set_card_flag_invalid_inputs(sample_deck_with_cards: tuple[DeckModel, NoteModel, list[CardModel]]) -> None:
    """Vérifie le rejet des couleurs de drapeau invalides et des identifiants inconnus."""
    _, note, _ = sample_deck_with_cards

    # Couleur interdite
    res_bad_color = MCPToolRegistry.set_card_flag(note_id=note.id, flag="magenta_inconnu")
    data_bad_color = json.loads(res_bad_color)
    assert data_bad_color["status"] == "error"
    assert "invalide" in data_bad_color["message"].lower()

    # Note inconnue
    res_bad_note = MCPToolRegistry.set_card_flag(note_id=999999, flag="blue")
    data_bad_note = json.loads(res_bad_note)
    assert data_bad_note["status"] == "error"
    assert "introuvable" in data_bad_note["message"].lower()


# ── 3. Suspension SRS (suspend_card / unsuspend_card) ─────────────────────


def test_suspend_and_unsuspend_card(sample_deck_with_cards: tuple[DeckModel, NoteModel, list[CardModel]]) -> None:
    """Vérifie la suspension et réactivation d'une carte physique."""
    _, _, cards = sample_deck_with_cards
    target_card = cards[0]
    assert not target_card.is_suspended

    # 1. Suspendre
    res_sus = MCPToolRegistry.suspend_card(card_id=target_card.id)
    data_sus = json.loads(res_sus)
    assert data_sus["status"] == "success"
    assert data_sus["card_id"] == target_card.id
    assert data_sus["is_suspended"] is True

    reloaded = CardModel.get_by_id(target_card.id)
    assert reloaded.is_suspended is True

    # 2. Réactiver (unsuspend)
    res_unsus = MCPToolRegistry.unsuspend_card(card_id=target_card.id)
    data_unsus = json.loads(res_unsus)
    assert data_unsus["status"] == "success"
    assert data_unsus["card_id"] == target_card.id
    assert data_unsus["is_suspended"] is False

    reloaded = CardModel.get_by_id(target_card.id)
    assert reloaded.is_suspended is False


def test_suspend_card_unknown_id() -> None:
    """Vérifie le rejet d'une carte introuvable."""
    res = MCPToolRegistry.suspend_card(card_id=999999)
    data = json.loads(res)
    assert data["status"] == "error"
    assert "introuvable" in data["message"].lower()


# ── 4. Correction OCR de planche (correct_plate_ocr) ───────────────────────


def test_correct_plate_ocr_success(sample_album_plate: tuple[DocumentModel, DocumentPageModel, MediaModel]) -> None:
    """Vérifie la mise à jour de la couche OCR textuelle sans altération de l'image."""
    doc, page, media = sample_album_plate
    corrected_text = "Ventricule gauche et artère aorte (corrigé manuellement)"

    res_raw = MCPToolRegistry.correct_plate_ocr(
        plate_id=page.id,
        corrected_text=corrected_text,
    )
    data = json.loads(res_raw)
    assert data["status"] == "success"
    assert data["plate_id"] == page.id
    assert data["page_number"] == 1
    assert data["document_id"] == doc.id
    assert data["ocr_text_length"] == len(corrected_text)

    # Vérification en base
    reloaded_page = DocumentPageModel.get_by_id(page.id)
    assert reloaded_page.ocr_text == corrected_text
    # L'image liée n'a pas bougé
    assert reloaded_page.media_id == media.id


def test_correct_plate_ocr_unknown_plate() -> None:
    """Vérifie le rejet d'une planche inexistante."""
    res = MCPToolRegistry.correct_plate_ocr(plate_id=999999, corrected_text="Hello")
    data = json.loads(res)
    assert data["status"] == "error"
    assert "introuvable" in data["message"].lower()


# ── 5. Sauvegarde Manuelle SQLite (trigger_manual_backup) ──────────────────


def test_trigger_manual_backup_success(tmp_path: Path) -> None:
    """Vérifie la génération d'un snapshot SQLite horodaté dans le profil actif."""
    fake_db = tmp_path / "ankiforge.db"
    # Création d'une base SQLite valide
    with sqlite3.connect(fake_db) as conn:
        conn.execute("CREATE TABLE dummy (id INTEGER PRIMARY KEY);")
        conn.execute("INSERT INTO dummy VALUES (1);")

    fake_profiles_dir = tmp_path / "profiles"
    fake_profiles_dir.mkdir(parents=True)

    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=fake_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", fake_profiles_dir),
    ):
        res_raw = MCPToolRegistry.trigger_manual_backup(reason="pre_major_mutation")
        data = json.loads(res_raw)

        assert data["status"] == "success"
        assert "pre_major_mutation" in data["filename"] or "manual" in data["filename"]
        backup_path = Path(data["backup_path"])
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0


# ── 6. Invocations FastMCP Directes ─────────────────────────────────────────


def test_fastmcp_system_tools_registered_and_invocable(
    sample_deck_with_cards: tuple[DeckModel, NoteModel, list[CardModel]],
    sample_album_plate: tuple[DocumentModel, DocumentPageModel, MediaModel],
) -> None:
    """Vérifie que les 6 outils sont déclarés et invocables directement via le protocole FastMCP."""
    deck, note, cards = sample_deck_with_cards
    _, page, _ = sample_album_plate

    async def _run() -> None:
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert "export_deck_apkg" in tool_names
        assert "set_card_flag" in tool_names
        assert "suspend_card" in tool_names
        assert "unsuspend_card" in tool_names
        assert "correct_plate_ocr" in tool_names
        assert "trigger_manual_backup" in tool_names

        # 1. Invoquer set_card_flag
        flag_res = await mcp.call_tool("set_card_flag", arguments={"note_id": note.id, "flag": "turquoise"})
        flag_data = json.loads(_extract_text(flag_res))
        assert flag_data["status"] == "success"
        assert flag_data["flag"] == "turquoise"
        assert flag_data["flag_value"] == 6

        # 2. Invoquer suspend_card
        sus_res = await mcp.call_tool("suspend_card", arguments={"card_id": cards[0].id})
        sus_data = json.loads(_extract_text(sus_res))
        assert sus_data["status"] == "success"
        assert sus_data["is_suspended"] is True

        # 3. Invoquer unsuspend_card
        unsus_res = await mcp.call_tool("unsuspend_card", arguments={"card_id": cards[0].id})
        unsus_data = json.loads(_extract_text(unsus_res))
        assert unsus_data["status"] == "success"
        assert unsus_data["is_suspended"] is False

        # 4. Invoquer correct_plate_ocr
        plate_res = await mcp.call_tool("correct_plate_ocr", arguments={"plate_id": page.id, "corrected_text": "Texte mis à jour via FastMCP"})
        plate_data = json.loads(_extract_text(plate_res))
        assert plate_data["status"] == "success"
        assert plate_data["plate_id"] == page.id

    asyncio.run(_run())


def test_mcp_tool_registry_system_tools_dispatch(
    sample_deck_with_cards: tuple[DeckModel, NoteModel, list[CardModel]],
    sample_album_plate: tuple[DocumentModel, DocumentPageModel, MediaModel],
    tmp_path: Path,
) -> None:
    """Vérifie la parité de dispatch des 6 outils via MCPToolRegistry directement."""
    from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry

    deck, note, cards = sample_deck_with_cards
    _, page, _ = sample_album_plate

    # 1. export_deck_apkg
    out_apkg = tmp_path / "mcp_deck.apkg"
    obs = MCPToolRegistry.export_deck_apkg(deck_name=deck.name, output_path=str(out_apkg))
    assert json.loads(obs)["status"] == "success"

    # 2. set_card_flag
    obs = MCPToolRegistry.set_card_flag(note_id=note.id, flag="purple")
    assert json.loads(obs)["flag"] == "purple"

    # 3. suspend_card
    obs = MCPToolRegistry.suspend_card(card_id=cards[0].id)
    assert json.loads(obs)["is_suspended"] is True

    # 4. unsuspend_card
    obs = MCPToolRegistry.unsuspend_card(card_id=cards[0].id)
    assert json.loads(obs)["is_suspended"] is False

    # 5. correct_plate_ocr
    obs = MCPToolRegistry.correct_plate_ocr(plate_id=page.id, corrected_text="Texte via MCP")
    assert json.loads(obs)["status"] == "success"

    # 6. trigger_manual_backup
    fake_db = tmp_path / "ankiforge.db"
    with sqlite3.connect(fake_db) as conn:
        conn.execute("CREATE TABLE dummy (id INT);")
    fake_profiles_dir = tmp_path / "profiles_mcp"
    fake_profiles_dir.mkdir(parents=True)

    with (
        patch("ankiforge.database.backup.ProfileManager.get_db_path", return_value=fake_db),
        patch("ankiforge.database.backup.get_active_profile", return_value="default"),
        patch("ankiforge.database.backup.ProfileManager.PROFILES_DIR", fake_profiles_dir),
    ):
        obs = MCPToolRegistry.trigger_manual_backup(reason="mcp_test")
        assert json.loads(obs)["status"] == "success"

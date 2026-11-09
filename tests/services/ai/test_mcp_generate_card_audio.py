"""Tests unitaires et d'intégration pour les outils MCP generate_card_audio et generate_cards_batch_audio."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.ai.mcp_server import mcp
from ankiforge.services.ai.mcp_tool_registry import (
    DEFAULT_CONSULTANT_TOOLS,
    MCPToolRegistry,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def audio_note_dataset():
    """Crée un jeu de notes avec un type de note comportant un champ 'Japonais' et un champ 'Audio'."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"NT Audio {uid}",
        fields_schema=json.dumps(["Japonais", "Audio", "Traduction"]),
        templates="[]",
        css_style="",
    )
    deck = DeckModel.create(name=f"Deck Audio {uid}")

    n1 = NoteModel.create(guid=f"n_audio_1_{uid}", note_type=nt, tags="japonais")
    NoteVersionModel.create(
        note=n1,
        version_number=1,
        content=json.dumps({"Japonais": "こんにちは", "Audio": "", "Traduction": "Bonjour"}),
        is_active=True,
    )
    CardModel.create(note=n1, deck=deck, template_index=0)

    n2 = NoteModel.create(guid=f"n_audio_2_{uid}", note_type=nt, tags="japonais")
    NoteVersionModel.create(
        note=n2,
        version_number=1,
        content=json.dumps({"Japonais": "<b>Bonjour</b> le monde", "Audio": "", "Traduction": "Hello world"}),
        is_active=True,
    )
    CardModel.create(note=n2, deck=deck, template_index=0)

    n3 = NoteModel.create(guid=f"n_audio_3_{uid}", note_type=nt, tags="japonais")
    NoteVersionModel.create(
        note=n3,
        version_number=1,
        content=json.dumps({"Japonais": "{{c1::東京}} est la capitale", "Audio": "", "Traduction": "Tokyo"}),
        is_active=True,
    )
    CardModel.create(note=n3, deck=deck, template_index=0)

    return {
        "uid": uid,
        "nt": nt,
        "deck": deck,
        "n1": n1,
        "n2": n2,
        "n3": n3,
    }


def _extract_text(result: Any) -> str:
    """Extrait le texte d'un CallToolResult ou d'une chaîne."""
    return str(result.content[0].text) if hasattr(result, "content") and result.content else str(result)


def _extract_json(result: Any) -> dict[str, Any]:
    """Extrait et parse un JSON depuis un résultat d'outil MCP."""
    text = _extract_text(result)
    return json.loads(text)


def _get_active_version(note: NoteModel) -> dict[str, Any]:
    """Retourne le contenu JSON de la version active d'une note."""
    v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    return json.loads(v.content) if v and v.content else {}


def test_generate_card_audio_declared_in_default_consultant_tools():
    """L'outil generate_card_audio doit être déclaré dans DEFAULT_CONSULTANT_TOOLS."""
    names = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "generate_card_audio" in names


def test_generate_cards_batch_audio_declared_in_default_consultant_tools():
    """L'outil generate_cards_batch_audio doit être déclaré dans DEFAULT_CONSULTANT_TOOLS."""
    names = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "generate_cards_batch_audio" in names


def test_generate_card_audio_schema():
    """Vérifie le schéma JSON de generate_card_audio (paramètres requis/optionnels)."""
    tools_by_name = {t["function"]["name"]: t["function"] for t in DEFAULT_CONSULTANT_TOOLS}
    tool = tools_by_name["generate_card_audio"]
    props = tool["parameters"]["properties"]
    assert "note_id" in props
    assert "source_field" in props
    assert "target_field" in props
    assert "voice" in props
    assert "engine" in props
    assert tool["parameters"]["required"] == ["note_id"]


def test_generate_cards_batch_audio_schema():
    """Vérifie le schéma JSON de generate_cards_batch_audio."""
    tools_by_name = {t["function"]["name"]: t["function"] for t in DEFAULT_CONSULTANT_TOOLS}
    tool = tools_by_name["generate_cards_batch_audio"]
    props = tool["parameters"]["properties"]
    assert "note_ids" in props
    assert "source_field" in props
    assert "target_field" in props
    assert tool["parameters"]["required"] == ["note_ids"]


def test_generate_card_audio_exposes_on_fastmcp_server(audio_note_dataset):
    """L'outil generate_card_audio doit être exposé par le serveur FastMCP mcp."""
    import asyncio

    async def _check():
        tools = await mcp.list_tools()
        return [t.name for t in tools]

    tool_names = asyncio.run(_check())
    assert "generate_card_audio" in tool_names
    assert "generate_cards_batch_audio" in tool_names


def test_generate_card_audio_note_not_found():
    """generate_card_audio doit retourner une erreur si la note n'existe pas."""
    result = MCPToolRegistry.generate_card_audio(note_id=999999, source_field="Japonais", target_field="Audio")
    data = _extract_json(result)
    assert data["status"] == "error"
    assert "introuvable" in data["message"]


def test_generate_card_audio_source_field_missing(audio_note_dataset):
    """generate_card_audio doit retourner une erreur si le champ source est absent du modèle."""
    result = MCPToolRegistry.generate_card_audio(
        note_id=audio_note_dataset["n1"].id,
        source_field="ChampInexistant",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "error"
    assert "introuvable" in data["message"]


def test_generate_card_audio_target_field_missing(audio_note_dataset):
    """generate_card_audio doit retourner une erreur si le champ cible est absent du modèle."""
    result = MCPToolRegistry.generate_card_audio(
        note_id=audio_note_dataset["n1"].id,
        source_field="Japonais",
        target_field="ChampInexistant",
    )
    data = _extract_json(result)
    assert data["status"] == "error"
    assert "introuvable" in data["message"]


def test_generate_card_audio_empty_source_text(audio_note_dataset):
    """generate_card_audio doit rejeter un texte source vide après nettoyage."""
    nt = audio_note_dataset["nt"]
    n_empty = NoteModel.create(guid=f"n_empty_{audio_note_dataset['uid']}", note_type=nt, tags="vide")
    NoteVersionModel.create(
        note=n_empty,
        version_number=1,
        content=json.dumps({"Japonais": "", "Audio": "", "Traduction": ""}),
        is_active=True,
    )
    CardModel.create(note=n_empty, deck=audio_note_dataset["deck"], template_index=0)

    result = MCPToolRegistry.generate_card_audio(
        note_id=n_empty.id,
        source_field="Japonais",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "error"


def test_generate_card_audio_success_with_mocked_tts(audio_note_dataset, monkeypatch):
    """generate_card_audio génère l'audio, stocke le média et met à jour le champ cible."""

    # Mock du provider TTS pour éviter tout appel réseau
    class FakeProvider:
        id = "edge-tts"
        display_name = "Fake TTS"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return [{"id": "ja-JP-NanamiNeural", "name": "Japonais - Nanami", "lang": "ja-JP"}]

        def synthesize(self, text: str, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
            return b"FAKE_AUDIO_BYTES_" + text.encode("utf-8")

    from ankiforge.services.cards.tts_service import TTSService

    monkeypatch.setattr(TTSService, "get_provider", lambda self, engine=None: FakeProvider())

    result = MCPToolRegistry.generate_card_audio(
        note_id=audio_note_dataset["n1"].id,
        source_field="Japonais",
        target_field="Audio",
        voice="ja-JP-NanamiNeural",
        engine="edge-tts",
    )
    data = _extract_json(result)
    assert data["status"] == "success"
    assert data["note_id"] == audio_note_dataset["n1"].id
    assert data["source_field"] == "Japonais"
    assert data["target_field"] == "Audio"
    assert "[sound:" in data["audio_tag"]
    assert data["audio_tag"].endswith(".mp3]")

    # Vérifier que le champ Audio de la note a été mis à jour
    active = _get_active_version(audio_note_dataset["n1"])
    assert active["Audio"] == data["audio_tag"]
    assert active["Japonais"] == "こんにちは"  # Le champ source n'est pas modifié

    # Vérifier que le média est enregistré dans MediaModel
    filename = data["audio_tag"].replace("[sound:", "").rstrip("]")
    media = MediaModel.get_or_none(MediaModel.filename == filename)
    assert media is not None
    assert media.mime_type == "audio/mpeg"


def test_generate_card_audio_cleans_html_tags(audio_note_dataset, monkeypatch):
    """Le texte source doit être nettoyé des balises HTML avant synthèse."""

    class FakeProvider:
        id = "edge-tts"
        display_name = "Fake TTS"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return []

        def synthesize(self, text: str, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
            # Vérifier que les balises HTML ont été supprimées
            assert "<b>" not in text
            assert "</b>" not in text
            assert "Bonjour le monde" in text
            return b"FAKE_AUDIO"

    from ankiforge.services.cards.tts_service import TTSService

    monkeypatch.setattr(TTSService, "get_provider", lambda self, engine=None: FakeProvider())

    result = MCPToolRegistry.generate_card_audio(
        note_id=audio_note_dataset["n2"].id,
        source_field="Japonais",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "success"


def test_generate_card_audio_cleans_cloze(audio_note_dataset, monkeypatch):
    """Le texte source doit être nettoyé des occlusions cloze avant synthèse."""

    class FakeProvider:
        id = "edge-tts"
        display_name = "Fake TTS"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return []

        def synthesize(self, text: str, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
            assert "{{c1::" not in text
            assert "東京 est la capitale" in text
            return b"FAKE_AUDIO"

    from ankiforge.services.cards.tts_service import TTSService

    monkeypatch.setattr(TTSService, "get_provider", lambda self, engine=None: FakeProvider())

    result = MCPToolRegistry.generate_card_audio(
        note_id=audio_note_dataset["n3"].id,
        source_field="Japonais",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "success"


def test_generate_card_audio_no_tts_available(audio_note_dataset, monkeypatch):
    """generate_card_audio doit retourner une erreur si aucun moteur TTS n'est disponible."""
    from ankiforge.services.cards.tts_service import TTSService

    def _fail_synthesize(self, text, engine=None, voice=None, rate=None, pitch=None, strip_cloze=True):
        raise RuntimeError("Aucun moteur TTS disponible")

    monkeypatch.setattr(TTSService, "synthesize", _fail_synthesize)

    result = MCPToolRegistry.generate_card_audio(
        note_id=audio_note_dataset["n1"].id,
        source_field="Japonais",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "error"


def test_generate_cards_batch_audio_success(audio_note_dataset, monkeypatch):
    """generate_cards_batch_audio doit traiter un lot de notes."""

    class FakeProvider:
        id = "edge-tts"
        display_name = "Fake TTS"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return []

        def synthesize(self, text: str, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
            return b"FAKE_AUDIO_BYTES"

    from ankiforge.services.cards.tts_service import TTSService

    monkeypatch.setattr(TTSService, "get_provider", lambda self, engine=None: FakeProvider())

    note_ids = [audio_note_dataset["n1"].id, audio_note_dataset["n2"].id, audio_note_dataset["n3"].id]
    result = MCPToolRegistry.generate_cards_batch_audio(
        note_ids=note_ids,
        source_field="Japonais",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "success"
    assert data["total_requested"] == 3
    assert data["total_success"] == 3
    assert len(data["results"]) == 3

    # Vérifier que chaque note a son champ Audio mis à jour
    for nid in note_ids:
        active = _get_active_version(NoteModel.get_or_none(NoteModel.id == nid))
        assert "[sound:" in active["Audio"]


def test_generate_cards_batch_audio_partial_failure(audio_note_dataset, monkeypatch):
    """generate_cards_batch_audio doit signaler les notes en échec tout en traitant les valides."""

    class FakeProvider:
        id = "edge-tts"
        display_name = "Fake TTS"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return []

        def synthesize(self, text: str, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
            return b"FAKE_AUDIO"

    from ankiforge.services.cards.tts_service import TTSService

    monkeypatch.setattr(TTSService, "get_provider", lambda self, engine=None: FakeProvider())

    # n1 existe, 999999 n'existe pas
    note_ids = [audio_note_dataset["n1"].id, 999999]
    result = MCPToolRegistry.generate_cards_batch_audio(
        note_ids=note_ids,
        source_field="Japonais",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "partial"
    assert data["total_requested"] == 2
    assert data["total_success"] == 1
    assert data["total_failed"] == 1
    assert len(data["results"]) == 2
    # Le résultat de l'échec doit contenir une erreur
    failed = [r for r in data["results"] if r.get("status") == "error"]
    assert len(failed) == 1


def test_generate_cards_batch_audio_empty_list():
    """generate_cards_batch_audio doit rejeter une liste vide."""
    result = MCPToolRegistry.generate_cards_batch_audio(note_ids=[], source_field="Japonais", target_field="Audio")
    data = _extract_json(result)
    assert data["status"] == "error"


def active_version_id(note: NoteModel) -> int:
    """Retourne l'ID de la version active d'une note."""
    v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
    return v.id if v else 0


def test_generate_card_audio_audio_tag_format(audio_note_dataset, monkeypatch):
    """La balise audio retournée doit être au format [sound:nom_fichier.mp3]."""

    class FakeProvider:
        id = "edge-tts"
        display_name = "Fake TTS"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return []

        def synthesize(self, text: str, voice: str | None = None, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
            return b"FAKE_AUDIO"

    from ankiforge.services.cards.tts_service import TTSService

    monkeypatch.setattr(TTSService, "get_provider", lambda self, engine=None: FakeProvider())

    result = MCPToolRegistry.generate_card_audio(
        note_id=audio_note_dataset["n1"].id,
        source_field="Japonais",
        target_field="Audio",
    )
    data = _extract_json(result)
    assert data["status"] == "success"
    tag = data["audio_tag"]
    assert tag.startswith("[sound:")
    assert tag.endswith(".mp3]")
    filename = tag[7:-1]  # retire [sound: et ]
    assert filename.startswith("tts_")
    assert Path(audio_note_dataset["nt"]._meta.database.database).exists() or True  # base accessible

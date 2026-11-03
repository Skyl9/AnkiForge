"""Tests de couverture ciblés pour TTSService et TextNormalizer afin de résorber le risque CRAP."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.cards.tts_service import (
    SystemSpeechProvider,
    TextNormalizer,
    TTSProvider,
    TTSService,
)

pytestmark = pytest.mark.unit


def test_text_normalizer_complete_pipeline() -> None:
    """Couvre l'ensemble des méthodes de TextNormalizer (cloze, html, markdown, maths, audio tags)."""
    # 1. strip_html
    assert TextNormalizer.strip_html(None) == ""  # type: ignore[arg-type]
    assert TextNormalizer.strip_html("<p>Paragraphe<br/>Ligne 2</p>").strip() == "Paragraphe Ligne 2"

    # 2. expand_cloze
    assert TextNormalizer.expand_cloze("La capitale est {{c1::Paris::Indice}}.") == "La capitale est Paris."
    assert TextNormalizer.expand_cloze("{{c2::Rome}} est belle.") == "Rome est belle."
    assert TextNormalizer.expand_cloze(None) == ""  # type: ignore[arg-type]

    # 3. remove_audio_tags
    assert TextNormalizer.remove_audio_tags("Texte [sound:test_123.mp3] ici.") == "Texte  ici."
    assert TextNormalizer.remove_audio_tags(None) == ""  # type: ignore[arg-type]

    # 4. clean_markdown_and_math
    raw_md = "Voir [lien](https://example.com), image ![alt](img.png), **gras** et $E=mc^2$."
    cleaned_md = TextNormalizer.clean_markdown_and_math(raw_md)
    assert "[lien]" not in cleaned_md
    assert "lien" in cleaned_md
    assert "![alt]" not in cleaned_md
    assert "**" not in cleaned_md
    assert "$" not in cleaned_md

    # 5. Pipeline complet clean_for_tts
    complex_text = "<h3>Question {{c1::importante}}</h3> : Voir [doc](http://x) [sound:old.wav] !"
    final_text = TextNormalizer.clean_for_tts(complex_text)
    assert final_text == "Question importante : Voir doc !"


class DummyMockProvider(TTSProvider):
    """Moteur TTS de test isolé pour valider l'orchestration TTSService sans appels réseau."""

    id = "dummy-tts"
    display_name = "Dummy Mock TTS"

    def __init__(self) -> None:
        self.should_fail: bool = False

    def is_available(self) -> bool:
        return True

    def get_voices(self) -> list[dict[str, Any]]:
        return [{"id": "fr-test", "name": "Voix Test", "gender": "Female"}]

    def synthesize(self, text: str, voice: str | None = None, rate: str | None = None, pitch: str | None = None) -> bytes:
        if self.should_fail:
            raise RuntimeError("Erreur de test simulée sur DummyMockProvider")
        return b"FAKEMP3DATA12345"


def test_tts_service_synthesis_and_caching(mock_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Couvre synthesize et get_cached_audio_path sur TTSService (CC=21, anciennement CRAP=436.6)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        media_mgr = MediaManager(media_dir=tmp_path)
        service = TTSService(media_manager=media_mgr)

        dummy_provider = DummyMockProvider()
        service._providers["dummy-tts"] = dummy_provider

        # 1. Synthèse réussie
        tag, file_path = service.synthesize("Bonjour le monde", engine="dummy-tts", voice="fr-test")
        assert tag.startswith("[sound:tts_")
        assert file_path.exists()
        assert file_path.read_bytes() == b"FAKEMP3DATA12345"

        # 2. Vérification du cache
        cached_path = service.get_cached_audio_path("Bonjour le monde", engine="dummy-tts", voice="fr-test")
        assert cached_path == file_path

        # 3. Ré-exécution avec hit de cache immédiat (le provider ne doit pas être ré-appelé)
        dummy_provider.synthesize = MagicMock(side_effect=AssertionError("Ne doit pas être appelé"))  # type: ignore[method-assign]
        tag_cached, path_cached = service.synthesize("Bonjour le monde", engine="dummy-tts", voice="fr-test")
        assert tag_cached == tag
        assert path_cached == file_path


def test_tts_service_fallback_and_system_provider() -> None:
    """Couvre le mécanisme de bascule sur erreur (fallback) et SystemSpeechProvider."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        media_mgr = MediaManager(media_dir=tmp_path)
        service = TTSService(media_manager=media_mgr)

        p1 = DummyMockProvider()
        p1.id = "edge-tts"
        p1.should_fail = True

        p2 = DummyMockProvider()
        p2.id = "piper"

        service._providers["edge-tts"] = p1
        service._providers["piper"] = p2

        # edge-tts échoue, repli transparent automatique vers piper
        tag, path = service.synthesize("Repli de test", engine="edge-tts")
        assert tag.startswith("[sound:tts_")
        assert path.exists()

    # Couverture de base SystemSpeechProvider
    sys_prov = SystemSpeechProvider()
    assert sys_prov.id == "system"
    voices = sys_prov.get_voices()
    assert isinstance(voices, list)

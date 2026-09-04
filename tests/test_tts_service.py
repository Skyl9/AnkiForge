"""
Tests unitaires pour le service de synthèse vocale (TTSService) et TextNormalizer.
Couvre le nettoyage HTML/Cloze, le cache MD5, les providers et la déduplication média.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.cards.tts_service import (
    SystemSpeechProvider,
    TextNormalizer,
    TTSProvider,
    TTSService,
)


def test_text_normalizer_strip_html() -> None:
    """Vérifie que le HTML est éradiqué tout en préservant le texte."""
    raw = "<b>Bonjour</b> à tous<br/>Comment <i>allez-vous</i> ?<div>Bienvenue</div>"
    clean = TextNormalizer.strip_html(raw)
    assert "<b>" not in clean
    assert "<i>" not in clean
    assert "<br/>" not in clean
    assert " ".join(clean.split()) == "Bonjour à tous Comment allez-vous ? Bienvenue"


def test_text_normalizer_expand_cloze() -> None:
    """Vérifie que les occlusions Anki (clozes) sont développées avec le texte cible."""
    raw = "La capitale de la France est {{c1::Paris::Indice}} et celle de l'Espagne est {{c2::Madrid}}."
    expanded = TextNormalizer.expand_cloze(raw)
    assert expanded == "La capitale de la France est Paris et celle de l'Espagne est Madrid."


def test_text_normalizer_remove_audio_tags() -> None:
    """Vérifie que les balises sonores existantes [sound:xxx] sont retirées."""
    raw = "Hello World [sound:tts_12345.mp3] [sound:other.wav]"
    clean = TextNormalizer.remove_audio_tags(raw)
    assert clean.strip() == "Hello World"


def test_text_normalizer_clean_markdown_and_math() -> None:
    """Vérifie le nettoyage du markdown et des formules mathématiques."""
    raw = "Calcul : \\( x^2 + y^2 = z^2 \\) et lien [Wiki](https://fr.wikipedia.org) avec **gras**."
    clean = TextNormalizer.clean_markdown_and_math(raw)
    assert "\\(" not in clean
    assert "\\)" not in clean
    assert "[Wiki]" not in clean
    assert "Wiki" in clean
    assert "**gras**" not in clean
    assert "gras" in clean


def test_text_normalizer_full_pipeline() -> None:
    """Vérifie la chaîne complète clean_for_tts."""
    raw = "<div>{{c1::Pomme::Fruit}}</div> rouge [sound:old.mp3] <b>croquante</b>"
    clean = TextNormalizer.clean_for_tts(raw, strip_cloze=True)
    assert clean == "Pomme rouge croquante"

    # Sans expansion de cloze
    clean_no_strip = TextNormalizer.clean_for_tts(raw, strip_cloze=False)
    assert "{{c1::Pomme::Fruit}}" in clean_no_strip


def test_tts_service_available_engines() -> None:
    """Vérifie la liste des moteurs disponibles dans TTSService."""
    service = TTSService()
    engines = service.get_available_engines()
    engine_ids = [e["id"] for e in engines]
    assert "edge-tts" in engine_ids
    assert "piper" in engine_ids
    assert "system" in engine_ids


class MockSuccessProvider(TTSProvider):
    id = "mock"
    display_name = "Mock Provider"

    def is_available(self) -> bool:
        return True

    def get_voices(self) -> list[dict[str, str]]:
        return [{"id": "v1", "name": "Voice 1", "lang": "fr-FR"}]

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        return b"MOCK_AUDIO_DATA_FOR_" + text.encode("utf-8")


def test_tts_service_synthesize_caching(tmp_path: Path) -> None:
    """Vérifie la génération, l'archivage dans MediaManager et le cache MD5."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path

    service = TTSService(media_manager=media_mgr)
    mock_provider = MockSuccessProvider()
    service._providers["mock"] = mock_provider

    # Premier appel : synthèse réelle
    tag1, path1 = service.synthesize("Bonjour le monde", engine="mock", voice="v1")
    assert tag1.startswith("[sound:")
    assert tag1.endswith(".wav]")
    assert path1.exists()
    assert path1.read_bytes().startswith(b"MOCK_AUDIO_DATA_FOR_Bonjour le monde")

    # Deuxième appel : doit réutiliser le cache média immédiatement sans ré-exécuter le provider
    mock_provider.synthesize = MagicMock(side_effect=RuntimeError("Ne devrait pas être appelé"))  # type: ignore[assignment]
    tag2, path2 = service.synthesize("Bonjour le monde", engine="mock", voice="v1")
    assert tag1 == tag2
    assert path1 == path2


def test_tts_service_empty_text_error() -> None:
    """Vérifie qu'un texte vide ou ne contenant que du HTML lève une ValueError."""
    service = TTSService()
    with pytest.raises(ValueError, match="vide après normalisation"):
        service.synthesize("   <br/>  <b></b>  ")


def test_system_speech_provider_available_or_graceful() -> None:
    """Vérifie que SystemSpeechProvider ne crash pas et expose des voix."""
    provider = SystemSpeechProvider()
    voices = provider.get_voices()
    assert isinstance(voices, list)
    assert len(voices) >= 1


def test_piper_executable_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la détection de l'exécutable Piper dans un sous-dossier piper/."""
    from ankiforge.services.cards.tts_service import PiperSidecarProvider

    monkeypatch.setattr("ankiforge.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)

    # Avant installation
    assert PiperSidecarProvider.get_piper_executable() is None

    # Création d'un binaire factice dans piper/piper
    sub_dir = tmp_path / "tools" / "tts" / "piper"
    sub_dir.mkdir(parents=True)
    fake_exe = sub_dir / "piper"
    fake_exe.write_text("#!/bin/sh\necho piper")
    fake_exe.chmod(0o755)

    detected = PiperSidecarProvider.get_piper_executable()
    assert detected is not None
    assert detected == fake_exe

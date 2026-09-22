"""
Tests unitaires pour le service de synthèse vocale (TTSService) et TextNormalizer.
Couvre le nettoyage HTML/Cloze, le cache MD5, les providers et la déduplication média.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.cards.tts_service import (
    KokoroSidecarProvider,
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
    mock_provider.synthesize = MagicMock(side_effect=RuntimeError("Ne devrait pas être appelé"))
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
    monkeypatch.setattr("ankiforge.utils.environment.is_testing", lambda: True)

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


def test_kokoro_command_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la détection du runner Kokoro (run.py ou binaire)."""
    monkeypatch.setattr("ankiforge.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankiforge.utils.environment.is_testing", lambda: True)

    # Avant installation
    assert KokoroSidecarProvider.get_kokoro_command() is None
    assert KokoroSidecarProvider().is_available() is False

    # Création d'un script run.py factice
    kokoro_dir = tmp_path / "tools" / "tts" / "kokoro"
    kokoro_dir.mkdir(parents=True)
    run_py = kokoro_dir / "run.py"
    run_py.write_text("print('kokoro')")

    cmd = KokoroSidecarProvider.get_kokoro_command()
    assert cmd is not None
    assert str(run_py) in cmd[-1]


def test_kokoro_synthesize_missing_runner_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que synthesize() lève RuntimeError si le runner est absent."""
    monkeypatch.setattr("ankiforge.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankiforge.utils.environment.is_testing", lambda: True)

    provider = KokoroSidecarProvider()
    with pytest.raises(RuntimeError, match="Le runner Kokoro est introuvable"):
        provider.synthesize("Bonjour")


def test_kokoro_synthesize_subprocess_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la synthèse par subprocess avec code retour 0 et production de fichier WAV."""
    import subprocess

    monkeypatch.setattr("ankiforge.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankiforge.utils.environment.is_testing", lambda: True)

    kokoro_dir = tmp_path / "tools" / "tts" / "kokoro"
    kokoro_dir.mkdir(parents=True)
    run_py = kokoro_dir / "run.py"
    run_py.write_text("print('stub')")

    # Mock is_functional
    monkeypatch.setattr(KokoroSidecarProvider, "is_functional", classmethod(lambda cls: (True, "Opérationnel")))

    # Simuler subprocess.run produisant le fichier WAV attendu
    fake_wav_bytes = b"RIFF....WAVEfmt ...."

    def fake_subprocess_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        # Trouver l'argument --output
        if "--output" in cmd:
            out_idx = cmd.index("--output") + 1
            out_file = Path(cmd[out_idx])
            out_file.write_bytes(fake_wav_bytes)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    provider = KokoroSidecarProvider()
    audio = provider.synthesize("Hello world", voice="af_heart", rate="+10%")
    assert audio == fake_wav_bytes


def test_kokoro_synthesize_subprocess_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie qu'un code retour non-nul du subprocess déclenche une RuntimeError claire."""
    import subprocess

    monkeypatch.setattr("ankiforge.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankiforge.utils.environment.is_testing", lambda: True)

    kokoro_dir = tmp_path / "tools" / "tts" / "kokoro"
    kokoro_dir.mkdir(parents=True)
    (kokoro_dir / "run.py").write_text("print('stub')")

    monkeypatch.setattr(KokoroSidecarProvider, "is_functional", classmethod(lambda cls: (True, "Opérationnel")))

    def fake_subprocess_fail(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"", stderr=b"OOM or syntax error")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_fail)

    provider = KokoroSidecarProvider()
    with pytest.raises(RuntimeError, match="Kokoro a échoué"):
        provider.synthesize("Crash text")


def test_kokoro_install_runner_creates_executable_and_executes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que install_runner déploie un run.py valide et fonctionnel."""
    monkeypatch.setattr("ankiforge.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankiforge.utils.environment.is_testing", lambda: True)

    ok = KokoroSidecarProvider.install_runner()
    assert ok is True

    run_py = tmp_path / "tools" / "tts" / "kokoro" / "run.py"
    assert run_py.exists()
    assert run_py.stat().st_size > 100

    # Vérifier que is_functional() probe et confirme que run.py s'exécute avec succès
    functional, msg = KokoroSidecarProvider.is_functional()
    assert functional is True
    assert msg == "Opérationnel"

    # Vérifier la synthèse réelle de fallback via ce run.py
    provider = KokoroSidecarProvider()
    data = provider.synthesize("Bonjour depuis Kokoro", voice="af_heart")
    assert len(data) > 44  # Header WAV standard = 44 octets
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WAVE"


def test_tts_service_cache_helpers(tmp_path: Path) -> None:
    """Vérifie get_cached_audio_path et has_cached_audio."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path

    service = TTSService(media_manager=media_mgr)
    mock_provider = MockSuccessProvider()
    service._providers["mock"] = mock_provider

    text = "Phrase pour test cache"
    # Avant synthèse
    assert service.has_cached_audio(text, engine="mock", voice="v1") is False
    assert service.get_cached_audio_path(text, engine="mock", voice="v1") is None

    # Synthèse
    _, audio_path = service.synthesize(text, engine="mock", voice="v1")
    assert audio_path.exists()

    # Après synthèse
    assert service.has_cached_audio(text, engine="mock", voice="v1") is True
    cached_path = service.get_cached_audio_path(text, engine="mock", voice="v1")
    assert cached_path == audio_path


def test_tts_service_purge_audio_cache(tmp_path: Path) -> None:
    """Vérifie que purge_audio_cache supprime les fichiers tts_ et libère l'espace."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path

    service = TTSService(media_manager=media_mgr)

    # Création de faux fichiers audio et d'un fichier image à ne pas toucher
    tts1 = tmp_path / "tts_12345.mp3"
    tts2 = tmp_path / "tts_67890.wav"
    image = tmp_path / "image.png"

    tts1.write_bytes(b"A" * 1000)
    tts2.write_bytes(b"B" * 2000)
    image.write_bytes(b"C" * 500)

    count, freed = service.purge_audio_cache(only_orphans=False)
    assert count == 2
    assert freed == 3000
    assert not tts1.exists()
    assert not tts2.exists()
    assert image.exists()  # L'image est préservée

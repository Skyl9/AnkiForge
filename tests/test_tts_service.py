"""Tests unitaires pour le service de synthèse vocale (TTSService) et TextNormalizer.

Couvre le nettoyage HTML/Cloze, le cache MD5, les providers et la déduplication média.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ankidraft.services.cards.media_manager import MediaManager
from ankidraft.services.cards.tts_service import (
    KokoroSidecarProvider,
    SystemSpeechProvider,
    TextNormalizer,
    TTSProvider,
    TTSService,
)

pytestmark = pytest.mark.integration


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

    def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
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


@pytest.mark.slow
def test_system_speech_provider_available_or_graceful() -> None:
    """Vérifie que SystemSpeechProvider ne crash pas et expose des voix."""
    provider = SystemSpeechProvider()
    voices = provider.get_voices()
    assert isinstance(voices, list)
    assert len(voices) >= 1


def test_piper_executable_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la détection de l'exécutable Piper dans un sous-dossier piper/."""
    from ankidraft.services.cards.tts_service import PiperSidecarProvider

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

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
    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

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
    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

    provider = KokoroSidecarProvider()
    with pytest.raises(RuntimeError, match="Le runner Kokoro est introuvable"):
        provider.synthesize("Bonjour")


def test_kokoro_synthesize_subprocess_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la synthèse par subprocess avec code retour 0 et production de fichier WAV."""
    import subprocess

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

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

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

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


def test_kokoro_install_runner_creates_executable_and_reports_missing_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que install_runner déploie run.py mais que is_functional() signale les modèles manquants."""
    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

    KokoroSidecarProvider.clear_functional_cache()
    assert KokoroSidecarProvider.has_runner() is False
    assert KokoroSidecarProvider.has_models() is False

    ok = KokoroSidecarProvider.install_runner()
    assert ok is True

    run_py = tmp_path / "tools" / "tts" / "kokoro" / "run.py"
    assert run_py.exists()
    assert run_py.stat().st_size > 100

    # Runner présent mais modèles ONNX absents
    assert KokoroSidecarProvider.has_runner() is True
    assert KokoroSidecarProvider.has_models() is False

    functional, msg = KokoroSidecarProvider.is_functional()
    assert functional is False
    assert "Modèles ONNX manquants" in msg

    # Après ajout des fichiers de modèles ONNX
    kokoro_dir = tmp_path / "tools" / "tts" / "kokoro"
    (kokoro_dir / "kokoro-v1.0.onnx").write_bytes(b"dummy_onnx")
    (kokoro_dir / "voices-v1.0.bin").write_bytes(b"dummy_voices")

    assert KokoroSidecarProvider.has_models() is True
    functional2, msg2 = KokoroSidecarProvider.is_functional(force_refresh=True)
    assert functional2 is True
    assert msg2 == "Opérationnel"


def test_kokoro_download_and_install_downloads_models_and_marks_operational(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que download_and_install_kokoro déploie le runner et télécharge les modèles vérifiés."""
    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)
    KokoroSidecarProvider.clear_functional_cache()

    download_calls: list[tuple[str, Path, str, int]] = []

    def fake_download(url: str, dest: Path, sha: str, *, max_bytes: int, **kwargs: object) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"downloaded_content")
        download_calls.append((url, dest, sha, max_bytes))

    monkeypatch.setattr("ankidraft.services.cards.tts_service._download_verified", fake_download)
    monkeypatch.setattr(KokoroSidecarProvider, "ensure_venv", classmethod(lambda cls, **kwargs: None))

    progress_messages: list[str] = []
    service = TTSService()
    success = service.download_and_install_kokoro(progress_callback=progress_messages.append)

    assert success is True
    kokoro_dir = tmp_path / "tools" / "tts" / "kokoro"
    assert (kokoro_dir / "run.py").is_file()
    assert (kokoro_dir / "kokoro-v1.0.onnx").is_file()
    assert (kokoro_dir / "voices-v1.0.bin").is_file()

    # Vérification des URLs et empreintes SHA-256 officielles
    assert len(download_calls) == 2
    model_call = next(c for c in download_calls if "kokoro-v1.0.onnx" in c[0])
    voices_call = next(c for c in download_calls if "voices-v1.0.bin" in c[0])
    assert model_call[2] == "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"
    assert voices_call[2] == "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"

    assert KokoroSidecarProvider.has_models() is True
    functional, _ = KokoroSidecarProvider.is_functional(force_refresh=True)
    assert functional is True


def test_kokoro_runner_script_fails_cleanly_without_fallback_tone_when_models_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que run.py quitte en erreur sans émettre de faux bip 440 Hz si les modèles sont absents."""
    import subprocess
    import sys

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

    KokoroSidecarProvider.install_runner()
    run_py = tmp_path / "tools" / "tts" / "kokoro" / "run.py"
    out_wav = tmp_path / "output.wav"

    res = subprocess.run(
        [sys.executable, str(run_py), "--text", "Test synth", "--output", str(out_wav)],
        capture_output=True,
        check=False,
    )
    # Le runner doit sortir en code d'erreur (non-zéro) et ne pas générer le fichier wav
    assert res.returncode != 0
    assert not out_wav.exists()
    assert b"introuvables" in res.stderr.lower() or b"introuvables" in res.stdout.lower()


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


def test_sidecar_providers_functional_cache() -> None:
    """Vérifie que PiperSidecarProvider et KokoroSidecarProvider mettent en cache le résultat de is_functional."""
    from unittest.mock import patch

    from ankidraft.services.cards.tts_service import KokoroSidecarProvider, PiperSidecarProvider

    PiperSidecarProvider.clear_functional_cache()
    KokoroSidecarProvider.clear_functional_cache()

    with patch.object(PiperSidecarProvider, "get_piper_executable", return_value=Path("/bin/piper")), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        # Premier appel : exécute subprocess.run
        ok1, msg1 = PiperSidecarProvider.is_functional()
        assert ok1 is True
        assert mock_run.call_count == 1

        # Second appel : résultat mis en cache, pas de subprocess.run
        ok2, msg2 = PiperSidecarProvider.is_functional()
        assert ok2 is True
        assert mock_run.call_count == 1

        # Forcer le rafraîchissement
        ok3, msg3 = PiperSidecarProvider.is_functional(force_refresh=True)
        assert ok3 is True
        assert mock_run.call_count == 2

        # Invalidation du cache
        PiperSidecarProvider.clear_functional_cache()
        PiperSidecarProvider.is_functional()
        assert mock_run.call_count == 3

    with (
        patch.object(KokoroSidecarProvider, "get_kokoro_command", return_value=["python", "run.py"]),
        patch.object(KokoroSidecarProvider, "has_models", return_value=True),
        patch("subprocess.run") as mock_run_k,
    ):
        mock_run_k.return_value = MagicMock(returncode=0)

        ok_k1, _ = KokoroSidecarProvider.is_functional()
        assert ok_k1 is True
        assert mock_run_k.call_count == 1

        ok_k2, _ = KokoroSidecarProvider.is_functional()
        assert ok_k2 is True
        assert mock_run_k.call_count == 1


KokoroSidecarProvider.clear_functional_cache()


class MockFailingEdgeTTSProvider:
    """Mock provider that simulates Edge-TTS failing with a 403-like error."""

    id = "edge-tts"
    display_name = "Edge-TTS (Mock Failing)"

    def is_available(self) -> bool:
        return True

    def get_voices(self) -> list[dict[str, str]]:
        return [{"id": "fr-FR-VivienneMultilingualNeural", "name": "Vivienne", "lang": "fr-FR"}]

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        # Simule une erreur 403 Forbidden d'edge-tts
        raise RuntimeError("Edge-TTS synthesis failed: 403 Forbidden")


class MockSuccessFallbackProvider:
    """Mock provider that simulates a successful fallback (Piper/System)."""

    id = "piper"
    display_name = "Piper TTS (Mock Success)"

    def is_available(self) -> bool:
        return True

    def get_voices(self) -> list[dict[str, str]]:
        return [{"id": "fr_FR-siwis-low", "name": "Piper French", "lang": "fr-FR"}]

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> bytes:
        return b"FALLBACK_AUDIO_DATA_FOR_" + text.encode("utf-8")


def test_tts_service_fallback_on_edge_tts_failure(tmp_path: Path) -> None:
    """Vérifie le repli transparent vers un moteur de secours quand Edge-TTS échoue (ex: 403)."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path

    service = TTSService(media_manager=media_mgr)

    # Remplacer edge-tts par un mock qui échoue
    service._providers["edge-tts"] = MockFailingEdgeTTSProvider()
    # Ajouter un provider de repli qui réussit
    service._providers["piper"] = MockSuccessFallbackProvider()

    # La synthèse doit réussir via le repli Piper
    tag, path = service.synthesize("Bonjour le monde", engine="edge-tts")

    assert tag.startswith("[sound:")
    assert tag.endswith(".wav]")  # Piper produit du WAV
    assert path.exists()
    assert path.read_bytes() == b"FALLBACK_AUDIO_DATA_FOR_Bonjour le monde"


def test_tts_service_fallback_chain_exhausted_raises(tmp_path: Path) -> None:
    """Vérifie qu'une erreur est levée quand tous les moteurs échouent."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path

    service = TTSService(media_manager=media_mgr)

    # Tous les providers échouent
    class MockAlwaysFailingProvider(TTSProvider):
        id = "edge-tts"
        display_name = "Always Failing"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return []

        def synthesize(self, text: str, **kwargs: object) -> bytes:
            raise RuntimeError("Simulated failure")

    service._providers["edge-tts"] = MockAlwaysFailingProvider()
    service._providers["piper"] = MockAlwaysFailingProvider()
    service._providers["system"] = MockAlwaysFailingProvider()

    with pytest.raises(RuntimeError, match="Tous les moteurs TTS ont échoué"):
        service.synthesize("Test", engine="edge-tts")


def test_tts_service_fallback_preserves_cache_key_differentiation(tmp_path: Path) -> None:
    """Vérifie que le cache différencie correctement les moteurs utilisés (edge-tts vs piper)."""
    media_mgr = MediaManager()
    media_mgr.media_dir = tmp_path

    service = TTSService(media_manager=media_mgr)

    # Premier appel : edge-tts échoue, piper réussit
    service._providers["edge-tts"] = MockFailingEdgeTTSProvider()
    service._providers["piper"] = MockSuccessFallbackProvider()

    tag1, path1 = service.synthesize("Test cache", engine="edge-tts")
    assert "piper" in tag1 or path1.suffix == ".wav"  # Piper a été utilisé

    # Deuxième appel : edge-tts maintenant "disponible" (mock success)
    class MockSuccessEdgeTTSProvider(TTSProvider):
        id = "edge-tts"
        display_name = "Edge-TTS (Mock Success)"

        def is_available(self) -> bool:
            return True

        def get_voices(self, target_lang: str | None = None) -> list[dict[str, str]]:
            return [{"id": "fr-FR-VivienneMultilingualNeural", "name": "Vivienne", "lang": "fr-FR"}]

        def synthesize(self, text: str, **kwargs: object) -> bytes:
            return b"EDGE_TTS_AUDIO_DATA_FOR_" + text.encode("utf-8")

    service._providers["edge-tts"] = MockSuccessEdgeTTSProvider()

    # Le cache doit être différent car le moteur est différent
    tag2, path2 = service.synthesize("Test cache", engine="edge-tts")
    assert tag1 != tag2  # Clés de cache différentes car moteurs différents
    assert path1 != path2
    assert path2.read_bytes().startswith(b"EDGE_TTS_AUDIO_DATA_FOR_")


def test_piper_is_functional_rosetta_architecture_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que [Errno 86] Bad CPU type est capturé et explicité comme prérequis Rosetta 2."""
    import subprocess

    from ankidraft.services.cards.tts_service import PiperSidecarProvider

    PiperSidecarProvider.clear_functional_cache()
    fake_exe = tmp_path / "piper"
    fake_exe.touch(mode=0o755)

    monkeypatch.setattr(PiperSidecarProvider, "get_piper_executable", lambda: fake_exe)

    def fake_run_bad_cpu(*args: object, **kwargs: object) -> None:
        raise OSError(86, "Bad CPU type in executable: " + str(fake_exe))

    monkeypatch.setattr(subprocess, "run", fake_run_bad_cpu)

    ok, msg = PiperSidecarProvider.is_functional()
    assert ok is False
    assert "Rosetta 2" in msg
    assert "softwareupdate --install-rosetta" in msg


def test_piper_executable_resolution_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la détection de piper dans le venv Python dédié tools/tts/piper/venv."""
    import platform

    from ankidraft.services.cards.tts_service import PiperSidecarProvider

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

    bin_dir = tmp_path / "tools" / "tts" / "piper" / "venv" / ("Scripts" if platform.system() == "Windows" else "bin")
    bin_dir.mkdir(parents=True)
    piper_bin = bin_dir / ("piper.exe" if platform.system() == "Windows" else "piper")
    piper_bin.write_text("#!/bin/sh\necho 'piper-venv'")
    piper_bin.chmod(0o755)

    detected = PiperSidecarProvider.get_piper_executable()
    assert detected is not None
    assert detected == piper_bin


def test_piper_ensure_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie la création du venv piper-tts via ensure_venv."""
    import platform
    import subprocess

    from ankidraft.services.cards.tts_service import PiperSidecarProvider

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: False)
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/uv" if cmd == "uv" else None)

    commands_run: list[list[str]] = []

    def fake_subprocess_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        commands_run.append(cmd)
        # Créer le binaire factice piper attendu dans le venv
        bin_dir = tmp_path / "tools" / "tts" / "piper" / "venv" / ("Scripts" if platform.system() == "Windows" else "bin")
        bin_dir.mkdir(parents=True, exist_ok=True)
        exe = bin_dir / ("piper.exe" if platform.system() == "Windows" else "piper")
        if not exe.exists():
            exe.write_text("#!/bin/sh\necho piper")
            exe.chmod(0o755)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    exe_path = PiperSidecarProvider.ensure_venv()
    assert exe_path is not None
    assert exe_path.exists()
    assert any("venv" in cmd and str(tmp_path) in str(cmd) for cmd in commands_run)
    assert any("piper-tts" in cmd for cmd in commands_run)


def test_piper_voice_catalog_and_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie le catalogue des voix officielles et le téléchargement d'une voix (ex: ja_JP)."""
    from ankidraft.services.cards.tts_service import (
        _PIPER_VOICE_CATALOG,
        PiperSidecarProvider,
        TTSService,
    )

    assert "fr_FR-siwis-low" in _PIPER_VOICE_CATALOG
    assert "ja_JP-hi_fi_captain-medium" in _PIPER_VOICE_CATALOG
    assert "en_US-lessac-medium" in _PIPER_VOICE_CATALOG

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.environment.is_testing", lambda: True)

    downloaded_urls: list[str] = []

    def fake_download_verified(url: str, dest: Path, sha256: str, **kwargs: object) -> None:
        downloaded_urls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("mock content")

    monkeypatch.setattr("ankidraft.services.cards.tts_service._download_verified", fake_download_verified)

    service = TTSService()
    success = service.download_piper_voice("ja_JP-hi_fi_captain-medium")
    assert success is True
    assert len(downloaded_urls) == 2
    assert any("ja_JP-hi_fi_captain-medium.onnx" in u for u in downloaded_urls)
    assert any("ja_JP-hi_fi_captain-medium.onnx.json" in u for u in downloaded_urls)

    # Vérification que PiperSidecarProvider.get_voices liste maintenant cette voix
    voices = PiperSidecarProvider().get_voices()
    voice_ids = [v["id"] for v in voices]
    assert any("ja_JP-hi_fi_captain-medium" in vid for vid in voice_ids)


def test_piper_download_and_install_macos_arm64(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que download_and_install_piper sur macOS arm64 privilégie ensure_venv avec piper-tts natif."""
    import platform

    from ankidraft.services.cards.tts_service import PiperSidecarProvider, TTSService

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")

    venv_called = False
    fake_piper_exe = tmp_path / "tools" / "tts" / "piper" / "venv" / "bin" / "piper"

    def fake_ensure_venv(progress_callback: object = None) -> Path:
        nonlocal venv_called
        venv_called = True
        fake_piper_exe.parent.mkdir(parents=True, exist_ok=True)
        fake_piper_exe.touch(mode=0o755)
        return fake_piper_exe

    monkeypatch.setattr(PiperSidecarProvider, "ensure_venv", fake_ensure_venv)

    downloaded_voices: list[str] = []

    def fake_download_voice(self: object, voice_id: str, progress_callback: object = None) -> bool:
        downloaded_voices.append(voice_id)
        # Créer le faux fichier de voix ONNX
        v_dest = tmp_path / "tools" / "tts" / "voices" / f"{voice_id}.onnx"
        v_dest.parent.mkdir(parents=True, exist_ok=True)
        v_dest.touch()
        return True

    monkeypatch.setattr(TTSService, "download_piper_voice", fake_download_voice)

    res = TTSService.download_and_install_piper()
    assert res is True
    assert venv_called is True
    assert "fr_FR-siwis-low" in downloaded_voices


def test_piper_download_and_install_standalone_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie l'extraction de l'archive officielle Piper sur architecture x86_64 / Linux."""
    import platform

    from ankidraft.services.cards.tts_service import PiperSidecarProvider, TTSService

    monkeypatch.setattr("ankidraft.services.cards.tts_service.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("ankidraft.utils.paths.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")

    downloaded: list[str] = []

    def fake_download_verified(url: str, dest: Path, sha256: str, **kwargs: object) -> None:
        downloaded.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.touch()

    monkeypatch.setattr("ankidraft.services.cards.tts_service._download_verified", fake_download_verified)
    monkeypatch.setattr("ankidraft.services.cards.tts_service.safe_extract_tar", lambda *args, **kwargs: None)

    fake_exe = tmp_path / "tools" / "tts" / "piper" / "piper"
    fake_exe.parent.mkdir(parents=True, exist_ok=True)
    fake_exe.touch(mode=0o755)
    monkeypatch.setattr(PiperSidecarProvider, "get_piper_executable", lambda: fake_exe)
    monkeypatch.setattr(TTSService, "download_piper_voice", lambda *args, **kwargs: True)

    success = TTSService.download_and_install_piper()
    assert success is True
    assert any("piper_linux_x86_64.tar.gz" in u for u in downloaded)


def test_system_speech_provider_macos_parses_all_voices_and_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que SystemSpeechProvider sous macOS ne tronque plus à 15 voix et parse les noms complexes."""
    import platform
    import subprocess

    fake_say_output = """Albert              en_US    # Hello! My name is Albert.
Alice               it_IT    # Ciao! Mi chiamo Alice.
Alva                sv_SE    # Hej! Jag heter Alva.
Amélie (Français (Canada)) fr_CA    # Bonjour! Je m’appelle Amélie.
Anna                de_DE    # Hallo! Ich heiße Anna.
Bad News            en_US    # Hello! My name is Bad News.
Carmit              he_IL    # שלום, שמי כרמית.
Damayanti           id_ID    # Halo! Nama saya Damayanti.
Daniel              en_GB    # Hello! My name is Daniel.
Daria               bg_BG    # Hello! My name is Daria.
Eddy (Allemand (Allemagne)) de_DE    # Hallo! Ich heiße Eddy.
Eddy (Anglais (R.-U.)) en_GB    # Hello! My name is Eddy.
Eddy (Anglais (É.-U.)) en_US    # Hello! My name is Eddy.
Eddy (Espagnol (Espagne)) es_ES    # ¡Hola! Me llamo Eddy.
Eddy (Français (France)) fr_FR    # Bonjour, je m’appelle Eddy.
Eddy (Japonais (Japon)) ja_JP    # こんにちは! 私の名前はEddyです。
Ellen               nl_BE    # Hallo, mijn naam is Ellen.
Flo (Français (France)) fr_FR    # Bonjour, je m’appelle Flo.
Jacques             fr_FR    # Bonjour, je m’appelle Jacques.
Kyoko (Japonais (Japon)) ja_JP    # こんにちは! 私の名前はKyokoです。
Kyoko (Japonais (Japon)) ja_JP    # こんにちは! 私の名前はKyokoです.
Thomas (Français (France)) fr_FR    # Bonjour, je m’appelle Thomas.
Zuzana              cs_CZ    # Dobrý den, jmenuji se Zuzana.
"""

    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: fake_say_output)

    provider = SystemSpeechProvider()
    voices = provider.get_voices()

    # Plus de 15 voix doivent être retournées (aucune troncature arbitraire)
    assert len(voices) > 15

    # Déduplication de Kyoko (présent 2 fois dans la sortie)
    kyoko_voices = [v for v in voices if "Kyoko" in v["id"]]
    assert len(kyoko_voices) == 1
    assert kyoko_voices[0]["lang"] == "ja_JP"
    assert kyoko_voices[0]["id"] == "Kyoko (Japonais (Japon))"

    # Vérification du nom avec espaces multiples (Bad News)
    bad_news = next((v for v in voices if v["id"] == "Bad News"), None)
    assert bad_news is not None
    assert bad_news["lang"] == "en_US"

    # Vérification de voix française au-delà du 15e index
    fr_voices = [v for v in voices if v["lang"] == "fr_FR"]
    assert len(fr_voices) >= 3


def test_system_speech_provider_filter_by_target_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie le filtrage optionnel par target_lang sur SystemSpeechProvider."""
    import platform
    import subprocess

    fake_say_output = """Albert              en_US    # Hello!
Eddy (Français (France)) fr_FR    # Bonjour
Eddy (Japonais (Japon)) ja_JP    # こんにちは!
Kyoko (Japonais (Japon)) ja_JP    # こんにちは!
Thomas (Français (France)) fr_FR    # Bonjour
"""
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: fake_say_output)

    provider = SystemSpeechProvider()

    # Filtrage japonais avec "ja"
    ja_voices = provider.get_voices(target_lang="ja")
    assert len(ja_voices) == 2
    assert all(v["lang"] == "ja_JP" for v in ja_voices)
    assert any("Kyoko" in v["id"] for v in ja_voices)

    # Filtrage japonais avec "ja_JP"
    ja_jp_voices = provider.get_voices(target_lang="ja_JP")
    assert len(ja_jp_voices) == 2

    # Filtrage français avec "fr"
    fr_voices = provider.get_voices(target_lang="fr")
    assert len(fr_voices) == 2
    assert all(v["lang"] == "fr_FR" for v in fr_voices)

    # Filtrage langue inexistante
    empty = provider.get_voices(target_lang="ru")
    assert empty == []

    # Vérification cas limite de voix sans locale renseignée
    from ankidraft.services.cards.tts_service import match_tts_lang

    assert match_tts_lang("", "ja") is False
    assert match_tts_lang("ja_JP", None) is True
    assert match_tts_lang("ja_JP", "") is True


def test_tts_service_facade_get_voices(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie que la façade TTSService expose get_voices avec filtrage target_lang."""
    import platform
    import subprocess

    fake_say_output = """Kyoko (Japonais (Japon)) ja_JP    # こんにちは!
Thomas (Français (France)) fr_FR    # Bonjour
"""
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(subprocess, "check_output", lambda *args, **kwargs: fake_say_output)

    service = TTSService()
    ja_voices = service.get_voices(engine="system", target_lang="ja")
    assert len(ja_voices) == 1
    assert ja_voices[0]["id"] == "Kyoko (Japonais (Japon))"


def test_system_speech_provider_fallbacks_and_other_platforms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vérifie les replis d'erreur et le comportement multi-plateforme de SystemSpeechProvider."""
    import platform
    import subprocess

    provider = SystemSpeechProvider()

    # 1. macOS avec échec de subprocess
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    def failing_check_output(*args: object, **kwargs: object) -> str:
        raise subprocess.SubprocessError("say command failed")

    monkeypatch.setattr(subprocess, "check_output", failing_check_output)

    # Sans target_lang -> repli Thomas
    fallback_voices = provider.get_voices()
    assert len(fallback_voices) == 1
    assert fallback_voices[0]["id"] == "Thomas"

    # Avec target_lang="ja" lors d'une erreur -> liste vide (pas de fausse voix japonaise)
    assert provider.get_voices(target_lang="ja") == []
    # Avec target_lang="fr" lors d'une erreur -> repli Thomas (fr_FR correspond)
    assert len(provider.get_voices(target_lang="fr")) == 1

    # 2. Plateforme non-Darwin (Linux / Windows)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    linux_voices = provider.get_voices()
    assert len(linux_voices) == 1
    assert linux_voices[0]["id"] == "default"
    assert provider.get_voices(target_lang="ja") == []
    assert len(provider.get_voices(target_lang="fr")) == 1

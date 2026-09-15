"""
Tests d'intégration pour l'étape DAG AUDIO_TTS dans PipelineOrchestrator.
Vérifie l'enrichissement par lot des cartes mémoires (mode append et replace_field).
"""

import json
from pathlib import Path
from unittest.mock import patch

from ankiforge.database.models import PipelineStepModel
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState


class MockTTSSvc:
    def synthesize(
        self,
        text: str,
        engine: str = "edge-tts",
        voice: str | None = None,
        rate: str = "+0%",
        pitch: str = "+0Hz",
        strip_cloze: bool = True,
    ) -> tuple[str, Path]:
        h = f"{len(text)}_{text[:4]}"
        return f"[sound:tts_{h}.mp3]", Path(f"/fake/path/tts_{h}.mp3")


def test_orchestrator_audio_tts_append_mode() -> None:
    """Vérifie l'étape AUDIO_TTS avec le mode 'append' (concaténation au champ source)."""
    initial_cards = [
        {"Front": "Bonjour", "Back": "Hello"},
        {"Front": "{{c1::Pomme}}", "Back": "Apple"},
    ]

    state = PipelineRunState()
    state.set_variable("generated_cards", initial_cards)

    step = PipelineStepModel(
        step_order=1,
        step_type="AUDIO_TTS",
        config_data=json.dumps(
            {
                "source_field": "Front",
                "target_field": "Front",
                "insertion_mode": "append",
                "engine": "edge-tts",
                "voice": "fr-FR-VivienneMultilingualNeural",
                "strip_cloze": True,
            }
        ),
    )

    orchestrator = PipelineOrchestrator(steps=[step], initial_state=state)

    progress_reports: list[tuple[int, int, str]] = []
    orchestrator.signals.step_progress.connect(lambda cur, tot, msg: progress_reports.append((cur, tot, msg)))

    with patch("ankiforge.services.cards.tts_service.get_tts_service", return_value=MockTTSSvc()):
        orchestrator._execute_audio_tts(step)

    updated_cards = state.get_variable("generated_cards")
    assert len(updated_cards) == 2

    # Carte 1 : "Bonjour [sound:tts_...mp3]"
    assert updated_cards[0]["Front"].startswith("Bonjour [sound:tts_")
    assert updated_cards[0]["Front"].endswith(".mp3]")
    assert updated_cards[0]["Back"] == "Hello"

    # Carte 2 : cloze préservé dans le champ texte avec tag audio
    assert "{{c1::Pomme}}" in updated_cards[1]["Front"]
    assert "[sound:tts_" in updated_cards[1]["Front"]

    # Progression signalée
    assert len(progress_reports) == 2
    assert progress_reports[0][0] == 1
    assert progress_reports[0][1] == 2
    assert progress_reports[1][0] == 2


def test_orchestrator_audio_tts_replace_field_mode() -> None:
    """Vérifie l'étape AUDIO_TTS avec le mode 'replace_field' vers un champ dédié."""
    initial_cards = [
        {"fields": {"Front": "Guten Tag", "Back": "Good day", "Audio": ""}},
    ]

    state = PipelineRunState()
    state.set_variable("generated_cards", initial_cards)

    step = PipelineStepModel(
        step_order=1,
        step_type="AUDIO_TTS",
        config_data=json.dumps(
            {
                "source_field": "Front",
                "target_field": "Audio",
                "insertion_mode": "replace_field",
                "engine": "edge-tts",
            }
        ),
    )

    orchestrator = PipelineOrchestrator(steps=[step], initial_state=state)

    with patch("ankiforge.services.cards.tts_service.get_tts_service", return_value=MockTTSSvc()):
        orchestrator._execute_audio_tts(step)

    updated_cards = state.get_variable("generated_cards")
    assert len(updated_cards) == 1
    # Front est resté intact
    assert updated_cards[0]["fields"]["Front"] == "Guten Tag"
    # Audio a été assigné
    assert updated_cards[0]["fields"]["Audio"].startswith("[sound:tts_")
    assert updated_cards[0]["fields"]["Audio"].endswith(".mp3]")


def test_orchestrator_audio_tts_resilience_to_failures() -> None:
    """Vérifie que l'échec de synthèse d'une carte ne bloque pas le reste du lot."""
    cards = [
        {"Front": "Card 1", "Back": "Answer 1"},
        {"Front": "Card 2 Error", "Back": "Answer 2"},
        {"Front": "Card 3", "Back": "Answer 3"},
    ]

    state = PipelineRunState()
    state.set_variable("generated_cards", cards)

    class FlakyTTSSvc:
        def synthesize(self, text: str, **kwargs: object) -> tuple[str, Path]:
            if "Error" in text:
                raise RuntimeError("Erreur réseau simulée")
            return f"[sound:{text}.mp3]", Path(f"/fake/{text}.mp3")

    step = PipelineStepModel(
        step_order=1,
        step_type="AUDIO_TTS",
        config_data=json.dumps({"source_field": "Front", "target_field": "Front"}),
    )

    orchestrator = PipelineOrchestrator(steps=[step], initial_state=state)

    with patch("ankiforge.services.cards.tts_service.get_tts_service", return_value=FlakyTTSSvc()):
        orchestrator._execute_audio_tts(step)

    updated = state.get_variable("generated_cards")
    assert "[sound:Card 1.mp3]" in updated[0]["Front"]
    assert "[sound:" not in updated[1]["Front"]  # Échec ignoré gracieusement
    assert "[sound:Card 3.mp3]" in updated[2]["Front"]

"""
Tests unitaires et d'interface headless pour MCP-ADV-04 :
Streaming Extended Thinking et Repli Automatique (ThoughtStepWidget, ConsultantWorker, ConsultantView).
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.viewmodels.consultant_viewmodel import ConsultantViewModel
from ankiforge.ui.views.consultant_view.widgets.thought_step_widget import ThoughtStepWidget

# ---------------------------------------------------------------------------
# ThoughtStepWidget — Unit Tests
# ---------------------------------------------------------------------------


class TestThoughtStepWidgetExtendedThinking:
    """Teste le streaming live, le chronomètre et l'auto-repli du ThoughtStepWidget."""

    def test_initial_state_not_running(self, qtbot: Any) -> None:
        """Un widget créé avec is_running=False doit afficher l'icône cerveau et le titre statique."""
        w = ThoughtStepWidget(step=1, thought_text="Voici ma pensée", is_running=False)
        qtbot.addWidget(w)
        assert not w.is_running
        assert "Réflexion" in w.lbl_title.text()
        assert w.lbl_content.isHidden()

    def test_initial_state_running(self, qtbot: Any) -> None:
        """Un widget créé avec is_running=True doit afficher le spinner et le titre actif."""
        w = ThoughtStepWidget(step=1, thought_text="", is_running=True)
        qtbot.addWidget(w)
        assert w.is_running
        assert "en cours" in w.lbl_title.text()

    def test_append_delta_accumulates_text(self, qtbot: Any) -> None:
        """append_delta accumule le texte et active le streaming."""
        w = ThoughtStepWidget(step=1, thought_text="", is_running=False)
        qtbot.addWidget(w)

        w.append_delta("Première ")
        w.append_delta("pensée.")

        assert w.get_thought_text() == "Première pensée."
        assert w.is_running
        assert w.lbl_content.text() == "Première pensée."

    def test_append_delta_starts_timer(self, qtbot: Any) -> None:
        """append_delta démarre le timer interne."""
        w = ThoughtStepWidget(step=1, thought_text="", is_running=False)
        qtbot.addWidget(w)

        w.append_delta("début...")
        assert w._timer.isActive()

    def test_finish_thinking_stops_timer(self, qtbot: Any) -> None:
        """finish_thinking stoppe le timer et replie le widget."""
        w = ThoughtStepWidget(step=1, thought_text="Réflexion complète.", is_running=True)
        qtbot.addWidget(w)
        assert w._timer.isActive()

        w.finish_thinking(duration_seconds=2.5, tokens_count=120)

        assert not w._timer.isActive()
        assert not w.is_running

    def test_finish_thinking_auto_collapse(self, qtbot: Any) -> None:
        """Après finish_thinking, le contenu doit être masqué (replié par défaut)."""
        w = ThoughtStepWidget(step=1, thought_text="Ma réflexion.", is_running=True)
        qtbot.addWidget(w)
        # Déplie pour vérifier le repli automatique
        w.lbl_content.show()

        w.finish_thinking(duration_seconds=1.0, tokens_count=50)

        assert w.lbl_content.isHidden()
        assert "Détails" in w.btn_toggle.text()

    def test_finish_thinking_updates_badge(self, qtbot: Any) -> None:
        """finish_thinking affiche durée et tokens dans le badge d'audit."""
        w = ThoughtStepWidget(step=1, thought_text="Réflexion.", is_running=True)
        qtbot.addWidget(w)

        w.finish_thinking(duration_seconds=3.4, tokens_count=820)

        title_text = w.lbl_title.text()
        assert "3.4s" in title_text
        assert "820" in title_text

    def test_toggle_content_visibility(self, qtbot: Any) -> None:
        """L'utilisateur peut déplier/replier manuellement après la réflexion."""
        w = ThoughtStepWidget(step=1, thought_text="Texte de pensée.", is_running=False)
        qtbot.addWidget(w)

        # Initialement replié
        assert w.lbl_content.isHidden()

        # Déplie
        w._toggle_content()
        assert not w.lbl_content.isHidden()
        assert "Masquer" in w.btn_toggle.text()

        # Replie
        w._toggle_content()
        assert w.lbl_content.isHidden()
        assert "Détails" in w.btn_toggle.text()

    def test_estimate_tokens_non_empty(self, qtbot: Any) -> None:
        """L'estimation de tokens pour un texte non vide est strictement positive."""
        assert ThoughtStepWidget._estimate_tokens("Bonjour je suis une réflexion étendue.") > 0

    def test_estimate_tokens_empty(self, qtbot: Any) -> None:
        """L'estimation de tokens pour un texte vide retourne 0."""
        assert ThoughtStepWidget._estimate_tokens("") == 0

    def test_format_duration_seconds(self, qtbot: Any) -> None:
        """La durée en dessous de 60s est affichée en secondes décimales."""
        w = ThoughtStepWidget()
        assert w._format_duration(3.4) == "3.4s"
        assert w._format_duration(59.9) == "59.9s"

    def test_format_duration_minutes(self, qtbot: Any) -> None:
        """La durée au-dessus de 60s est affichée en mm:ss."""
        w = ThoughtStepWidget()
        assert w._format_duration(65.0) == "01:05"
        assert w._format_duration(130.0) == "02:10"

    def test_update_text_finish_thinking_called(self, qtbot: Any) -> None:
        """update_text(is_running=False) doit appeler finish_thinking."""
        w = ThoughtStepWidget(step=1, thought_text="", is_running=True)
        qtbot.addWidget(w)

        w.update_text("Réflexion terminée.", is_running=False)

        assert not w.is_running
        assert w.lbl_content.isHidden()
        assert w.get_thought_text() == "Réflexion terminée."

    def test_streaming_title_contains_duration(self, qtbot: Any) -> None:
        """Pendant le streaming, le titre contient la durée courante."""
        w = ThoughtStepWidget(step=1, thought_text="", is_running=True)
        qtbot.addWidget(w)
        # Force le démarrage du chrono
        w._start_time = time.perf_counter() - 2.5
        w._update_running_title()
        assert "en cours" in w.lbl_title.text()


# ---------------------------------------------------------------------------
# ConsultantWorker — Thought Delta Signal
# ---------------------------------------------------------------------------


class TestConsultantWorkerThoughtDelta:
    """Vérifie que thought_delta_signal est bien émis lors d'un thought_delta dans le stream."""

    def test_thought_delta_signal_emitted(self, qtbot: Any) -> None:
        """ConsultantWorker émet thought_delta_signal pour les events thought_delta du moteur."""
        mock_engine_events = [
            {"type": "thought_delta", "step": 1, "delta": "Je réfléchis "},
            {"type": "thought_delta", "step": 1, "delta": "intensément."},
            {"type": "thought", "step": 1, "content": "Je réfléchis intensément.", "is_running": False},
            {"type": "text_delta", "delta": "Voici ma réponse."},
            {"type": "text", "content": "Voici ma réponse."},
            {"type": "finished", "content": "Voici ma réponse.", "next_steps": [], "tokens_used": 50, "cost_usd": 0.001, "token_budget": 50000, "cost_budget": 0.5},
        ]

        async def fake_chat_stream(*args: Any, **kwargs: Any) -> Any:
            for ev in mock_engine_events:
                yield ev

        collected_deltas: list[tuple[int, str]] = []

        worker = ConsultantWorker(instruction="Test streaming thought delta")

        with patch("ankiforge.services.workers.consultant_worker.ConsultantEngine") as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.chat_stream = fake_chat_stream
            MockEngine.return_value = mock_engine_instance

            with qtbot.waitSignal(worker.finished_signal, timeout=5000):
                worker.thought_delta_signal.connect(lambda step, delta: collected_deltas.append((step, delta)))
                worker.start()

        assert len(collected_deltas) == 2
        assert collected_deltas[0] == (1, "Je réfléchis ")
        assert collected_deltas[1] == (1, "intensément.")

    def test_thought_emitted_signal_still_fires(self, qtbot: Any) -> None:
        """Le signal thought_emitted continue d'être émis après un thought_delta."""
        mock_engine_events = [
            {"type": "thought_delta", "step": 1, "delta": "Un delta"},
            {"type": "thought", "step": 1, "content": "Pensée complète.", "is_running": False},
            {"type": "text", "content": "Réponse."},
            {"type": "finished", "content": "Réponse.", "next_steps": [], "tokens_used": 10, "cost_usd": 0.001, "token_budget": 50000, "cost_budget": 0.5},
        ]

        async def fake_stream(*args: Any, **kwargs: Any) -> Any:
            for ev in mock_engine_events:
                yield ev

        thought_events: list[tuple[int, str, bool]] = []
        worker = ConsultantWorker(instruction="Test thought signal after delta")

        with patch("ankiforge.services.workers.consultant_worker.ConsultantEngine") as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.chat_stream = fake_stream
            MockEngine.return_value = mock_engine_instance

            with qtbot.waitSignal(worker.finished_signal, timeout=5000):
                worker.thought_emitted.connect(lambda s, c, r: thought_events.append((s, c, r)))
                worker.start()

        assert len(thought_events) == 1
        assert thought_events[0] == (1, "Pensée complète.", False)


# ---------------------------------------------------------------------------
# ConsultantViewModel — Thought Delta
# ---------------------------------------------------------------------------


class TestConsultantViewModelThoughtDelta:
    """Vérifie record_thought_delta dans le ViewModel."""

    def test_record_thought_delta_accumulates(self) -> None:
        """record_thought_delta accumule les deltas pour un même step."""

        vm = ConsultantViewModel()

        vm.record_thought_delta(1, "Première partie ")
        vm.record_thought_delta(1, "deuxième partie.")

        # La pensée accumulée pour step=1 doit contenir les deux parties
        found = False
        for step, text in vm._current_thoughts:
            if step == 1:
                assert text == "Première partie deuxième partie."
                found = True
        assert found

    def test_record_thought_delta_emits_signal(self, qtbot: Any) -> None:
        """record_thought_delta émet thought_delta_added."""
        vm = ConsultantViewModel()
        received: list[tuple[int, str]] = []

        vm.thought_delta_added.connect(lambda s, d: received.append((s, d)))
        vm.record_thought_delta(2, "Bonjour monde.")

        assert len(received) == 1
        assert received[0] == (2, "Bonjour monde.")

    def test_record_thought_delta_creates_new_step(self) -> None:
        """record_thought_delta crée une nouvelle entrée pour un step inconnu."""
        vm = ConsultantViewModel()
        vm.record_thought_delta(99, "Delta unique.")
        assert any(s == 99 for s, _ in vm._current_thoughts)

    def test_record_thought_delta_does_not_override_step(self) -> None:
        """Deux deltas sur le même step ne créent pas deux entrées distinctes."""
        vm = ConsultantViewModel()
        vm.record_thought_delta(1, "Alpha ")
        vm.record_thought_delta(1, "Beta.")
        count = sum(1 for s, _ in vm._current_thoughts if s == 1)
        assert count == 1


# ---------------------------------------------------------------------------
# Integration — Streaming persisté dans ConsultantMessageModel.thoughts
# ---------------------------------------------------------------------------


class TestThoughtPersistence:
    """Vérifie que les pensées accumulées sont bien persistées en BDD."""

    def test_thoughts_persist_in_add_assistant_message(self) -> None:
        """Les pensées accumulées doivent être incluses dans add_assistant_message."""
        from ankiforge.database.models import (
            ConsultantMessageModel,
            ConsultantSessionModel,
            db,
        )

        vm = ConsultantViewModel()

        with db.atomic():
            session = ConsultantSessionModel.create(title="Test persist thoughts", created_at=__import__("datetime").datetime.now())
        vm._current_session = session

        # Simuler l'accumulation de deltas dans les pensées
        vm.record_thought_delta(1, "Réflexion ")
        vm.record_thought_delta(1, "complète.")

        msg = vm.add_assistant_message("Réponse finale.")
        assert msg["thoughts"] is not None
        assert len(msg["thoughts"]) > 0

        # Vérifier que la pensée est persistée en BDD
        db_msg = ConsultantMessageModel.select().where(ConsultantMessageModel.session == session).first()
        assert db_msg is not None
        assert db_msg.thoughts is not None

        # Nettoyage
        with db.atomic():
            ConsultantMessageModel.delete().where(ConsultantMessageModel.session == session).execute()
            session.delete_instance()

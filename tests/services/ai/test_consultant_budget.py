"""
Tests unitaires pour le suivi du budget tokens & coûts en temps réel du Consultant IA.
Vérifie le calcul des tokens réels et du coût USD (pricing_service), l'émission des signaux de budget,
et l'interruption préventive automatique au seuil de 80%.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.consultant_engine import ConsultantEngine
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.views.consultant_view.widgets.chat_message_widget import ChatMessageWidget
from ankiforge.ui.views.consultant_view.widgets.session_sidebar import ConsultantSessionSidebar

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_llm_config():
    return LLMConfigModel(
        name="GPT-4o Test",
        provider="openai",
        model_name="gpt-4o",
        temperature=0.7,
        max_tokens=4096,
        is_active=True,
    )


def test_chat_message_widget_budget_badge(qtbot):
    """Vérifie que la bulle de message affiche le badge de consommation budget."""
    msg = ChatMessageWidget("AnkiForge AI", text="Réponse test", is_user=False)
    qtbot.addWidget(msg)
    msg.show()

    assert hasattr(msg, "lbl_budget_info")
    assert msg.lbl_budget_info.isHidden()

    # Mise à jour du budget
    msg.update_budget(tokens=1250, cost_usd=0.0031)
    assert not msg.lbl_budget_info.isHidden()
    assert "1 250" in msg.lbl_budget_info.text() or "1250" in msg.lbl_budget_info.text()
    assert "$0.0031" in msg.lbl_budget_info.text()

    # mark_as_finished avec budget
    msg.mark_as_finished(text="Terminé", tokens=2500, cost_usd=0.0062)
    assert not msg.lbl_budget_info.isHidden()
    assert "$0.0062" in msg.lbl_budget_info.text()


def test_session_sidebar_budget_metrics(qtbot):
    """Vérifie que la barre latérale affiche les métriques de tokens et de coût."""
    sidebar = ConsultantSessionSidebar()
    qtbot.addWidget(sidebar)

    sidebar.update_metrics(tokens=15000, modified_cards=3, cost_usd=0.0450)
    assert "15 000" in sidebar.lbl_footer_tokens.text() or "15000" in sidebar.lbl_footer_tokens.text()
    assert "$0.0450" in sidebar.lbl_footer_tokens.text()
    assert "3 mod." in sidebar.lbl_footer_cards.text()


def test_consultant_budget_warning_at_80_percent(mock_llm_config):
    """Vérifie l'émission de budget_warning et l'interruption préventive à 80% du quota."""

    async def _run():
        # Configurer un budget bas pour le test (1000 tokens)
        SettingsService.set("ai/consultant_token_budget", 1000)
        SettingsService.set("ai/consultant_cost_budget", 0.05)

        events_collected = []

        mock_provider = MagicMock()
        # Réponse générée suffisante pour consommer > 800 tokens (80% de 1000)
        mock_provider.generate.return_value = (
            "Voici une analyse détaillée de votre collection Anki. Plusieurs cartes présentent des formulations trop longues qui violent la règle d'atomicité de Wozniak. "
        ) * 45

        engine = ConsultantEngine(llm_config=mock_llm_config, ai_provider=mock_provider)

        async for event in engine.chat_stream("Analyse mon deck"):
            events_collected.append(event)

        # Vérifier la présence de budget_update
        budget_updates = [e for e in events_collected if e.get("type") == "budget_update"]
        assert len(budget_updates) > 0
        assert budget_updates[-1]["tokens_used"] >= 800

        # Vérifier l'événement budget_warning (seuil >= 80% atteint)
        warning_events = [e for e in events_collected if e.get("type") == "budget_warning"]
        assert len(warning_events) == 1
        assert warning_events[0]["threshold"] == 0.8
        assert warning_events[0]["tokens_used"] >= 800

        # Vérifier que le message final mentionne l'arrêt préventif
        finish_events = [e for e in events_collected if e.get("type") == "finished"]
        assert len(finish_events) == 1
        assert "80%" in finish_events[0]["text"] or "budget" in finish_events[0]["text"].lower()

    asyncio.run(_run())

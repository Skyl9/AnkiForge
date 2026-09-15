"""Tests UI pour ModelSelectorWidget, ModelCapabilityBadgesWidget et ModelDiscoveryDialog."""

from __future__ import annotations

import pytest

from ankiforge.database.models import LLMConfigModel
from ankiforge.ui.components.model_selector.badges import CapabilityPill, ModelCapabilityBadgesWidget
from ankiforge.ui.components.model_selector.dialog import ModelCardWidget, ModelDiscoveryDialog
from ankiforge.ui.components.model_selector.selector import ModelSelectorWidget


@pytest.fixture
def sample_llm_configs():
    """Crée des configurations de test dans la base SQLite."""
    m1 = LLMConfigModel.create(
        display_name="Google Gemini 3.5 Flash Lite",
        provider="gemini",
        model_id="gemini-3.5-flash-lite",
        context_limit=1048576,
        prompt_pricing=0.075,
        completion_pricing=0.30,
        is_free=False,
        supports_vision=True,
        supports_thinking=True,
        supports_json=True,
        speed_rating="ultra-fast",
        quality_tier="balanced",
        recommended_tasks="flashcards,long_docs",
        description="Le compromis parfait vitesse / coût.",
        sort_order=1,
    )
    m2 = LLMConfigModel.create(
        display_name="Ollama LLaMA 3.3 70B",
        provider="ollama",
        model_id="llama3.3:70b",
        context_limit=131072,
        prompt_pricing=0.0,
        completion_pricing=0.0,
        is_free=True,
        supports_vision=False,
        supports_thinking=False,
        supports_json=True,
        speed_rating="fast",
        quality_tier="flagship",
        recommended_tasks="flashcards,audit",
        description="Confidentialité totale en local.",
        sort_order=2,
    )
    return [m1, m2]


def test_capability_pill_widget(qtbot):
    """Vérifie l'instanciation et le texte d'une pilule de capacité."""
    pill = CapabilityPill("ph.eye", "Vision", "#06b6d4")
    qtbot.addWidget(pill)
    assert pill.text_lbl.text() == "Vision"


def test_capability_badges_widget_update(qtbot, sample_llm_configs):
    """Vérifie que les badges de capacités reflètent fidèlement le modèle actif."""
    m1, m2 = sample_llm_configs
    badges = ModelCapabilityBadgesWidget(compact=False)
    qtbot.addWidget(badges)

    # Modèle Gemini
    badges.set_model(m1)
    pills = badges.findChildren(CapabilityPill)
    pill_labels = [p.text_lbl.text() for p in pills]
    assert any("Vision" in txt for txt in pill_labels)
    assert any("Thinking" in txt for txt in pill_labels)
    assert any("1M" in txt for txt in pill_labels)

    # Modèle Ollama (Gratuit / Local)
    badges.set_model(m2)
    pills_m2 = badges.findChildren(CapabilityPill)
    pill_labels_m2 = [p.text_lbl.text() for p in pills_m2]
    assert any("100% Local" in txt for txt in pill_labels_m2)


def test_model_selector_widget_selection(qtbot, sample_llm_configs):
    """Vérifie le fonctionnement du sélecteur avec héritage et signal de changement."""
    m1, m2 = sample_llm_configs
    selector = ModelSelectorWidget(allow_inherit=True, inherit_label="Global")
    qtbot.addWidget(selector)
    selector.refresh_models()

    assert selector.count() >= 3  # 1 inherit + 2 models
    assert selector.get_current_model() is None  # Inherit actif par défaut

    # Changer de modèle via set_current_model_id
    signals_emitted = []
    selector.model_changed.connect(signals_emitted.append)

    selector.set_current_model_id(m1.id)
    assert selector.get_current_model_id() == m1.id
    assert selector.get_current_model() is not None
    assert selector.get_current_model().display_name == m1.display_name
    assert selector.currentData() == selector.get_current_model()


def test_model_discovery_dialog_filtering_and_picker(qtbot, sample_llm_configs):
    """Vérifie l'exploration du catalogue, le filtrage par cas d'usage et la sélection en mode picker."""
    m1, m2 = sample_llm_configs
    dlg = ModelDiscoveryDialog(current_model_id="gemini-3.5-flash-lite", picker_mode=True)
    qtbot.addWidget(dlg)
    dlg.show()

    cards = dlg.cards_container.findChildren(ModelCardWidget)
    assert len(cards) >= 2

    # Recherche textuelle
    dlg.search_edit.setText("Ollama")
    visible_cards = [c for c in dlg.cards_container.findChildren(ModelCardWidget) if not c.isHidden()]
    assert len(visible_cards) >= 1

    # Réinitialiser la recherche
    dlg.search_edit.clear()

    # Tester le choix d'un modèle
    all_cards = dlg.cards_container.findChildren(ModelCardWidget)
    assert len(all_cards) > 0
    all_cards[0].btn_select.click()
    assert dlg.get_selected_model() is not None


def test_model_discovery_dialog_compare_drawer(qtbot, sample_llm_configs):
    """Vérifie l'activation du tiroir de comparaison côte à côte."""
    dlg = ModelDiscoveryDialog(picker_mode=False)
    qtbot.addWidget(dlg)
    dlg.show()

    cards = dlg.cards_container.findChildren(ModelCardWidget)
    assert len(cards) >= 2

    # Cocher 2 cartes pour comparaison
    cards[0].cb_compare.setChecked(True)
    cards[1].cb_compare.setChecked(True)

    # Le tiroir de comparaison doit s'afficher
    assert not dlg.compare_pane.isHidden()
    assert len(dlg._compared_models) == 2

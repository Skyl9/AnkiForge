"""
Tests de l'indicateur de compatibilité Vision du moteur IA sélectionné.

Couvre la politique partagée (`resolve_vision_support` / `effective_vision` / `vision_tooltip`),
le badge, puis sa synchronisation réelle dans le Studio de Création et la Batch Factory.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from ankiforge.database.models import LLMConfigModel
from ankiforge.repositories.persona_repository import PersonaRepository
from ankiforge.services.ai.model_catalog import ModelCatalog
from ankiforge.ui.components.inputs import OptionToggleRow
from ankiforge.ui.components.vision_capability import (
    VISION_SUPPORTED_LABEL,
    VISION_TOOLTIP,
    VISION_UNSUPPORTED_BADGE_LABEL,
    VISION_UNSUPPORTED_LABEL,
    VisionCapabilityBadge,
    VisionCapabilityNotice,
    effective_vision,
    resolve_vision_support,
    sync_vision_capability,
    vision_tooltip,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.batch_view import BatchView
from ankiforge.ui.views.creation_view import CreationView

pytestmark = pytest.mark.ui


def _make_engine(name: str, model_id: str, provider: str = "mock", supports_vision: bool = False) -> LLMConfigModel:
    return LLMConfigModel.create(
        display_name=name,
        provider=provider,
        model_id=model_id,
        supports_vision=supports_vision,
        sort_order=1,
    )


def _add_engine_through_the_writer(name: str, model_id: str, provider: str) -> LLMConfigModel:
    """Crée le moteur comme le fait l'application (via le repository), pas en injectant la colonne.

    C'est le seul moyen de prouver la chaîne complète : politique d'écriture → déclaration → vues.
    Un test qui écrit `supports_vision=False` à la main passerait même si la politique d'écriture,
    la migration ou l'onglet Moteurs IA écrivaient n'importe quoi.
    """
    return PersonaRepository().create_llm_config(display_name=name, provider=provider, model_id=model_id)


def _select_engine(view: Any, engine: LLMConfigModel) -> None:
    for idx in range(view.engine_combo.count()):
        data = view.engine_combo.itemData(idx)
        if data is not None and getattr(data, "id", None) == engine.id:
            view.engine_combo.setCurrentIndex(idx)
            return
    raise AssertionError(f"moteur {engine.display_name} absent du sélecteur")


# ─────────────────────────────── Politique partagée ───────────────────────────────


def test_resolve_vision_support_declared_flag_wins() -> None:
    assert resolve_vision_support(_make_engine("Vision", "gpt-4o", "openai", supports_vision=True)) is True
    assert resolve_vision_support(_make_engine("Texte", "deepseek-r1:8b", "groq", supports_vision=False)) is False


def test_resolve_vision_support_reads_the_declaration_and_nothing_else() -> None:
    """La lecture ne consulte jamais le catalogue : seule la colonne déclarée fait foi.

    Un modèle dont le nom ferait dire « Vision » au catalogue reste donc « texte seul » si la
    déclaration le dit, et l'inverse. C'est ce qui rend la valeur affichée non ambiguë : deux
    sources de vérité se contrediraient au premier changement de version du catalogue.
    """
    # Le catalogue Croirait `qwen2-vl:7b` multimodal ; la ligne déclare le contraire.
    assert ModelCatalog.get_model_spec("ollama", "qwen2-vl:7b").supports_vision is True
    assert resolve_vision_support(_make_engine("qwen2-vl:7b", "qwen2-vl:7b", "ollama", supports_vision=False)) is False

    # Et l'inverse : une déclaration « Vision » tient même d'un modèle que le catalogue ignore.
    assert resolve_vision_support(_make_engine("clip-local", "clip-local:13b", "ollama", supports_vision=True)) is True


def test_resolve_vision_support_unknown_without_engine() -> None:
    assert resolve_vision_support(None) is None


def test_effective_vision_never_sends_images_to_a_text_only_model() -> None:
    vision_engine = _make_engine("Vision", "gpt-4o", "openai", supports_vision=True)
    text_engine = _make_engine("Texte", "deepseek-r1:8b", "groq", supports_vision=False)

    assert effective_vision(True, vision_engine) is True
    assert effective_vision(False, vision_engine) is False
    assert effective_vision(True, text_engine) is False


def test_vision_tooltip_explains_both_states_and_the_incompatibility() -> None:
    text_engine = _make_engine("Texte", "deepseek-r1:8b", "groq", supports_vision=False)

    base = vision_tooltip(_make_engine("Vision", "gpt-4o", "openai", supports_vision=True))
    assert base == VISION_TOOLTIP
    assert "multimodal" in base.lower()
    assert "token" in base.lower()

    blocked = vision_tooltip(text_engine)
    assert VISION_UNSUPPORTED_LABEL in blocked
    assert blocked.startswith(VISION_TOOLTIP)


def test_vision_capability_badge_exposes_its_state(qtbot: Any) -> None:
    badge = VisionCapabilityBadge()
    qtbot.addWidget(badge)

    badge.set_support_status(True)
    assert badge.text() == VISION_SUPPORTED_LABEL
    assert badge.isEnabled()

    badge.set_support_status(False)
    assert badge.text() == "Vision non supportée"
    assert VISION_UNSUPPORTED_LABEL in badge.toolTip()

    badge.set_support_status(None)
    assert badge.text() == "Vision non vérifiée"


def test_vision_capability_notice_keeps_the_reason_on_screen(qtbot: Any) -> None:
    """Le message ne doit pas vivre dans une infobulle : l'utilisateur doit le voir sans survoler."""
    notice = VisionCapabilityNotice()
    qtbot.addWidget(notice)

    notice.set_support_status(True)
    assert notice.isHidden()

    notice.set_support_status(None)
    assert notice.isHidden()

    notice.set_support_status(False)
    assert notice.text() == VISION_UNSUPPORTED_LABEL
    assert notice.isHidden() is False
    assert notice.wordWrap()


def test_sync_vision_capability_is_the_single_sync_seam(qtbot: Any) -> None:
    text_engine = _make_engine("Texte", "o1-mini", "openai", supports_vision=False)
    vision_engine = _make_engine("Vision", "gpt-4o", "openai", supports_vision=True)

    badge, notice = VisionCapabilityBadge(), VisionCapabilityNotice()
    toggle = OptionToggleRow("Vision (PDF)", icon_name="ph.eye")
    qtbot.addWidget(badge)
    qtbot.addWidget(notice)
    qtbot.addWidget(toggle)

    assert sync_vision_capability(badge, notice, text_engine, toggle) is False
    assert badge.text() == "Vision non supportée"
    assert notice.isHidden() is False
    assert toggle.isEnabled() is False
    assert VISION_UNSUPPORTED_LABEL in toggle.toolTip()

    assert sync_vision_capability(badge, notice, vision_engine, toggle) is True
    assert badge.text() == VISION_SUPPORTED_LABEL
    assert notice.isHidden()
    assert toggle.isEnabled()
    assert toggle.toolTip() == VISION_TOOLTIP

    assert sync_vision_capability(badge, notice, None, toggle) is None
    assert badge.text() == "Vision non vérifiée"
    assert notice.isHidden()
    assert toggle.isEnabled()  # « non vérifié » ne doit pas bloquer un moteur multimodal inconnu


# ─────────────────────────────── Studio de Création ───────────────────────────────


def test_creation_view_vision_badge_follows_the_selected_engine(qtbot: Any, mock_db: Any) -> None:
    uid = uuid.uuid4().hex[:6]
    text_engine = _make_engine(f"Texte {uid}", "deepseek-r1:8b", "groq", supports_vision=False)
    vision_engine = _make_engine(f"Vision {uid}", "gpt-4o", "openai", supports_vision=True)

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    _select_engine(view, text_engine)
    assert view.vision_cap_badge.text() == "Vision non supportée"
    assert VISION_UNSUPPORTED_LABEL in view.vision_card.toolTip()
    assert not view.vision_card.isEnabled()
    # La raison du grisé est lisible sans survol, pas tapie dans l'infobulle
    assert view.vision_cap_notice.text() == VISION_UNSUPPORTED_LABEL
    assert view.vision_cap_notice.isHidden() is False
    assert view.vision_badge.text() == "OFF"
    # Grisé : un style inline de couleur prime sur le rendu désactivé de Qt.
    assert DesignTokens.TEXT_MUTED in view.lbl_vision_title.styleSheet()

    _select_engine(view, vision_engine)
    assert view.vision_cap_badge.text() == VISION_SUPPORTED_LABEL
    assert view.vision_cap_notice.isHidden()
    assert view.vision_card.isEnabled()
    assert view.vision_card.toolTip() == VISION_TOOLTIP
    assert DesignTokens.TEXT_PRIMARY in view.lbl_vision_title.styleSheet()

    view.vision_cb.setChecked(True)
    assert view.vision_badge.text() == "ON"

    # Un modèle texte seul recharge le badge OFF même si la préférence Vision reste mémorisée
    _select_engine(view, text_engine)
    assert view.vision_badge.text() == "OFF"
    assert view.vision_cb.isChecked() is True


def test_creation_view_tooltip_documents_the_vision_tradeoff(qtbot: Any, mock_db: Any) -> None:
    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    assert view.vision_card.toolTip().startswith("Vision Multimodale")
    # L'infobulle doit dire ce que coûte et ce que rapporte la Vision, pas seulement ce qu'elle est.
    tooltip = view.vision_card.toolTip().lower()
    assert "multimodal" in tooltip
    assert "token" in tooltip
    assert view.vision_cb.toolTip() == view.vision_card.toolTip()


def test_creation_view_construction_preserves_the_stored_vision_preference(qtbot: Any, mock_db: Any) -> None:
    """Ouvrir le Studio ne doit pas réécrire la préférence enregistrée.

    La caseVision est masquée : elle n'est animée que par l'utilisateur. Un rendu appelé pendant la
    construction et qui persisterait son état par défaut effacerait un « Vision » choisi pour de bon.
    """
    from ankiforge.services.settings_service import SettingsService

    SettingsService.set("creation/use_vision", True, category="creation")

    view = CreationView(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    assert SettingsService.get("creation/use_vision") is True
    assert view.vision_cb.isChecked() is True

    # En revanche, un choix explicite de l'utilisateur est bien persisté.
    view.vision_cb.setChecked(False)
    assert SettingsService.get("creation/use_vision") is False


def test_creation_view_never_sends_a_multimodal_payload_to_a_text_only_engine(qtbot: Any, mock_db: Any, monkeypatch: Any) -> None:
    """Le pipeline ne doit jamais recevoir use_vision=True avec un moteur incapable de lire les images."""
    import json

    from ankiforge.services.ai.base import LLMProvider

    uid = uuid.uuid4().hex[:6]
    text_engine = _make_engine(f"Texte {uid}", "deepseek-r1:8b", "groq", supports_vision=False)

    class _Provider(LLMProvider):
        def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json", max_tokens: int | None = None) -> str:
            return json.dumps({"cards": [{"Front": "Q", "Back": "R"}]})

    class _AIManager:
        def create_provider_from_config(self, config: Any) -> LLMProvider:
            return _Provider()

    view = CreationView(ai_manager=_AIManager())
    qtbot.addWidget(view)
    view.refresh_data()
    view.vision_cb.setChecked(True)
    _select_engine(view, text_engine)

    view._on_generate(text_source="Contenu source", source_title="Saisie Libre")
    assert view.orchestrator is not None
    assert view.orchestrator.state.get_variable("use_vision") is False
    view.thread_pool.waitForDone(2000)


# ─────────────────────────────── Batch Factory ───────────────────────────────


def test_batch_view_vision_badge_and_toggle_follow_the_selected_engine(qtbot: Any, mock_db: Any) -> None:
    uid = uuid.uuid4().hex[:6]
    text_engine = _make_engine(f"Texte {uid}", "deepseek-r1:8b", "groq", supports_vision=False)
    vision_engine = _make_engine(f"Vision {uid}", "gpt-4o", "openai", supports_vision=True)

    view = BatchView()
    qtbot.addWidget(view)
    view.refresh_data()

    _select_engine(view, vision_engine)
    assert view.vision_cap_badge.text() == VISION_SUPPORTED_LABEL
    assert view.cb_vision.isEnabled()
    assert view.cb_vision.toolTip() == VISION_TOOLTIP

    view.cb_vision.set_checked(True)
    assert view._default_queue_targets()["use_vision"] is True

    _select_engine(view, text_engine)
    assert view.vision_cap_badge.text() == "Vision non supportée"
    assert VISION_UNSUPPORTED_LABEL in view.cb_vision.toolTip()
    assert not view.cb_vision.isEnabled()
    assert view.vision_cap_notice.text() == VISION_UNSUPPORTED_LABEL
    assert view.vision_cap_notice.isHidden() is False
    assert view._default_queue_targets()["use_vision"] is False
    # La préférence utilisateur est préservée pour le prochain moteur multimodal
    assert view.cb_vision.isChecked() is True

    _select_engine(view, vision_engine)
    assert view.cb_vision.isEnabled()
    assert view.vision_cap_notice.isHidden()
    assert view._default_queue_targets()["use_vision"] is True


def test_batch_view_disabled_toggle_ignores_user_clicks(qtbot: Any, mock_db: Any) -> None:
    """Grisé = non actionnable : un clic ne doit pas réactiver la Vision sur un moteur texte seul."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    uid = uuid.uuid4().hex[:6]
    text_engine = _make_engine(f"Texte {uid}", "deepseek-r1:8b", "groq", supports_vision=False)

    view = BatchView()
    qtbot.addWidget(view)
    view.refresh_data()
    view.cb_vision.set_checked(False)
    _select_engine(view, text_engine)
    assert not view.cb_vision.isEnabled()

    QTest.mouseClick(view.cb_vision, Qt.MouseButton.LeftButton, pos=view.cb_vision.rect().center())

    assert view.cb_vision.isChecked() is False


# ─────────────── Chaîne complète : politique d'écriture ➔ déclaration ➔ vues ───────────────

# (fournisseur, modèle, attendu) — les modèles « texte seul » nommés par le ticket, un multimodal
# connu, et un moteur qu'AnkiForge propose lui-même en défaut.
_TEXT_ONLY_MODELS = [("openai", "o1-mini"), ("groq", "deepseek-r1-distill-llama-70b"), ("ollama", "deepseek-r1:8b")]
_MULTIMODAL_MODELS = [("openai", "gpt-4o"), ("gemini", "gemini-3.5-flash-lite"), ("anthropic", "claude-3-5-sonnet-20240620")]


@pytest.mark.parametrize(("provider", "model_id"), _TEXT_ONLY_MODELS)
def test_a_text_only_model_added_by_the_user_greys_out_both_views(qtbot: Any, mock_db: Any, provider: str, model_id: str) -> None:
    """Critère d'acceptation, de bout en bout : le moteur est créé comme par l'application,
    puis les deux vues doivent refuser la Vision et l'annoncer."""
    uid = uuid.uuid4().hex[:6]
    engine = _add_engine_through_the_writer(f"Texte {uid}", model_id, provider)
    assert engine.supports_vision is False, "la politique d'écriture a accordé la Vision à un modèle texte"

    creation = CreationView(ai_manager=None)
    qtbot.addWidget(creation)
    creation.refresh_data()
    _select_engine(creation, engine)

    assert creation.vision_cap_badge.text() == VISION_UNSUPPORTED_BADGE_LABEL
    assert creation.vision_cap_notice.text() == VISION_UNSUPPORTED_LABEL
    assert creation.vision_cap_notice.isHidden() is False
    assert not creation.vision_card.isEnabled()

    batch = BatchView()
    qtbot.addWidget(batch)
    batch.refresh_data()
    _select_engine(batch, engine)

    assert batch.vision_cap_badge.text() == VISION_UNSUPPORTED_BADGE_LABEL
    assert batch.vision_cap_notice.text() == VISION_UNSUPPORTED_LABEL
    assert batch.vision_cap_notice.isHidden() is False
    assert not batch.cb_vision.isEnabled()
    assert batch._default_queue_targets()["use_vision"] is False


@pytest.mark.parametrize(("provider", "model_id"), _MULTIMODAL_MODELS)
def test_a_multimodal_model_added_by_the_user_stays_enabled_in_both_views(qtbot: Any, mock_db: Any, provider: str, model_id: str) -> None:
    """Témoin négatif : une politique d'écriture trop prudente ferait ici perdre la Vision à tort.

    C'est le test qui aurait détecté un `claude-3-5-sonnet-20240620` déclaré « texte seul » alors
    qu'AnkiForge le propose comme moteur par défaut.
    """
    uid = uuid.uuid4().hex[:6]
    engine = _add_engine_through_the_writer(f"Vision {uid}", model_id, provider)
    assert engine.supports_vision is True

    creation = CreationView(ai_manager=None)
    qtbot.addWidget(creation)
    creation.refresh_data()
    _select_engine(creation, engine)
    assert creation.vision_card.isEnabled()
    assert creation.vision_cap_badge.text() == VISION_SUPPORTED_LABEL

    batch = BatchView()
    qtbot.addWidget(batch)
    batch.refresh_data()
    _select_engine(batch, engine)
    assert batch.cb_vision.isEnabled()
    assert batch.vision_cap_badge.text() == VISION_SUPPORTED_LABEL

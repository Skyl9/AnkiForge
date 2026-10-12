"""Tests UI pour ModelSelectorWidget, ModelCapabilityBadgesWidget et ModelDiscoveryDialog."""

from __future__ import annotations

import pytest

from ankiforge.database.models import LLMConfigModel
from ankiforge.ui.components.model_selector.badges import CapabilityPill, ModelCapabilityBadgesWidget
from ankiforge.ui.components.model_selector.dialog import ModelCardWidget, ModelDiscoveryDialog
from ankiforge.ui.components.model_selector.selector import ModelSelectorWidget

pytestmark = pytest.mark.ui


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


def test_model_discovery_provider_filter_and_current_model(qtbot, sample_llm_configs):
    """Vérifie le filtrage par fournisseur, la détection du modèle actuel et la réinitialisation."""
    dlg = ModelDiscoveryDialog(current_model_id="gemini-3.5-flash-lite", picker_mode=True)
    qtbot.addWidget(dlg)
    dlg.show()

    # Vérifier que la carte courante a bien le flag is_current
    cards = dlg.cards_container.findChildren(ModelCardWidget)
    current_cards = [c for c in cards if c.is_current]
    assert len(current_cards) == 1
    assert "Gemini" in current_cards[0].title_lbl.text()

    # Filtrer par Ollama
    dlg.prov_buttons["ollama"].click()
    ollama_cards = [c for c in dlg.cards_container.findChildren(ModelCardWidget) if not c.isHidden()]
    assert len(ollama_cards) >= 1
    assert all("ollama" in getattr(c.model, "provider", "").lower() for c in ollama_cards)

    # Réinitialiser tous les filtres
    dlg._reset_all_filters()
    all_cards = [c for c in dlg.cards_container.findChildren(ModelCardWidget) if not c.isHidden()]
    assert len(all_cards) >= 2


def test_model_card_double_click_selection(qtbot, sample_llm_configs):
    """Vérifie que le double-clic sur une carte sélectionne le modèle immédiatement."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent

    m1, _ = sample_llm_configs
    card = ModelCardWidget(model=m1, is_installed=True, picker_mode=True)
    qtbot.addWidget(card)

    selected_models = []
    card.selected.connect(selected_models.append)

    # Simuler un double clic
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPoint(10, 10),
        QPoint(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    card.mouseDoubleClickEvent(event)

    assert len(selected_models) == 1
    assert selected_models[0].id == m1.id


def test_model_discovery_dialog_dimensions_and_compare_hidden_in_picker_mode(qtbot, sample_llm_configs):
    """Vérifie le format 840x540 en picker_mode, le masquage de compare_pane et les libellés raccourcis."""
    # 1. Mode Sélecteur (picker_mode=True)
    dlg_picker = ModelDiscoveryDialog(picker_mode=True)
    qtbot.addWidget(dlg_picker)

    assert dlg_picker.width() <= 840
    assert dlg_picker.height() <= 540

    # Volet de comparaison masqué
    assert dlg_picker.compare_pane.isHidden()

    # Puces "Comparer" masquées sur les cartes en mode sélecteur
    picker_cards = dlg_picker.cards_container.findChildren(ModelCardWidget)
    assert len(picker_cards) >= 2
    for card in picker_cards:
        assert card.cb_compare.isHidden()

    # Puces fournisseurs avec libellés raccourcis
    assert dlg_picker.prov_buttons["gemini"].text() == "Gemini"
    assert dlg_picker.prov_buttons["anthropic"].text() == "Claude"
    assert dlg_picker.prov_buttons["ollama"].text() == "Ollama"
    assert dlg_picker.prov_buttons["openai"].text() == "OpenAI"
    assert dlg_picker.prov_buttons["groq"].text() == "Groq"
    assert dlg_picker.prov_buttons["opencode"].text() == "OpenCode"
    assert dlg_picker.prov_buttons["openrouter"].text() == "OpenRouter"

    # 2. Mode Catalogue (picker_mode=False)
    dlg_catalog = ModelDiscoveryDialog(picker_mode=False)
    qtbot.addWidget(dlg_catalog)

    assert dlg_catalog.width() <= 960
    assert dlg_catalog.height() <= 600

    catalog_cards = dlg_catalog.cards_container.findChildren(ModelCardWidget)
    assert len(catalog_cards) >= 2
    for card in catalog_cards:
        assert not card.cb_compare.isHidden()


def test_vision_model_discovery_dialog_bounded_and_responsive(qtbot, sample_llm_configs):
    """Vérifie que la modale de sélection de moteur de vision ne dépasse pas en largeur et reste responsive."""
    from PySide6.QtCore import Qt

    dlg = ModelDiscoveryDialog(picker_mode=True, require_vision=True)
    qtbot.addWidget(dlg)

    # Titre contextuel vision
    assert "Moteur de Vision" in dlg.windowTitle()
    assert dlg.btn_cap_vision.isChecked()
    assert not dlg.btn_cap_vision.isEnabled()

    # Contraintes de dimensionnement : ne doit JAMAIS avoir une taille minimale excessive (> 700px)
    assert dlg.minimumSizeHint().width() <= 680

    dlg.show()
    qtbot.waitExposed(dlg)

    # Après affichage, la largeur ne doit pas exploser à 2000px+
    assert dlg.width() <= 840
    assert dlg.height() <= 540

    # Aucun ascenseur horizontal requis
    assert dlg.scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff or not dlg.scroll_area.horizontalScrollBar().isVisible()

    # Seuls des modèles supportant la vision sont listés
    cards = [c for c in dlg.cards_container.findChildren(ModelCardWidget) if not c.isHidden()]
    assert len(cards) >= 1
    for c in cards:
        assert getattr(c.model, "supports_vision", False) is True


def test_vision_model_discovery_dialog_simulated_screen_sizes(qtbot, monkeypatch, sample_llm_configs):
    """Vérifie le respect des bornes de résolution à 1920x1080, 1280x800, 1024x768 et 800x600."""
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    screen = QApplication.primaryScreen()
    assert screen is not None

    # 1. Grand écran (1920x1080)
    monkeypatch.setattr(screen, "availableGeometry", lambda: QRect(0, 0, 1920, 1080))
    dlg_fhd = ModelDiscoveryDialog(picker_mode=True, require_vision=True)
    qtbot.addWidget(dlg_fhd)
    assert dlg_fhd.width() == 840
    assert dlg_fhd.height() == 540

    # 2. Écran MacBook 13" / portable standard (1280x800)
    monkeypatch.setattr(screen, "availableGeometry", lambda: QRect(0, 0, 1280, 800))
    dlg_1280 = ModelDiscoveryDialog(picker_mode=True, require_vision=True)
    qtbot.addWidget(dlg_1280)
    assert dlg_1280.width() == 840
    assert dlg_1280.height() == 540
    assert dlg_1280.width() <= 1280

    # 3. Petit écran (1024x768)
    monkeypatch.setattr(screen, "availableGeometry", lambda: QRect(0, 0, 1024, 768))
    dlg_1024 = ModelDiscoveryDialog(picker_mode=True, require_vision=True)
    qtbot.addWidget(dlg_1024)
    assert dlg_1024.width() <= 1024 * 0.85
    assert dlg_1024.height() <= 768 * 0.85
    assert dlg_1024.width() <= 840

    # Mode catalogue complet sur petit écran (1024x768)
    dlg_cat_1024 = ModelDiscoveryDialog(picker_mode=False, require_vision=True)
    qtbot.addWidget(dlg_cat_1024)
    assert dlg_cat_1024.width() <= 1024 * 0.85
    assert dlg_cat_1024.height() <= 768 * 0.85

    # 4. Écran très compact (800x600)
    monkeypatch.setattr(screen, "availableGeometry", lambda: QRect(0, 0, 800, 600))
    dlg_800 = ModelDiscoveryDialog(picker_mode=True, require_vision=True)
    qtbot.addWidget(dlg_800)
    assert dlg_800.width() <= int(800 * 0.85)
    assert dlg_800.height() <= int(600 * 0.85)


def test_album_transcription_dialog_dimensions_bounded_on_small_screens(qtbot, monkeypatch):
    """Vérifie que AlbumTranscriptionDialog est plafonnée à 90% de la géométrie disponible."""
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication

    from ankiforge.database.models import DocumentModel
    from ankiforge.ui.dialogs.album_transcription_dialog import AlbumTranscriptionDialog

    screen = QApplication.primaryScreen()
    assert screen is not None

    doc = DocumentModel.create(title="Test Album", source_type="album")

    # Petit écran (1024x768)
    monkeypatch.setattr(screen, "availableGeometry", lambda: QRect(0, 0, 1024, 768))
    dlg = AlbumTranscriptionDialog(doc=doc)
    qtbot.addWidget(dlg)

    assert dlg.width() <= int(1024 * 0.9)
    assert dlg.height() <= int(768 * 0.9)
    assert dlg.minimumWidth() <= dlg.width()
    assert dlg.minimumHeight() <= dlg.height()


def test_model_selector_widget_require_vision_and_native(qtbot, sample_llm_configs):
    """Vérifie que ModelSelectorWidget filtre sur supports_vision et propose l'OCR natif si demandé."""
    selector = ModelSelectorWidget(require_vision=True, include_native_vision=True)
    qtbot.addWidget(selector)

    # Doit contenir m1 (Gemini avec vision) et Apple Vision, mais PAS m2 (Llama sans vision)
    model_ids = [selector.combo.itemData(i).model_id for i in range(selector.combo.count()) if selector.combo.itemData(i)]
    assert "gemini-3.5-flash-lite" in model_ids
    assert "llama3.3:70b" not in model_ids
    assert "apple_vision" in model_ids

    # Sélection de Apple Vision
    selector.set_current_model_id("apple_vision")
    curr = selector.get_current_model()
    assert curr is not None
    assert curr.model_id == "apple_vision"
    assert curr.provider == "native"

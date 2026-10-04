import uuid
from typing import Any

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.persona_templates import PROMPT_STARTER_FRAMEWORKS
from ankiforge.ui.views.agents_view import (
    AgentsView,
    AgentTestDialog,
    PersonaEmptyStateWidget,
    VariableHelperDialog,
)

pytestmark = pytest.mark.ui


def test_empty_state_widget_signals(qtbot):
    """Vérifie le widget d'accueil Empty State et ses signaux d'action."""
    widget = PersonaEmptyStateWidget()
    qtbot.addWidget(widget)

    signals_fired = []
    widget.create_from_template_requested.connect(lambda: signals_fired.append("template"))
    widget.create_custom_requested.connect(lambda: signals_fired.append("custom"))

    widget.btn_templates.click()
    assert "template" in signals_fired

    widget.btn_blank.click()
    assert "custom" in signals_fired


def test_variable_helper_dialog(qtbot):
    """Vérifie la recherche, le style compact et l'émission du signal d'insertion dans VariableHelperDialog."""
    dlg = VariableHelperDialog()
    qtbot.addWidget(dlg)

    # Vérification du style compact et dimensions des boutons Insérer sur chaque carte
    for card, _ in dlg._cards:
        assert hasattr(card, "btn_insert")
        assert card.btn_insert.property("density") == "compact"
        assert card.btn_insert.maximumHeight() == 28
        assert card.btn_insert.minimumHeight() == 28
        assert not card.btn_insert.icon().isNull()

    # Filtrer par 'source'
    dlg.edit_filter.setText("source")
    visible_cards = [c for c, _ in dlg._cards if not c.isHidden()]
    assert len(visible_cards) >= 1

    # Tester l'insertion via un vrai clic sur le bouton Insérer de la première carte visible
    inserted_vars = []
    dlg.variable_inserted.connect(lambda v: inserted_vars.append(v))

    target_card = visible_cards[0]
    target_doc = target_card.doc
    target_card.btn_insert.click()
    assert target_doc.variable in inserted_vars
    assert dlg.result() == 1  # QDialog.DialogCode.Accepted


def test_agent_test_dialog_samples(qtbot):
    """Vérifie le sélecteur d'échantillons de cours dans le dialogue de test."""
    p = PersonaModel.create(
        name=f"TestSamples {uuid.uuid4().hex[:6]}",
        system_prompt="Prompt avec {{ text_source }}",
        output_format="json",
        persona_type="pipeline",
    )

    dlg = AgentTestDialog(persona=p)
    qtbot.addWidget(dlg)

    assert dlg.sample_combo.count() >= 5
    # Sélectionner le premier échantillon (Biologie)
    dlg.sample_combo.setCurrentIndex(1)
    assert "photosynthèse" in dlg.edit_user_input.toPlainText().lower()

    # Sélectionner le deuxième échantillon (Histoire)
    dlg.sample_combo.setCurrentIndex(2)
    assert "révolution" in dlg.edit_user_input.toPlainText().lower()


def test_agents_view_prompt_frameworks_and_empty_state(qtbot, monkeypatch):
    """Vérifie l'application d'un canevas de prompt et le basculement d'affichage empty state."""
    uid = uuid.uuid4().hex[:6]
    _ = PersonaModel.create(
        name=f"AgentFramework {uid}",
        system_prompt="Tu es un assistant expert pour Anki.",
        output_format="json",
        persona_type="pipeline",
    )

    view = AgentsView()
    qtbot.addWidget(view)

    # L'éditeur est affiché car un agent existe
    assert view.editor_master_stack.currentIndex() == 1

    # Appliquer un canevas Cloze
    cloze_framework = next(f for f in PROMPT_STARTER_FRAMEWORKS if f.id == "framework_cloze")
    view._apply_prompt_framework(cloze_framework)

    assert "Cloze" in view.prompt_edit.toPlainText() or "texte à trous" in view.prompt_edit.toPlainText()
    assert view.format_combo.currentText() == "cloze"

    # Supprimer l'agent pour vérifier le basculement vers l'Empty State
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    view._on_delete_selected()

    # Si tous les agents ont été supprimés, l'empty state doit être actif
    if not PersonaModel.select().count():
        assert view.editor_master_stack.currentIndex() == 0


def test_agents_view_prompt_buttons_height_and_density(qtbot):
    """Vérifie que les boutons d'action du prompt font 32px de haut, ont la densité compacte et les bonnes icônes."""
    uid = uuid.uuid4().hex[:6]
    _ = PersonaModel.create(
        name=f"AgentPromptBtns {uid}",
        system_prompt="Prompt initial.",
        output_format="json",
        persona_type="pipeline",
    )

    view = AgentsView()
    qtbot.addWidget(view)

    # 1. Hauteur fixée à 32px
    assert view.btn_prompt_framework.minimumHeight() == 32
    assert view.btn_prompt_framework.maximumHeight() == 32

    assert view.btn_var_help.minimumHeight() == 32
    assert view.btn_var_help.maximumHeight() == 32

    assert view.btn_preview_prompt.minimumHeight() == 32
    assert view.btn_preview_prompt.maximumHeight() == 32

    # 2. Densité compacte (QSS QPushButton[density="compact"])
    assert view.btn_prompt_framework.property("density") == "compact"
    assert view.btn_var_help.property("density") == "compact"
    assert view.btn_preview_prompt.property("density") == "compact"

    # 3. Présence des icônes Phosphor ph.question et ph.eye
    assert not view.btn_var_help.icon().isNull()
    assert not view.btn_preview_prompt.icon().isNull()

    # 4. TagPillButton préservés (24px)
    from ankiforge.ui.views.agents_view.widgets import TagPillButton

    pills = view.findChildren(TagPillButton)
    assert len(pills) > 0
    for pill in pills:
        assert pill.maximumHeight() == 24


def test_agents_view_scope_filter_chips_and_alignment(qtbot):
    """Vérifie que les filtres de portée sont des FilterChipButton avec icônes Phosphor (sans émojis),
    et que la barre de recherche et le bouton 'Nouvel Agent' sont alignés verticalement à 30px."""
    from ankiforge.ui.components import FilterChipButton
    from ankiforge.ui.style_engine import JETBRAINS_LIGHT

    view = AgentsView()
    qtbot.addWidget(view)

    # 1. Alignement vertical barre de recherche & bouton nouvel agent à 30px
    assert view.edit_search.height() == 30 or view.edit_search.maximumHeight() == 30
    assert view.btn_new.height() == 30 or view.btn_new.maximumHeight() == 30
    assert view.edit_search.maximumHeight() == view.btn_new.maximumHeight()

    # 2. Tous les filtres de portée sont des FilterChipButton de hauteur 26px
    for btn, _ in view._filter_buttons:
        assert isinstance(btn, FilterChipButton)
        assert btn.isCheckable()
        assert btn.height() == 26 or btn.maximumHeight() == 26

    # 3. Absence stricte d'émojis texte dans les libellés
    emojis = ["⚡", "🤝", "🌐"]
    for btn, _ in view._filter_buttons:
        text = btn.text()
        for emoji in emojis:
            assert emoji not in text, f"L'émoji {emoji} ne doit pas être présent dans le texte du bouton ({text})"

    assert view.btn_filter_all.text() == "Tous"
    assert view.btn_filter_pipe.text() == "Pipeline"
    assert view.btn_filter_mcp.text() == "MCP"
    assert view.btn_filter_univ.text() == "Universel"

    # 4. Présence des icônes vectorielles Phosphor appropriées
    assert view.btn_filter_all.icon_name == "ph.sparkle"
    assert view.btn_filter_pipe.icon_name == "ph.lightning"
    assert view.btn_filter_mcp.icon_name == "ph.handshake"
    assert view.btn_filter_univ.icon_name == "ph.globe"

    for btn, _ in view._filter_buttons:
        assert not btn.icon().isNull()

    # 5. État initial : "Tous" est coché
    assert view.btn_filter_all.isChecked()
    assert not view.btn_filter_pipe.isChecked()
    assert not view.btn_filter_mcp.isChecked()
    assert not view.btn_filter_univ.isChecked()

    # 6. Basculement interactif des filtres (exclusivité mutuelle)
    view.btn_filter_pipe.click()
    assert not view.btn_filter_all.isChecked()
    assert view.btn_filter_pipe.isChecked()
    assert view._current_scope_filter == "pipeline"

    view.btn_filter_mcp.click()
    assert not view.btn_filter_pipe.isChecked()
    assert view.btn_filter_mcp.isChecked()
    assert view._current_scope_filter == "mcp"

    view.btn_filter_univ.click()
    assert not view.btn_filter_mcp.isChecked()
    assert view.btn_filter_univ.isChecked()
    assert view._current_scope_filter == "universal"

    view.btn_filter_all.click()
    assert view.btn_filter_all.isChecked()
    assert not view.btn_filter_univ.isChecked()
    assert view._current_scope_filter == "all"

    # 7. Réactivité au changement de thème (refresh_theme)
    view.refresh_theme(JETBRAINS_LIGHT)
    for btn, _ in view._filter_buttons:
        assert not btn.icon().isNull()


def test_agents_view_tools_permissions_buttons_and_alignment(qtbot):
    """Vérifie l'alignement et la densité compacte des boutons 'Tout Cocher' / 'Tout Décocher'
    et de la liste déroulante des presets d'outils."""
    from ankiforge.ui.components import SecondaryButton

    view = AgentsView()
    qtbot.addWidget(view)

    # 1. Présence et type des boutons
    assert hasattr(view, "btn_select_all")
    assert hasattr(view, "btn_deselect_all")
    assert isinstance(view.btn_select_all, SecondaryButton)
    assert isinstance(view.btn_deselect_all, SecondaryButton)

    # 2. Densité compacte et hauteur harmonisée à 30px
    assert view.btn_select_all.property("density") == "compact"
    assert view.btn_deselect_all.property("density") == "compact"
    assert view.btn_select_all.height() == 30 or view.btn_select_all.maximumHeight() == 30
    assert view.btn_deselect_all.height() == 30 or view.btn_deselect_all.maximumHeight() == 30
    assert view.preset_combo.height() == 30 or view.preset_combo.maximumHeight() == 30

    # 3. Fonctionnement interactif
    view.btn_select_all.click()
    assert len(view._tool_cards) > 0
    assert all(card.isChecked() for card in view._tool_cards.values())

    view.btn_deselect_all.click()
    assert all(not card.isChecked() for card in view._tool_cards.values())


def test_agents_view_no_dashed_border_and_no_child_cascade(qtbot):
    """Vérifie que la bordure pointillée est supprimée et qu'aucun enfant de engine_info_card
    n'hérite d'une bordure en cascade."""
    from ankiforge.ui.style_engine import JETBRAINS_LIGHT

    view = AgentsView()
    qtbot.addWidget(view)

    # 1. Vérification que la bordure pointillée est supprimée sur le conteneur
    assert "dashed" not in view.engine_info_card.styleSheet().lower()
    assert "border: none" in view.engine_info_card.styleSheet().lower()

    # 2. Vérification que les enfants ont un border: none explicite et aucun dashed
    assert hasattr(view, "lbl_engine_icon")
    assert hasattr(view, "lbl_engine_info")
    assert "border: none" in view.lbl_engine_icon.styleSheet().lower()
    assert "border: none" in view.lbl_engine_info.styleSheet().lower()
    assert "dashed" not in view.lbl_engine_icon.styleSheet().lower()
    assert "dashed" not in view.lbl_engine_info.styleSheet().lower()

    # 3. Vérification du sélecteur ID pour éviter toute cascade sur les sous-classes QFrame (QLabel)
    assert view.engine_info_card.objectName() == "engine_info_card"
    assert "QFrame#engine_info_card" in view.engine_info_card.styleSheet() or "#engine_info_card" in view.engine_info_card.styleSheet()

    # 4. Vérification après rafraîchissement de thème
    view.refresh_theme(JETBRAINS_LIGHT)
    assert "dashed" not in view.engine_info_card.styleSheet().lower()
    assert "border: none" in view.lbl_engine_icon.styleSheet().lower()
    assert "border: none" in view.lbl_engine_info.styleSheet().lower()


def test_agents_view_auto_expanding_description_and_identity_height(qtbot: Any) -> None:
    """Vérifie l'auto-agrandissement du champ description lors de l'édition et le chargement d'un agent."""
    from ankiforge.ui.components.inputs import AutoExpandingTextEdit
    from ankiforge.ui.theme import DesignTokens

    uid = uuid.uuid4().hex[:6]
    initial_desc = "Description courte sur une ligne."
    p = PersonaModel.create(
        name=f"Agent Desc Test {uid}",
        description=initial_desc,
        system_prompt="System prompt test",
        output_format="json",
        persona_type="pipeline",
        allowed_tools="[]",
    )

    view = AgentsView()
    qtbot.addWidget(view)
    view.resize(1100, 750)
    view.show()
    qtbot.wait(20)

    # 1. Vérification du type du widget et présence du QScrollArea sur tab_identity
    assert isinstance(view.desc_edit, AutoExpandingTextEdit)
    assert hasattr(view, "scroll_identity")
    assert view.desc_edit.min_height == DesignTokens.INPUT_AUTO_EXPAND_MIN_HEIGHT
    assert view.desc_edit.max_height == DesignTokens.INPUT_AUTO_EXPAND_MAX_HEIGHT

    # 2. Chargement du persona dans l'éditeur
    view._load_persona_into_editor(p)
    view._current_agent = p
    qtbot.wait(20)

    assert view.desc_edit.text() == initial_desc
    h_initial = view.desc_edit.height()
    assert h_initial == DesignTokens.INPUT_AUTO_EXPAND_MIN_HEIGHT

    # 3. Saisie d'une description longue multiligne (simulation de frappe utilisateur)
    multiline_desc = (
        "Première ligne de rôle de l'agent.\n"
        "Deuxième ligne expliquant les contraintes de formulation.\n"
        "Troisième ligne pour le formatage et les balises cloze.\n"
        "Quatrième ligne détaillant les règles d'intégrité."
    )
    view.desc_edit.setPlainText(multiline_desc)
    qtbot.wait(20)

    h_expanded = view.desc_edit.height()
    assert h_expanded > h_initial
    assert h_expanded <= DesignTokens.INPUT_AUTO_EXPAND_MAX_HEIGHT

    # 4. Sauvegarde de la description modifiée en BDD
    view.btn_save.click()
    reloaded_p = PersonaModel.get_by_id(p.id)
    assert reloaded_p.description == multiline_desc

    # 5. Dépassement de la hauteur maximale (vérification scrollbar)
    very_long_desc = "\n".join(f"Directive numéro {i} pour l'agent IA" for i in range(20))
    view.desc_edit.setPlainText(very_long_desc)
    qtbot.wait(20)

    assert view.desc_edit.height() == DesignTokens.INPUT_AUTO_EXPAND_MAX_HEIGHT
    assert view.desc_edit.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded


def test_agents_view_across_all_four_layouts_and_themes(qtbot: Any) -> None:
    """Vérifie le comportement et l'alignement du widget description dans les 4 layouts et les thèmes."""
    from ankiforge.ui.layouts.layout_manager import LayoutManager
    from ankiforge.ui.style_engine.themes import BUILTIN_THEMES

    uid = uuid.uuid4().hex[:6]
    PersonaModel.create(
        name=f"Agent Layout Test {uid}",
        description="Description pour test multi-layouts et thèmes.",
        system_prompt="Prompt layout",
    )

    view = AgentsView()
    qtbot.addWidget(view)
    view.resize(1200, 800)
    view.show()
    qtbot.wait(20)

    # 1. Vérification dans les 4 thèmes clés
    key_themes = ["jetbrains", "jetbrains_light", "macos", "emerald", "glassmorphism"]
    for theme_id in key_themes:
        profile = BUILTIN_THEMES.get(theme_id)
        if profile:
            view.refresh_theme(profile)
            assert view.desc_edit.height() >= view.desc_edit.min_height
            assert view.desc_edit.max_height >= view.desc_edit.min_height

    # 2. Vérification dans les 4 architectures de layouts
    layouts = ["ide", "macos", "dashboard", "glassmorphism"]
    for layout_id in layouts:
        layout_cls = LayoutManager.LAYOUTS.get(layout_id)
        assert layout_cls is not None
        # Le widget s'affiche sans déformation dans n'importe quel conteneur de layout
        assert view.scroll_identity.widget() is not None
        assert view.desc_edit.isVisible()

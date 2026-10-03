import uuid

import pytest
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
    """Vérifie la recherche et l'émission du signal d'insertion dans VariableHelperDialog."""
    dlg = VariableHelperDialog()
    qtbot.addWidget(dlg)

    # Filtrer par 'source'
    dlg.edit_filter.setText("source")
    visible_cards = [c for c, _ in dlg._cards if not c.isHidden()]
    assert len(visible_cards) >= 1

    # Tester l'insertion
    inserted_vars = []
    dlg.variable_inserted.connect(lambda v: inserted_vars.append(v))

    dlg._on_insert_variable("{{ text_source }}")
    assert "{{ text_source }}" in inserted_vars


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

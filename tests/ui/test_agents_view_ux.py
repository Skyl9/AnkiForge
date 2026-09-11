import uuid

from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.persona_templates import PROMPT_STARTER_FRAMEWORKS
from ankiforge.ui.views.agents_view import (
    AgentsView,
    AgentTestDialog,
    PersonaEmptyStateWidget,
    VariableHelperDialog,
)


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

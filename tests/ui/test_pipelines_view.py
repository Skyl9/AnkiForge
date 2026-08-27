import json
from typing import Any

from PySide6.QtWidgets import QPlainTextEdit

from ankiforge.database.models import PersonaModel, PipelineModel, PipelineStepModel
from ankiforge.ui.views.pipelines_view import (
    PRESET_TEMPLATES,
    PersonaIdentityCard,
    PersonaSelectorDialog,
    PipelinesView,
    PromptPreviewDialog,
    StepPickerDialog,
    audit_pipeline_dag,
)


def test_pipelines_view_initialization_and_refresh(qtbot):
    """Vérifie l'initialisation et le chargement des pipelines, personas, flux DAG et inspecteur."""
    p1 = PersonaModel.create(name="Architecte Test", system_prompt="Test Prompt", output_format="json")
    PersonaModel.create(name="Linter Test", system_prompt="Linter Prompt", output_format="json")

    pipe = PipelineModel.create(name="Pipeline Test DAG")
    s1 = PipelineStepModel.create(pipeline=pipe, step_type="RAG_RETRIEVAL", step_order=1, config_data=json.dumps({"top_k": 4}))
    s2 = PipelineStepModel.create(pipeline=pipe, persona=p1, step_type="LLM_PROMPT", step_order=2)
    PipelineStepModel.create(
        pipeline=pipe,
        step_type="HUMAN_VALIDATION",
        step_order=3,
        on_success_step=s1,
        on_failure_step=s2,
        failure_behavior="goto_failure_step",
        config_data=json.dumps({"human_title": "Validation Spécifique"}),
    )

    view = PipelinesView()
    qtbot.addWidget(view)

    assert view.pipeline_combo.count() == 1
    assert len(view.current_steps) == 3
    assert len(view._step_widgets) == 3
    assert not view.inspector.isHidden()

    # Vérification des types et des liaisons DAG chargées
    assert view.current_steps[0]["type"] == "RAG_RETRIEVAL"
    assert view.current_steps[0]["config"]["top_k"] == 4
    assert view.current_steps[1]["type"] == "LLM_PROMPT"
    assert view.current_steps[1]["persona"].name == "Architecte Test"
    assert view.current_steps[2]["type"] == "HUMAN_VALIDATION"
    assert view.current_steps[2]["on_success_order"] == 1
    assert view.current_steps[2]["on_failure_order"] == 2
    assert view.current_steps[2]["failure_behavior"] == "goto_failure_step"
    assert view.current_steps[2]["config"]["human_title"] == "Validation Spécifique"


def test_pipelines_view_add_step_and_save_with_branching(qtbot):
    """Vérifie l'ajout d'actions systèmes et d'agents avec branchements, config_data et sauvegarde Peewee."""
    p_gen = PersonaModel.create(name="Générateur Test", system_prompt="Test", output_format="json")
    pipe = PipelineModel.create(name="Pipeline Vide")

    view = PipelinesView()
    qtbot.addWidget(view)

    # Sélectionner le pipeline créé
    idx = view.pipeline_combo.findText("Pipeline Vide")
    if idx >= 0:
        view.pipeline_combo.setCurrentIndex(idx)

    # Ajouter Étape 1 : Pause Copilote
    view.add_step({"type": "HUMAN_VALIDATION"})

    # Ajouter Étape 2 : Agent IA
    view.add_step({"type": "LLM_PROMPT", "persona": p_gen})

    assert len(view.current_steps) == 2

    # Configurer un branchement conditionnel et un config_data sur l'étape 1
    view.current_steps[0]["on_success_order"] = 2
    view.current_steps[0]["failure_behavior"] = "continue"
    view.current_steps[0]["config"] = {"human_title": "Pause Test Titre"}

    # Sauvegarder
    view.btn_save_pipeline.click()

    # Vérification en BDD
    saved_steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == pipe).order_by(PipelineStepModel.step_order))
    assert len(saved_steps) == 2
    assert saved_steps[0].step_type == "HUMAN_VALIDATION"
    assert saved_steps[0].persona is None
    assert saved_steps[0].on_success_step == saved_steps[1]
    assert saved_steps[0].failure_behavior == "continue"
    assert json.loads(saved_steps[0].config_data)["human_title"] == "Pause Test Titre"

    assert saved_steps[1].step_type == "LLM_PROMPT"
    assert saved_steps[1].persona.name == "Générateur Test"


def test_pipelines_view_inline_insertion(qtbot):
    """Vérifie l'insertion contextuelle d'une étape entre deux étapes existantes."""
    pipe = PipelineModel.create(name="Pipeline Insertion")
    PipelineStepModel.create(pipeline=pipe, step_type="RAG_RETRIEVAL", step_order=1)
    PipelineStepModel.create(pipeline=pipe, step_type="HUMAN_VALIDATION", step_order=2)

    view = PipelinesView()
    qtbot.addWidget(view)

    idx = view.pipeline_combo.findText("Pipeline Insertion")
    if idx >= 0:
        view.pipeline_combo.setCurrentIndex(idx)

    assert len(view.current_steps) == 2
    # Insérer une étape Python Tool à la position 1 (entre 0 et 1)
    view.add_step({"type": "PYTHON_TOOL", "config": {"tool_name": "clean_html_latex"}}, insert_at=1)

    assert len(view.current_steps) == 3
    assert view.current_steps[0]["type"] == "RAG_RETRIEVAL"
    assert view.current_steps[1]["type"] == "PYTHON_TOOL"
    assert view.current_steps[2]["type"] == "HUMAN_VALIDATION"


def test_step_picker_dialog_filtering_and_selection(qtbot):
    """Vérifie le filtrage et la sélection d'éléments dans le catalogue StepPickerDialog."""
    p1 = PersonaModel.create(name="Persona Recherche", system_prompt="Expert en RAG et synthèse")
    p2 = PersonaModel.create(name="Persona Code", system_prompt="Expert Python")

    dlg = StepPickerDialog(personas=[p1, p2])
    qtbot.addWidget(dlg)

    # Vérification du nombre de cartes initiales (1 Prompt Libre + 2 Personas + 4 Actions Système = 7)
    assert len(dlg._cards) == 7

    # Filtrer par "Code"
    dlg.edit_search.setText("Code")
    visible_cards = [c for c, _ in dlg._cards if not c.isHidden()]
    assert len(visible_cards) >= 1

    # Sélectionner une carte
    dlg._cards[0][0].click() if hasattr(dlg._cards[0][0], "click") else dlg._on_item_selected(dlg._cards[0][0].payload)
    assert dlg.selected_step_data is not None


def test_persona_identity_card_and_selector(qtbot):
    """Vérifie la mise à jour de la carte d'identité Persona et le sélecteur associé."""
    p1 = PersonaModel.create(name="Persona A", system_prompt="Prompt pour A")
    p2 = PersonaModel.create(name="Persona B", system_prompt="Prompt pour B")

    card = PersonaIdentityCard()
    qtbot.addWidget(card)

    card.set_persona(p1)
    assert "Persona A" in card.lbl_title.text()

    card.set_persona(None)
    assert "Aucun Agent" in card.lbl_title.text()

    # Sélecteur
    dlg = PersonaSelectorDialog(personas=[p1, p2], current_persona=p1)
    qtbot.addWidget(dlg)
    dlg._on_selected({"persona": p2})
    assert dlg.selected_persona == p2


def test_pipelines_view_clone_pipeline(qtbot):
    """Vérifie le clonage complet d'un pipeline avec toutes ses étapes, config et liaisons."""
    p1 = PersonaModel.create(name="Agent Clone", system_prompt="Clone", output_format="json")
    pipe = PipelineModel.create(name="Pipeline Original")
    s1 = PipelineStepModel.create(pipeline=pipe, persona=p1, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps({"input_variable": "custom_in"}))
    PipelineStepModel.create(pipeline=pipe, step_type="HUMAN_VALIDATION", step_order=2, on_success_step=s1)

    view = PipelinesView()
    qtbot.addWidget(view)

    # Sélectionner le pipeline
    idx = view.pipeline_combo.findText("Pipeline Original")
    if idx >= 0:
        view.pipeline_combo.setCurrentIndex(idx)

    view._on_clone_pipeline()

    cloned_pipe = PipelineModel.get_or_none(PipelineModel.name == "Pipeline Original (Copie)")
    assert cloned_pipe is not None
    cloned_steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == cloned_pipe).order_by(PipelineStepModel.step_order))
    assert len(cloned_steps) == 2
    assert cloned_steps[0].step_type == "LLM_PROMPT"
    assert json.loads(cloned_steps[0].config_data)["input_variable"] == "custom_in"
    assert cloned_steps[1].step_type == "HUMAN_VALIDATION"
    assert cloned_steps[1].on_success_step == cloned_steps[0]


def test_pipelines_view_reorder_and_delete_step(qtbot):
    """Vérifie le réordonnancement (Monter/Descendre) et la suppression d'étapes."""
    pipe = PipelineModel.create(name="Pipeline Reorder")
    PipelineStepModel.create(pipeline=pipe, step_type="RAG_RETRIEVAL", step_order=1)
    PipelineStepModel.create(pipeline=pipe, step_type="HUMAN_VALIDATION", step_order=2)

    view = PipelinesView()
    qtbot.addWidget(view)

    idx = view.pipeline_combo.findText("Pipeline Reorder")
    if idx >= 0:
        view.pipeline_combo.setCurrentIndex(idx)

    assert len(view._step_widgets) == 2
    # Inverser les étapes (Descendre la première)
    view._step_widgets[0].btn_down.click()
    assert view.current_steps[0]["type"] == "HUMAN_VALIDATION"
    assert view.current_steps[1]["type"] == "RAG_RETRIEVAL"

    # Supprimer une étape
    view._step_widgets[0].btn_delete.click()
    assert len(view.current_steps) == 1
    assert view.current_steps[0]["type"] == "RAG_RETRIEVAL"


def test_pipelines_view_preset_template_instantiation(qtbot):
    """Vérifie l'instanciation directe d'un modèle prédéfini."""
    PersonaModel.create(name="Default Agent", system_prompt="Test", output_format="json")
    view = PipelinesView()
    qtbot.addWidget(view)

    tpl = PRESET_TEMPLATES[0]
    view._apply_preset_template(tpl)

    created_pipe = PipelineModel.get_or_none(PipelineModel.name == f"{tpl['name']} (Instancié)")
    assert created_pipe is not None
    steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == created_pipe).order_by(PipelineStepModel.step_order))
    assert len(steps) == len(tpl["steps"])


def test_dag_linter_audit():
    """Vérifie la détection d'anomalies par le linter DAG."""
    # DAG Valide
    valid_steps: list[dict[str, Any]] = [
        {"type": "RAG_RETRIEVAL", "config": {"output_variable": "text_source"}},
        {"type": "LLM_PROMPT", "persona": PersonaModel(name="Arch"), "config": {"input_variable": "text_source", "output_variable": "cards"}},
    ]
    issues = audit_pipeline_dag(valid_steps)
    assert len(issues) == 0

    # DAG avec variable manquante
    broken_steps: list[dict[str, Any]] = [
        {"type": "LLM_PROMPT", "persona": PersonaModel(name="Arch"), "config": {"input_variable": "inexistant_variable"}},
    ]
    issues_broken = audit_pipeline_dag(broken_steps)
    assert len(issues_broken) == 1
    assert "inexistant_variable" in issues_broken[0]


def test_prompt_preview_dialog(qtbot):
    """Vérifie la modale d'aperçu Jinja2 du prompt interpolé."""
    dlg = PromptPreviewDialog("Prompt avec {{ state.variables.text_source }} et {{ state.initial_prompt }}")
    qtbot.addWidget(dlg)
    assert "Soit A une matrice carrée" in dlg.findChild(QPlainTextEdit).toPlainText()

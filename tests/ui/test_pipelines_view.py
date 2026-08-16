from ankiforge.database.models import PersonaModel, PipelineModel, PipelineStepModel
from ankiforge.ui.views.pipelines_view import PipelinesView


def test_pipelines_view_initialization_and_refresh(qtbot):
    """Vérifie l'initialisation et le chargement des pipelines et personas."""
    p1 = PersonaModel.create(name="Architecte Test", system_prompt="Test Prompt", output_format="json")
    PersonaModel.create(name="Linter Test", system_prompt="Linter Prompt", output_format="json")

    pipe = PipelineModel.create(name="Pipeline Test DAG")
    PipelineStepModel.create(pipeline=pipe, step_type="RAG_RETRIEVAL", step_order=1)
    PipelineStepModel.create(pipeline=pipe, persona=p1, step_type="LLM_PROMPT", step_order=2)
    PipelineStepModel.create(pipeline=pipe, step_type="HUMAN_VALIDATION", step_order=3)

    view = PipelinesView()
    qtbot.addWidget(view)

    assert view.pipeline_combo.count() == 1
    assert len(view.current_steps) == 3
    assert len(view._step_widgets) == 3

    # Vérification des types
    assert view.current_steps[0]["type"] == "RAG_RETRIEVAL"
    assert view.current_steps[1]["type"] == "LLM_PROMPT"
    assert view.current_steps[1]["persona"].name == "Architecte Test"
    assert view.current_steps[2]["type"] == "HUMAN_VALIDATION"


def test_pipelines_view_add_step_and_save(qtbot):
    """Vérifie l'ajout d'actions systèmes et d'agents, puis la sauvegarde en base."""
    PersonaModel.create(name="Générateur Test", system_prompt="Test", output_format="json")
    pipe = PipelineModel.create(name="Pipeline Vide")

    view = PipelinesView()
    qtbot.addWidget(view)

    # Ajouter une étape Action Système (Pause)
    view.element_to_add_combo.setCurrentIndex(1)  # Pause Copilote
    view.btn_add_step.click()

    # Ajouter un Agent IA
    # Trouver l'index de l'agent dans le combo
    agent_idx = -1
    for i in range(view.element_to_add_combo.count()):
        data = view.element_to_add_combo.itemData(i)
        if data and data.get("persona") and data["persona"].name == "Générateur Test":
            agent_idx = i
            break
    assert agent_idx != -1
    view.element_to_add_combo.setCurrentIndex(agent_idx)
    view.btn_add_step.click()

    assert len(view.current_steps) == 2

    # Sauvegarder
    view.btn_save_pipeline.click()

    # Vérification en BDD
    saved_steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == pipe).order_by(PipelineStepModel.step_order))
    assert len(saved_steps) == 2
    assert saved_steps[0].step_type == "HUMAN_VALIDATION"
    assert saved_steps[0].persona is None
    assert saved_steps[1].step_type == "LLM_PROMPT"
    assert saved_steps[1].persona.name == "Générateur Test"


def test_pipelines_view_reorder_and_delete_step(qtbot):
    """Vérifie le réordonnancement (Monter/Descendre) et la suppression d'étapes."""
    pipe = PipelineModel.create(name="Pipeline Reorder")
    PipelineStepModel.create(pipeline=pipe, step_type="RAG_RETRIEVAL", step_order=1)
    PipelineStepModel.create(pipeline=pipe, step_type="HUMAN_VALIDATION", step_order=2)

    view = PipelinesView()
    qtbot.addWidget(view)

    assert len(view._step_widgets) == 2
    # Inverser les étapes (Descendre la première)
    view._step_widgets[0].btn_down.click()
    assert view.current_steps[0]["type"] == "HUMAN_VALIDATION"
    assert view.current_steps[1]["type"] == "RAG_RETRIEVAL"

    # Supprimer une étape
    view._step_widgets[0].btn_delete.click()
    assert len(view.current_steps) == 1
    assert view.current_steps[0]["type"] == "RAG_RETRIEVAL"

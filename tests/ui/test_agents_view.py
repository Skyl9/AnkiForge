import json
import uuid

from ankiforge.database.models import LLMConfigModel, PersonaModel
from ankiforge.ui.views.agents_view import AgentsView


def test_agents_view_load_and_selection(qtbot):
    """Vérifie le chargement des agents et l'affichage des informations."""
    uid = uuid.uuid4().hex[:6]
    cfg = LLMConfigModel.create(provider="openai", model_id=f"gpt-4o-{uid}", display_name=f"GPT-4o {uid}")
    PersonaModel.create(
        name=f"Architecte {uid}",
        description="Crée le plan de cours",
        system_prompt="Tu es un architecte...",
        output_format="json",
        allowed_tools=json.dumps(["query_vector_db", "generate_css"]),
        llm_config=cfg,
    )

    view = AgentsView()
    qtbot.addWidget(view)

    assert view.persona_list.count() >= 1
    assert view.name_edit.text() == f"Architecte {uid}"
    assert view.desc_edit.text() == "Crée le plan de cours"
    assert view.format_combo.currentText() == "json"

    # Vérification des checkboxes d'outils
    assert view._tool_checkboxes["query_vector_db"].isChecked() is True
    assert view._tool_checkboxes["generate_css"].isChecked() is True
    assert view._tool_checkboxes["read_anki_stats"].isChecked() is False

    # Vérification du moteur sélectionné
    assert view.engine_combo.currentData() is not None
    assert view.engine_combo.currentData().id == cfg.id


def test_agents_view_save_modifications(qtbot):
    """Vérifie la mise à jour des outils, du prompt et du moteur dédié."""
    uid = uuid.uuid4().hex[:6]
    p = PersonaModel.create(
        name=f"Linteur {uid}",
        system_prompt="Prompt initial",
        output_format="text",
        allowed_tools="[]",
    )

    view = AgentsView()
    qtbot.addWidget(view)

    # Modifier le prompt via insertion de snippet
    view.prompt_edit.setPlainText("Prompt avec ")
    view._insert_jinja_snippet("{{ text_source }}")

    # Cocher un outil
    view._tool_checkboxes["read_anki_stats"].setChecked(True)

    # Sauvegarder
    view.btn_save.click()

    # Recharger depuis la BDD
    updated_p = PersonaModel.get_by_id(p.id)
    assert "{{ text_source }}" in updated_p.system_prompt
    tools = json.loads(updated_p.allowed_tools)
    assert "read_anki_stats" in tools

import json
import uuid

from ankiforge.database.models import LLMConfigModel, PersonaFolderModel, PersonaModel
from ankiforge.ui.views.agents_view import (
    AgentPromptPreviewDialog,
    AgentsView,
    AgentTestDialog,
)


def test_agents_view_load_and_selection(qtbot):
    """Vérifie le chargement des agents et l'affichage des informations."""
    uid = uuid.uuid4().hex[:6]
    folder = PersonaFolderModel.create(name=f"Dossier {uid}")
    cfg = LLMConfigModel.create(provider="openai", model_id=f"gpt-4o-{uid}", display_name=f"GPT-4o {uid}")
    PersonaModel.create(
        name=f"Architecte {uid}",
        description="Crée le plan de cours",
        system_prompt="Tu es un architecte...",
        output_format="json",
        persona_type="pipeline",
        folder=folder,
        allowed_tools=json.dumps(["query_vector_db", "generate_css"]),
        llm_config=cfg,
    )

    view = AgentsView()
    qtbot.addWidget(view)

    assert view.persona_tree.topLevelItemCount() >= 1
    assert view.name_edit.text() == f"Architecte {uid}"
    assert view.desc_edit.text() == "Crée le plan de cours"
    assert view.format_combo.currentText() == "json"
    assert view.scope_combo.currentData() == "pipeline"
    assert view.folder_combo.currentData() == folder.id

    # Vérification des checkboxes d'outils
    assert view._tool_checkboxes["query_vector_db"].isChecked() is True
    assert view._tool_checkboxes["generate_css"].isChecked() is True
    assert view._tool_checkboxes["read_anki_stats"].isChecked() is False

    # Vérification du moteur sélectionné
    assert view.engine_combo.currentData() is not None
    assert view.engine_combo.currentData().id == cfg.id


def test_agents_view_save_modifications(qtbot):
    """Vérifie la mise à jour des outils, du prompt, de la portée, du dossier et du moteur dédié."""
    uid = uuid.uuid4().hex[:6]
    folder = PersonaFolderModel.create(name=f"Dossier Cible {uid}")
    p = PersonaModel.create(
        name=f"Linteur {uid}",
        system_prompt="Prompt initial",
        output_format="text",
        persona_type="pipeline",
        allowed_tools="[]",
    )

    view = AgentsView()
    qtbot.addWidget(view)

    # Modifier le prompt via insertion de snippet
    view.prompt_edit.setPlainText("Prompt avec ")
    view._insert_jinja_snippet("{{ text_source }}")

    # Changer la portée vers MCP
    idx_mcp = view.scope_combo.findData("mcp")
    if idx_mcp != -1:
        view.scope_combo.setCurrentIndex(idx_mcp)

    # Changer le dossier
    idx_f = view.folder_combo.findData(folder.id)
    if idx_f != -1:
        view.folder_combo.setCurrentIndex(idx_f)

    # Cocher un outil
    view._tool_checkboxes["read_anki_stats"].setChecked(True)

    # Sauvegarder
    view.btn_save.click()

    # Recharger depuis la BDD
    updated_p = PersonaModel.get_by_id(p.id)
    assert "{{ text_source }}" in updated_p.system_prompt
    assert updated_p.persona_type == "mcp"
    assert updated_p.folder.id == folder.id
    tools = json.loads(updated_p.allowed_tools)
    assert "read_anki_stats" in tools


def test_agents_view_clone_and_filter(qtbot):
    """Vérifie la duplication d'un agent et le filtrage par recherche et par portée."""
    uid = uuid.uuid4().hex[:6]
    p = PersonaModel.create(
        name=f"AgentUnique {uid}",
        description="Description unique",
        system_prompt="Prompt unique",
        output_format="json",
        persona_type="mcp",
        allowed_tools="[]",
    )

    view = AgentsView()
    qtbot.addWidget(view)

    # Filtrer par recherche textuelle
    view.edit_search.setText(f"AgentUnique {uid}")
    assert view.persona_tree.topLevelItemCount() >= 1

    # Filtrer par scope
    view._set_scope_filter("mcp")
    view._set_scope_filter("pipeline")
    view._set_scope_filter("all")

    # Sélectionner et cloner
    view._current_agent = p
    view._on_clone_agent()

    clones = list(PersonaModel.select().where(PersonaModel.name.contains(f"AgentUnique {uid} (Copie)")))
    assert len(clones) == 1
    assert clones[0].persona_type == "mcp"


def test_agents_view_subfolders_and_hierarchy(qtbot):
    """Vérifie la gestion des dossiers et sous-dossiers récursifs et suppression."""
    uid = uuid.uuid4().hex[:6]
    parent_folder = PersonaFolderModel.create(name=f"Parent {uid}")
    sub_folder = PersonaFolderModel.create(name=f"Enfant {uid}", parent=parent_folder)

    assert sub_folder.get_full_path() == f"Parent {uid} / Enfant {uid}"

    p = PersonaModel.create(
        name=f"Agent Sub {uid}",
        system_prompt="Test Subfolder",
        folder=sub_folder,
    )

    view = AgentsView()
    qtbot.addWidget(view)

    # Vérification que le parent et l'enfant sont dans l'arbre
    assert view.persona_tree.topLevelItemCount() >= 1

    # Suppression récursive du dossier parent
    view._delete_folder_recursive(parent_folder)
    view.refresh_data()

    # L'agent doit exister et être libéré (folder=None)
    reloaded_p = PersonaModel.get_by_id(p.id)
    assert reloaded_p.folder is None


def test_agents_view_dialogs(qtbot):
    """Vérifie l'ouverture et le fonctionnement des modales associées."""
    uid = uuid.uuid4().hex[:6]
    p = PersonaModel.create(
        name=f"TestDialogs {uid}",
        system_prompt="Prompt avec {{ text_source }}",
        output_format="json",
        persona_type="universal",
    )

    # Preview Jinja2 Dialog
    dlg_preview = AgentPromptPreviewDialog(template_str=p.system_prompt)
    qtbot.addWidget(dlg_preview)
    assert dlg_preview is not None

    # Test Agent Dialog
    dlg_test = AgentTestDialog(persona=p)
    qtbot.addWidget(dlg_test)
    dlg_test._run_test()
    assert "Réponse du Modèle :" in dlg_test.output_text.toPlainText() or "Prompt Système Interpolé" in dlg_test.output_text.toPlainText()

import json
import uuid

from ankiforge.database.models import PersonaFolderModel, PersonaModel
from ankiforge.services.ai.persona_templates import PERSONA_TEMPLATES
from ankiforge.ui.views.agents_view.dialogs.persona_wizard_dialog import (
    PersonaCreationWizardDialog,
)


def test_persona_wizard_init_and_mode_switch(qtbot):
    """Vérifie l'initialisation du wizard et le basculement entre galerie et mode personnalisé."""
    dlg = PersonaCreationWizardDialog()
    qtbot.addWidget(dlg)

    assert dlg.stack.currentIndex() == 0
    assert dlg.btn_mode_gallery.isChecked()

    dlg._switch_mode(1)
    assert dlg.stack.currentIndex() == 1
    assert dlg.btn_mode_custom.isChecked()

    dlg._switch_mode(0)
    assert dlg.stack.currentIndex() == 0
    assert dlg.btn_mode_gallery.isChecked()


def test_persona_wizard_gallery_filtering(qtbot):
    """Vérifie la recherche textuelle et le filtrage par catégorie dans la galerie."""
    dlg = PersonaCreationWizardDialog()
    qtbot.addWidget(dlg)

    # Filtrer par catégorie 'Langues & Traduction'
    dlg._set_category_filter("Langues & Traduction")
    visible_cards = [card for card, _ in dlg._template_cards if not card.isHidden()]
    assert len(visible_cards) >= 1
    assert all(card.template.category == "Langues & Traduction" for card, _ in dlg._template_cards if not card.isHidden())

    # Réinitialiser à Tous
    dlg._set_category_filter("all")
    visible_cards_all = [card for card, _ in dlg._template_cards if not card.isHidden()]
    assert len(visible_cards_all) == len(PERSONA_TEMPLATES)

    # Filtrer par recherche textuelle
    dlg.edit_gallery_search.setText("Wozniak")
    visible_wozniak = [card for card, _ in dlg._template_cards if not card.isHidden()]
    assert len(visible_wozniak) >= 1
    assert any("Wozniak" in card.template.name for card in visible_wozniak)


def test_persona_wizard_create_from_template(qtbot):
    """Vérifie la création d'un persona depuis un modèle prêt à l'emploi."""
    uid = uuid.uuid4().hex[:6]
    folder = PersonaFolderModel.create(name=f"Dossier {uid}")

    dlg = PersonaCreationWizardDialog(cached_folders=[folder], current_folder=folder)
    qtbot.addWidget(dlg)

    # Sélectionner le template KaTeX
    stem_tpl = next(t for t in PERSONA_TEMPLATES if t.id == "stem_katex")
    dlg._on_template_card_clicked(stem_tpl)

    agent_name = f"Maths KaTeX {uid}"
    dlg.edit_template_agent_name.setText(agent_name)

    # Créer
    dlg._on_create_from_template()

    assert dlg.created_persona is not None
    created = PersonaModel.get_or_none(PersonaModel.name == agent_name)
    assert created is not None
    assert created.output_format == "json"
    assert created.persona_type == "pipeline"
    assert created.folder.id == folder.id
    assert "$formule$" in created.system_prompt


def test_persona_wizard_create_custom_persona(qtbot):
    """Vérifie la création d'un persona personnalisé vierge."""
    uid = uuid.uuid4().hex[:6]
    folder = PersonaFolderModel.create(name=f"Dossier Custom {uid}")

    dlg = PersonaCreationWizardDialog(cached_folders=[folder], current_folder=folder)
    qtbot.addWidget(dlg)

    dlg._switch_mode(1)
    agent_name = f"Agent Vierge {uid}"
    dlg.edit_custom_name.setText(agent_name)
    dlg.edit_custom_desc.setText("Description personnalisée")
    dlg.edit_custom_prompt.setPlainText("Prompt sur mesure {{ text_source }}")

    idx_mcp = dlg.combo_custom_scope.findData("mcp")
    if idx_mcp != -1:
        dlg.combo_custom_scope.setCurrentIndex(idx_mcp)

    dlg._on_create_custom_persona()

    assert dlg.created_persona is not None
    created = PersonaModel.get_or_none(PersonaModel.name == agent_name)
    assert created is not None
    assert created.description == "Description personnalisée"
    assert created.persona_type == "mcp"
    assert "Prompt sur mesure" in created.system_prompt
    tools = json.loads(created.allowed_tools)
    assert isinstance(tools, list)

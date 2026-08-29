"""
Tests unitaires pour le service de versioning des Personas / Agents IA (PersonaVersionService).
"""

import json

from ankiforge.database.models import LLMConfigModel, PersonaModel, PersonaVersionModel
from ankiforge.services.ai.persona_version_service import PersonaVersionService


def test_create_snapshot_initial(mock_db):
    """Vérifie la création du snapshot initial v1 d'un persona."""
    persona = PersonaModel.create(
        name="Auditeur Wozniak",
        description="Auditeur 20 règles",
        system_prompt="Tu es un auditeur Wozniak.",
        output_format="json",
        persona_type="pipeline",
        allowed_tools=json.dumps(["query_peewee"]),
    )

    v1 = PersonaVersionService.create_snapshot(persona, commit_message="Création initiale")
    assert v1 is not None
    assert v1.version_number == 1
    assert v1.is_active is True
    assert v1.system_prompt == "Tu es un auditeur Wozniak."
    assert v1.commit_message == "Création initiale"

    versions = PersonaVersionService.get_versions(persona.id)
    assert len(versions) == 1
    assert versions[0].id == v1.id


def test_create_snapshot_deduplication(mock_db):
    """Vérifie qu'un snapshot n'est pas recréé si aucun champ n'a été modifié."""
    persona = PersonaModel.create(
        name="Extracteur",
        system_prompt="Extrais le cours.",
        output_format="text",
    )

    v1 = PersonaVersionService.create_snapshot(persona, commit_message="V1")
    v2 = PersonaVersionService.create_snapshot(persona, commit_message="V2 tentative")

    assert v1.id == v2.id
    assert PersonaVersionModel.select().where(PersonaVersionModel.persona == persona).count() == 1


def test_create_snapshot_increment(mock_db):
    """Vérifie l'incrémentation de version et la bascule du flag is_active."""
    persona = PersonaModel.create(
        name="Générateur QA",
        system_prompt="Génère 5 questions.",
        output_format="json",
    )

    v1 = PersonaVersionService.create_snapshot(persona, commit_message="V1")

    # Modification du prompt
    persona.system_prompt = "Génère 10 questions précises et atomiques."
    persona.save()

    v2 = PersonaVersionService.create_snapshot(persona, commit_message="Augmentation du volume de questions")
    assert v2 is not None
    assert v2.version_number == 2
    assert v2.is_active is True
    assert v2.system_prompt == "Génère 10 questions précises et atomiques."

    # L'ancienne version doit être désactivée
    v1_reloaded = PersonaVersionModel.get_by_id(v1.id)
    assert v1_reloaded.is_active is False

    versions = PersonaVersionService.get_versions(persona.id)
    assert len(versions) == 2
    assert versions[0].version_number == 2
    assert versions[1].version_number == 1


def test_restore_version(mock_db):
    """Vérifie la restauration d'une version passée et la mise à jour du persona."""
    llm1 = LLMConfigModel.create(display_name="GPT-4o", provider="openai", model_id="gpt-4o")
    llm2 = LLMConfigModel.create(display_name="Claude 3.5 Sonnet", provider="anthropic", model_id="claude-3-5-sonnet")

    persona = PersonaModel.create(
        name="Traducteur",
        description="Traduction FR vers EN",
        system_prompt="Translate from French to English.",
        output_format="text",
        persona_type="pipeline",
        llm_config=llm1,
    )

    v1 = PersonaVersionService.create_snapshot(persona, commit_message="V1")

    # Mutation vers V2
    persona.system_prompt = "Translate from French to German with KaTeX formulas."
    persona.output_format = "json"
    persona.llm_config = llm2
    persona.save()

    v2 = PersonaVersionService.create_snapshot(persona, commit_message="V2 German")

    # Restauration de V1
    restored_persona = PersonaVersionService.restore_version(v1.id)
    assert restored_persona.system_prompt == "Translate from French to English."
    assert restored_persona.output_format == "text"
    assert restored_persona.llm_config_id == llm1.id

    # Vérification des flags is_active
    v1_reloaded = PersonaVersionModel.get_by_id(v1.id)
    v2_reloaded = PersonaVersionModel.get_by_id(v2.id)
    assert v1_reloaded.is_active is True
    assert v2_reloaded.is_active is False


def test_diff_prompt():
    """Vérifie le calcul des différentiels de prompt pour l'affichage visuel."""
    old_p = "Ligne 1\nLigne 2 originale\nLigne 3"
    new_p = "Ligne 1\nLigne 2 modifiée\nLigne 3\nLigne 4 ajoutée"

    diff = PersonaVersionService.diff_prompt(old_p, new_p)
    types = [chunk["type"] for chunk in diff]

    assert "equal" in types
    assert "insert" in types
    assert "delete" in types


def test_cascade_delete_persona(mock_db):
    """Vérifie que la suppression d'un persona supprime en cascade toutes ses versions."""
    persona = PersonaModel.create(
        name="Agent Éphémère",
        system_prompt="Test cascade.",
    )
    PersonaVersionService.create_snapshot(persona, "V1")
    persona.system_prompt = "Test cascade modif."
    PersonaVersionService.create_snapshot(persona, "V2", force=True)

    assert PersonaVersionModel.select().where(PersonaVersionModel.persona == persona).count() == 2

    persona.delete_instance()
    assert PersonaVersionModel.select().where(PersonaVersionModel.persona == persona).count() == 0

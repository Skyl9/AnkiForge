# tests/test_models.py
import json
import pytest
from peewee import IntegrityError

from ankiforge.database.models import (
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    FolderModel,
    DocumentModel,
    AgentModel,
    PipelineModel,
    PipelineStepModel,
)


def test_note_version_default_source():
    """Vérifie que la source par défaut lors de la création d'une version via add_version est 'manual'."""
    note_type = NoteTypeModel.create(name="Basic Default", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="unique-default", note_type=note_type)

    # Action sans préciser la source
    version = note.add_version({"Front": "Test"})

    assert version.source == "manual"


def test_deck_hierarchy_and_card_cascade():
    """Vérifie la hiérarchie des paquets et la suppression en cascade des cartes."""
    from ankiforge.database.models import DeckModel, CardModel

    parent_deck = DeckModel.create(name="Parent")
    child_deck = DeckModel.create(name="Parent::Child", parent_deck=parent_deck)

    note_type = NoteTypeModel.create(name="Basic Hierarchy", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="NoteHierarchy", note_type=note_type)

    CardModel.create(note=note, deck=child_deck, template_index=0)
    assert CardModel.select().count() == 1

    # Si on supprime la note, la carte disparaît
    note.delete_instance()
    assert CardModel.select().count() == 0


def test_deck_cascade_deletion():
    """Vérifie que la suppression d'un deck supprime les cartes associées."""
    from ankiforge.database.models import DeckModel, CardModel

    deck = DeckModel.create(name="DeckToKill")
    note_type = NoteTypeModel.create(name="Basic Deck Cascade", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="NoteDeck", note_type=note_type)

    CardModel.create(note=note, deck=deck, template_index=0)
    assert CardModel.select().count() == 1

    deck.delete_instance()
    assert CardModel.select().count() == 0


def test_seed_initial_data_is_idempotent():
    """Vérifie que l'appel multiple à seed_initial_data ne duplique pas les données."""
    from ankiforge.database.models import seed_initial_data, LLMConfigModel

    # Vidons les tables pour le test
    AgentModel.delete().execute()
    PipelineModel.delete().execute()
    LLMConfigModel.delete().execute()

    # Premier appel
    seed_initial_data()
    agent_count = AgentModel.select().count()
    assert agent_count > 0

    llm_count = LLMConfigModel.select().count()
    assert llm_count > 0

    # Deuxième appel
    seed_initial_data()
    assert AgentModel.select().count() == agent_count
    assert LLMConfigModel.select().count() == llm_count


def test_note_versioning_system():
    """Vérifie que la méthode add_version crée bien un historique et désactive l'ancienne version."""

    # 1. PRÉPARATION (Given)
    note_type = NoteTypeModel.create(name="Test Model", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note = NoteModel.create(guid="unique-123", note_type=note_type, status="new")

    # 2. ACTION (When) - On ajoute une version 1 (comme le ferait l'IA)
    v1_content = {"Front": "Question 1", "Back": "Réponse 1"}
    v1 = note.add_version(v1_content, source="ai")

    # On ajoute une version 2 (comme le ferait l'utilisateur via l'interface)
    v2_content = {"Front": "Question 1 (Corrigée)", "Back": "Réponse 1"}
    v2 = note.add_version(v2_content, source="manual")

    # 3. VÉRIFICATION (Then)
    assert note.versions.count() == 2, "La note devrait posséder exactement 2 versions."

    # On recharge les versions depuis la base pour être sûr de leur état actuel
    v1_reloaded = NoteVersionModel.get_by_id(v1.id)
    v2_reloaded = NoteVersionModel.get_by_id(v2.id)

    assert v1_reloaded.is_active is False, "L'ancienne version (v1) devrait être désactivée."
    assert v2_reloaded.is_active is True, "La nouvelle version (v2) devrait être active."
    assert v2_reloaded.version_number == 2, "La v2 devrait porter le numéro 2."

    # On vérifie que les données ne sont pas corrompues
    saved_content = json.loads(v2_reloaded.content)
    assert saved_content["Front"] == "Question 1 (Corrigée)"


def test_document_can_be_orphan():
    """Vérifie qu'on peut créer un document sans l'attacher à un dossier (folder=None)."""
    doc = DocumentModel.create(title="Doc Orphelin", content="Contenu libre")

    # Le document doit exister en base avec folder à null
    doc_from_db = DocumentModel.get_by_id(doc.id)
    assert doc_from_db.title == "Doc Orphelin"
    assert doc_from_db.folder is None


def test_cascade_deletion_folder_documents():
    """Vérifie que la suppression d'un dossier détruit bien tous les documents à l'intérieur."""

    # 1. PRÉPARATION
    folder = FolderModel.create(name="Mathématiques Ensimag")

    doc1 = DocumentModel.create(title="Chapitre 1", content="Contenu 1", folder=folder)
    doc2 = DocumentModel.create(title="Chapitre 2", content="Contenu 2", folder=folder)

    assert DocumentModel.select().count() == 2

    # 2. ACTION - On détruit le dossier
    folder.delete_instance()

    # 3. VÉRIFICATION - SQLite doit avoir fait le ménage automatiquement
    assert not DocumentModel.select().where(DocumentModel.title == doc2.title)
    assert not DocumentModel.select().where(DocumentModel.title == doc1.title)
    assert DocumentModel.select().count() == 0, "Les documents orphelins n'ont pas été supprimés en cascade !"


def test_cascade_deletion_note_versions():
    """Vérifie que supprimer une Note détruit tout son historique de versions."""

    # 1. PRÉPARATION
    note_type = NoteTypeModel.create(name="Basic", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="abc", note_type=note_type)
    note.add_version({"Test": "1"})
    note.add_version({"Test": "2"})

    assert NoteVersionModel.select().count() == 2

    # 2. ACTION - On détruit la note racine
    note.delete_instance()

    # 3. VÉRIFICATION
    assert NoteVersionModel.select().count() == 0, "L'historique n'a pas été supprimé avec la Note !"


def test_cascade_deletion_agent_pipeline_step():
    """Vérifie que la suppression d'un Agent supprime ses étapes dans le pipeline."""
    pipeline = PipelineModel.create(name="Pipe Test Agent Cascade")
    agent = AgentModel.create(name="Agent à supprimer", system_prompt="Prompt")
    PipelineStepModel.create(pipeline=pipeline, agent=agent, step_order=1)

    assert PipelineStepModel.select().count() == 1

    agent.delete_instance()

    assert PipelineStepModel.select().count() == 0, "L'étape du pipeline n'a pas été supprimée en cascade !"


def test_cascade_deletion_pipeline_steps():
    """Vérifie que la suppression d'un Pipeline supprime toutes ses étapes."""
    pipeline = PipelineModel.create(name="Pipe à supprimer")
    agent = AgentModel.create(name="Agent survivant", system_prompt="Prompt")
    PipelineStepModel.create(pipeline=pipeline, agent=agent, step_order=1)

    assert PipelineStepModel.select().count() == 1

    pipeline.delete_instance()

    assert PipelineStepModel.select().count() == 0, "L'étape du pipeline n'a pas été supprimée en cascade !"
    assert AgentModel.select().where(AgentModel.id == agent.id).exists(), "L'Agent aurait dû survivre à la suppression du Pipeline."


def test_ignored_duplicate_unique_constraint():
    """Vérifie qu'on ne peut pas ajouter deux fois la même paire de notes ignorées."""
    note_type = NoteTypeModel.create(name="Basic Dupe", fields_schema="[]", templates="[]", css_style="")
    note_a = NoteModel.create(guid="A", note_type=note_type)
    note_b = NoteModel.create(guid="B", note_type=note_type)

    from ankiforge.database.models import IgnoredDuplicateModel

    IgnoredDuplicateModel.create(note_a=note_a, note_b=note_b)

    with pytest.raises(IntegrityError):
        IgnoredDuplicateModel.create(note_a=note_a, note_b=note_b)


def test_llmconfig_unique_name_and_defaults():
    """Vérifie l'unicité du nom d'affichage et les valeurs par défaut."""
    from ankiforge.database.models import LLMConfigModel

    config1 = LLMConfigModel.create(display_name="GPT-4", provider="openai", model_id="gpt-4")

    assert config1.context_limit == 8192
    assert config1.temperature == 0.7

    with pytest.raises(IntegrityError):
        LLMConfigModel.create(display_name="GPT-4", provider="anthropic", model_id="claude")


def test_cascade_deletion_ignored_duplicate():
    """Vérifie que supprimer l'une des notes d'une paire ignorée supprime l'enregistrement d'ignorance."""
    note_type = NoteTypeModel.create(name="Basic Dupe Cascade", fields_schema="[]", templates="[]", css_style="")
    note_a = NoteModel.create(guid="CascadeA", note_type=note_type)
    note_b = NoteModel.create(guid="CascadeB", note_type=note_type)

    from ankiforge.database.models import IgnoredDuplicateModel

    IgnoredDuplicateModel.create(note_a=note_a, note_b=note_b)
    assert IgnoredDuplicateModel.select().count() == 1

    note_a.delete_instance()

    assert IgnoredDuplicateModel.select().count() == 0


def test_pipeline_step_unique_constraint():
    """Vérifie qu'on ne peut pas avoir deux étapes avec le même ordre dans un même pipeline."""

    # 1. PRÉPARATION
    pipeline = PipelineModel.create(name="Génération Standard")
    agent_extract = AgentModel.create(name="Extracteur", system_prompt="Test")
    agent_control = AgentModel.create(name="Controleur", system_prompt="Test")

    # 2. ACTION - On assigne l'extracteur à l'étape 1 (Succès)
    PipelineStepModel.create(pipeline=pipeline, agent=agent_extract, step_order=1)

    # 3. VÉRIFICATION - Tenter d'assigner le contrôleur à l'étape 1 doit faire crasher la base
    with pytest.raises(IntegrityError):
        PipelineStepModel.create(pipeline=pipeline, agent=agent_control, step_order=1)


def test_purge_old_versions():
    # 1. Préparation
    note_type = NoteTypeModel.create(name="Basic", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="purge_test", note_type=note_type)

    # Création de 8 versions
    for i in range(1, 9):
        note.add_version({"Test": f"Version {i}"})

    assert note.versions.count() == 8

    # 2. Action (On ne garde que les 3 dernières)
    deleted = NoteModel.purge_old_versions(keep_last=3)

    # 3. Vérification
    assert deleted == 5
    assert note.versions.count() == 3

    # On vérifie que ce sont bien les versions 6, 7 et 8 qui ont survécu
    remaining_versions = [v.version_number for v in note.versions.order_by(NoteVersionModel.version_number)]
    assert remaining_versions == [6, 7, 8]

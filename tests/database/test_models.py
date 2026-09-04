# tests/test_models.py
import json
from typing import Any, cast

import pytest
from peewee import IntegrityError

from ankiforge.database.models import (
    AICacheModel,
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    FolderModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    SettingModel,
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
    from ankiforge.database.models import CardModel, DeckModel

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
    from ankiforge.database.models import CardModel, DeckModel

    deck = DeckModel.create(name="DeckToKill")
    note_type = NoteTypeModel.create(name="Basic Deck Cascade", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="NoteDeck", note_type=note_type)

    CardModel.create(note=note, deck=deck, template_index=0)
    assert CardModel.select().count() == 1

    deck.delete_instance()
    assert CardModel.select().count() == 0


def test_seed_initial_data_is_idempotent():
    """Vérifie que l'appel multiple à seed_initial_data ne duplique pas les données."""
    from ankiforge.database.models import LLMConfigModel, seed_initial_data

    # Vidons les tables pour le test
    PersonaModel.delete().execute()
    PipelineModel.delete().execute()
    LLMConfigModel.delete().execute()

    # Premier appel
    seed_initial_data()
    agent_count = PersonaModel.select().count()
    assert agent_count > 0

    llm_count = LLMConfigModel.select().count()
    assert llm_count > 0

    # Deuxième appel
    seed_initial_data()
    assert PersonaModel.select().count() == agent_count
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
    assert cast(Any, note).versions.count() == 2, "La note devrait posséder exactement 2 versions."

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
    agent = PersonaModel.create(name="Agent à supprimer", system_prompt="Prompt")
    PipelineStepModel.create(pipeline=pipeline, persona=agent, step_order=1)

    assert PipelineStepModel.select().count() == 1

    agent.delete_instance()

    assert PipelineStepModel.select().count() == 0, "L'étape du pipeline n'a pas été supprimée en cascade !"


def test_cascade_deletion_pipeline_steps():
    """Vérifie que la suppression d'un Pipeline supprime toutes ses étapes."""
    pipeline = PipelineModel.create(name="Pipe à supprimer")
    agent = PersonaModel.create(name="Agent survivant", system_prompt="Prompt")
    PipelineStepModel.create(pipeline=pipeline, persona=agent, step_order=1)

    assert PipelineStepModel.select().count() == 1

    pipeline.delete_instance()

    assert PipelineStepModel.select().count() == 0, "L'étape du pipeline n'a pas été supprimée en cascade !"
    assert PersonaModel.select().where(PersonaModel.id == agent.id).exists(), "L'Agent aurait dû survivre à la suppression du Pipeline."


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
    agent_extract = PersonaModel.create(name="Extracteur", system_prompt="Test")
    agent_control = PersonaModel.create(name="Controleur", system_prompt="Test")

    # 2. ACTION - On assigne l'extracteur à l'étape 1 (Succès)
    PipelineStepModel.create(pipeline=pipeline, persona=agent_extract, step_order=1)

    # 3. VÉRIFICATION - Tenter d'assigner le contrôleur à l'étape 1 doit faire crasher la base
    with pytest.raises(IntegrityError):
        PipelineStepModel.create(pipeline=pipeline, persona=agent_control, step_order=1)


def test_purge_old_versions():
    # 1. Préparation
    note_type = NoteTypeModel.create(name="Basic", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="purge_test", note_type=note_type)

    # Création de 8 versions
    for i in range(1, 9):
        note.add_version({"Test": f"Version {i}"})

    assert cast(Any, note).versions.count() == 8

    # 2. Action (On ne garde que les 3 dernières)
    deleted = NoteModel.purge_old_versions(keep_last=3)

    # 3. Vérification
    assert deleted == 5
    assert cast(Any, note).versions.count() == 3

    # On vérifie que ce sont bien les versions 6, 7 et 8 qui ont survécu
    remaining_versions = [v.version_number for v in cast(Any, note).versions.order_by(NoteVersionModel.version_number)]
    assert remaining_versions == [6, 7, 8]


def test_media_version_cascade_and_restrict():
    """Vérifie le versionnement des médias : restriction sur suppression de média lié et cascade sur version."""
    # 1. Préparation
    note_type = NoteTypeModel.create(name="Media Test", fields_schema="[]", templates="[]", css_style="")
    note = NoteModel.create(guid="media_guid", note_type=note_type)
    version = note.add_version({"Front": "Test"})

    media = MediaModel.create(filename="abc.png", original_name="test.png", checksum="sha256_hash", mime_type="image/png")

    # Associer le média à la version de note
    _liaison = NoteVersionMediaModel.create(note_version=version, media=media)

    assert NoteVersionMediaModel.select().count() == 1

    # 2. Vérification de RESTRICT sur le média
    # Si on tente de détruire le média alors qu'il est lié, cela doit lever une IntegrityError (due à la contrainte SQLite foreign key)
    with pytest.raises(IntegrityError):
        media.delete_instance()

    # 3. Vérification de CASCADE sur la version de note
    # Si on détruit la version de la note, la liaison NoteVersionMediaModel doit être supprimée
    version.delete_instance()
    assert NoteVersionMediaModel.select().count() == 0

    # Maintenant que la liaison est supprimée, on doit pouvoir détruire le média physique
    media.delete_instance()
    assert MediaModel.select().count() == 0


def test_pipeline_conditional_steps():
    """Vérifie que les étapes de pipeline supportent les branchements conditionnels."""
    pipeline = PipelineModel.create(name="Conditional Pipeline")
    agent_gen = PersonaModel.create(name="Générateur", system_prompt="Prompt")
    agent_ok = PersonaModel.create(name="Succès", system_prompt="Prompt")
    agent_err = PersonaModel.create(name="Erreur", system_prompt="Prompt")

    step_ok = PipelineStepModel.create(pipeline=pipeline, persona=agent_ok, step_order=2)
    step_err = PipelineStepModel.create(pipeline=pipeline, persona=agent_err, step_order=3)

    # Étape principale qui branche vers step_ok en cas de succès et step_err en cas d'échec
    step_gen = PipelineStepModel.create(pipeline=pipeline, persona=agent_gen, step_order=1, on_success_step=step_ok, on_failure_step=step_err, failure_behavior="goto_failure_step")

    # Recharger et vérifier
    step_gen_reloaded = PipelineStepModel.get_by_id(step_gen.id)
    assert step_gen_reloaded.on_success_step == step_ok
    assert step_gen_reloaded.on_failure_step == step_err
    assert step_gen_reloaded.failure_behavior == "goto_failure_step"

    # Vérifier le comportement SET NULL en cas de suppression d'une cible
    step_ok.delete_instance()
    step_gen_after_delete = PipelineStepModel.get_by_id(step_gen.id)
    assert step_gen_after_delete.on_success_step is None
    assert step_gen_after_delete.on_failure_step == step_err


def test_ai_cache_uniqueness():
    """Vérifie l'unicité de la clé composite (prompt_hash, system_prompt_hash, model_id, temperature) dans le cache d'IA."""
    AICacheModel.create(prompt_hash="p1", system_prompt_hash="s1", model_id="m1", temperature=0.7, response_content="Response 1")

    assert AICacheModel.select().count() == 1

    # Tenter d'insérer le même hash d'appel doit lever une IntegrityError
    with pytest.raises(IntegrityError):
        AICacheModel.create(prompt_hash="p1", system_prompt_hash="s1", model_id="m1", temperature=0.7, response_content="Response 2")


def test_setting_model_crud_and_json():
    """Vérifie la persistance, la mise à jour et la conversion JSON de SettingModel."""
    # 1. Enregistrement scalaire
    SettingModel.set_value("theme_id", "jetbrains_light", category="appearance")
    assert SettingModel.get_value("theme_id") == "jetbrains_light"

    # 2. Mise à jour de la même clé (upsert)
    SettingModel.set_value("theme_id", "emerald_light", category="appearance")
    assert SettingModel.get_value("theme_id") == "emerald_light"

    # 3. Enregistrement de structures JSON complexes (dict, bool, list)
    SettingModel.set_value("layout_config", {"sidebar_width": 240, "compact": True}, category="appearance")
    config = SettingModel.get_value("layout_config")
    assert isinstance(config, dict)
    assert config["sidebar_width"] == 240
    assert config["compact"] is True

    # 4. get_category
    cat_settings = SettingModel.get_category("appearance")
    assert "theme_id" in cat_settings
    assert "layout_config" in cat_settings
    assert cat_settings["theme_id"] == "emerald_light"

    # 5. set_many (lot atomique)
    SettingModel.set_many({"ui/language": "English", "app/export_path": "/tmp/export"}, category="general")
    assert SettingModel.get_value("ui/language") == "English"
    assert SettingModel.get_value("app/export_path") == "/tmp/export"

    # 6. Fallback par défaut
    assert SettingModel.get_value("non_existent_key", default="default_val") == "default_val"


def test_document_page_model_and_multimodal_chunk():
    """Vérifie l'intégrité de DocumentPageModel et des champs multimodaux de DocumentChunkModel."""
    doc = DocumentModel.create(title="Doc Multimodal", file_type="album", total_pages=2)
    media1 = MediaModel.create(filename="p1.png", original_name="p1.png", checksum="hash1", mime_type="image/png")
    media2 = MediaModel.create(filename="p2.png", original_name="p2.png", checksum="hash2", mime_type="image/png")

    page1 = DocumentPageModel.create(document=doc, media=media1, page_number=1, rotation=90)
    assert page1.rotation == 90
    assert page1.page_number == 1

    # L'unicité de (document, page_number) doit être respectée
    with pytest.raises(IntegrityError):
        DocumentPageModel.create(document=doc, media=media2, page_number=1)

    # DocumentChunkModel avec champs multimodaux (audio/bounding_box)
    chunk = DocumentChunkModel.create(
        document=doc,
        chunk_index=0,
        content="Extrait audio transcrit",
        start_time=12.5,
        end_time=45.0,
        media=media1,
        bounding_box="[10, 20, 100, 200]",
    )
    assert chunk.start_time == 12.5
    assert chunk.end_time == 45.0
    assert chunk.media == media1
    assert chunk.bounding_box == "[10, 20, 100, 200]"

    # Suppression de média met media_id à NULL sur chunk (on_delete="SET NULL")
    media1.delete_instance()
    chunk_reloaded = DocumentChunkModel.get_by_id(chunk.id)
    assert chunk_reloaded.media is None

# tests/test_models.py
import json
import pytest
from peewee import IntegrityError

from src import (NoteModel, NoteTypeModel, NoteVersionModel,
                 FolderModel, DocumentModel,
                 AgentModel, PipelineModel, PipelineStepModel)


def test_note_versioning_system():
    """Vérifie que la méthode add_version crée bien un historique et désactive l'ancienne version."""

    # 1. PRÉPARATION (Given)
    note_type = NoteTypeModel.create(name="Test Model", fields_schema='["Front", "Back"]', templates='[]', css_style='')
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
    assert DocumentModel.select().count() == 0, "Les documents orphelins n'ont pas été supprimés en cascade !"


def test_cascade_deletion_note_versions():
    """Vérifie que supprimer une Note détruit tout son historique de versions."""

    # 1. PRÉPARATION
    note_type = NoteTypeModel.create(name="Basic", fields_schema='[]', templates='[]', css_style='')
    note = NoteModel.create(guid="abc", note_type=note_type)
    note.add_version({"Test": "1"})
    note.add_version({"Test": "2"})

    assert NoteVersionModel.select().count() == 2

    # 2. ACTION - On détruit la note racine
    note.delete_instance()

    # 3. VÉRIFICATION
    assert NoteVersionModel.select().count() == 0, "L'historique n'a pas été supprimé avec la Note !"


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
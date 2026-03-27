# tests/test_batch_worker.py
import pytest
import json
from src.database.models import (DeckModel, NoteTypeModel, PipelineModel,
                                 AgentModel, PipelineStepModel, DocumentModel, FolderModel, NoteModel)
from src.ui.views.batch_view import BatchWorker


# ==========================================
# LE MOCK IA INTELLIGENT (Avec des échecs programmés)
# ==========================================

class StatefulDummyProvider:
    """Un faux fournisseur IA qui retourne différentes réponses selon le nombre d'appels."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # S'il n'y a plus de réponses prévues, on renvoie la dernière
        if self.call_count >= len(self.responses):
            return self.responses[-1]

        response = self.responses[self.call_count]
        self.call_count += 1
        return response


# ==========================================
# LES TESTS DU BATCH WORKER
# ==========================================

def setup_batch_environment() -> tuple:
    """Prépare la base de données avec 3 documents, 1 paquet et 1 pipeline."""
    deck = DeckModel.create(name="Batch Deck")
    note_type = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]',
                                     templates='[{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]',
                                     css_style='')

    pipeline = PipelineModel.create(name="Batch Pipe")
    agent = AgentModel.create(name="Agent Unique", system_prompt="Test")
    PipelineStepModel.create(pipeline=pipeline, agent=agent, step_order=1)

    folder = FolderModel.create(name="Cours")
    doc1 = DocumentModel.create(title="Doc 1", content="Contenu 1", folder=folder)
    doc2 = DocumentModel.create(title="Doc 2", content="Contenu 2", folder=folder)
    doc3 = DocumentModel.create(title="Doc 3", content="Contenu 3", folder=folder)

    return deck, note_type, pipeline, [doc1.id, doc2.id, doc3.id]


def test_batch_worker_partial_failure():
    """
    Simule 3 documents. L'IA réussit le 1er, rate le 2ème (JSON cassé), et réussit le 3ème.
    Le Worker doit survivre, sauvegarder 2 notes, et émettre (succès=2, erreurs=1).
    """
    deck, note_type, pipeline, doc_ids = setup_batch_environment()

    # 1. PRÉPARATION : Le scénario de l'IA
    responses = [
        '{"notes": [{"Front": "Q1", "Back": "R1"}]}',  # Doc 1 : Succès
        '{"notes": [ { Front: Oups, JSON cassé } ]}',  # Doc 2 : Échec (Erreur de syntaxe)
        '{"notes": [{"Front": "Q3", "Back": "R3"}]}'  # Doc 3 : Succès
    ]
    mock_provider = StatefulDummyProvider(responses)

    worker = BatchWorker(
        ai_provider=mock_provider,
        doc_ids=doc_ids,
        deck_id=deck.id,
        model_id=note_type.id,
        pipeline_id=pipeline.id
    )

    # 2. CAPTURE DES SIGNAUX
    progress_values = []
    worker.progress_val.connect(lambda val: progress_values.append(val))

    final_results = []
    worker.finished.connect(lambda success, error: final_results.append((success, error)))

    # 3. EXÉCUTION (Synchrone)
    worker.run()

    # 4. VÉRIFICATIONS (Assertions)
    # L'IA a dû être appelée 3 fois (une fois par document)
    assert mock_provider.call_count == 3

    # La barre de progression a dû émettre 0%, 33%, 66% et 100% (environ)
    assert len(progress_values) > 0
    assert progress_values[-1] == 100, "La barre de progression ne s'est pas terminée à 100%."

    # Le signal de fin a dû remonter 2 succès et 1 erreur
    assert len(final_results) == 1, "Le signal 'finished' n'a pas été émis."
    success_count, error_count = final_results[0]
    assert success_count == 2
    assert error_count == 1

    # Vérification BDD : on doit avoir exactement 2 notes sauvegardées (pour le Doc 1 et Doc 3)
    assert NoteModel.select().count() == 2, "La base de données n'a pas enregistré le bon nombre de cartes."
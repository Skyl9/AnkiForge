# tests/test_ai_pipeline.py
from ankiforge.database.models import NoteTypeModel, AgentModel, PipelineModel, PipelineStepModel
from ankiforge.ui.views.creation_view import GenerationThread


# ==========================================
# LE "MOCK" DE L'INTELLIGENCE ARTIFICIELLE
# ==========================================

class DummyProvider:
    """Un faux fournisseur IA qui recrache exactement ce qu'on lui dit de dire."""

    def __init__(self, forced_response: str):
        self.forced_response = forced_response
        self.call_count = 0

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        return self.forced_response


# ==========================================
# LES TESTS DU PIPELINE
# ==========================================

def setup_dummy_pipeline() -> tuple:
    """Fonction utilitaire pour préparer la base de données de test."""
    note_type = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates='[]', css_style='')
    pipeline = PipelineModel.create(name="Test Pipe")
    agent = AgentModel.create(name="Agent", system_prompt="Tu es un test.")
    PipelineStepModel.create(pipeline=pipeline, agent=agent, step_order=1)

    return note_type, pipeline


def test_generation_thread_success_with_clean_json():
    """Vérifie que le thread extrait bien le JSON même si l'IA ajoute des balises Markdown."""
    note_type, pipeline = setup_dummy_pipeline()

    # 1. PRÉPARATION : On simule une IA qui répond avec des balises "```json" (très fréquent)
    fake_ai_response = """
    Voici vos flashcards générées :
    ```json
    {
        "notes": [
            {"Front": "Question 1", "Back": "Réponse 1"}
        ]
    }
    ```
    Bonnes révisions !
    """
    mock_provider = DummyProvider(fake_ai_response)

    thread = GenerationThread(
        ai_provider=mock_provider,
        text_source="Le cours de Maths...",
        note_type=note_type,
        pipeline_id=pipeline.id
    )

    # 2. CAPTURE DES SIGNAUX
    # Au lieu d'afficher dans l'UI, on stocke le résultat émis dans une liste locale
    emitted_results = []
    thread.finished.connect(lambda data: emitted_results.append(data))

    # 3. EXÉCUTION (Synchrone)
    thread.run()

    # 4. VÉRIFICATIONS
    assert mock_provider.call_count == 1, "L'IA n'a pas été appelée exactement 1 fois."

    assert len(emitted_results) == 1, "Le signal 'finished' n'a pas été émis."

    notes_extracted = emitted_results[0]
    assert len(notes_extracted) == 1, "Le nettoyeur JSON n'a pas réussi à extraire la note."
    assert notes_extracted[0]["Front"] == "Question 1"


def test_generation_thread_handles_invalid_json():
    """Vérifie que le thread ne crashe pas si l'IA hallucine et renvoie un JSON corrompu."""
    note_type, pipeline = setup_dummy_pipeline()

    # 1. PRÉPARATION : JSON cassé (il manque des guillemets)
    bad_json_response = '{ "notes": [ { Front: "Question" } ] }'
    mock_provider = DummyProvider(bad_json_response)

    thread = GenerationThread(
        ai_provider=mock_provider,
        text_source="Cours de test",
        note_type=note_type,
        pipeline_id=pipeline.id
    )

    # 2. CAPTURE DES SIGNAUX
    emitted_errors = []
    thread.error.connect(lambda msg: emitted_errors.append(msg))

    emitted_results = []
    thread.finished.connect(lambda data: emitted_results.append(data))

    # 3. EXÉCUTION
    thread.run()

    # 4. VÉRIFICATIONS
    assert len(emitted_results) == 0, "Le signal 'finished' a été émis alors que le JSON est invalide !"
    assert len(emitted_errors) == 1, "Le signal 'error' n'a pas été émis pour avertir l'utilisateur."
    assert "brisé le format JSON" in emitted_errors[0]


def test_generation_thread_multiple_agents():
    """Vérifie que les données transitent correctement entre DEUX agents successifs."""
    note_type, pipeline = setup_dummy_pipeline()

    # On ajoute un deuxième agent au pipeline (le Contrôleur)
    agent2 = AgentModel.create(name="Contrôleur", system_prompt="Corrige.")
    PipelineStepModel.create(pipeline=pipeline, agent=agent2, step_order=2)

    # L'IA va répondre la même chose deux fois, mais on vérifie qu'elle est bien appelée deux fois
    fake_ai_response = '{"notes": [{"Front": "Test", "Back": "Test"}]}'
    mock_provider = DummyProvider(fake_ai_response)

    thread = GenerationThread(
        ai_provider=mock_provider,
        text_source="Cours",
        note_type=note_type,
        pipeline_id=pipeline.id
    )

    # EXÉCUTION
    thread.run()

    # VÉRIFICATION : L'Extracteur (1) PUIS le Contrôleur (2) = 2 appels
    assert mock_provider.call_count == 2, "Le pipeline n'a pas fait transiter les données au deuxième agent."
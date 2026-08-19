from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.services.ai.base import MockProvider


def test_consultant_worker_success():
    """Vérifie que le ConsultantWorker assemble le contexte et obtient une réponse texte."""

    # Le MockProvider renvoie du texte libre si on lui demande 'response_format="text"'
    provider = MockProvider()
    context_data = {"documents": [{"titre": "Doc1", "contenu": "Le droit civil..."}]}
    instruction = "Fais un résumé"

    worker = ConsultantWorker(ai_provider=provider, context_data=context_data, instruction=instruction)

    # Capture des signaux
    emitted_responses = []
    emitted_progress = []

    worker.finished_signal.connect(lambda res: emitted_responses.append(res))
    worker.progress.connect(lambda msg: emitted_progress.append(msg))

    # Exécution synchrone
    worker.run()

    # Vérifications
    assert len(emitted_responses) == 1
    assert "Ceci est une réponse simulée en texte libre" in emitted_responses[0]

    # On vérifie que le thread a bien émis des messages de progression pour l'UI
    assert len(emitted_progress) >= 2
    assert "Initialisation" in emitted_progress[0]

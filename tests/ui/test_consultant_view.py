import uuid

from ankiforge.database.models import (
    DeckModel,
    DocumentModel,
)
from ankiforge.ui.views.consultant_view import ConsultantView


def test_consultant_view_initialization(qtbot):
    """Vérifie l'initialisation du Consultant IA et le message d'accueil."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    assert view is not None
    assert view.chat_messages_layout.count() >= 2  # Stretch + Welcome message


def test_consultant_view_context_attachment(qtbot):
    """Vérifie l'attachement dynamique de paquets et documents au contexte actif."""
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Cardio {uid}")
    doc = DocumentModel.create(title=f"Doc Cardiologie {uid}", content="Contenu de test anatomie.")

    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    # Attacher le deck et le document
    view._attach_context(f"deck_{deck.id}")
    view._attach_context(f"doc_{doc.id}")

    assert len(view.active_context) == 2
    assert f"deck_{deck.id}" in view.active_context
    assert f"doc_{doc.id}" in view.active_context

    # Vérification des données construites
    ctx_data = view._build_context_data()
    assert len(ctx_data["documents"]) == 1
    assert ctx_data["documents"][0]["titre"] == f"Doc Cardiologie {uid}"
    assert len(ctx_data["paquets"]) == 1
    assert ctx_data["paquets"][0]["nom"] == f"Deck Cardio {uid}"

    # Réinitialisation de la mémoire
    view._on_clear_memory()
    assert len(view.active_context) == 0


def test_consultant_view_quick_prompts(qtbot):
    """Vérifie le fonctionnement des suggestions rapides de prompts."""
    view = ConsultantView(ai_manager=None)
    qtbot.addWidget(view)

    view._on_quick_prompt_clicked("🔍 Trouver les cartes doublons")
    assert view.chat_input.toPlainText() == "Trouver les cartes doublons"

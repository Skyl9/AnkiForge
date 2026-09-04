"""
Tests unitaires pour le service ContextCompactor (Compaction dynamique et Next Steps).
"""

from ankiforge.services.ai.context_compactor import ContextCompactor


def test_estimate_tokens_string():
    text = "Ceci est un texte de test pour vérifier l'estimation de tokens."
    tokens = ContextCompactor.estimate_tokens(text)
    assert tokens > 0
    assert tokens == int(len(text) / 3.5)


def test_estimate_tokens_empty():
    assert ContextCompactor.estimate_tokens("") == 0
    assert ContextCompactor.estimate_tokens([]) == 0


def test_compact_in_flight_short_conversation():
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    compacted = ContextCompactor.compact_in_flight(messages, max_tokens=1000)
    assert len(compacted) == 3
    assert compacted == messages


def test_compact_in_flight_large_tool_outputs():
    # Longue conversation avec de très gros résultats d'outils
    huge_tool_output = "Ligne de données SQL\n" * 50
    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Analyse les cartes du deck 1"},
        {"role": "tool", "name": "query_peewee", "content": huge_tool_output},
        {"role": "assistant", "content": "J'ai analysé ces cartes."},
        {"role": "user", "content": "Maintenant analyse le deck 2"},
        {"role": "tool", "name": "query_peewee", "content": huge_tool_output},
        {"role": "assistant", "content": "Analyse du deck 2."},
        {"role": "user", "content": "Fais un résumé"},
        {"role": "assistant", "content": "Voici le résumé"},
        {"role": "user", "content": "Dernière question"},
    ]

    compacted = ContextCompactor.compact_in_flight(messages, max_tokens=200, keep_last_turns=1)
    assert len(compacted) == len(messages)
    # Les premiers retours d'outils doivent être condensés
    assert "condensée" in str(compacted[2]["content"])
    # Le message system reste intact
    assert compacted[0]["content"] == "System prompt"
    # Le dernier message reste intact
    assert compacted[-1]["content"] == "Dernière question"


def test_compact_post_task_generation():
    messages = [
        {"role": "user", "content": "Refactorise le Paquet 'Vocabulaire Japonais' pour le modèle 'Standard'"},
        {"role": "assistant", "content": "Les cartes du paquet ont été refactorisées avec succès."},
    ]
    recap, next_steps = ContextCompactor.compact_post_task(messages)
    assert "Résumé" in recap
    assert len(next_steps) >= 2
    assert any("Vocabulaire Japonais" in s or "Japonais" in s for s in next_steps)

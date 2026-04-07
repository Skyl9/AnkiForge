# Gestion de l'Intelligence Artificielle

AnkiForge est conçu pour être "Agnostique" en matière d'IA. Il peut se connecter à n'importe quel fournisseur sans changer la logique interne du programme.

## Fournisseurs supportés

Toutes les IA implémentent l'interface abstraite `LLMProvider`. Le basculement se fait dynamiquement via le fichier `.env` ou l'interface utilisateur.

1. **Ollama (Local & Gratuit) :** Idéal pour une utilisation hors-ligne (ex: modèle `llama3`).
2. **Google Gemini :** Accès cloud très rapide et performant via l'API Google AI Studio.
3. **Groq / OpenRouter :** Accès universel compatible avec le standard OpenAI.
4. **MockProvider :** Un fournisseur de secours utilisé pour les **tests** ou en cas de crash réseau, renvoyant un JSON pré-formaté.

## Résilience et Parsing JSON

Les LLMs ont tendance à rajouter des balises Markdown (````json ... ````) ou du texte de politesse autour de leurs réponses. 

Notre utilitaire interne (`parse_ai_json_response`) utilise des expressions régulières pour isoler de force le bloc JSON. Les tests unitaires valident ce comportement contre toutes les "hallucinations" connues.**
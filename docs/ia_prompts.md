# Intelligence Artificielle & Prompts 🧠

AnkiForge n'est pas lié à un fournisseur unique. Le système est conçu pour être totalement agnostique, vous laissant le choix entre la puissance du cloud et la confidentialité du local.

## Fournisseurs Supportés

Le projet implémente l'interface `LLMProvider` pour garantir une compatibilité universelle :

*   **Local** : Ollama (standard par défaut), LM Studio.
*   **Cloud** : Google Gemini (via API native), Groq (Llama 3 ultra-rapide), OpenAI.
*   **Compatible OpenAI** : Tout backend respectant le standard API de OpenAI peut être configuré.

## Moteur de Prompts (Jinja2)

Les prompts envoyés à l'IA ne sont pas de simples chaînes de caractères codées en dur. AnkiForge utilise **Jinja2** pour l'injection dynamique de contexte :

*   Injection du texte source extrait.
*   Contextualisation selon les préférences de l'utilisateur (langue, niveau de détail).
*   Formatage strict pour forcer une réponse JSON valide.

## Bouclier Anti-Hallucination

L'IA peut parfois être imprévisible. AnkiForge met en place plusieurs couches de sécurité :

1.  **Format JSON Forcé** : Utilisation du mode JSON des APIs (quand disponible) ou d'un parsing Regex robuste.
2.  **Validation Post-Parsing** : Chaque objet généré est validé par rapport au schéma attendu avant d'être inséré en base de données.
3.  **Gestion des Erreurs** : En cas de réponse invalide, le système peut retenter la génération avec un prompt de correction automatique.

## Confidentialité

En utilisant le fournisseur **Ollama**, aucune donnée ne quitte votre ordinateur. C'est la solution recommandée pour le traitement de documents sensibles ou personnels.

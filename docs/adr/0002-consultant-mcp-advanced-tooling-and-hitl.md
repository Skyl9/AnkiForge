# Outillage MCP avancé, Two-Phase Commit et Streaming de Pensée pour le Consultant IA

Afin de doter le Consultant IA d'une capacité d'intervention chirurgicale sur la collection sans risquer de corrompre les données ni de bloquer les interfaces, nous établissons un contrat d'outillage MCP avancé fondé sur la validation en deux phases (*Two-Phase Commit*), le streaming unifié des blocs de réflexion (*Extended Thinking*) et l'injection de composants graphiques interactifs dans le fil de discussion.

## Statut
Accepté

## Options considérées
1. **Mutations directes en base par les outils MCP** : Rejeté car dangereux. Tout appel d'outil modifiant des notes ou des modèles de cartes doit impérativement faire l'objet d'une revue humaine préalable avec différentiel visuel (Diff).
2. **Modales bloquantes synchrones (`QDialog.exec()`) dans la boucle ReAct** : Rejeté car incompatible avec le serveur persistant externe (daemon SSE) et risque de figer le thread de travail lors des appels à distance.
3. **Validation en deux phases via `StagedPatch` persistant avec verrouillage optimiste** : Retenu. L'outil génère un patch structuré (`patch_id`, diff avant/après, empreinte de révision de la note cible). L'application n'a lieu qu'après validation explicite par l'utilisateur (clic IHM dans le chat ou appel MCP dédié `apply_patch(patch_id)`).
4. **Streaming post-génération ou balises `<think>` brutes** : Rejeté car les temps de réflexion des grands modèles (Claude 3.7 Thinking, Gemini 2.5, DeepSeek R1) créent un gel apparent de l'IHM. Un streaming temps réel unifié des `thought_delta` vers `ThoughtStepWidget` avec repli automatique au premier mot de texte est retenu.

## Conséquences
- **Sécurité et intégrité** : Aucune mutation chirurgicale n'est appliquée sans validation humaine préalable. Le verrouillage optimiste prévient tout écrasement en cas de modification concurrente de la note cible.
- **Transparence et auditabilité** : Les blocs de pensée sont streamés en direct avec chronomètre et estimation des tokens, puis repliés automatiquement dans un badge d'audit consultable à tout moment. Les pensées et patchs sont persistés dans `ConsultantMessageModel` pour la reprise de session.
- **Richesse de l'IHM** : Des widgets PySide6 natifs (`EmbeddedCardTableWidget`, `EmbeddedCardPreviewWidget`) sont intégrés directement dans le fil de discussion. Leur état est figé après action pour préserver l'historique conversationnel.
- **Interopérabilité MCP** : Les outils chirurgicaux (`refactor_cards_by_criteria`, `diagnose_deck_weaknesses`, `search_knowledge_context`, `list_card_models_manifest`) fonctionnent de façon identique dans l'IHM Qt et via le serveur daemon SSE externe.

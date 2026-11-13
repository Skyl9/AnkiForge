---
title: FAQ et Dépannage
description: Réponses aux questions fréquentes et solutions aux problèmes courants dans AnkiDraft.
---

# FAQ et Dépannage

Retrouvez ici les réponses aux questions les plus fréquentes des utilisateurs d'AnkiDraft.

## 1. Questions générales

### AnkiDraft remplace-t-il Anki ?
Non : AnkiDraft et Anki sont complémentaires. **AnkiDraft** est l'atelier de création et d'audit de vos flashcards à partir de vos cours, tandis qu'**Anki** (Desktop, AnkiWeb, AnkiMobile, AnkiDroid) reste l'application dans laquelle vous effectuez vos révisions espacées quotidiennes.

### Puis-je utiliser AnkiDraft gratuitement et sans connexion internet ?
Oui. L'application est gratuite, fonctionne hors ligne, et vous pouvez utiliser des modèles d'IA locaux gratuits grâce à [Ollama](/fr/ai-setup/local-models-ollama/) sans aucune clé API payante.

### Mes cours PDF et mes cartes sont-ils envoyés dans le cloud ?
Non. Vos fichiers PDF, votre base de données et vos médias restent stockés localement sur votre ordinateur (`~/.ankidraft/`). Si vous utilisez un fournisseur cloud (OpenAI, Gemini, Claude), seuls les passages sélectionnés pour une génération sont transmis directement à votre compte API.

## 2. Résolution des problèmes courants

### macOS affiche un avertissement à la première ouverture
Assurez-vous d'avoir bien glissé **AnkiDraft** dans votre dossier **Applications** depuis le fichier `.dmg`. Si macOS demande une confirmation au premier lancement, faites un clic droit sur l'icône d'AnkiDraft > **Ouvrir**.

### Mes formules mathématiques ne s'affichent pas dans Anki
Vérifiez que vous utilisez bien les délimiteurs compatibles MathJax/KaTeX (`\( ... \)` pour une formule en ligne et `\[ ... \]` pour un bloc centré).

### Comment signaler un bug ou suggérer une amélioration ?
Dans AnkiDraft, ouvrez **Paramètres** (<kbd>Ctrl+,</kbd>) > **Aide** > **Signaler une idée ou un bug**, ou ouvrez un ticket sur le [dépôt GitHub officiel](https://github.com/Skyl9/AnkiDraft/issues).

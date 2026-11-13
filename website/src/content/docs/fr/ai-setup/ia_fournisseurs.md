---
title: Configurer vos Fournisseurs d'IA (OpenAI, Gemini, Claude)
description: Connecter vos clés API en toute sécurité et maîtriser votre budget de jetons dans AnkiDraft.
---

# Configurer vos Fournisseurs d'IA (OpenAI, Gemini, Claude)

AnkiDraft est **agnostique du fournisseur d'IA** : vous êtes libre d'utiliser le service de votre choix ou d'alterner selon vos besoins.

## 1. Fournisseurs compatibles

Dans **Paramètres** (<kbd>Ctrl+,</kbd>) > **Fournisseurs IA**, vous pouvez configurer :
- **OpenAI** (GPT-4o, GPT-4o-mini, etc.)
- **Google Gemini** (Gemini 2.5 Flash, Gemini 2.5 Pro)
- **Anthropic Claude** (Claude Sonnet, Claude Haiku)
- **Tout serveur compatible OpenAI** (Mistral, OpenRouter, serveur universitaire local)
- **Ollama (100 % gratuit et hors ligne)** : voir le guide [Utiliser un Modèle Local avec Ollama](/fr/ai-setup/local-models-ollama/).

## 2. Sécurité de vos clés API

- Vos clés API sont enregistrées dans le **trousseau sécurisé de votre système d'exploitation** (macOS Keychain, Windows Credential Manager, Secret Service Linux).
- Elles ne transitent par aucun serveur intermédiaire : AnkiDraft communique directement depuis votre ordinateur vers l'API du fournisseur sélectionné.
- Les journaux techniques masquent automatiquement toute clé (`sk-*`, `AIza*`).

## 3. Contrôle du budget

Avant de lancer une génération importante sur un livre entier, AnkiDraft estime le nombre de jetons (*tokens*) nécessaires et vous permet de fixer un plafond par exécution pour éviter toute surprise de facturation.

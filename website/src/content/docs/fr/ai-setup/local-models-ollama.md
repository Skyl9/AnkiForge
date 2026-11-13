---
title: Utiliser un Modèle Local Gratuit avec Ollama
description: Générer vos flashcards 100 % hors ligne et gratuitement sur votre ordinateur avec Ollama.
---

# Utiliser un Modèle Local Gratuit avec Ollama

Vous ne souhaitez pas utiliser d'API payante ou vous étudiez des documents confidentiels sans connexion internet ? AnkiDraft s'intègre nativement avec **Ollama**.

## 1. Installer Ollama en 2 minutes

1. Téléchargez et installez Ollama depuis [ollama.com](https://ollama.com).
2. Ouvrez un terminal et téléchargez un modèle adapté à la configuration de votre ordinateur :
   - **Ordinateur avec 8 Go de RAM** : `ollama pull llama3.2:3b` ou `ollama pull qwen2.5:3b`
   - **Ordinateur avec 16 Go+ de RAM (ex. Mac M1/M2/M3/M4)** : `ollama pull qwen2.5:7b` ou `ollama pull mistral`

## 2. Activer Ollama dans AnkiDraft

1. Ouvrez **Paramètres** (<kbd>Ctrl+,</kbd>) > **Fournisseurs IA**.
2. Sélectionnez **Ollama (Local)** : l'adresse par défaut `http://localhost:11434` est détectée automatiquement.
3. Cliquez sur **Rafraîchir les modèles** et choisissez le modèle que vous venez de télécharger.
4. Vous pouvez désormais générer et auditer vos flashcards gratuitement et 100 % hors ligne !

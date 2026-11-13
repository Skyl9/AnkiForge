---
title: Pipelines de Génération et Couverture Intelligente
description: Automatiser la création de cartes par étapes et combler les lacunes de vos paquets grâce à la couverture intelligente.
---

# Pipelines de Génération et Couverture Intelligente

Pour les cours volumineux, AnkiDraft combine deux moteurs complémentaires : les **Pipelines de génération** (workflows DAG) et la **Couverture intelligente** (RAG & Smart Coverage).

## 1. Enchaîner plusieurs étapes automatiquement (Pipeline DAG)

Un pipeline vous permet d'enchaîner automatiquement plusieurs actions sur vos chapitres :
1. **Recherche des passages clés** dans votre cours.
2. **Extraction des flashcards** selon le modèle de carte choisi.
3. **Vérification qualité automatique** (filtrage des cartes trop longues) et **génération audio TTS**.
4. **Passage en revue humaine** avant validation finale.

## 2. Détecter les chapitres oubliés (Smart Coverage)

Grâce à l'indexation sémantique locale de vos documents et aux liens de provenance (`NoteChunkLinkModel`), AnkiDraft compare vos cartes existantes à l'intégralité de votre cours :
- Il met en évidence les sections qui ne possèdent encore aucune flashcard.
- Vous pouvez demander à l'IA de **générer uniquement les cartes manquantes** sans dupliquer celles que vous avez déjà créées.

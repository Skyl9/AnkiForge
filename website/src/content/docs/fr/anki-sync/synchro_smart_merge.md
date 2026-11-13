---
title: Synchronisation, Doublons et Fusion Intelligente (Smart Merge)
description: Résoudre les conflits lors d'un import Anki et éliminer les cartes en doublon.
---

# Synchronisation, Doublons et Fusion Intelligente (Smart Merge)

Lorsque vous travaillez à plusieurs sur un même paquet ou que vous modifiez une carte à la fois dans Anki et dans AnkiDraft, l'outil de **Fusion Intelligente (Smart Merge)** protège votre travail.

## 1. Comment fonctionne Smart Merge lors d'un import `.apkg` ?

Si une carte entrante possède le même identifiant qu'une carte déjà présente dans AnkiDraft :
- **Si seules les statistiques de révision ont changé dans Anki** : aucun conflit n'est déclenché, la mise à jour est transparente.
- **Si le texte de la carte a été modifié des deux côtés** : la fenêtre de comparaison à 3 panneaux (*Version locale*, *Base commune*, *Version importée*) s'ouvre pour vous permettre de choisir la formulation à conserver ou de combiner les deux.

## 2. Détecter et fusionner les doublons

Depuis l'éditeur ou via le Consultant IA, vous pouvez lancer une recherche de doublons sur vos paquets :
- **Doublons exacts** : cartes ayant le même recto.
- **Doublons proches** : cartes formulées légèrement différemment mais portant sur la même définition, détectées rapidement grâce au calcul de similarité intégré.

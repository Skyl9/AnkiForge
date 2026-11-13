---
title: Modèles de Cartes, Gabarits et Styles CSS
description: Personnaliser vos types de notes Recto/Verso, Cloze et leur mise en forme visuelle pour Anki.
---

# Modèles de Cartes, Gabarits et Styles CSS

AnkiDraft prend en charge tous les types de notes d'Anki et vous permet d'adapter leur présentation visuelle.

## 1. Les types de notes prêts à l'emploi

- **Basique (Recto / Verso)** : une question ciblée au recto, la réponse et un mémo de cours optionnel au verso.
- **Basique (et carte inversée)** : génère automatiquement la carte dans les deux sens (idéal pour le vocabulaire bilingue).
- **Texte à trous (Cloze)** : masque un ou plusieurs termes clés `{{c1::...}}` au sein d'une phrase de contexte.

## 2. Personnaliser les champs et le style CSS

Vous pouvez ajouter des champs personnalisés (ex. *Source*, *Moyen mnémotechnique*, *Audio*, *Illustration*) et ajuster la feuille de style CSS de vos cartes avec un aperçu immédiat en mode clair et en mode sombre.

## 3. Réconciliation intelligente à l'import

Lorsque vous importez un paquet `.apkg` contenant un type de note déjà présent dans votre collection, AnkiDraft le reconnaît automatiquement sans créer de doublon de modèle (`Basique-12345`).

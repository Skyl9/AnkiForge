---
title: Éditeur de Notes, Formules KaTeX et Textes à Trous
description: Rédiger et mettre en forme vos cartes avec aperçu mathématique KaTeX en direct, occlusions Cloze et historique.
---

# Éditeur de Notes, Formules KaTeX et Textes à Trous

L'éditeur de notes d'AnkiDraft (<kbd>Ctrl+2</kbd>) vous offre un confort d'écriture immédiat avec prévisualisation en temps réel du rendu Anki.

## 1. Écrire des formules mathématiques et chimiques (KaTeX)

AnkiDraft affiche instantanément vos équations LaTeX sans attendre l'export vers Anki :
- **Formule en ligne** : entourez votre expression de `\( ... \)` ou `$ ... $` (ex. `$E = mc^2$`).
- **Formule en bloc centré** : utilisez `\[ ... \]` ou `$$ ... $$`.
- **Autocomplétion LaTeX** : tapez `\` suivi des premières lettres d'un symbole (`\alpha`, `\frac`, `\sum`) pour afficher la liste des commandes disponibles.

## 2. Créer des textes à trous (Cloze)

Les cartes à trous sont idéales pour mémoriser une définition précise ou une énumération courte :
1. Sélectionnez le mot ou l'expression à masquer dans votre texte.
2. Appuyez sur le bouton **Cloze** de la barre d'outils pour insérer automatiquement `{{c1::votre texte}}`.
3. Vous pouvez ajouter un indice optionnel avec la syntaxe `{{c1::réponse::indice}}`.

## 3. Historique de révision (Time Machine)

Vous avez modifié une carte par erreur ? Chaque enregistrement (<kbd>Ctrl+S</kbd>) conserve une version dans l'historique local de la note : vous pouvez comparer et restaurer une formulation antérieure en un clic.

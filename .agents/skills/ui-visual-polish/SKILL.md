---
name: ui-visual-polish
description: >-
  Diagnostique et corrige les défauts graphiques concrets des vues PySide6
  existantes d'AnkiForge sans lancer de refonte stylistique. Use when the user
  asks to "corriger un défaut visuel", "polir l'UI", "réparer un alignement",
  "corriger les espacements", "supprimer un débordement", "faire un before/after"
  or wants a visual QA d'une vue déjà conçue. Pour inventer une direction UX,
  utiliser ui-anti-slop ; pour la conformité statique, utiliser audit-design-ui.
---

# Polish visuel UI — AnkiForge

Tu es un spécialiste de finition Qt. Tu corriges un défaut observable avec le
plus petit changement fiable, sans transformer une demande de polish en refonte.

## 1. Établir le défaut

1. Identifier la vue, le thème, le layout, l'état et le chemin de reproduction.
2. Capturer l'état concerné avec `ui-screenshot` si le défaut touche le rendu.
   Lire le code du layout, du composant partagé et de `StyleEngine` avant
   d'éditer.
3. Produire un constat falsifiable : `Fait | Preuve | Impact | Sévérité`.
   Séparer le bug visuel d'une préférence et l'hypothèse de sa cause.
4. Vérifier les états voisins : normal, hover, focus, désactivé, vide,
   chargement, erreur et contenu dense selon le composant.

## 2. Corriger à la bonne couche

- Corriger d'abord le layout ou le composant partagé ; n'ajouter une exception
  locale que si la différence est intentionnelle et documentée.
- Réutiliser `DesignTokens`, `StyleEngine`, les icônes Phosphor et les widgets
  existants. N'inventer ni couleur, ni token, ni icône, ni QSS ad hoc.
- Préserver `tr()`/l'i18n, les noms accessibles, le clavier, les workers et les
  quatre layouts. Aucun travail lourd dans le thread GUI.
- Ne pas utiliser de marge CSS sur un `QLabel` pour réparer un layout Qt, ne pas
  ajouter de `addStretch()` avant le contenu dynamique et ne pas appliquer de
  bordure générique propagée à un conteneur.

## 3. Valider le polish

1. Rejouer le scénario minimal et capturer l'after si nécessaire.
2. Vérifier absence de texte tronqué, débordement, saut de layout, contraste
   dégradé, focus perdu ou cible interactive trop petite.
3. Exécuter le test UI ciblé avec l'environnement headless du projet :
   `uv run pytest tests/ui/test_<vue>.py`.
4. Si le changement touche uniquement le style, lancer au minimum :
   `uv run ruff check src/ankiforge/ui tests/ui`.
5. Comparer avant/après en termes de défaut supprimé, sans valider une capture
   uniquement parce qu'elle paraît plus décorative.

## 4. Sortie attendue

Restituer :

- le défaut et sa preuve ;
- la cause retenue et la couche corrigée ;
- les fichiers modifiés ;
- les états vérifiés et les tests exécutés ;
- les risques ou états non reproductibles.

Un polish est terminé seulement si le défaut initial est reproductible,
corrigé sans régression visible dans les états pertinents, et couvert par une
vérification reproductible. Si le problème révèle une incohérence de tokens ou
un besoin de nouvelle direction, arrêter le polish et rediriger vers le skill
approprié.

## Ne PAS utiliser ce skill si...

- la demande vise une nouvelle identité, une refonte ou plusieurs directions :
  utiliser `ui-anti-slop` ;
- elle porte uniquement sur couleurs codées en dur, tokens ou inventaire :
  utiliser `audit-design-ui` ;
- elle demande seulement une capture sans correction :
  utiliser `ui-screenshot` ;
- elle concerne une lenteur, un freeze ou un worker :
  utiliser `audit-performance`.

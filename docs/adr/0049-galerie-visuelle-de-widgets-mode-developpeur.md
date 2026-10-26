# ADR 0049 — Galerie visuelle de widgets (mode développeur) avec données factices

## Statut
Accepté

## Contexte
Le développement et la validation visuelle de l'UI d'AnkiForge nécessitent d'observer chaque widget/dialogue/vue avec des données déterministes, sans dépendre d'une vraie collection ni de mocks ad hoc créés par l'agent. Les paramètres (`preferences_dialog.py`) contiennent déjà une forme de galerie de modaux réutilisable comme patron.

## Décisions

1. **Emplacement** : fenêtre séparée `WidgetGalleryWindow`, ouvrable depuis le menu « Outils développeur », sans perturber la fenêtre principale.
2. **Enregistrement** : registre déclaratif (`@gallery_widget` + liste explicite par famille : `components`, `dialogs`, `views`, `widgets`, `layouts`, `viewmodels`). Traçable, contrôle de l'ordre et des données factices.
3. **Données factices** : module dédié `src/ankiforge/dev/` (factories déterministes) réutilisable par l'app (galerie) et les tests. Pas de pollution de la base utilisateur (profil dev / base en mémoire / sandbox).
4. **Activation** : mode développeur uniquement (`--dev` / `ANKIFORGE_ENV=dev`), masquée en production.
5. **Widgets lourds** (WebEngine, DB, réseau) : instanciation avec services mockés/fakes et base en mémoire ; les widgets trop lourds sont reportés si nécessaire.
6. **Première tranche** : famille `dialogs` (quick win, patron existant), puis extension aux autres familles.

## Conséquences
- Nouveau module `src/ankiforge/dev/` à créer (factories de données factices).
- Nouveau composant UI `WidgetGalleryWindow` + entrée menu conditionnelle au mode dev.
- Registre déclaratif à maintenir ; chaque nouveau widget doit être enregistré pour apparaître dans la galerie.
- Tests headless : ouverture de la galerie + instanciation de chaque widget enregistré sans crash.

## Termes canoniques
- **Galerie de widgets (mode développeur)** : fenêtre dédiée permettant d'observer visuellement l'ensemble des widgets de l'application alimentés par des données factices déterministes, activée uniquement en mode développeur.
- _Avoid_ : mocks d'interface, Storybook, bac à sable UI.
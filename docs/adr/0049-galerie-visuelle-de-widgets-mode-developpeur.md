# ADR 0049 — Galerie visuelle de widgets (mode développeur) avec données factices

## Statut
Accepté

## Contexte
Le développement et la validation visuelle de l'UI d'AnkiForge nécessitent d'observer chaque widget/dialogue/vue avec des données déterministes, sans dépendre d'une vraie collection ni de mocks ad hoc créés par l'agent. Les paramètres (`preferences_dialog.py`) contiennent déjà une forme de galerie de modaux réutilisable comme patron.

## Décisions

1. **Emplacement** : fenêtre séparée `WidgetGalleryWindow`, ouvrable depuis le menu « Outils développeur », sans perturber la fenêtre principale.
2. **Enregistrement** : registre déclaratif (`@gallery_widget` + liste explicite par famille : `components`, `dialogs`, `layouts`, `models`, `shell`, `viewmodels`). Traçable, contrôle de l'ordre et des données factices. Les familles `views` et `widgets` restent hors périmètre (tickets dédiés).
3. **Données factices** : module dédié `src/ankiforge/dev/` (factories déterministes) réutilisable par l'app (galerie) et les tests. Pas de pollution de la base utilisateur (profil dev / base en mémoire / sandbox). Le modèle Qt factice (`FakeNoteTableModel`) vit dans `dev/fake_qt_models.py`, séparé de `dev/fake_services.py` pour ne pas faire dépendre les faux services de la couche UI.
4. **Activation** : mode développeur uniquement (`--dev` / `ANKIFORGE_ENV=development`), masquée en production. L'entrée du menu et l'onglet « Développeur » de `SettingsModal` ne sont créés que si `is_development()` est vrai.
5. **Widgets lourds** (WebEngine, DB, réseau) : instanciation avec services mockés/fakes et base en mémoire ; les widgets trop lourds sont reportés si nécessaire.
6. **Première tranche** : famille `dialogs` (quick win, patron existant), puis extension aux autres familles.
7. **Objets non visuels** : les layouts, ViewModels, modèles Qt et délégués ne sont pas des widgets autonomes. Un module dédié `ui/widget_gallery/previews.py` fournit les conteneurs d'aperçu génériques (`ObjectPreview`, `ItemModelPreview`, `DelegatePreview`) qui les rendent observables sans dupliquer leur logique : inspecteur de signaux, tableau/liste lié, lignes peintes par le délégué.
8. **Coquille applicative recomposée** : la **vraie** `MainWindow` n'est jamais instanciée en galerie (timers réseau, worker de métriques, démon MCP). `ShellPreviewWindow` recompose sa coquille avec les **vrais** layouts et le **vrai** `MainWindow.view_registry()`, chaque vue étant remplacée par un substitut textuel. `SettingsModal`, dialogue autonome, est en revanche instanciée réellement.
9. **Entrées modales** : `GalleryEntry.modal` (décorateur `gallery_widget(..., modal=True)`) distingue les aperçus qui s'ouvrent légitimement via `exec()`. L'aperçu reste toujours affiché dans le volet ; le bouton « Ouvrir en modal » n'est activé que pour ces entrées.

## Conséquences
- Nouveau module `src/ankiforge/dev/` (factories de données factices, `fake_qt_models.py` pour les modèles Qt).
- Nouveau composant UI `WidgetGalleryWindow` + entrée menu conditionnelle au mode dev.
- Nouveau module `ui/widget_gallery/previews.py` (conteneurs d'aperçu non visuels) et six modules de familles sous `ui/widget_gallery/families/`.
- Registre déclaratif à maintenir ; chaque nouveau widget doit être enregistré pour apparaître dans la galerie.
- Tests headless : smoke test paramétré de toutes les entrées, couverture par introspection de chaque famille, vérification du registre de la coquille et du câblage modal/disposition (`tests/ui/test_widget_gallery.py`).
- Documentation : `docs/dev/galerie_widgets.md` et section « Outils Développeur » de `docs/Dossier_architecture/07_inventaire_composants_ui.md`.

## Termes canoniques
- **Galerie de widgets (mode développeur)** : fenêtre dédiée permettant d'observer visuellement l'ensemble des widgets de l'application alimentés par des données factices déterministes, activée uniquement en mode développeur.
- _Avoid_ : mocks d'interface, Storybook, bac à sable UI.
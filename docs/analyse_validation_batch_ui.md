# Analyse — Améliorer la validation humaine du batch (UI)

Date : 2026-09-23. Statut : **analyse validée** (grill, pas encore implémentée). Porteurs : session opencode.
Réf. vocabulaire : `CONTEXT.md` (Revue, Tâche révisable, Rangée ouvrable, Décision de revue, Clé de rangée).

## 1. Demande

« Comment améliorer la validation de la batchfactory » → périmètre resserré en grill aux décisions
humaines de la **Revue** (staging) et à l'**UI de validation** : ce document analyse *où* s'insère
l'amélioration, pas une refonte du backend.

Objectifs opérationnels :

1. La revue ne **disparaît plus** (perte de revue par fermeture, remplacement silencieux, page non affichée).
2. Les rangées de la **file d'attente** sont cliquables et redirigent vers la revue d'une tâche (révision ou relecture).
3. L'identité d'une tâche ne dépend plus de sa position dans la file (bug de marquage de mauvaise tâche).

## 2. État actuel (faits vérifiés dans le code)

- La revue = `BatchStagingPanel`, **enfant brut d'un `QSplitter`** (`view.py:492-496`), index 2 du splitter
  laissé *collapsible* (`view.py:506-510`) ; `IdePanel` utilisé déjà pour build/queue/terminal (`view.py:139,407,461`).
- Visibilité pilotée par `setVisible` : caché au départ (`batch_staging_panel.py:85`), montré par `load_task`
  (`:370`), fermé par le X (`:126`), par accept (`:815`, `:861`) et par reject (`:837`).
- Garde de non-remplacement : `if not force and self.isVisible() and self._current_task_idx != task_idx` (`:351`).
  `isVisible()` est **faux** dès que (a) le panneau est fermé ou (b) la page batch n'est pas le widget courant
  (`main_window.py:549`) → une tâche suivante remplace silencieusement la revue en cours.
- File = `BatchQueueTable` (`batch_queue_table.py:68`) : **aucun** `itemClicked`/`cellClicked` ; seule
  interaction = boutons cellule « Examiner »/retry/delete rangée À réviser (`:269-292`). Row == index de tâche
  (identité, `:102-105` + `:205` via `review_requested.emit(row_idx)`).
- Signaux : `cards_accepted = Signal(int, list)` / `task_rejected = Signal(int)` (`batch_staging_panel.py:69-70`),
  câblés sur l'index brut `_current_task_idx` (`view.py:1441,1455`) — vulnérable au décalage d'index (D4).
- `_prepared_notes_by_task` (`view.py:111`) conserve les notes par index de tâche ; les snapshots ont
  `_batch_task_id` (`models.py`) comme identifiant de tâche ; les tâches legacy n'ont aucune clé d'identité.
- Onglet « résultat à côté des logs » du standard : `IdePanel` du patron `results_panel` de la vue création
  (`creation_view/view.py:526,671-677`, `closable=False`), API `add_tab`/`set_active_tab`/`set_tab_title`
  (`panels.py:654,696,417`).

## 3. Problèmes identifiés

| # | Problème | Code | Conséquence |
|---|----------|------|-------------|
| D1 | Fermeture par X | `batch_staging_panel.py:126` | Revue perdue, retour manuel |
| D2 | Remplacement silencieux si `isVisible()` faux | `:351` (payload `batch_worker.py:323`, snapshot `:482`) | La revue change de contenu sans action utilisateur |
| D3 | Pas d'auto-avance après accept/reject | `:815,837,861` | Le panneau reste fermé, on cherche la tâche suivante |
| D4 | Index comme identité | `view.py:1441,1455` ; suppression `view.py:817-821` | Marquage d'une mauvaise tâche après suppression d'une rangée en amont |
| D5 | Remplacement pendant page non affichée | `main_window.py:549` + garde `isVisible` | Au retour, la revue affiche la dernière tâche, pas la vôtre |
| D6 | `_toggle_terminal` écrit 2 tailles pour 3 enfants | `view.py:520,527` | Quirque de taille du panneau de revue |
| D7 | Re-rendu complet de la file sous une revue vivante | `batch_queue_table.py:186-267` ; `view.py:1612,1623` | Statuts/rangée divergent de la revue affichée |

Gap non-fonctionnel : les tests (`tests/ui/test_batch_views.py`, `test_batch_widgets.py`) couvrent le
*routage* (signaux, statuts) mais aucune règle de persistance/clique/identité de rangée.

## 4. Décisions retenues (grill Q4–Q13)

1. **Q4 · Onglet spécialisé** : la Revue devient un **onglet non fermable du `terminal_panel`** existant
   (`IdePanel`), à côté du journal `root@ankiforge:~/pipeline_logs`. L'enfant splitter (=2) et le
   minimum-height forcé sont supprimés ; l'autofocus est piloté par `set_active_tab`.
2. **Q5+Q10 · Cliquabilité** : **simple-clic** sur rangée **À réviser** → révision ; **double-clic** sur rangée
   traitée avec notes (`Succès`/`Acceptée`/`Partiel`/`Rejetée`) → relecture. Curseur pointeur + hover + tooltip
   sur les cellules ouvrables ; les boutons « Examiner » existants sont conservés.
3. **Q10 · Autofocus + badge** : `task_review_ready` → autofocus de l'onglet Revue **seulement si aucune revue n'est
   active** ; sinon pas de yank, log + incrément du compte. Titre d'onglet `Revue (n)` où n = tâches À réviser.
4. **Q12 · Identité stable** : chaque tâche reçoit une **clé de rangée** (`_queue_uid`, uuid à l'insertion) ;
   `cards_accepted`/`task_rejected` passent cette clé ; la vue résout clé→index au moment du traitement.
5. **Q13+Q8 · Auto-avance** : après accept/reject → charge la prochaine tâche À réviser (`_staging_task_list`) ;
   si aucune → état vide « Plus de tâche à réviser » (onglet toujours visible).
6. **Q9 · Pas de garde de non-save** : bascule immédiate, notes conservées dans `_prepared_notes_by_task`,
   pastille visuelle sur les cartes modifiées (`user_edited=True`).
7. **Garde par état explicite** : remplacer le test `isVisible()` par `_review_active` géré par le panneau
   (actif dès qu'une revue est ouverte, inactif sur vidage/fermeture) → D2 et D5 corrigés.

## 5. Points d'insertion (file:line actuels)

- `view.py:491-499` : retirer `main_splitter.addWidget(self.staging_panel)` ; brancher `terminal_panel.add_tab("Revue", staging_panel, closable=False)`.
- `view.py:1393-1400` (`_on_task_review_ready`) : autofocus onglet (si revue inactive) + badge + log.
- `view.py:1402-1411` (`_staging_task_list`) : source des tâches À réviser (backend de l'auto-avance/badge).
- `view.py:1428-1439` (`_on_open_staging_for_task`) : accueil du clic simple (réutilise `force=True`).
- `view.py:1441-1460` (`_on_staging_accepted`/`_on_staging_rejected`) : résolution par clé de rangée → index puis traitement.
- `view.py:817-828` (`_remove_from_queue`/`_on_clear_queue`) : les suppressions ne cassent plus l'identité.
- `batch_staging_panel.py:56-89` : état `_review_active`, uid courant, suppression min-height/`_ensure_splitter_space`.
- `batch_staging_panel.py:318-377` (`_nav_to_task`/`load_task`) : passage clé de rangée + garde `_review_active`.
- `batch_staging_panel.py:815,837,861` : fermer via auto-avance au lieu de `setVisible(False)`.
- `batch_queue_table.py:107-175` (`_build_ui`) : connecter `itemClicked`/`itemDoubleClicked` (après `:138`).
- `batch_queue_table.py:186-267` (`_render`) : curseur pointeur/tooltip sur cellules ouvrables ; garder `review_requested(row)`.
- `batch_queue_table.py:269-292` : conserver les actions cellulaires existantes.
- `panels.py:654/696/417` : `add_tab`/`set_active_tab`/`set_tab_title` (badge par titre).

## 6. Plan de tests

- `tests/ui/test_batch_views.py` :
  - la Revue est un onglet non fermable de `terminal_panel` ; l'onglet reste après accept/reject/fermeture ;
  - `task_review_ready` → autofocus si revue inactive, pas de yank si active ;
  - clic simple rangée À réviser → `_on_open_staging_for_task` ; double-clic rangée traitée → relecture ;
  - **régression D4** : deux tâches, suppression de la première, accept de la deuxième → la **bonne** rangée est marquée ;
  - auto-avance après accept puis état vide « Plus de tâche à réviser » ;
  - badge titre `Revue (n)` incrément/décrément cohérent avec l'état de la file.
- `tests/ui/test_batch_widgets.py` :
  - `load_task` avec `_review_active` : pas de remplacement silencieux ; revue vide → état ouvert vide ;
  - clés de rangée stables pour legacy et snapshot (`_queue_uid` préservé sur re-rendu).
- Mettre à jour les tests existants qui utilisent `cards_accepted(int, list)`/`task_rejected(int)` (signature → clé de rangée).

## 7. Hors périmètre (volontairement)

- Backend du pipeline (étape Linter format-only, auto-validation de *contenu*, Juge Fact-Checker non branché,
  Levenshtein absent du batch) : analysé, candidates pour une suite, mais hors de cette demande-UX.
- Incohérence de défaut `auto_validation` (dataclasses `True` vs case UI décochée) : à traiter séparément.
- `_EN_STATUS_LABELS` (code mort, `view.py:78-87`) : peut être supprimé au passage du refactoring UI.

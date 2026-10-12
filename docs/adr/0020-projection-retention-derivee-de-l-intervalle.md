# Projection de rétention dérivée de l'intervalle plutôt que de l'état FSRS importé

**Statut :** Accepté

Le Cockpit expose une courbe de rétention projetée et une charge à l'équilibre. Faute de pouvoir fonder cette projection sur un état mémoire réel — la Forge ne renseigne jamais la stabilité calculée par Anki (les colonnes `stability`/`difficulty`/`retrievability` de `CardModel` restent à `0.0`), ne stocke aucune date d'échéance (`due`) ni aucun historique de révision (aucune table `revlog`) — nous dérivons la stabilité de l'intervalle courant (`S ≈ ivl`, exact à 90 % de rétention cible) et nous calculons la charge comme une **charge à l'équilibre** (`Σ 1/ivl`), plutôt que d'enrichir l'import pour lire l'état FSRS d'Anki. La courbe suit la loi de puissance canonique `R(t,S) = (1 + (19/81)·t/S)^{-0.5}`, ancrée à la révision (100 % à `t = 0`), et non une projection calendaire.

## Options considérées

1. **Option A — Importer l'état mémoire FSRS réel** (colonne `data` d'Anki : `s`, `d`) et les dates d'échéance : Rejeté dans ce périmètre.
   - **Chantier distinct** : touche l'importeur, le modèle de données, une migration et sa suite de tests — un ticket à part entière.
   - **Péremption immédiate** : AnkiForge est un IDE d'*authoring*, il ne révise pas. Un état FSRS importé serait faux dès la première révision dans Anki, produisant une précision trompeuse.

2. **Option B — Dériver la stabilité de l'intervalle courant** (`S ≈ ivl`) : **Retenu**.
   - **Exactitude sous hypothèse explicite** : Anki dimensionne l'intervalle pour viser la rétention cible ; à 90 %, l'inversion de la loi de puissance donne `S ≈ ivl` (car `(19/81)/(0,9⁻² − 1) = 1`).
   - **Disponible immédiatement** : exploite les seules données réellement présentes, sans migration.

3. **Option C — Rétention statistique depuis l'historique de révision** : Impossible, aucune table `revlog` n'existe.

## Conséquences

- **Ancre explicitement « depuis une révision »** : la courbe part de 100 % et décrit ce qui serait retenu à J+1/J+3/J+7/J+14 après une révision. Aucune hypothèse de phase sur la position courante des cartes n'est fabriquée.
- **Cartes sans état SRS (`ivl = 0`) exclues** de la courbe et de la charge, comptées séparément ; les cartes suspendues sont exclues de la charge seulement.
- **Artefacts mensongers retirés** : le KPI `fsrs_retention_pct` (factice, toujours à 90 %) est remplacé, le bouton « Optimiser FSRS-4.5 (ML Local) » (sans effet réel) est supprimé, et la courbe décorative `RetentionCurveCanvas` est retirée.
- **Service unique** : `FsrsProjectionService` fait autorité sur le calcul ; le Dashboard le rend, l'onglet Analyse/SRS y est branché.

# Garde-Fou MCP autonome et comparateur sémantique de cartes

**Statut :** accepté

Afin de fluidifier la collaboration avec les agents d'intelligence artificielle externes (Claude Code, Antigravity CLI, Cursor) sans polluer le Consultant IA in-app, nous déplaçons l'examen et la validation des propositions de cartes directement dans la vue MCP sous un sous-onglet dédié, et nous remplaçons le diff JSON brut par un **comparateur sémantique de cartes** champ par champ avec diff mot-à-mot intra-ligne, édition directe in-place et prévisualisation Anki en direct.

## Le problème

1. **Expulsion du contexte de travail** : Lorsqu'un agent externe soumet une proposition de modification (`propose_card_refactor`, `propose_card_split` ou `create_note`), l'application forçait la redirection vers l'onglet « Consultant IA » et ouvrait le panneau latéral de l'inspecteur (`WorkspaceInspectorWidget`), interrompant l'utilisateur qui supervise son agent MCP ou son terminal.
2. **Absence de réactivité temps réel** : La création d'un `StagedPatchModel` par un outil MCP n'émettait aucun signal Qt vers l'interface. L'IHM ne découvrait les propositions qu'au rechargement manuel de la vue.
3. **Opacité et rusticité du diff JSON** : L'inspecteur se contentait d'effectuer un `difflib.unified_diff` sur la sérialisation textuelle `json.dumps()` des dictionnaires `original` et `modified`. L'utilisateur devait déchiffrer des accolades, des guillemets et des retours à la ligne échappés, sans surlignage mot-à-mot intra-ligne ni distinction claire des champs métier (Recto/Verso).

## Options considérées

1. **Garder l'inspecteur dans le Consultant IA et ajouter un simple raccourci** :
   Rejeté. L'utilisateur qui travaille avec un agent externe via MCP ne souhaite pas être basculé dans le chat du Consultant in-app. Cela crée une friction cognitive et mélange deux flux de travail distincts.
2. **Section unique défilante dans le tableau de bord MCP** :
   Rejeté. Le tableau de bord MCP accumule déjà le pilotage du cycle de vie, les endpoints, les snippets et l'historique d'activité. Y insérer un diff complexe de cartes alourdit la page et nuit à la lisibilité de la comparaison plein écran.
3. **Scission de l'onglet MCP en sous-onglets avec comparateur sémantique dédié** :
   **Retenu**.

## Décisions et Règles d'Architecture

### 1. Sous-onglets de l'onglet « Serveur MCP »
L'onglet Serveur MCP (`MCPServerDashboardWidget` ou composant conteneur MCP) s'articule désormais en deux sous-onglets stables :
- **« 🔌 Supervision & Configuration »** : le tableau de bord existant (cycle de vie, points de terminaison, snippets client, journal d'activité).
- **« 🛡️ Garde-Fou & Validation »** : un espace dédié plein écran affichant un badge dynamique du nombre de propositions en attente (ex: `Garde-Fou (3)`).

### 2. Ergonomie Maître-Détail (Master-Detail)
Le sous-onglet « Garde-Fou & Validation » s'organise en deux zones :
- **Volet gauche (Maître)** : file des patchs en attente présentés sous forme de cartes d'en-tête (type de patch : Refactor, Scission, Création ; note ID ; titre ; paquet cible ; horodatage), avec filtre rapide et actions de lot (`[ ✅ Tout appliquer ]`, `[ ❌ Tout rejeter ]`).
- **Zone droite (Détail)** : comparateur haute fidélité du patch sélectionné avec boutons d'action individuels (`[ ✅ Appliquer ]`, `[ ❌ Rejeter ]`, `[ 📋 Copier le feedback ]`).

### 3. Comparateur sémantique de cartes champ par champ & Diff mot-à-mot
Le visualiseur abandonne tout affichage de JSON brut pour une approche métier :
- **Découpage par champ** (Front/Recto, Back/Verso, Tags, etc.) avec indicateur d'état (`Identique` ou `Modifié`).
- **Deux colonnes synchronisées côte-à-côte** :
  - Colonne gauche : *Actuel en BDD* (lecture seule, surlignage des suppressions en rouge barré).
  - Colonne droite : *Proposition Agent MCP* (éditable en direct par l'utilisateur, surlignage des ajouts en vert).
- **Diff mot-à-mot intra-ligne (Word-level diff)** : s'appuie sur `difflib.SequenceMatcher` tokenisé sur les mots et espaces (`compute_word_diff_html`) pour isoler précisément les modifications sans marquer tout le paragraphe.
- **Bascule vers le Rendu Anki Live** : un onglet secondaire permet de visualiser instantanément le rendu HTML/CSS réel de la carte (recto et verso) via `CardPreviewWidget`.

### 4. Réactivité événementielle sans perturbation
- Dès qu'un outil MCP instancie un `StagedPatchModel`, un signal Qt `mcp_patch_staged` est relayé par `MCPServerDaemon` via `event_bus`.
- L'interface met à jour immédiatement le badge `Garde-Fou (N)` et affiche un toast informatif discret, sans commutation forcée d'écran, préservant la concentration de l'utilisateur.

### 5. Polymorphisme des patchs (Refactor, Split, Création)
Le comparateur gère nativement les 3 régimes :
- *Modification (`card`)* : comparaison Avant/Après champ par champ.
- *Scission (`split`)* : carte d'origine comparée à la liste des N cartes atomiques résultantes.
- *Création (`note_create` / `batch_note_create`)* : affichage structuré des champs, contrôle préventif des doublons sur le champ clé et aperçu du rendu.

## Conséquences

- **Autonomie MCP** : Les utilisateurs d'agents externes travaillent entièrement depuis l'espace MCP sans interférence avec le Consultant IA.
- **Clarté cognitive** : La comparaison champ par champ élimine la pollution syntaxique du JSON et accélère la prise de décision humaine.
- **Réutilisabilité** : Le composant de diff de carte (`CardDiffViewer`) est découplé et testable de façon unitaire et modulaire.

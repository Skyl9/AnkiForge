# Décorrélation des flux de validation MCP et du Consultant IA

**Statut :** accepté

Afin de garantir l'autonomie et l'herméticité du flux de travail des agents MCP externes par rapport au Consultant IA in-app, nous découplons strictement le traitement des patchs en attente (`StagedPatchModel`) : les propositions émises par les agents MCP sont administrées exclusivement dans le sous-onglet « Garde-Fou & Validation » du Serveur MCP sans jamais alimenter l'Espace de Travail du Consultant IA, et les rafraîchissements d'interface consécutifs aux mutations MCP sont strictement passifs, éliminant toute commutation automatique d'onglet.

---

## Le Problème

1. **Éjection intempestive du contexte lors d'une validation MCP** : Lorsqu'un utilisateur valide ou rejette un patch dans le sous-onglet « Garde-Fou & Validation » du Serveur MCP (`MCPGardeFouWidget`), l'écriture en base déclenche un événement `mcp_data_mutated`. Ce signal invoquait `refresh_data()` sur l'ensemble des vues, y compris `ConsultantView`.
2. **Effet de bord actif dans un rafraîchissement passif** : `ConsultantView.refresh_data()` appelait `self._reload_pending_patches()`, qui interrogeait `StagedPatchRegistry.list_pending()` et réinjectait ces patchs dans la file du `WorkspaceInspectorWidget` (volet droit du Consultant IA). Si d'autres patchs restaient en attente, la méthode appelait `_activate_workspace_tab()`.
3. **Double bogue de contrôle d'onglet** :
   - `_reload_pending_patches()` tentait d'ignorer la bascule si l'onglet MCP était actif via `getattr(self.chat_panel.tabs_bar, "active_tab_idx", -1) != 0`. Or, `ScrollableTabBarWidget` ne dispose d'aucun attribut `active_tab_idx`. L'expression valait systématiquement `-1 != 0` (toujours vrai).
   - `_activate_workspace_tab()` forçait brutalement l'activation du panneau gauche `self.chat_panel.set_active_tab(1)` (« Consultant IA »), arrachant l'utilisateur de sa vue de supervision MCP pour le renvoyer dans le chat in-app.
4. **Couplage indésirable entre deux flux asynchrones** : Les agents MCP autonomes (CLI, Antigravity, Claude Code) et le Consultant IA in-app partagent le modèle `StagedPatchModel` mais représentent deux paradigmes d'assistance différents. Mêler leurs files d'attente créait des interférences, des doublons de notification et bloquait la perspective d'une extraction ou d'un élagage futur du consultant in-app.

---

## Options Considérées

1. **Conserver l'alimentation croisée et corriger uniquement le test d'index** :
   *Rejeté*. Si l'utilisateur consulte le Consultant IA, les patchs de ses agents terminaux continueraient d'apparaître dans son inspecteur de chat, créant une confusion cognitive et maintenant une dépendance structurelle forte entre les deux modules.
2. **Décorrélation stricte des flux de validation et passivité de `refresh_data()`** :
   *Retenu*. Le Garde-Fou MCP devient l'unique gestionnaire des patchs MCP. L'Inspecteur du Consultant IA n'affiche que les diffs générés par la session de chat locale. `refresh_data()` devient strictement passif et ne touche à aucun onglet.

---

## Décisions et Règles d'Architecture

### 1. Décorrélation des Files d'Attente
- Les patchs en attente créés via le protocole MCP (`StagedPatchModel`) sont interrogés, affichés et arbitrés **uniquement** dans le sous-onglet `Garde-Fou & Validation` (`MCPGardeFouWidget`).
- `WorkspaceInspectorWidget` (dans `ConsultantView`) ne consomme plus les patchs persistés de la table `staged_patch` issus du serveur MCP. Il est dédié aux diffs et cartes interactives émis par la conversation du Consultant IA in-app.

### 2. Passivité Stricte et Idempotence de `refresh_data()`
- L'invariance d'interface suivante est gravée : `refresh_data()` ne doit **jamais** modifier l'onglet actif d'un panneau (`chat_panel`, `context_panel` ou `SegmentedTabBar`), ni basculer de vue, ni afficher de volet rétractable.
- Lors de la réception de `mcp_data_mutated`, les vues mettent à jour leurs compteurs, badges et sélections sans jamais modifier la disposition active de l'utilisateur.

### 2 bis. Routage Granulaire par Domaine
- `MCPDataMutatedEvent` porte un champ `domain` (`cards`, `decks`, `models`, `docs`) résolu une seule fois par `resolve_mcp_mutation_domain()` dans le serveur MCP, puis injecté dans la charge utile.
- `MainWindow._on_mcp_data_mutated` ne réveille que les vues de la table `_MCP_DOMAIN_VIEWS` :
  - `cards` → `edition`, `analysis` ;
  - `decks` → `creation`, `batch`, `edition` (sélecteurs de paquets) ;
  - `models` → `card-models`, `edition` ;
  - `docs` → `documents`.
- Une vue peut exposer `apply_mcp_mutation(mutation)` pour une mise à jour granulaire (ligne de table, éditeur, sélection) ; à défaut, `refresh_data()` est appelé. Aucune vue hors domaine n'est plus réveillée par une mutation externe.
- Les types historiques émis par `ConsultantToolRegistry.apply_patch` (`card`, `split`, `model`, `css`) sont routés comme leurs équivalents canoniques afin de préserver la compatibilité des agents existants.

### 3. Nettoyage de `_activate_workspace_tab()`
- `_activate_workspace_tab()` ne pilote plus que le volet droit `self.context_panel.open_tab(self._workspace_tab_title)`. L'appel `self.chat_panel.set_active_tab(1)` est supprimé.
- L'activation de l'espace de travail ne se produit que lors d'une action utilisateur explicite (clic d'inspection depuis une carte inline de chat), jamais de manière automatique lors d'un rechargement de données.

### 4. Résolution Sémantique de l'Onglet Actif dans `IdePanel`
- Pour tout contrôle d'état d'un panneau `IdePanel`, l'accès à l'onglet actif s'effectue via l'indice de sa pile de contenu `self.content_stack.currentIndex()` ou `self.tabs_bar.current_index()`, interdisant l'usage d'attributs fantômes non typés.

---

## Conséquences

- **Stabilité de Navigation** : La validation ou le rejet d'un patch MCP maintient fidèlement l'utilisateur sur le sous-onglet Garde-Fou, sans aucun saut d'écran vers le chat.
- **Réactivité Ciblée** : Seules les vues du domaine muté se rafraîchissent, ce qui supprime les rechargements inutiles et préserve sélection, ascenseur et saisies en cours dans les autres vues.
- **Préparation du Dégagement de Dette** : Cette décorrélation isole hermétiquement le serveur MCP, rendant possible l'évolution ou la suppression ultérieure du Consultant in-app sans aucun risque de régression sur la chaîne d'outillage MCP.
- **Conformité ADR 0029 & 0030** : Réaffirme le principe d'autonomie des agents externes posé par les architectures précédentes.

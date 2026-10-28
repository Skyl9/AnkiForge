# Spécification Technique Unifiée — Écosystème Serveur MCP, Staged Bundles & Pipelines DAG

**Statut :** 📋 Validée pour découpage via `/to-tickets`  
**Date :** 25 Octobre 2026  
**Auteur :** Antigravity Supervisor (Tech Lead / Architecte)  
**ADRs de référence :** [ADR 0010](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0010-adresses-de-region-et-exclusion-non-destructive.md), [ADR 0041](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0041-integration-mcp-declenchement-pipeline-et-chaine-finition-staged.md), [ADR 0043](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0043-regime-staged-bundles-atomicite-sequentielle-et-overlay-mcp.md)  
**Contexte métier :** [CONTEXT.md](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/CONTEXT.md#L250-L280)

---

## 1. Problématique (Problem Statement)

L'architecture MCP actuelle d'AnkiForge présentait quatre limitations majeures bridant la collaboration homme-machine :

1. **Paralysie des flux d'agents autonomes** :
   En contraignant chaque mutation unitaire à un arrêt immédiat avec validation humaine, un agent externe (Claude Code, Antigravity CLI, Cursor) était incapable de dérouler un scénario cohérent d'authoring (ex. 1. créer une arborescence de paquets, 2. y créer 20 flashcards, 3. leur assigner des étiquettes taxonomiques). L'étape 2 échouait immédiatement car le paquet n'existait pas encore physiquement en base de données.
2. **Gaspillage du potentiel des modèles d'IA hors API & Absence de chaîne de finition** :
   Les modèles de raisonnement avancés (*extended thinking*) disponibles dans les forfaits des agents externes surpassent souvent les modèles d'API directe à un coût nul pour AnkiForge. Cependant, le moteur MCP interdisait le déclenchement des pipelines DAG, privant les cartes générées par l'agent des étapes à haute valeur ajoutée d'AnkiForge (nettoyage HTML/LaTeX, linter des 20 règles de Wozniak, déduplication Levenshtein, audio TTS).
3. **Asymétrie perméable & Risques de suppressions non contrôlées** :
    Certains outils d'hygiène (`delete_empty_cards`, `move_cards_to_deck`, `set_tags_bulk`) effectuaient des mutations directes sans validation humaine, violant le principe de précaution du Two-Phase Commit (ADR 0043). Par ailleurs, des anomalies critiques subsistaient (`propose_css_tune` orphelin sans persistance, seuil arbitraire de 5 cartes sur `sanitize_fields_html`).
4. **Interface du Garde-Fou inadaptée au multi-opérations** :
   Le widget du Garde-Fou affichait une liste plate conçue uniquement pour des modifications de cartes textuelles, incapable de présenter des blocs structurés d'opérations, des créations/renommages de paquets, des suppressions ou des modifications de tags avec un rendu polymorphe adapté.

---

## 2. Solution Proposée

Une refonte globale et cohérente unifiant le serveur MCP, le moteur Two-Phase Commit et l'IHM autour de **cinq piliers** :

```mermaid
flowchart TD
    subgraph ClientMCP["Agent Externe (Claude / Antigravity)"]
        Agent[Modèle Hors API + Raisonnement]
    end

    subgraph CoreMCP["Serveur MCP AnkiForge (mcp_server.py)"]
        Router{Régime Opération}
        Session[Gestionnaire de Session Staged Bundle]
        Overlay[Staged Overlay : Contexte Virtuel Intra-Bundle]
        DAGTrigger[trigger_pipeline_run]
    end

    subgraph Engine["Moteur DAG & Chaîne de Finition"]
        Worker[PipelineOrchestrator Async]
        Tools[Nettoyage LaTeX / Wozniak / TTS]
    end

    subgraph TwoPC["Registre Two-Phase Commit (StagedPatchRegistry)"]
        ModelBundle[StagedBundleModel]
        ModelPatch[StagedPatchModel (step_order)]
    end

    subgraph UI["Garde-Fou IHM (MCPGardeFouWidget)"]
        ViewMaster[Liste Maître : Groupes & Effectif]
        ViewDetail[Détail Polymorphe : Cartes, Decks, Tags, Deletion]
        ViewSeq[Validation Séquentielle Pas-à-Pas]
    end

    subgraph BDD["Base SQLite Peewee"]
        SQLite[(Collection Anki & Forge)]
    end

    Agent -->|Lectures directes| Router
    Router -->|SELECT direct| BDD
    
    Agent -->|begin_staged_bundle / mutations| Session
    Session --> Overlay
    Session -->|commit_staged_bundle| ModelBundle
    ModelBundle --> ModelPatch

    Agent -->|trigger_pipeline_run| DAGTrigger
    DAGTrigger --> Worker
    Worker --> Tools
    Tools -->|Fin de chaîne| ModelBundle

    ModelBundle --> ViewMaster
    ViewMaster --> ViewDetail
    ViewDetail --> ViewSeq
    
    ViewSeq -->|Valider étape / Tout valider| BDD
    ViewSeq -.->|Rejet étape k -> Arrêt en cascade| ModelPatch
```

1. **Binarité Stricte 100% Staged** :
   - Les **lectures** sont directes, passives et synchrones.
   - **Toutes les écritures sans exception** (créations, modifications, suppressions, déplacements, tags, styles, pipelines) deviennent des propositions en attente de validation humaine dans l'onglet `Garde_fou_validation`.
2. **Staged Bundles & Sessions Transactionnelles** :
   - Capacité pour l'agent d'ouvrir un bloc (`begin_staged_bundle`), d'exécuter N outils séquentiellement sans blocage, puis de sceller le bloc (`commit_staged_bundle`).
3. **Contexte Virtuel (Staged Overlay)** :
   - Résolution intra-bundle des dépendances : le validateur autorise l'utilisation d'entités créées dans les étapes antérieures du même bloc sans exiger leur présence physique préalable en base de données.
4. **Déclenchement Asynchrone de Pipelines DAG (`trigger_pipeline_run`)** :
   - L'agent injecte ses flashcards candidates créées hors API ; le pipeline DAG applique la chaîne de finition (nettoyage LaTeX, Wozniak, Levenshtein, `AUDIO_TTS`) dans un worker découplé sans timeout, puis encapsule le résultat dans un `StagedBundle`.
5. **IHM Garde-Fou Polymorphe & Validation Séquentielle** :
   - Présentation par groupes maîtres avec décompte d'opérations et progression.
   - Rendu adaptatif du détail (diff sémantique, arborescence de paquets, badges de tags, alertes de destruction).
   - Validation pas-à-pas avec retouche en place, règle d'arrêt en cascade (Fail-Fast Reject) en cas de refus d'une étape, et raccourci « Tout valider le bloc ».

---

## 3. User Stories Extensives

### A. Flux Agent & Staged Bundles
1. **En tant qu'** agent MCP réorganisant une matière d'étude,  
   **Je veux** ouvrir un Staged Bundle via `begin_staged_bundle("Restructuration Neurologie")`, créer le paquet `Médecine::Neurologie` à l'étape 1, déplacer 15 cartes à l'étape 2 et leur assigner le tag `neuro::snc` à l'étape 3,  
   **Afin d'** enchaîner l'ensemble de la réorganisation sans être bloqué entre chaque appel d'outil par l'absence d'intervention humaine synchrone.
2. **En tant qu'** agent MCP,  
   **Je veux** pouvoir vérifier les étapes en attente de mon bundle actif via `get_staged_pending_operations(bundle_id)`,  
   **Afin de** maintenir un raisonnement cohérent en tenant compte du décalage entre la base de données physique et mes propositions staged.
3. **En tant qu'** agent MCP constatant une incohérence dans mon raisonnement,  
   **Je veux** annuler un bundle en cours d'élaboration via `abort_staged_bundle(bundle_id)`,  
   **Afin de** ne pas encombrer la file d'attente de l'utilisateur avec des propositions caduques.

### B. Déclenchement de Pipelines DAG & Modèles Hors API
4. **En tant qu'** utilisateur opérant depuis un agent CLI (Claude Code, Antigravity CLI),  
   **Je veux** utiliser les capacités de raisonnement de mon modèle de pointe abonné pour rédiger des cartes et appeler `trigger_pipeline_run(pipeline_id, deck_name, cards_json)`,  
   **Afin de** faire exécuter automatiquement par AnkiForge la chaîne de finition (nettoyage LaTeX, linter Wozniak, synthèse vocale `AUDIO_TTS`) sans consommer de tokens d'API payante pour la génération initiale.
5. **En tant qu'** agent MCP ayant déclenché un pipeline,  
   **Je veux** recevoir immédiatement un `run_id` et interroger la progression via `get_pipeline_run(run_id)` sans subir de timeout réseau,  
   **Afin d'** être informé lorsque le statut passe à `staged` avec l'identifiant du patch prêt pour validation.

### C. Mutations Documents RAG & Délimitation de Portée
6. **En tant qu'** agent MCP analysant un cours importé par l'utilisateur,  
   **Je veux** exclure les sections hors-sujet via `exclude_document_region` ou `neutralize_document_region` ([ADR 0010](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0010-adresses-de-region-et-exclusion-non-destructive.md)),  
   **Afin d'** épurer le dénominateur de couverture et cibler l'indexation vectorielle sur le cœur académique sans altérer le document physique.
7. **En tant qu'** agent MCP,  
   **Je veux** pérenniser en base les corrections orthographiques et typographiques KaTeX d'un document existant via `update_document_content`, puis lancer `reindex_document`,  
   **Afin de** garantir que les chunks RAG reflètent un texte propre et correctement indexé.

### D. Expérience Utilisateur dans le Garde-Fou
8. **En tant qu'** utilisateur consultant l'onglet `Garde_fou_validation`,  
   **Je veux** visualiser mes propositions regroupées par blocs fonctionnels avec un badge indiquant le nombre d'étapes (ex. `[GROUPE] Refactorisation Cardio · 4 étapes`),  
   **Afin de** comprendre la finalité d'ensemble du travail de l'agent.
9. **En tant qu'** utilisateur examinant une étape d'un bundle,  
   **Je veux** que la vue de détail s'adapte automatiquement (vue de cartes, vue d'arborescence de paquets, vue de tags, ou alerte de suppression),  
   **Afin de** juger de la pertinence de la modification avec le composant visuel le plus pertinent.
10. **En tant qu'** utilisateur,  
    **Je veux** pouvoir corriger directement un champ texte dans le diff avant de valider l'étape,  
    **Afin d'** ajuster un détail sans rejeter l'ensemble de la proposition de l'agent.
11. **En tant qu'** utilisateur constatant une erreur critique à l'étape 2 d'un bundle de 5 étapes,  
    **Je veux** cliquer sur `Rejeter la suite du bloc`,  
    **Afin d'** annuler immédiatement toutes les étapes dépendantes subséquentes et empêcher toute corruption en cascade.
12. **En tant qu'** utilisateur faisant pleinement confiance à un bloc de propositions,  
    **Je veux** cliquer sur `Tout valider le bloc`,  
    **Afin d'** appliquer l'intégralité des opérations en une seule transaction SQLite sans répétition fastidieuse.

---

## 4. Décisions d'Implémentation

### A. Modèle de Données & Schéma SQLite (Migration 047)

Création de la table `staged_bundles` et extension de la table `staged_patches` :

```python
class StagedBundleModel(BaseModel):
    """Regroupement transactionnel d'opérations staged ordonnées."""

    bundle_id = CharField(unique=True, index=True)  # ex: "bundle_e4b109"
    title = CharField(max_length=255)
    explanation = TextField(default="")
    status = CharField(default="pending", index=True)  # "building", "pending", "applied", "rejected", "partial"
    total_steps = IntegerField(default=0)
    current_step = IntegerField(default=1)
    created_at = DateTimeField(default=datetime.datetime.now)
    applied_at = DateTimeField(null=True)

    class Meta:
        table_name = "staged_bundles"


class StagedPatchModel(BaseModel):
    """Patch chirurgical individuel ou étape d'un bundle."""

    patch_id = CharField(unique=True, index=True)
    bundle = ForeignKeyField(StagedBundleModel, backref="patches", null=True, on_delete="CASCADE")
    step_order = IntegerField(default=1)  # 1..N au sein du bundle
    patch_type = CharField()  # "note_create", "batch_note_create", "card_update", "split",
    # "deck_create", "deck_rename", "deck_delete", "set_tags",
    # "note_delete", "css", "model", "pipeline"
    target_id = IntegerField(default=0)
    original_version_id = IntegerField(null=True)
    diff_payload = TextField()  # JSON sérialisé
    status = CharField(default="pending", index=True)  # "pending", "applied", "rejected"
    created_at = DateTimeField(default=datetime.datetime.now)
    applied_at = DateTimeField(null=True)

    class Meta:
        table_name = "staged_patches"
```

### B. Moteur Staged Overlay (`StagedPatchRegistry`)

`StagedPatchRegistry` maintient en mémoire le contexte virtuel du bundle actif (`_active_bundles: dict[str, StagedOverlay]`) :
- `StagedOverlay` enregistre :
  - `created_decks: set[str]` : noms de paquets créés dans les étapes précédentes du bundle.
  - `renamed_decks: dict[str, str]` : correspondances ancien nom -> nouveau nom.
  - `created_notes_first_fields: dict[str, list[str]]` : valeurs clés pour prévenir les doublons internes au lot.
  - `deleted_notes: set[int]` : notes marquées pour suppression.
- **Validation anti-hallucination augmentée** :
  Lorsqu'une étape déclare `create_note(deck_name="Sciences::Physique")`, le contrôle vérifie :
  ```python
  if DeckModel.get_or_none(DeckModel.name == deck_name) or (bundle_overlay and deck_name in bundle_overlay.created_decks):
      # Paquet valide (physique ou staged dans le même bundle) !
  ```

### C. Contrats d'API & Outils MCP (FastMCP)

#### 1. Cycle de Vie des Bundles
- `begin_staged_bundle(title: str, explanation: str = "") -> str`  
  *Retourne* : `{"status": "bundle_opened", "bundle_id": "bundle_xxx", "title": "..."}`.
- `commit_staged_bundle(bundle_id: str) -> str`  
  *Contrôle* : Vérifie que le bundle contient au moins 1 étape. Scelle le bundle au statut `pending` et émet la notification IHM.  
  *Retourne* : `{"status": "staged", "bundle_id": "bundle_xxx", "total_steps": N}`.
- `abort_staged_bundle(bundle_id: str) -> str`  
  *Supprime* : Supprime le bundle en cours de construction et ses étapes associées.
- `get_staged_pending_operations(bundle_id: str = "") -> str`  
  *Retourne* : Liste détaillée des bundles et étapes en attente de validation avec leur état virtuel.

#### 2. Déclenchement de Pipelines DAG ([ADR 0041](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0041-integration-mcp-declenchement-pipeline-et-chaine-finition-staged.md))
- `trigger_pipeline_run(pipeline_id: int, deck_name: str, cards_json: str, note_type_name: str = "", document_id: int | None = None, variables_json: str = "{}") -> str`  
  *Contrôle anti-hallucination* : Valide `deck_name` contre `DeckRepository`.  
  *Exécution* : Initialise `PipelineRunState`, instancie `PipelineOrchestrator`, injecte les cartes dans `generated_cards`, lance le worker dans `QThreadPool`.  
  *Retourne immédiatement* : `{"status": "started", "run_id": 42, "pipeline_name": "...", "cards_count": 15}`.  
  *Finalisation worker* : Crée automatiquement un `StagedBundle` de type `batch_note_create` contenant les cartes traitées par la chaîne de finition DAG et marque le run au statut `staged`.

#### 3. Mutations Documents & RAG (ADR 0043 & ADR 0010)
- `exclude_document_region(document_id: int, region_address: str, reason: str = "") -> str`
- `neutralize_document_region(document_id: int, region_address: str, neutralized: bool = True) -> str`
- `update_document_content(document_id: int, content: str, reason: str = "") -> str`
- `reindex_document(document_id: int, chunk_size: int = 500, overlap: int = 50) -> str`

#### 4. Hygiène, Paquets & Suppressions (100% 2PC)
- `propose_card_deletion(note_id: int, reason: str = "") -> str`
- `propose_batch_card_deletion(note_ids_json: str, reason: str = "") -> str`
- `propose_deck_rename(old_name: str, new_name: str, reason: str = "") -> str`
- `propose_deck_deletion(deck_name: str, move_cards_to_deck: str = "", reason: str = "") -> str`

#### 5. Pipelines DAG & Outils Python
- `create_pipeline(name: str, description: str = "", steps_json: str = "[]") -> str`
- `update_pipeline_step(pipeline_id: int, step_order: int, config_json: str) -> str`
- `clone_pipeline(pipeline_id: int, new_name: str) -> str`
- `create_or_update_python_tool(name: str, display_name: str, description: str, python_code: str) -> str`

#### 6. Export, SRS & Système
- `export_deck_apkg(deck_name: str, output_path: str = "", include_media: bool = True) -> str`
- `set_card_flag(note_id: int, flag: str) -> str`
- `suspend_card(card_id: int) -> str` / `unsuspend_card(card_id: int) -> str`
- `correct_plate_ocr(plate_id: int, corrected_text: str) -> str`
- `trigger_manual_backup(reason: str = "") -> str`

#### 7. Corrections Critiques Appliquées
- `propose_css_tune` : Enregistre obligatoirement un `StagedPatch` (`patch_type="css"`).
- `delete_empty_cards` : Devient une proposition staged (`patch_type="empty_cards_delete"`).
- `sanitize_fields_html` : Génère obligatoirement un patch 2PC sans seuil magique.

### D. Refonte de l'Interface Garde-Fou (`MCPGardeFouWidget`)

1. **Volet Maître (Gauche)** :
   - Liste hiérarchique : Bundles au premier niveau, étapes déroulables au second niveau.
   - Badge d'effectif (`4 étapes`), badge d'état (`En cours · Étape 2/4`).
   - Raccourci global `Tout valider le bloc` et bouton `Tout rejeter`.
2. **Zone de Détail Polymorphe (Droite)** :
   - `QStackedWidget` adaptatif piloté par la nature de l'étape courante :
     - **Index 0 (Cartes & Diff)** : [`CardSemanticDiffWidget`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/widgets/card_semantic_diff_widget.py) avec word-level diff KaTeX/HTML.
     - **Index 1 (Paquets & Arborescence)** : Visualiseur d'arborescence affichant l'ancien et le nouveau chemin hiérarchique, avec contrôle de collision de nom.
     - **Index 2 (Tags & Métadonnées)** : Tableau comparatif affichant les tags ajoutés (badges verts), retirés (badges rouges) et conservés.
     - **Index 3 (Avertissement de Suppression)** : Bannière rouge vif avec décompte d'impact (notes supprimées, cartes filles détruites, orphelins évités).
     - **Index 4 (Pipelines & Scripts)** : Inspecteur de code Python colorisé et graphe d'étapes.
3. **Barre d'Action Séquentielle** :
   - Bouton `Valider cette étape` : Applique l'opération en base SQLite sous transaction atomique, met à jour `current_step = current_step + 1` et bascule l'affichage sur l'étape suivante.
   - Bouton `Rejeter la suite du bloc` : Déclenche un dialogue de confirmation explicite, marque toutes les étapes de $k$ à $N$ au statut `rejected`, et notifie l'agent.
   - Bouton `Tout valider le bloc` : Applique séquentiellement toutes les étapes restantes sous un unique bloc `with db.atomic():`.
   - Champ d'édition directe : Les données de l'étape courante sont modifiables en place via `sync_direct_edit` avant le clic de validation.

---

## 5. Décisions de Test

### A. Coutures Clés de Test (Seams)
1. **Seam 1 : `StagedPatchRegistry` & Moteur de Bundle**
   - Tests unitaires purs sur l'ouverture, l'accumulation d'étapes, la résolution du Staged Overlay et la règle de rejet en cascade.
   - Fichier cible : `tests/ai/test_staged_bundles.py`.
2. **Seam 2 : FastMCP Endpoints & Garde-Fous Anti-Hallucination**
   - Invocations de tous les nouveaux outils MCP via client de test in-process.
   - Validation que les rejets documentés (import de document brut, AnkiConnect) renvoient les erreurs contractuelles.
   - Fichier cible : `tests/ai/test_mcp_extended_tools.py`.
3. **Seam 3 : Déclenchement Asynchrone de Pipeline (`trigger_pipeline_run`)**
   - Test d'intégration avec mock déterministe de LLM : vérification du renvoi immédiat de `run_id`, exécution de la chaîne de finition DAG dans le worker, et génération du bundle staged final.
   - Fichier cible : `tests/ai/test_mcp_pipeline_trigger.py`.
4. **Seam 4 : Interface PySide6 `MCPGardeFouWidget` (Headless Qt via `pytest-qt`)**
   - Test des composants visuels, sélection de bundle, polymorphisme de la zone de détail, simulation de clics sur `Valider cette étape` et vérification de la cascade de rejet.
   - Fichier cible : `tests/ui/test_mcp_garde_fou_widget.py`.

### B. Précédents & Fixtures Existantes
- Réutilisation de la fixture d'isolation Peewee mémoire partagée `memdb_test_<worker>`.
- Mocks LLM stricts (règle non négociable 5 : zéro appel réseau réel en test).
- Fixture `cleanup_qt_widgets` pour le nettoyage des composants graphiques.

---

## 6. Hors Périmètre (Out of Scope)

Conformément aux arbitrages motivés de l'**ADR 0043**, les capacités suivantes sont **formellement exclues** :
1. **Création ou importation de documents bruts via MCP** (`create_document`) : Sanctuarisation anti-hallucination ; les documents doivent être importés via l'IHM.
2. **Création d'albums visuels & ajout de planches via MCP** : Même motif de protection de la source que pour les documents.
3. **Pilotage de la Batch Factory par l'agent MCP** (`trigger_batch_run`) : Prévention des boucles récursives sur API payantes pour protéger les budgets étudiants. La génération se fait via `trigger_pipeline_run` (modèle hors API).
4. **Synchronisation socket directe AnkiConnect** : Préservation du cycle distribué sécurisé (`.apkg`/`.colpkg` à IDs stables) sans risque de corruption de la base Anki locale.

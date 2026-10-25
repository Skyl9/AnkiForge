# Périmètre des Mutations MCP : Garde-Fous 2PC Systématiques et Rejets Motivés

**Statut :** accepté (complète et affine l'ADR 0017, l'ADR 0034 et l'ADR 0041)

---

## 1. Contexte & Problématique

Le serveur MCP d'AnkiForge a été initialement conçu avec un régime asymétrique strict ([ADR 0017](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0017-regime-ecriture-mcp-paquets-direct-vs-notes-staged.md)) et un centrage sur le Two-Phase Commit ([ADR 0034](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0034-architecture-mcp-garde-fou-2pc-et-centrage-harness.md)). Si 58 outils de consultation, d'audit et de mutation partielle de cartes ont été déployés, de larges pans de l'application restaient en lecture seule ou inaccessibles.

À la suite de l'arbitrage autorisant le déclenchement des pipelines DAG de finition par des agents externes ([ADR 0041](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0041-integration-mcp-declenchement-pipeline-et-chaine-finition-staged.md)), une revue exhaustive des capacités de modification de l'application a été menée afin de délimiter clairement ce qu'un agent MCP doit pouvoir modifier, ce qui lui est formellement interdit, et les mécanismes de validation humaine requis.

---

## 2. Rejets Formels & Motivations d'Architecture

Quatre capacités de modification ont été **explicitement rejetées** par arbitrage produit et technique :

| Capacité rejetée | Motif d'arbitrage |
| :--- | :--- |
| **Création / Importation de documents bruts** (`create_document`) | **Anti-hallucination documentaire** : l'ingestion d'un cours ou d'un livre doit être initiée par l'humain dans l'application pour garantir l'authenticité de la source et éviter l'injection de documents fabriqués de toutes pièces par un agent. |
| **Création d'albums visuels & ajout de planches** | **Même motif anti-hallucination** : les supports graphiques/OCR doivent provenir de documents physiques vérifiés et importés via l'IHM. |
| **Pilotage de la Batch Factory** (`trigger_batch_run`) | **Protection budgétaire des utilisateurs (notamment étudiants)** : déléguer des traitements de masse asynchrones à des agents externes ferait courir un risque de boucles récursives consommant des quotas d'API payantes. La création par lots doit s'opérer directement par l'agent via `trigger_pipeline_run` (modèle hors API, ADR 0041). |
| **Synchronisation AnkiConnect direct** | **Préservation du cycle distribué sans corruption** : AnkiForge privilégie les archives stables `.apkg`/`.colpkg` et l'isolation des processus. Un dialogue socket en direct avec l'extension AnkiConnect risquerait d'altérer la base Anki en cours de session. |

---

## 3. Décisions & Arbitrages de Mutation Validés

### A. Documents Existants & RAG
L'agent MCP peut intervenir sur la **qualité et le périmètre** des documents déjà importés :
- **Exclusion et Neutralisation de Régions ([ADR 0010](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0010-adresses-de-region-et-exclusion-non-destructive.md))** : `exclude_document_region` et `neutralize_document_region` permettent d'écarter les sections parasites (bibliographies, errata, tables des matières) du dénominateur de couverture et du RAG.
- **Enregistrement de corrections Markdown** : `update_document_content` permet à l'agent de sauvegarder en base les corrections orthographiques, KaTeX et de mise en page issues de `format_markdown_document`.
- **Réindexation RAG** : `reindex_document` relance le découpage sémantique (`ChunkingService`) et l'indexation vectorielle FAISS/ChromaDB après modification.

### B. Two-Phase Commit Systématique pour la Suppression & les Paquets
L'intégrité de la collection impose une règle absolue : **toute action destructive ou structurelle requiert un `StagedPatch` validé par l'humain** :
- **Suppression ciblée de notes** (`delete_note`, `delete_notes_batch`) : génère un patch `note_delete` ou `batch_note_delete`. Aucune carte physique n'est effacée directement.
- **Renommage de paquet** (`rename_deck`) : génère un patch de réorganisation `deck_rename`.
- **Suppression de paquet** (`delete_deck`) : génère un patch `deck_delete` vérifiant préalablement la présence de cartes filles.

### C. Composition de Pipelines DAG & Outils Python
L'agent externe peut adapter ou concevoir les chaînes de finition de ses générations :
- **Gestion des Pipelines DAG** : `create_pipeline`, `update_pipeline_step`, `clone_pipeline`.
- **Outils Python réutilisables** : exposition de l'outil `create_or_update_python_tool` (s'appuyant sur le service existant `MCPToolService` et la sandbox `run_python_tool`).

### D. Outillage Périphérique & Sauvegarde
- **Export `.apkg` autonome** : `export_deck_apkg(deck_name, output_path)` permet à l'agent d'exporter un paquet finalisé à identifiants stables sans passer par l'IHM.
- **Drapeaux et Suspension SRS** : `set_card_flag(note_id, flag_color)`, `suspend_card(card_id)`, `unsuspend_card(card_id)` pour l'audit et le tri en révision.
- **Correction d'OCR de planches** : `correct_plate_ocr(plate_id, corrected_text)` pour rectifier les artefacts de vision sur les albums existants.
- **Sauvegarde manuelle** : `trigger_manual_backup()` pour créer un instantané de sécurité SQLite avant des mutations volumineuses.

---

## 4. Matrice des Outils & Régimes de Validation

| Domaine | Outil MCP | Régime d'Écriture |
| :--- | :--- | :--- |
| **Documents & RAG** | `exclude_document_region`<br>`neutralize_document_region`<br>`update_document_content`<br>`reindex_document` | Écriture directe idempotente (non-destructif, réversible) |
| **Hygiène & Suppression** | `propose_card_deletion`<br>`propose_deck_rename`<br>`propose_deck_deletion` | **StagedPatch (Two-Phase Commit)** obligatoire |
| **Pipelines & Python** | `create_pipeline`<br>`update_pipeline_step`<br>`create_or_update_python_tool` | Écriture directe avec validation syntaxique / sandbox |
| **SRS & Révision** | `set_card_flag`<br>`suspend_card`<br>`unsuspend_card` | Écriture directe synchrone |
| **Albums** | `correct_plate_ocr` | Écriture directe sur la couche texte de la planche |
| **Export & Système** | `export_deck_apkg`<br>`trigger_manual_backup` | Opération système synchrone |

---

## 5. Conséquences

- **Sécurité maximale** : Aucune donnée sensible (notes, paquets) ne peut être détruite silencieusement grâce au 2PC universel sur les suppressions.
- **Autonomie accrue de l'agent CLI** : L'agent peut nettoyer les documents existants, affiner les pipelines DAG, exporter les decks en `.apkg` et assister l'étudiant dans le tri de ses cartes.
- **Sanctuarisation de la source** : Le rejet de l'import de documents et d'albums garantit qu'AnkiForge reste ancré dans les documents légitimes de l'utilisateur.

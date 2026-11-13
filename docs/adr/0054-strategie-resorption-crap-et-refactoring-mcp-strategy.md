# ADR 0054 : Stratégie de Résorption du Risque CRAP & Architecture PatchApplierStrategy pour le Serveur MCP

- **Statut** : Accepté
- **Date** : 2026-11-03
- **Décideurs** : Équipe d'ingénierie AnkiForge & Tristan Rigaud-Humbert
- **Périmètre** : Qualité logicielle (`script/verify.py`, `script/crap.py`), suite de tests (`tests/`), moteur MCP (`src/ankidraft/services/ai/staged_patch_registry.py`), vues UI.

---

## 1. Contexte & Problématique

L'introduction du calculateur d'indice CRAP (*Change Risk Anti-Patterns*, formule d'Alberto Savoia et Bob Evans : $\text{CRAP} = CC^2 \times (1 - cov)^3 + CC$) a permis d'auditer l'intégralité du codebase métier (`src/ankidraft/`, 6 244 fonctions).

L'inventaire met en évidence :
1. **Un socle globalement sain** : 91.7 % du codebase (5 725 fonctions) est strictement conforme au seuil de qualité ($\text{CRAP} \le 25.0$).
2. **Une concentration de dette technique sur 368 fonctions (5.9 %)** :
   - **110 fonctions monolithiques à complexité pure ($CC > 25$)** : Puisque le score CRAP minimum d'une fonction est mathématiquement égal à son $CC$ ($\min(\text{CRAP}) = CC$ à 100 % de couverture), aucun test ne peut les ramener sous le seuil de 25 sans découpage structurel.
   - Le cas le plus critique est `apply_staged_patch` dans `staged_patch_registry.py` (**$CC = 245$**, CRAP = 982.7), un monolithe de 450 lignes traitant 30 types d'opérations de mutation MCP au travers d'une immense cascade conditionnelle.
   - **258 fonctions à déficit de couverture ($CC \le 25$, couverture $< 10\%$)** : Concentrées dans les vues UI (`edition_view`, `documents_view`, `creation_view`) et certains services (`tts_service`, `main_window`). Leurs scores CRAP s'envolent (parfois $> 400$) uniquement en raison de l'absence de tests unitaires ou headless Qt.

Deux risques majeurs émergent :
- Si la *Verification Gate* applique un seuil dur aveugle (`--threshold 25`), toute retouche mineure dans un fichier hébergeant un monolithe legacy échoue immédiatement, bloquant les livraisons.
- Si rien n'est entrepris, le risque de régression silencieuse lors des interventions d'agents externes FastMCP reste critique.

---

## 2. Décision d'Architecture

### 2.1. Stratégie Séquentielle en Deux Phases

Le chantier de résorption est divisé en deux phases ordonnées :

1. **Phase 1 — « Quick Wins Tests » (Effort Modéré, Impact Massif)** :
   - Écriture de tests unitaires et d'interaction headless Qt sur les **258 fonctions sous-couvertes** ($CC \le 25$).
   - Objectif : diviser par 10 à 20 leur score CRAP pour les faire plonger sous 25 **sans modifier une seule ligne de code de production**.
   - Découpage en 3 lots fonctionnels :
     - *Lot 1* : Vues d'édition et gestion documentaire (`edition_view`, `documents_view`, `card_semantic_diff_widget`).
     - *Lot 2* : Navigation et composants cadres (`main_window.py`, `panels.py`, `creation_view`).
     - *Lot 3* : Services métier (`tts_service.py`, `duplicate_manager.py`, `yt_dlp_service.py`, `flexible_service.py`).

2. **Phase 2 — « Refactoring d'Architecture » (Découpage des Monolithes)** :
   - Restructuration des méthodes monstres à $CC > 25$ via des patrons de conception adaptés.

### 2.2. Architecture Cible pour le Moteur de Mutation MCP (`PatchApplierStrategy`)

Dans le cadre de l'ADR 0043, le chat in-app « Consultant » a été intégralement déposé au profit du serveur autonome FastMCP (`mcp_server.py`, `mcp_tool_registry.py`). Le composant `StagedPatchRegistry` constitue le pivot d'intégrité de la validation en deux phases (*Two-Phase Commit*).

La méthode monolithique `apply_staged_patch` ($CC = 245$) est restructurée selon le **Pattern Strategy** :
- Définition d'un protocole abstrait `PatchApplierStrategy` exposant une méthode unifiée `apply(operation: StagedOperation, context: PatchExecutionContext) -> MutationResult`.
- Extraction de sous-stratégies spécialisées, isolées et testables unitairement :
  - `NoteCreatePatchStrategy` (création de notes et cartes)
  - `NoteUpdateFieldsPatchStrategy` (mise à jour chirurgicale de champs)
  - `NoteDeletePatchStrategy` (archivage/suppression de note)
  - `DeckOperationPatchStrategy` (création, renommage, suppression de paquets)
  - `TagDiffPatchStrategy` (mutations sur les tags normalisés)
- `StagedPatchRegistry.apply_staged_patch` devient un simple aiguilleur (*dispatcher*) de 15 lignes cherchant la stratégie adéquate dans un dictionnaire de correspondance, faisant chuter son $CC$ de 245 à $\le 5$ et son CRAP sous 5.

### 2.3. Gestion du Garde-Fou dans la Verification Gate (`verify.py`)

- **Pendant la Phase 1 (Transition)** : L'étape `crap-check` de `verify.py` s'exécute en étape 8 (après `pytest-fast`) en mode **audit et reporting informatif** (`python script/crap.py --changed`), sans code d'erreur bloquant par défaut, pour ne pas paralyser le flux de livraison sur le legacy.
- **En Phase 2** : Enrichissement de `script/crap.py` pour restreindre le calcul du seuil `--threshold 25` aux seules lignes modifiées par Git (`git diff -U0`), transformant le seuil en garde-fou préventif strict sur les nouvelles fonctions.

---

## 3. Conséquences

### Positives
- **Résorption rapide de 70 % des alertes** sans risque de régression applicative grâce aux tests de la Phase 1.
- **Sécurisation de FastMCP** : modularisation du moteur de patch facilitant l'ajout de nouveaux outils par les agents externes sans inflation de complexité cyclomatique.
- **Fluidité de développement** : élimination des faux échecs de la porte pre-push sur le code préexistant non modifié.
- **Clarté conceptuelle** : alignement total avec l'ADR 0043 (zéro résidu de logique "Consultant" dans le moteur de patchs).

### Négatives / Contraintes
- Nécessite l'écriture d'environ 30 à 40 cas de tests headless Qt pour couvrir convenablement les slots des vues d'édition et de documents.
- La refactorisation en `PatchApplierStrategy` implique une migration soignée pour garantir qu'aucune des 30 opérations de mutation existantes ne perde sa gestion transactionnelle SQLite (`db.atomic()`).

---

## 4. Alternatives Écartées

1. **Seuil dur global immédiat (`--threshold 25`)** :
   *Rejeté*. Bloquerait instantanément tout commit touchant même marginalement `staged_patch_registry.py` ou `export_manager.py` tant que ces fichiers ne sont pas totalement réécrits.
2. **Décomposition procédurale interne (sous-méthodes privées `_apply_*` dans la même classe)** :
   *Rejeté*. Conserverait une classe `StagedPatchRegistry` de plus de 1 200 lignes et ne permettrait pas de tester les stratégies d'application de manière isolée sans instancier tout le registre.
3. **Approche opportuniste ("Boy Scout Rule" sans plan dédié)** :
   *Rejeté*. L'expérience démontre que les développeurs et agents contournent les monolithes lors des tâches métier sous la pression des délais, pérennisant la dette indéfiniment.

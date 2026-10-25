# Spécification Technique : Migration de Type de Note, Synchronisation des Cartes Physiques et Robustesse MCP

**Référence ADR :** [ADR 0045 : Migration de Type de Note, Synchronisation des Cartes Physiques et Robustesse MCP](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0045-migration-type-de-note-synchronisation-cartes-et-robustesse-mcp.md)  
**Date :** 2026-10-25  
**Statut :** Spécification Validée — Prête pour découpage en tickets (`/to-tickets`)

---

## 1. Problématique (Problem Statement)

Dans l'application AnkiForge, le changement de type de note pour des cartes existantes présentait des défaillances structurelles majeures :

1. **Désynchronisation et corruption des cartes physiques ([`CardModel`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/database/models/cards.py#L177))** :
   - L'implémentation historique de [`NoteTypeService.change_note_type`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/cards/note_type_service.py) ne créait ni ne supprimait jamais de cartes physiques.
   - En migrant d'un modèle à 1 gabarit (*Basique*) vers un modèle à 2 gabarits (*Basique et inversée*), la deuxième carte physique n'était jamais créée.
   - En migrant d'un modèle à 2 gabarits vers un modèle à 1 gabarit, la carte surnuméraire (`template_index = 1`) subsistait en base avec un index de gabarit invalide, causant des erreurs au rendu visuel et faussant les requêtes de révision.
2. **Remappage aveugle et perte silencieuse de données dans l'interface** :
   - Dans la vue d'Édition ([`EditionView`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/views/edition_view/view.py)), l'action ouvrait un simple sélecteur de modèle ([`ModelSelectWindow`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/dialogs/model_select_modal.py)) sans aucune interface de correspondance interactive.
   - Les champs étaient assignés à l'aveugle selon la correspondance de nom ou la position brute (`0 -> 0`, `1 -> 1`), entraînant la perte irrémédiable de données lorsque les schémas divergeaient.
   - L'action ne prenait en charge qu'une seule note à la fois, sans support de la sélection multiple.
3. **Fragilité et hallucinations des agents LLM via le protocole MCP** :
   - L'outil MCP `change_note_type` exigeait des chaînes JSON stringifiées (`note_ids_json: str`, `mapping_champs_json: str`), sources récurrentes d'échecs de syntaxe pour les LLM.
   - Aucune vérification pré-vol n'était opérée sur la validité des champs cibles spécifiés par l'agent.
   - Si des champs sources non vides risquaient d'être ignorés sans consigne, le système appliquait une troncature silencieuse.
   - Le patch intermédiaire (`StagedPatch`) ne fournissait aucun aperçu visuel (diff textuel) d'une note témoin avant/après remappage.
4. **Discordance avec les types à texte à trous (*Cloze*)** :
   - Absence de calcul dynamique des cartes dérivées des occlusions `{{c1::...}}`, `{{c2::...}}` et absence d'assainissement textuel lors de la bascule vers un type Standard.

---

## 2. Solution Proposée

Une refonte globale et unifiée de la **migration de type de note** articulée autour de 4 piliers :

1. **Moteur transactionnel de synchronisation des cartes physiques (`NoteTypeService.change_note_type`)** :
   - Remappage explicite des gabarits (`template_mapping`), préservation intégrale des métriques SRS FSRS (`ivl`, `reps`, `lapses`, `stability`, `difficulty`, `flags`) pour les cartes conservées.
   - Suppression transactionnelle des cartes surnuméraires non réassignées (conformité officielle Anki).
   - Génération conditionnelle des nouvelles cartes pour les gabarits cibles additionnels non vides.
   - Détection des occlusions `c1..cN` pour Cloze et nettoyage optionnel des marqueurs lors du passage en Standard.
2. **Dialogue interactif modal de migration (`ChangeNoteTypeDialog`)** :
   - Dialogue PySide6 dédié avec sélecteur de type cible, table de correspondance des champs avec pré-remplissage heuristique intelligent (exact > synonymes > position), table de correspondance des gabarits et prévisualisation avant/après en temps réel.
3. **Triple accès ergonomique dans la vue d'Édition (`EditionView`)** :
   - Clic droit contextuel sur le tableau (support unitaire et multi-sélection).
   - Bouton d'action de lot dans la barre d'outils supérieure.
   - Bouton de migration dans le panneau d'inspection de note latéral droit.
4. **Sécurisation robuste de l'outil MCP (`change_note_type`)** :
   - Arguments polymorphes (`list[int] | str`, `dict[str, str] | str`).
   - Validation pré-vol fail-fast avec retour d'erreur guidé (schémas source/cible et suggestions) si un champ est invalide ou si des champs non vides sont ignorés sans mapping.
   - Payload de staged patch enrichi avec diff textuel d'une note témoin et métriques des cartes (conservées, créées, supprimées).

---

## 3. User Stories (Extensives)

### US1 — Migration unitaire depuis l'éditeur de note
En tant qu'**utilisateur dans la vue d'Édition**,  
Je veux **changer le type de note de la note active via un dialogue dédié**,  
Afin de **remapper manuellement chaque champ source vers le bon champ cible et vérifier visuellement l'aperçu avant d'enregistrer**.

### US2 — Migration par lot avec sélection multiple
En tant qu'**utilisateur gérant une grande collection**,  
Je veux **sélectionner plusieurs notes dans le tableau et cliquer sur "Changer le type de note..."**,  
Afin de **migrer l'ensemble du lot de façon atomique vers le nouveau type de note avec les mêmes règles d'assignation de champs**.

### US3 — Préservation intégrale des statistiques SRS et alignement des cartes
En tant qu'**apprenant révisant quotidiennement ses cartes**,  
Je veux **migrer un lot de notes "Basique" vers "Basique (et inversée)" sans perdre mes intervalles de révision**,  
Afin que **ma carte recto existante conserve son historique FSRS exact pendant que la nouvelle carte verso est automatiquement créée**.

### US4 — Réduction du nombre de gabarits sans corruption
En tant qu'**utilisateur simplifiant un type de note complexe vers un type basique**,  
Je veux **que les cartes surnuméraires dont le gabarit n'existe plus dans le modèle cible soient proprement supprimées**,  
Afin d'**éviter toute carte orpheline invisible ou corrompue dans ma collection**.

### US5 — Transition intelligente vers ou depuis un type Cloze
En tant qu'**utilisateur convertissant une note à texte à trous en note standard**,  
Je veux **que les balises `{{c1::mot}}` soient nettoyées en `mot` et qu'une seule carte basique soit conservée**,  
Afin d'**obtenir une carte lisible sans balisage résiduel inesthétique**.

### US6 — Appel MCP fiable et tolérant pour l'agent IA
En tant qu'**agent IA (ou client MCP externe)**,  
Je veux **appeler `change_note_type` en passant des listes d'IDs et des dictionnaires de mapping natifs ou JSON**,  
Afin de **ne plus subir d'échecs d'analyse syntaxique liés aux doubles encodages de chaînes**.

### US7 — Diagnostic d'erreur constructif pour l'agent IA
En tant qu'**agent IA ayant proposé un mapping avec un nom de champ erroné ou ayant omis un champ non vide**,  
Je veux **recevoir une réponse d'erreur explicite décrivant les champs valides et une suggestion de mapping**,  
Afin de **corriger immédiatement mon appel sans halluciner ni altérer la base de données**.

### US8 — Inspection humaine du diff dans le StagedPatch
En tant qu'**utilisateur validant les propositions de l'IA (Two-Phase Commit)**,  
Je veux **consulter le diff textuel clair de la note migrée ainsi que le résumé des cartes créées/supprimées dans le patch**,  
Afin d'**approuver en toute confiance la mutation de ma collection**.

---

## 4. Décisions d'Implémentation

### A. Architecture du Service Backend (`NoteTypeService`)

Fichier : [`src/ankiforge/services/cards/note_type_service.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/cards/note_type_service.py)

#### 1. Signature enrichie de `change_note_type`
```python
@classmethod
def change_note_type(
    cls,
    note_ids: list[int],
    target_model: NoteTypeModel | str | int,
    mapping_champs: dict[str, str] | None = None,
    template_mapping: dict[int, int | None] | None = None,
    clean_cloze: bool = True,
) -> dict[str, Any]:
```

#### 2. Heuristique de suggestion de mapping des champs (`suggest_field_mapping`)
```python
@classmethod
def suggest_field_mapping(
    cls,
    source_fields: list[str],
    target_fields: list[str],
) -> dict[str, str]:
```
- **Niveau 1 — Correspondance exacte normalisée** : minuscule, suppression des espaces et accents (`réponse` == `reponse`).
- **Niveau 2 — Dictionnaire sémantique de synonymes canoniques** :
  - Question / Recto / Front / Text / Prompt
  - Réponse / Verso / Back / Extra / Solution
  - Notes / Remarques / Remarque / Commentaire / Addendum / Source
- **Niveau 3 — Alignement positionnel de repli** : `source_fields[i] -> target_fields[i]` si indices valides.
- **Niveau 4 — Ignoré / Chaîne vide** : tout champ restant.

#### 3. Validation pré-vol fail-fast (`validate_field_mapping`)
```python
@classmethod
def validate_field_mapping(
    cls,
    source_fields: list[str],
    target_fields: list[str],
    mapping_champs: dict[str, str] | None,
    sample_notes: list[NoteModel] | None = None,
) -> tuple[bool, str, dict[str, str]]:
```
- Détecte si des champs cibles renseignés n'existent pas dans le modèle de destination.
- Détecte si des champs sources **contenant du texte non vide** dans le lot de notes risquent d'être ignorés sans mention explicite `None` ou `""`.
- Retourne `(is_valid, error_message, suggested_mapping)`.

#### 4. Cycle de vie des cartes physiques (`CardModel`)
- Chargement des gabarits cibles (`target_templates = json.loads(target_nt.templates)`).
- Détection Cloze cible vs source.
- Pour chaque note du lot dans `with db.atomic():` :
  1. Application du remappage sur le contenu de la version active.
  2. Si `clean_cloze` et conversion Cloze -> Standard : passage d'une regex supprimant `{{c\d+::(.*?)(?:::.*?)?}}` au profit du texte capturé.
  3. Sauvegarde de la note et création de la nouvelle version (`source="note_type_change"`).
  4. Réassignation des cartes physiques existantes :
     - Pour chaque `c in note.cards` :
       - Si `template_mapping` spécifie un index cible valide `new_idx < len(target_templates)` :
         `c.template_index = new_idx; c.save()` (SRS préservé).
       - Si l'index cible est `None` ou hors limites des gabarits cibles : `c.delete_instance()` (suppression conforme Anki).
  5. Génération conditionnelle des nouvelles cartes :
     - Si cible est Standard : pour chaque index `t_idx` de gabarit cible non couvert par une carte physique existante :
       - Évaluation de `should_generate_card(target_templates[t_idx]["qfmt"], mapped_data)`.
       - Si `True` : `CardModel.create(note=note, deck=note.cards.first().deck or default_deck, template_index=t_idx)`.
     - Si cible est Cloze :
       - Calcul de `max_cloze = get_max_cloze_index(mapped_data)`.
       - Ajustement dynamique du nombre de cartes physiques pour couvrir les indices `0` à `max(0, max_cloze - 1)`.

---

### B. Interface Utilisateur PySide6

#### 1. Nouveau composant `ChangeNoteTypeDialog`
Fichier : [`src/ankiforge/ui/dialogs/change_note_type_dialog.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/dialogs/change_note_type_dialog.py)

- Hérite de `QDialog`.
- Respect strict des jetons de style (`DesignTokens`, `DESIGN.md`) et de l'internationalisation `tr()` (`ADR 0013`).
- **En-tête** : Résumé du lot (ex: *"Migration de 12 note(s) sélectionnée(s)"*) et sélecteur de modèle cible (`QComboBox`).
- **Onglet 1 : Correspondance des champs (Field Mapping)** :
  - `QTableWidget` : Colonne *Champ Source* (avec pastille verte si renseigné), Colonne *Flèche ➔*, Colonne *Champ Cible* (`QComboBox` listant les champs cibles + option `(Ignorer / Supprimer)`).
  - Indicateur visuel d'avertissement en cas de données ignorées.
- **Onglet 2 : Correspondance des gabarits (Card Templates)** :
  - `QTableWidget` : Colonne *Carte Existante* (Recto/Verso source), Colonne *Action*, Colonne *Gabarit Cible* (Gabarit 1..N ou Supprimer la carte).
- **Zone inférieure : Prévisualisation en direct (Live Preview)** :
  - Sélecteur de note témoin (si lot > 1).
  - Deux blocs de comparaison textuelle Avant / Après avec surlignage des champs affectés.
- **Boutons d'action** : `Annuler` et `Appliquer la migration`.

#### 2. Intégration dans `EditionView`
Fichier : [`src/ankiforge/ui/views/edition_view/view.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/views/edition_view/view.py)

- **Point 1 — Clic droit sur le tableau** :
  - L'action `Changer le type de note...` récupère `target_note_ids = self.get_target_note_ids(fallback_note_id)`.
  - Ouvre `ChangeNoteTypeDialog(note_ids=target_note_ids, parent=self)`.
- **Point 2 — Barre d'outils de lot** :
  - Un bouton d'action groupée `btn_change_note_type` s'active dès que des notes sont cochées.
- **Point 3 — Panneau d'édition latéral** :
  - Le clic sur le bouton de changement de modèle déclenche `ChangeNoteTypeDialog(note_ids=[self._current_note.id], parent=self)`.
- Rafraîchissement complet du tableau et toast de confirmation post-migration :
  `show_toast(self, tr("Migration réussie : %1 note(s) convertie(s) vers '%2'.", count, target_name))`

---

### C. Serveur MCP & Garde-Fous Agentiques

Fichiers :
- [`src/ankiforge/services/ai/mcp_server.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/ai/mcp_server.py)
- [`src/ankiforge/services/ai/staged_patch_registry.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/ai/staged_patch_registry.py)

#### 1. Signature tolérante de l'outil MCP
```python
@mcp.tool()
def change_note_type(
    note_ids: list[int] | str,
    target_model: str,
    mapping_champs: dict[str, str] | str = "",
    template_mapping: dict[str, Any] | str = "",
    clean_cloze: bool = True,
) -> str:
```

#### 2. Diagnostic pré-vol assisté pour l'IA
- Normalisation robuste des entrées via `parse_id_list` et parsing JSON tolérant.
- Appel à `NoteTypeService.validate_field_mapping(...)` :
  - Si invalide ou perte non sollicitée : retour d'un objet JSON explicite avec code d'erreur `FIELD_MAPPING_REQUIRED`, liste des champs cibles disponibles, liste des champs sources actifs, et `suggested_mapping`.
  - L'agent LLM dispose ainsi immédiatement de la matière exacte pour réussir son prochain appel sans halluciner.

#### 3. Diff riche dans `StagedPatchRegistry`
- Lors de la création du patch `note_type_change` :
  - Échantillonnage de la 1ère note du lot.
  - Génération du diff `{"before": sample_before, "after": sample_after}`.
  - Calcul du bilan prévisionnel : `cards_preserved`, `cards_created`, `cards_deleted`.
  - Intégration de ce diff dans le payload du `StagedPatch` pour affichage dans la vue Consultant et l'UI de revue.

---

## 5. Décisions de Test

### A. Coutures Clés (Seams) d'Intégration & Unitaire
1. **`NoteTypeService.change_note_type`** :
   - Tester la préservation stricte des compteurs SRS FSRS (`ivl`, `reps`, `lapses`, `flags`, `stability`).
   - Tester la création de nouvelles cartes physiques lors de la migration vers un modèle à gabarits supérieurs.
   - Tester la suppression physique des cartes surnuméraires lors de la migration vers un modèle à gabarits inférieurs.
   - Tester la migration Cloze ➔ Standard (nettoyage des balises de trous).
   - Tester la migration Standard ➔ Cloze (génération automatique des cartes selon `c1..cN`).
   - Tester l'atomicité totale en cas d'erreur de base de données (rollback).
2. **`NoteTypeService.suggest_field_mapping` & `validate_field_mapping`** :
   - Tester la reconnaissance des synonymes et de la casse.
   - Tester le rejet fail-fast en cas de champ cible inexistant ou de perte silencieuse de texte non vide.
3. **Outil MCP `change_note_type`** :
   - Tester le polymorphisme des arguments (JSON string, liste/dict natifs).
   - Tester le retour d'erreur guidé avec suggestion de mapping.
   - Tester le flux complet Two-Phase Commit (`change_note_type` -> `staged_patch` -> `preview_and_apply_patch`).
4. **Composant UI Headless PySide6 (`ChangeNoteTypeDialog`)** :
   - Tester l'instanciation en mode unitaire et en mode lot.
   - Tester le changement de sélection dans les tables de mapping.
   - Tester la propagation du signal de confirmation sans crash Qt.

### B. Précédents et Fixtures
- Base de données SQLite partagée en mémoire : `file:memdb_test_<worker>?mode=memory&cache=shared`.
- Fixture `sample_models_and_notes` de `tests/services/cards/test_note_type_service.py`.
- Fixture `cleanup_qt_widgets` et environnement headless `QT_QPA_PLATFORM=offscreen`.

---

## 6. Hors Périmètre (Out of Scope)

1. **Édition structurelle des types de notes cibles** :
   - Cette spécification concerne exclusivement le déplacement et remappage de notes vers un type existant. La modification de schéma d'un type de note (ajout/suppression de champs ou templates du type lui-même) relève de `propose_note_type_refactor`.
2. **Synchronisation d'ordonnancement actif Anki** :
   - La date d'échéance `due` et le journal `revlog` relèvent exclusivement du logiciel Anki et ne sont pas recalculés par AnkiForge (conformément au glossaire `CONTEXT.md`).
3. **Conversion automatique d'images d'occlusion (Image Occlusion)** :
   - La migration de cartes d'occlusion d'images (`Image Occlusion Enhanced`) vers du texte standard n'est pas traitée par ce workflow unifié et conserve son service dédié.

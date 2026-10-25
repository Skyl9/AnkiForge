# 45. Migration de Type de Note, Synchronisation des Cartes Physiques et Robustesse MCP

**Date :** 2026-10-25  
**Statut :** Accepté  

---

## 1. Contexte & Problématique

Dans AnkiForge, le changement de type de note pour des cartes existantes présentait plusieurs limitations critiques :

1. **Absence de synchronisation des cartes physiques (`CardModel`)** :
   - L'implémentation historique de [`NoteTypeService.change_note_type`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/cards/note_type_service.py) s'interdisait formellement de créer ou supprimer des cartes physiques, sous prétexte de « préserver l'historique SRS ».
   - **Conséquence directe** : si une note passait d'un modèle à 1 gabarit (ex: *Basique*) vers un modèle à 2 gabarits (ex: *Basique (carte inversée)*), la deuxième carte physique n'était jamais créée. Inversement, en passant d'un modèle à 2 gabarits vers un modèle à 1 gabarit, la carte physique d'indice `template_index = 1` restait orpheline en base avec un pointeur de gabarit inexistant, corrompant le rendu visuel et les requêtes de révision.
2. **Remappage aveugle et perte silencieuse de données dans l'IHM** :
   - Dans la vue d'Édition ([`EditionView`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/views/edition_view/view.py)), l'action ouvrait un simple sélecteur de modèle ([`ModelSelectWindow`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/dialogs/model_select_modal.py)) sans aucune étape de correspondance interactive.
   - Les champs étaient assignés à l'aveugle par simple coïncidence de nom ou par ordre positionnel (`0 -> 0`, `1 -> 1`). Tout champ source non concordant était jeté sans préavis.
   - L'action ne supportait qu'une seule note à la fois et ignorait la sélection multiple.
3. **Fragilité et hallucinations de l'IA via l'outil MCP (`change_note_type`)** :
   - L'outil MCP attendait des arguments rigides sérialisés en chaînes JSON (`note_ids_json: str`, `mapping_champs_json: str`), provoquant des rejets de format fréquents par les modèles de langage.
   - L'outil n'offrait aucun diagnostic ni auto-complétion si l'agent IA omettait des champs ou se trompait sur les noms de champs cibles/sources.
   - Le patch intermédiaire (`StagedPatch`) ne contenait aucun diff visuel compréhensible montrant l'état avant/après d'une note échantillon.
4. **Discordance avec les types à texte à trous (*Cloze*)** :
   - Les particularités des modèles Cloze (multiplication dynamique des cartes selon le nombre d'occlusions `{{c1::...}}`, `{{c2::...}}`) n'étaient pas prises en compte lors des bascules depuis ou vers un modèle standard.

---

## 2. Décisions Architecturales

### A. Cycle de Vie et Synchronisation Déterministe des Cartes Physiques

Lors d'une migration de type de note :
1. **Remappage explicite des gabarits (`template_mapping`)** :
   - Une table de correspondance associe chaque gabarit source existant à un gabarit cible (ex: `0 -> 0`, `1 -> 1`, ou `1 -> None`).
   - Pour chaque carte physique existante liée à un gabarit cible valide : son `template_index` est mis à jour et l'ensemble de ses statistiques SRS FSRS (`ivl`, `reps`, `lapses`, `stability`, `difficulty`, `retrievability`, `flags`, `is_suspended`) est intégralement préservé.
   - Pour les cartes physiques surnuméraires (pointant vers un gabarit source non réassigné ou absent du modèle cible) : la carte physique est supprimée de façon transactionnelle dans la base SQLite, en stricte conformité avec le comportement officiel d'Anki.
2. **Génération conditionnelle des nouveaux gabarits** :
   - Pour tout gabarit cible qui n'était pas couvert par une ancienne carte physique : le moteur évalue la règle de génération conditionnelle Anki ([`should_generate_card`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/cards/note_manager.py)). Si le recto généré n'est pas vide, une nouvelle carte physique [`CardModel`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/database/models/cards.py) est créée pour cette note dans le paquet d'origine.
3. **Atomicité globale** :
   - La migration du lot complet de notes et de l'ensemble de leurs cartes physiques s'exécute dans une transaction SQLite unique [`db.atomic()`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/database/base.py) : tout ou rien.

### B. Dialogue Interactif Modal de Migration (`ChangeNoteTypeDialog`)

Dans l'interface utilisateur PySide6 :
1. **Support unitaire et par lot via triple accès ergonomique** :
   - L'action est déclenchable depuis trois points de contact unifiés dans la vue d'Édition :
     1. Menu contextuel au clic droit sur le tableau (`VirtualTableView`) : action `Changer le type de note...` agissant sur la note ciblée ou la sélection multiple.
     2. Bouton d'action de lot dans la barre d'outils supérieure lorsqu'au moins une note/carte est cochée.
     3. Bouton/sélecteur de type dans le panneau d'inspection et d'édition de note latéral droit.
2. **Architecture du dialogue (`ChangeNoteTypeDialog`)** :
   - **Étape 1 : Choix du type de note cible** avec affichage du nombre de champs et de gabarits.
   - **Étape 2 : Table de correspondance des champs (Field Mapping Table)** :
     - Colonne Source (champs actuels avec indicateur de présence de données).
     - Colonne Cible (liste déroulante des champs du modèle cible + option `(Ignorer / Supprimer)`).
     - Algorithme de pré-remplissage heuristique intelligent :
       1. Correspondance exacte insensible à la casse et sans accents.
       2. Synonymes métier courants (`Question/Recto/Front`, `Réponse/Verso/Back`, `Remarques/Extra/Notes`).
       3. Alignement positionnel de repli.
   - **Étape 3 : Table de correspondance des gabarits (Template Mapping Table)** :
     - Visualisation des gabarits source et cible, avec indication claire des cartes qui seront conservées, créées ou supprimées.
   - **Étape 4 : Prévisualisation en direct (Live Preview)** :
     - Affiche le rendu avant / après sur la première note sélectionnée avec mise en valeur des champs modifiés ou ignorés.

### C. Robustesse et Tolérance de l'Outil MCP (`change_note_type`)

Pour éliminer les erreurs et hallucinations des agents LLM :
1. **Arguments souples et polymorphes** :
   - `note_ids` accepte indifféremment une liste Python d'entiers (`list[int]`), une liste JSON, ou une chaîne d'identifiants séparés par des virgules.
   - `mapping_champs` accepte indifféremment un dictionnaire Python (`dict[str, str]`), une chaîne JSON ou une structure simplifiée.
2. **Validation pré-vol fail-fast et assistance au diagnostic** :
   - Si des noms de champs cibles spécifiés par l'IA n'existent pas dans le modèle cible : l'outil ne plante pas silencieusement mais retourne une erreur explicite listant les champs cibles valides disponibles et propose une suggestion de mapping corrigée.
   - Si `mapping_champs` est omis ou partiel : l'outil tente une auto-résolution intelligente (nom exact > synonymes métier > ordre positionnel). Si toutefois des champs sources non vides risquent d'être ignorés/perdus sans consigne explicite, ou si l'ambiguïté est totale, l'outil rejette immédiatement la demande avec le statut `error` en renvoyant le schéma détaillé des champs sources et cibles pour forcer l'agent LLM à clarifier son intention.
3. **Payload enrichi dans le StagedPatch (Two-Phase Commit)** :
   - Le patch staged enregistre le diff textuel complet d'un échantillon (note témoin avec ses champs d'origine et ses nouveaux champs mappés), ainsi que le décompte précis des cartes conservées, créées et supprimées.
   - L'utilisateur humain visualisant le patch dans l'interface ou le consultant MCP peut constater visuellement le résultat avant d'approuver.

### D. Gestion Native des Modèles à Texte à Trous (*Cloze*)

1. **Migration vers un type Cloze** :
   - Vérification que le champ cible destiné à recevoir le texte contient au moins une occlusion au format `{{c1::...}}`. Si aucune occlusion n'est détectée, un avertissement explicite est remonté à l'utilisateur ou à l'agent.
   - Génération dynamique des cartes physiques d'indices `0` à `max(c_k) - 1` correspondant aux numéros d'occlusion trouvés.
2. **Migration depuis un type Cloze vers Standard** :
   - Possibilité d'assainir le texte en supprimant les marqueurs `{{c1::texte::indice}}` -> `texte` lors du transfert vers un champ standard pour éviter d'afficher des balises brutes inesthétiques.

---

## 3. Conséquences & Impacts

- **Intégrité de la collection** : Élimination définitive des cartes orphelines aux gabarits corrompus lors des conversions de types de notes.
- **Continuité des statistiques SRS** : Les révisions, lapses et métriques FSRS ne sont plus perdus ni mis à zéro lorsqu'une carte change de type de note.
- **Fiabilité agentique MCP** : Les modèles de langage peuvent manipuler et restructurer les types de notes sans risquer de corrompre la base de données SQLite ni d'échouer sur des erreurs de typage ou de sérialisation JSON.
- **Conformité Anki standard** : Comportement rigoureusement équivalent au menu *Change Note Type* officiel du logiciel Anki.

# 40. Normalisation syntaxique stricte, autocomplétion riche et gestionnaire unifié de taxonomie de tags

Date: 2026-10-25

## Statut

Accepté (Issu du cadrage `/grill-with-docs`)

## Contexte

Les étiquettes (tags) dans AnkiForge remplissent une double fonction :
1. Une organisation taxonomique et thématique définie par l'utilisateur (pouvant exploiter la hiérarchie `::`).
2. Une traçabilité documentaire fine générée par le pipeline d'ingestion et Smart Coverage (`doc:`, `source:`, `section:`, `page:`, `chunk:` selon l'ADR 0009 et l'ADR 0039).

Malgré les apports de l'ADR 0039 (portée descendante par paquet, masquage par défaut de la provenance dans `TagSelectWindow`, suppression du bridage SQL), l'écosystème de gestion des tags souffrait encore de disparités et de manques structurants :
- **Permissivité syntaxique sur les espaces** : historiquement, l'éditeur autorisait la saisie de tags contenant des espaces (stockés dans un tableau JSON `["médecine générale"]`), alors que la syntaxe officielle d'Anki interdit formellement les espaces au sein d'un tag individuel (les espaces servant de séparateur de tags). Cette divergence provoquait des scissions inattendues lors de l'export en `.apkg`.
- **Expérience de saisie incomplète** : le widget de saisie dans l'éditeur de notes (`NoteTagsEditorWidget`) et l'édition groupée (`GroupEditDialog`) ne proposaient aucune autocomplétion inline, obligeant l'utilisateur à taper le tag de mémoire ou à interrompre son flux pour ouvrir le sélecteur modal.
- **Absence d'un gestionnaire de taxonomie complet** : aucune interface ne permettait d'administrer l'arborescence des tags à l'échelle de la collection (renommer une branche parent avec propagation, fusionner deux étiquettes, supprimer un tag obsolète sur l'ensemble des notes, ou auditer les anomalies de casse et d'espaces).
- **Vulnérabilité de la traçabilité documentaire** : nécessité d'encadrer rigoureusement toute mutation globale pouvant altérer ou supprimer par mégarde les tags de provenance garantissant le calcul de couverture RAG.

## Décision

### 1. Normalisation syntaxique stricte (Alignement Anki) & Saisie réactive

- **Interdiction des espaces dans les tags individuels** :
  - À la frappe dans le champ de saisie, l'appui sur la barre d'espace valide immédiatement le tag en cours et initialise la saisie du tag suivant (comportement identique au navigateur de cartes Anki).
  - En cas de collage (*paste*) d'une chaîne contenant des espaces, les espaces internes sont automatiquement convertis en tirets bas (`_`) afin de préserver l'intention sémantique sans violer la règle Anki.
- **Préservation du stockage interne JSON canonique** :
  - La colonne `NoteModel.tags` conserve son format JSON canonique `["tag1", "tag2"]`, assurant la cohérence avec Peewee ORM et éliminant tout risque d'injection ou d'ambiguïté de découpage.
  - La conformité stricte sans espaces garantit que la sérialisation vers le format d'export Anki (`" tag1 tag2 "`) s'effectue de manière 100% bijective et prédictible.

### 2. Autocomplétion inline riche (Style IDE) avec Tag Scope

- **Composant popover contextuel** :
  - Déploiement d'un menu d'autocomplétion riche sous les champs de saisie de tags (`NoteTagsEditorWidget`, `GroupEditDialog`).
  - Surlignage dynamique des correspondances de recherche, décomposition visuelle des segments hiérarchiques (`::`) et affichage du compteur de notes associées.
  - Navigation fluide au clavier (flèches haut/bas, validation par `Tab` ou `Entrée`, touche `Échap` pour fermer).
- **Filtrage strict par portée contextuelle (Tag Scope)** :
  - Si un paquet est sélectionné dans la barre latérale, l'autocomplétion est strictement restreinte aux tags portés par les notes du paquet actif et de ses sous-paquets descendants.
  - Si aucun paquet n'est sélectionné, l'autocomplétion exploite l'intégralité du catalogue du profil actif.

### 3. Gestionnaire unifié de taxonomie (`Taxonomy Manager`)

- **Extension de `TagSelectWindow`** :
  - `TagSelectWindow` devient un composant unifié bi-mode : mode sélection simple (pour insertion dans les formulaires) et mode administration complète de la taxonomie (accessible via `Outils > Gestionnaire de tags (Taxonomie)` et par raccourci clavier).
- **Opérations taxonomiques avancées** :
  - **Renommage hiérarchique avec propagation contrôlée** : renommer un nœud `A::B` propose un dialogue interactif avec case cochée par défaut « Propager à toute la sous-arborescence (X sous-tags, Y notes) », permettant soit de renommer toute la branche (`A::B::*` -> `A::Nouveau::*`), soit de renommer uniquement le nœud local.
  - **Fusion de tags** : fusionner deux tags ou grappes via une transaction atomique SQLite, s'appuyant sur l'infrastructure éprouvée de `BulkHygieneService.apply_tag_merges()`.
  - **Suppression globale** : retrait d'un tag sur toutes les notes concernées avec dialogue récapitulatif du nombre de notes impactées.
- **Garde-fou critique pour les tags de provenance** :
  - Les tags de traçabilité documentaire (`doc:`, `source:`, `section:`, `page:`) ne peuvent pas être renommés, fusionnés ou supprimés silencieusement.
  - Toute action touchant à un tag de provenance déclenche un dialogue d'avertissement critique de niveau 2 explicitant la déliaison de couverture RAG et imposant une confirmation délibérée.

### 4. Audit de conformité et réparation assistée des tags historiques

- **Module d'audit de taxonomie** :
  - Analyse complète de la base SQLite pour détecter les anomalies héritées : tags contenant des espaces (legacy), doublons de casse (`Anatomie` vs `anatomie`), séparateurs `::` malformés ou segments vides.
- **Réparation assistée par grappe** :
  - Pour les tags legacy contenant des espaces, l'audit propose un choix assisté avant validation : substitution par tiret bas (`médecine_générale`) ou scission en plusieurs tags (`médecine` et `générale`).
  - L'application des corrections est strictement atomique sous `db.atomic()`, avec prévisualisation des notes et diff avant engagement définitif.

## Conséquences

### Positives
- **Compatibilité totale avec l'écosystème Anki** : élimination définitive de toute divergence syntaxique (espaces résiduels) lors des imports/exports `.apkg`.
- **Productivité d'édition accrue** : l'autocomplétion inline riche permet d'étiqueter les cartes à grande vitesse sans quitter le clavier ni mémoriser l'arborescence exacte.
- **Cohérence taxonomique garantie** : l'utilisateur dispose d'un outil central pour assainir, renommer et fusionner sa taxonomie sans passer par des requêtes manuelles ni risquer de corrompre les liens de provenance documentaire.
- **Sécurité et intégrité des données** : toutes les opérations multi-notes demeurent transactionnelles avec annulation automatique en cas d'erreur.

### Neutres / Points de vigilance
- **Performance de l'autocomplétion sur grandes bases** : le catalogue des tags du scope doit être mis en cache ou interrogé via des requêtes SQLite optimisées (`get_tags_for_scope`) pour éviter tout lag perceptible lors de la frappe.

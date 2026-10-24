# 39. Sélecteur de tags à portée hiérarchique, sanctuarisation de la provenance et harmonisation d'édition

Date: 2026-10-24

## Statut

Accepté (Issu du cadrage `/grill-with-docs`)

## Contexte

Dans la vue Édition et Navigateur de cartes (`EditionView`), le modal de filtrage par tag (`_show_tag_modal` ouvrant `TagSelectWindow`) présentait une anomalie majeure : l'ensemble des tags de la collection n'était pas affiché.

L'analyse de la cause racine dans le code source a mis en évidence plusieurs anomalies techniques et ergonomiques :

1. **Troncation arbitraire de la requête SQLite** :
   La méthode `EditionView._show_tag_modal()` exécutait une requête Peewee bridée par `.limit(500)`. Sur toute collection dépassant 500 notes, les tags portés par les notes au-delà de ce seuil étaient silencieusement ignorés.
2. **Divergence de désérialisation des tags** :
   Le chargement utilisait un `json.loads(str(note.tags))` ad-hoc ignorant les tags stockés sous forme de chaînes délimitées par des espaces (format standard Anki brut) et contournant la fonction canonique `parse_note_tags()` de `ankiforge.utils.tags`. De même, `TagSelectWindow._load_tags()` appliquait un parsing JSON strict vulnérable aux formats legacy.
3. **Absence de portée contextuelle par paquet** :
   L'ouverture du modal scannait la base globale (jusqu'à 500) sans tenir compte du paquet sélectionné dans la barre latérale, obligeant l'utilisateur à parcourir des tags non pertinents pour le deck en cours d'exploration.
4. **Pollution par les tags de traçabilité documentaire** :
   Les métadonnées techniques générées par le pipeline d'ingestion et Smart Coverage (`doc:`, `source:`, `section:`, `page:`, `chunk:`, ADR 0009) polluaient l'arborescence taxonomique au détriment des étiquettes sémantiques de révision.
5. **Fragmentation de l'expérience d'édition de tags** :
   Alors que le filtre de l'Édition disposait d'un sélecteur modal, la boîte d'Édition groupée (`GroupEditDialog`) et l'éditeur inline de note (`NoteTagsEditorWidget`) ne proposaient que des champs texte libres sans arborescence ni complétion des tags existants.

## Décision

### 1. Extraction exhaustive et portée contextuelle descendante (`Tag Scope`)

- **Suppression définitive de toute limite arbitraire** : élimination du `.limit(500)` dans `EditionView._show_tag_modal()`.
- **Couture de données canonique sur `NoteRepository`** :
  Ajout de la méthode `get_tags_for_scope(deck_id: int | None = None, include_descendants: bool = True) -> list[str]`.
  - Si un paquet est actif (`deck_id is not None`) : la requête restreint la recherche aux cartes rattachées au paquet et à tous ses sous-paquets descendants (`descendants_prefix(deck.name)`).
  - Si aucun paquet n'est sélectionné (`deck_id is None`) : extraction de 100% des tags uniques sur l'intégralité de la collection.
- **Normalisation canonique** : recours systématique à `parse_note_tags()` pour garantir la prise en charge transparente des tableaux JSON et des formats délimités par des espaces.

### 2. Sanctuarisation et bascule des tags de traçabilité documentaire

- Dans `TagSelectWindow`, les tags identifiés par `is_provenance_tag()` sont masqués par défaut afin de présenter une arborescence purement conceptuelle et sémantique.
- Une case à cocher explicite (« Afficher les tags de traçabilité ») est introduite dans l'en-tête du sélecteur pour permettre à l'utilisateur d'inspecter et de filtrer sur les tags techniques de provenance lorsqu'il le désire.

### 3. Harmonisation globale de l'expérience d'édition

Le sélecteur `TagSelectWindow` est généralisé comme composant d'assistance pour l'ensemble des flux de manipulation de tags :
- **Filtre de vue (`EditionView`)** : sélection d'un tag pour ajout immédiat à la barre de filtres (`_active_tags`).
- **Édition groupée (`GroupEditDialog`)** : ajout d'un bouton icône à côté des champs « Ajouter des tags » et « Retirer des tags » ouvrant `TagSelectWindow` avec insertion non destructive dans le champ de saisie libre.
- **Éditeur de carte active (`NoteTagsEditorWidget`)** : ajout d'un bouton d'arborescence ouvrant `TagSelectWindow` pour insérer un tag existant directement dans la liste des puces de la note.

## Conséquences

### Positives
- **Exhaustivité garantie** : 100% des tags d'une collection ou d'un paquet sont accessibles, quelle que soit la volumétrie.
- **Pertinence contextuelle** : l'utilisateur explore en priorité les tags pertinents pour le dossier ou le paquet dans lequel il travaille.
- **Clarté visuelle** : les tags techniques de traçabilité ne submergent plus les listes de révision par défaut.
- **Cohérence d'interface** : l'utilisateur dispose d'un outil unique et familier pour choisir un tag partout dans AnkiForge.

### Neutres / Points de vigilance
- Sur des collections massives (ex. 50 000+ cartes), la requête de collecte des tags doit cibler uniquement les colonnes nécessaires (`NoteModel.tags` et `CardModel.deck_id`) pour éviter toute instanciation coûteuse de modèles en mémoire.

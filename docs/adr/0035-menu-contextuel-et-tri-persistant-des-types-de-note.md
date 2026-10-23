# 35. Menu contextuel et tri persistant des types de note

Date: 2026-10-23

## Statut

Accepté

## Contexte

Dans AnkiForge, les types de note (modélisés par `NoteTypeModel`) constituent la clé de voûte de la génération et de la mise en page des cartes Anki.
Jusqu'alors :
1. La liste des types de note dans `CardModelsView` (volet latéral gauche) et dans le sélecteur modal `ModelSelectWindow` était affichée dans un ordre statique (sélection brute ou ordre alphabétique figé).
2. Aucun menu contextuel (clic droit) n'était disponible pour agir directement sur un élément ciblé.
3. Des opérations essentielles du cycle de vie d'un type de note manquaient à l'appel :
   - Impossible de renommer un type de note depuis l'interface sans modification directe en base de données SQLite.
   - Impossible de désigner un type de note par défaut pour les futures générations/créations de cartes.
   - Aucun pont direct pour naviguer depuis un type de note vers la vue Édition pré-filtrée sur les notes utilisant ce type.

## Décision

### 1. Menu contextuel unifié sur les types de note

Un menu contextuel `QMenu` (activé via `Qt.ContextMenuPolicy.CustomContextMenu` et `customContextMenuRequested`) est implémenté sur la liste des types de note dans `CardModelsView` ainsi que dans le dialogue modal `ModelSelectWindow`.

Ce menu propose les actions suivantes :
- **Renommer** : ouvre une boîte modale `QInputDialog` avec validation immédiate d'unicité et de non-vacuité, mettant à jour `NoteTypeModel.name` et actualisant l'arborescence/liste en temps réel.
- **Dupliquer** : duplique le type de note courant (`_on_duplicate_model`) avec suffixe incrémenté `(Copie N)`.
- **Définir comme modèle par défaut** : enregistre l'ID du modèle dans les réglages du profil (`card_models/default_note_type_id`) et actualise l'indicateur visuel.
- **Exporter (.afmodel / JSON)** : déclenche `ModelExportDialog` pour partager ou sauvegarder la définition complète du modèle.
- **Filtrer les notes associées** : émet une demande de navigation vers la vue Édition (`request_navigation.emit("edition", {"note_type_id": model.id, "note_type_name": model.name})`), pré-activant le filtre de modèle.
- **Séparateur**
- **Supprimer** : avec confirmation et respect de la contrainte `RESTRICT` (interdiction si des notes actives utilisent ce type de note).

### 2. Tri paramétrable et persistant par profil

Un bouton dédié avec icône de tri (`ph.sort-ascending`) est ajouté à côté du champ de recherche dans `CardModelsView` et `ModelSelectWindow`. Les mêmes critères de tri sont également accessibles via un sous-menu « Trier par... » dans le menu contextuel du clic droit.

Les cinq critères canoniques supportés sont :
1. **Nom (A → Z)** (`name_asc`)
2. **Nom (Z → A)** (`name_desc`)
3. **Date de création (Plus récents)** (`created_desc`)
4. **Date de création (Plus anciens)** (`created_asc`)
5. **Nombre de gabarits / cartes** (`template_count_desc`)

Le critère choisi est persisté immédiatement via `SettingsService.set("card_models/sort_order", ...)` et restauré au démarrage ou lors du rafraîchissement de la vue.

### 3. Matérialisation visuelle du modèle par défaut

Le type de note désigné comme modèle par défaut est distingué visuellement dans la liste par un indicateur explicite (badge textuel ou étoile dorée `★ Par défaut`), permettant à l'utilisateur d'identifier immédiatement son gabarit de référence.

## Conséquences

- Expérience utilisateur cohérente avec les standards de bureau (clic droit contextuel, découverte intuitive des actions).
- Possibilité de renommer un modèle de façon sûre sans rupture référentielle.
- Navigation fluide et bidirectionnelle entre la gestion des modèles de cartes et l'édition des notes.
- Conservation de l'ordre de tri préféré par profil utilisateur entre chaque session.

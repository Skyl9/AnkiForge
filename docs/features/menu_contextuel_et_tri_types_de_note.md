# Spécification Technique — Menu Contextuel et Tri Persistant des Types de Note

**Référence architecture :** [ADR 0035](../adr/0035-menu-contextuel-et-tri-persistant-des-types-de-note.md)  
**Domaine :** [CONTEXT.md](../../CONTEXT.md)  
**Date :** 2026-10-23  
**Statut :** Validé pour découpage en tickets

---

## Problématique (Problem Statement)

Dans AnkiForge, les types de note ([`NoteTypeModel`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/database/models/cards.py#L37-L46)) gouvernent la structure des champs et les gabarits de rendu des cartes Anki.
Cependant, l'expérience utilisateur souffre actuellement de plusieurs limitations majeures :
1. **Absence d'interactions contextuelles (clic droit)** : dans le volet latéral de la vue Modèles de cartes ([`CardModelsView`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/views/card_models_view/view.py)) et dans le sélecteur modal ([`ModelSelectWindow`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components/model_select_window.py)), le clic droit est inopérant. L'utilisateur doit naviguer entre les boutons du bas de panneau ou n'a aucun moyen d'accéder aux actions élémentaires sur un type de note ciblé.
2. **Impossibilité de renommer** : il n'existe aucune commande ni dialogue permettant de renommer un type de note existant sans passer par une modification directe manuelle de la base de données SQLite.
3. **Ordre statique non configurable** : les types de note sont présentés dans un ordre figé (ordre d'insertion ou nom A-Z en dur), sans possibilité d'inverser l'ordre, de trier par date d'ajout ou par complexité (nombre de cartes).
4. **Absence de désignation d'un modèle par défaut** : impossible d'indiquer quel type de note doit être pré-sélectionné lors de la création de nouvelles cartes ou dans les flux d'extraction par lot.
5. **Rupture de navigation vers les notes** : impossible de basculer en un clic depuis un type de note vers la vue Édition pour inspecter les notes qui l'utilisent.

---

## Solution proposée

Mettre en place un dispositif complet et homogène de gestion contextuelle et d'ordonnancement pour les types de note, déployé à la fois sur la vue dédiée [`CardModelsView`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/views/card_models_view/view.py) et sur la fenêtre modale [`ModelSelectWindow`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components/model_select_window.py) :
- **Menu contextuel (clic droit)** riche et standardisé : *Renommer*, *Dupliquer*, *Définir par défaut*, *Exporter (.afmodel / JSON)*, *Filtrer les notes associées (vers Vue Édition)*, et *Supprimer* (avec protection `RESTRICT`).
- **Moteur de tri à 5 critères canoniques** (`name_asc`, `name_desc`, `created_desc`, `created_asc`, `template_count_desc`), accessible via un bouton dédié d'en-tête et un sous-menu contextuel, persisté par profil utilisateur via [`SettingsService`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/settings_service.py).
- **Indicateur visuel de modèle par défaut** : matérialisation claire par badge ou étoile dorée (`★ Par défaut`).
- **Passerelle de navigation fluide** : signal de bascule vers [`EditionView`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/views/edition_view/view.py) avec filtre pré-positionné.

---

## User Stories (Extensives)

1. **US1 — Clic droit et menu contextuel dans la vue Modèles**  
   *En tant qu'utilisateur*, je veux faire un clic droit sur un type de note dans la liste latérale de la vue Modèles de cartes,  
   *afin d'accéder* immédiatement à l'ensemble des actions disponibles sur ce type de note sans chercher dans les boutons inférieurs.

2. **US2 — Renommage sécurisé d'un type de note**  
   *En tant qu'utilisateur*, je veux pouvoir renommer un type de note via une boîte de dialogue modale avec validation d'unicité,  
   *afin de corriger* une faute de frappe ou clarifier sa dénomination sans altérer les notes et cartes qui lui sont déjà rattachées.

3. **US3 — Tri personnalisé et persistant**  
   *En tant qu'utilisateur*, je veux pouvoir choisir mon critère d'ordonnancement (alphabétique direct/inverse, date de création, nombre de gabarits) via un bouton dédié ou le menu contextuel,  
   *afin de retrouver* rapidement mes types de note les plus récents ou les plus structurés, et retrouver ce même ordre lors de mes prochaines sessions.

4. **US4 — Définition et mise en valeur du type de note par défaut**  
   *En tant qu'utilisateur*, je veux désigner un type de note comme modèle par défaut et le repérer visuellement avec une étoile ou un badge,  
   *afin de savoir* quel gabarit sera utilisé en priorité lors de mes créations de cartes ou de mes générations automatiques.

5. **US5 — Filtrage direct des notes associées (navigation vers Édition)**  
   *En tant qu'utilisateur*, je veux cliquer sur « Filtrer les notes utilisant ce type » dans le menu contextuel,  
   *afin d'être basculé* instantanément dans la vue Édition avec le filtre pré-positionné sur ce type de note.

6. **US6 — Parité d'expérience dans la modale de sélection (`ModelSelectWindow`)**  
   *En tant qu'utilisateur*, je veux bénéficier du même menu contextuel et des mêmes fonctionnalités de tri lorsque j'ouvre la fenêtre modale de sélection de type de note depuis d'autres vues,  
   *afin de disposer* d'une interface prévisible et cohérente dans toute l'application.

---

## Décisions d'Implémentation

### 1. Modules et interfaces touchés

- [`src/ankiforge/ui/views/card_models_view/view.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/views/card_models_view/view.py) :
  - `self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)`
  - Connexion du signal `self.list_widget.customContextMenuRequested` au slot `_on_models_list_context_menu(pos: QPoint)`.
  - Construction du menu `QMenu` :
    - Action « Renommer » → appelle `_on_rename_model(model)`
    - Action « Dupliquer » → appelle `_on_duplicate_model()` (existant)
    - Action « Définir comme modèle par défaut » → appelle `_on_set_default_model(model)`
    - Action « Exporter (.afmodel / JSON) » → appelle `_on_export_json()` (existant)
    - Action « Filtrer les notes associées » → appelle `_on_filter_notes_by_model(model)`
    - Séparateur
    - Action « Supprimer » → appelle `_on_delete_model()` (existant)
    - Sous-menu « Trier par… » avec les 5 critères cochables.
  - Ajout d'un bouton de tri `self.btn_sort_models` (icône `ph.sort-ascending`, 28px) dans le bandeau de recherche (`search_row`).
  - Déclaration du signal de navigation : `request_navigation = Signal(str, object)`.

- [`src/ankiforge/ui/components/model_select_window.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components/model_select_window.py) :
  - `self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)`
  - Connexion de `customContextMenuRequested` au slot `_on_tree_context_menu(pos: QPoint)`.
  - Exclusion du menu sur le nœud racine `Tous les types de note` (id -1).
  - Ajout du bouton de tri à côté du champ de recherche `search_input`.
  - Intégration des actions Renommer, Dupliquer, Définir par défaut, Exporter, Supprimer, avec réactualisation de la fenêtre via `_load_models()`.

- [`src/ankiforge/ui/main_window.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/main_window.py) :
  - Dans `_on_view_selected` (ligne 880), traitement du filtre de modèle lors de la bascule vers `edition` :
    ```python
    if view_id == "edition" and isinstance(data, dict):
        if "note_id" in data and hasattr(widget, "select_note_by_id"):
            cast(Any, widget).select_note_by_id(data["note_id"])
        if "note_type_id" in data and hasattr(widget, "_on_model_selected"):
            cast(Any, widget)._on_model_selected(data["note_type_id"], data.get("note_type_name", ""))
    ```

- [`src/ankiforge/services/settings_service.py`](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/services/settings_service.py) :
  - Utilisation des clés persistantes :
    - `card_models/sort_order` (défaut : `"name_asc"`)
    - `card_models/default_note_type_id` (défaut : `None`)

### 2. Schéma de base de données & Migrations

- **Aucune migration DDL SQLite requise** :
  - `SettingModel` prend en charge nativement les paires clé-valeur de réglages par profil.
  - `NoteTypeModel.name` est déjà une colonne `CharField(unique=True)`.
  - `NoteModel.note_type` est protégé par `RESTRICT` en base (migration 037).

### 3. Contrats d'API et flux d'état

- **Logique de tri** :
  Fonction canonique `sort_note_types(models: list[NoteTypeModel], sort_order: str) -> list[NoteTypeModel]` :
  - `"name_asc"` : `sorted(models, key=lambda m: m.name.lower())`
  - `"name_desc"` : `sorted(models, key=lambda m: m.name.lower(), reverse=True)`
  - `"created_desc"` : `sorted(models, key=lambda m: m.id, reverse=True)`
  - `"created_asc"` : `sorted(models, key=lambda m: m.id)`
  - `"template_count_desc"` : tri par nombre de gabarits dans `json.loads(m.templates)` (décroissant), repli sur le nom.

- **Flux de renommage** :
  1. `QInputDialog.getText` avec le nom courant pré-rempli.
  2. Validation : non vide, distinct de l'actuel, non existant en BDD (`NoteTypeModel.get_or_none(name == new_name)`).
  3. En cas de collision : message d'avertissement `QMessageBox.warning` explicite.
  4. En cas de succès : `model.name = new_name; model.save()`, rechargement de la liste et sélection de l'élément renommé.

---

## Décisions de Test

### 1. Tests Unitaires & Intégration BDD (`tests/unit/`, `tests/integration/`)
- `test_note_type_sorting_logic` : test algorithmique pur validant les 5 critères de tri sur un jeu de `NoteTypeModel`.
- `test_rename_note_type_success_and_collision` : vérification de la mise à jour en BDD Peewee et du blocage en cas de doublon.
- `test_settings_service_persistence` : persistance et relecture des clés `card_models/sort_order` et `card_models/default_note_type_id`.

### 2. Tests Headless PySide6 (`pytest-qt`, `tests/ui/`)
- `test_card_models_view_context_menu_actions` : instanciation headless de `CardModelsView`, émission de `customContextMenuRequested`, vérification de la présence et de l'état des actions du menu.
- `test_card_models_view_sort_button_and_reorder` : clic sur les options du menu de tri et vérification de l'ordre résultant dans `self.list_widget`.
- `test_card_models_view_rename_dialog` : simulation d'un renommage valide et vérification de la mise à jour dans `list_widget` et `lbl_editor_title`.
- `test_card_models_view_filter_navigation_signal` : émission de l'action « Filtrer les notes associées » et vérification du signal `request_navigation` avec le payload `{"note_type_id": ..., "note_type_name": ...}`.
- `test_model_select_window_context_menu_and_sort` : validation des mêmes comportements dans `ModelSelectWindow`.

---

## Hors Périmètre (Out of Scope)

- **Réordonnancement manuel arbitraire par glisser-déposer (Drag & Drop)** : exclu conformément à la décision de conception (tri basé sur 5 critères logiques persistés dans les réglages).
- **Modification de la structure des champs ou des templates depuis le menu contextuel** : les gabarits et champs continuent d'être édités dans l'éditeur central.
- **Fusion ou migration massive de notes entre types de note** : cette opération relève des outils de nettoyage avancé et fera l'objet d'un chantier séparé.

# Spécification Technique — Table de Référence pour Drapeaux Anki Flags (0-7)

## Problématique (Problem Statement)

Actuellement, le champ `CardModel.flags` (IntegerField, valeurs 0-7) stocke uniquement la valeur numérique du drapeau Anki. Les libellés (noms) et couleurs des drapeaux sont gérés exclusivement via `FlagService` qui les persiste dans les paramètres du profil (`SettingsService` avec clé `anki/flag_labels`) via des dictionnaires Python en dur (`DEFAULT_FLAG_NAMES`, `DEFAULT_FLAG_COLORS`, `DEFAULT_FLAG_SEARCH_MAP`).

Cette architecture pose plusieurs problèmes :
- **Pas d'intégrité référentielle** : tout entier 0-255 est techniquement acceptable en base
- **Pas de jointure SQL native** : impossible de récupérer le libellé/couleur d'un drapeau sans passer par le service Python
- **Requêtes inefficaces** : impossible de requêter « toutes les cartes avec le drapeau 'Rouge' » en SQL pur
- **Pas de versionning** : les migrations futures ne peuvent pas versionner l'évolution des définitions de drapeaux
- **Couplage fort** : `FlagService`, `DesignTokens`, `NoteTableModel`, `FlagItemDelegate`, `EditionView` dupliquent tous les définitions

## Solution proposée

Introduire un **modèle de référence `FlagDefinitionModel`** en base de données qui définit canoniquement les 8 drapeaux Anki (0-7) avec leurs libellés natifs et couleurs, complété par une **table de liaison `ProfileFlagLabelModel`** pour la personnalisation par profil utilisateur.

Architecture cible :
```
FlagDefinitionModel (8 lignes canoniques, immuables)
    ↑ FK (value)
CardModel.flags

ProfileFlagLabelModel (personnalisations utilisateur)
    ↑ FK (profile_id, flag_definition_id)
    → custom_label
```

## User Stories (Extensives)

1. **En tant que développeur**, je veux une ForeignKey sur `CardModel.flags` vers `FlagDefinitionModel`, afin de garantir l'intégrité référentielle au niveau base de données.

2. **En tant que développeur**, je veux pouvoir faire une jointure SQL `JOIN flag_definition ON card.flags = flag_definition.value`, afin de récupérer libellé et couleur en une requête sans passer par Python.

3. **En tant qu'utilisateur**, je veux personnaliser le libellé du drapeau "Rouge" en "Urgent" pour mon profil, afin que l'interface affiche mon terme métier.

4. **En tant qu'utilisateur**, je veux que la réinitialisation d'un libellé personnalisé revienne au nom natif Anki, afin de ne pas perdre la sémantique d'origine.

5. **En tant que développeur**, je veux que les migrations Peewee versionnent l'évolution des définitions de drapeaux, afin de tracer les changements de schéma.

## Décisions d'Implémentation

### 1. Nouveaux Modèles Peewee (`src/ankiforge/database/models/flags.py` — nouveau fichier)

```python
class FlagDefinitionModel(BaseModel):
    """Définition canonique des 8 drapeaux Anki (0-7). Table de référence immuable."""

    value = IntegerField(unique=True, constraints=[Check("value BETWEEN 0 AND 7")])
    name = CharField()  # "Aucun", "Rouge", "Orange", "Vert", "Bleu", "Rose", "Turquoise", "Violet"
    color_hex = CharField()  # "#ef4444", "#f97316", "#10b981", "#3b82f6", "#ec4899", "#06b6d4", "#a855f7", "transparent"
    is_customizable = BooleanField(default=True)  # False pour value=0, True pour 1-7
    sort_order = IntegerField(default=0)  # Pour ordre d'affichage stable

    class Meta:
        table_name = "flag_definition"
        indexes = ((("value",), True),)  # Unique index sur value


class ProfileFlagLabelModel(BaseModel):
    """Libellé personnalisé d'un drapeau pour un profil utilisateur donné."""

    profile = ForeignKeyField("ProfileModel", backref="flag_labels", on_delete="CASCADE")
    flag_definition = ForeignKeyField(FlagDefinitionModel, backref="profile_labels", on_delete="CASCADE")
    custom_label = CharField(null=True)  # NULL = utilise le nom natif

    class Meta:
        table_name = "profile_flag_label"
        indexes = ((("profile", "flag_definition"), True),)  # Unique composite
```

### 2. Migration Peewee (`src/ankiforge/database/migrations/049_flag_definition_table.py`)

```python
"""Migration 049 : Table de référence FlagDefinitionModel + ProfileFlagLabelModel + FK sur CardModel."""


def migrate(migrator, database, fake=False, **kwargs):
    # 1. Créer FlagDefinitionModel
    migrator.create_model(FlagDefinitionModel)

    # 2. Pré-peupler les 8 drapeaux canoniques
    FlagDefinitionModel.insert_many(
        [
            {"value": 0, "name": "Aucun", "color_hex": "transparent", "is_customizable": False, "sort_order": 0},
            {"value": 1, "name": "Rouge", "color_hex": "#ef4444", "is_customizable": True, "sort_order": 1},
            {"value": 2, "name": "Orange", "color_hex": "#f97316", "is_customizable": True, "sort_order": 2},
            {"value": 3, "name": "Vert", "color_hex": "#10b981", "is_customizable": True, "sort_order": 3},
            {"value": 4, "name": "Bleu", "color_hex": "#3b82f6", "is_customizable": True, "sort_order": 4},
            {"value": 5, "name": "Rose", "color_hex": "#ec4899", "is_customizable": True, "sort_order": 5},
            {"value": 6, "name": "Turquoise", "color_hex": "#06b6d4", "is_customizable": True, "sort_order": 6},
            {"value": 7, "name": "Violet", "color_hex": "#a855f7", "is_customizable": True, "sort_order": 7},
        ]
    ).execute()

    # 3. Créer ProfileFlagLabelModel
    migrator.create_model(ProfileFlagLabelModel)

    # 4. Ajouter FK sur CardModel.flags → FlagDefinitionModel.value
    # Note: Peewee ne supporte pas FK vers champ non-PK natif, on utilise une contrainte CHECK + trigger
    # ou on ajoute une colonne flag_definition_id (FK) et on déprécie flags
    migrator.add_fields("cardmodel", flag_definition=ForeignKeyField(FlagDefinitionModel, field="value", backref="cards", null=True, on_delete="SET NULL"))
    # Backfill: UPDATE cardmodel SET flag_definition_id = (SELECT id FROM flag_definition WHERE value = cardmodel.flags)
    # Puis ajouter CHECK constraint: flags BETWEEN 0 AND 7

    # 5. Migrer les libellés personnalisés existants depuis SettingsService (JSON)
    # Lecture de anki/flag_labels par profil → INSERT dans profile_flag_label


def rollback(migrator, database, fake=False, **kwargs):
    migrator.remove_fields("cardmodel", "flag_definition")
    migrator.remove_model("profile_flag_label")
    migrator.remove_model("flag_definition")
```

### 3. Refactor `CardModel` (`src/ankiforge/database/models/cards.py`)

```python
# Remplacer:
flags = IntegerField(default=0)  # Drapeau Anki (0=Aucun, 1..7=Couleurs Anki)

# Par:
flags = IntegerField(default=0, constraints=[Check("flags BETWEEN 0 AND 7")])  # Gardé pour compat Anki import/export
flag_definition = ForeignKeyField("FlagDefinitionModel", field="value", backref="cards", null=True, on_delete="SET NULL")
```

### 4. Refactor `FlagService` (`src/ankiforge/services/cards/flag_service.py`)

- Supprimer `DEFAULT_FLAG_NAMES`, `DEFAULT_FLAG_COLORS`, `DEFAULT_FLAG_SEARCH_MAP`
- `get_flag_labels()` → jointure `FlagDefinitionModel` + `ProfileFlagLabelModel` (LEFT JOIN)
- `get_flag_name(flag_idx)` → `FlagDefinitionModel.get(value=flag_idx).name` + override profil
- `set_flag_labels()` → upsert dans `ProfileFlagLabelModel`
- `get_flag_search_map()` → construit dynamiquement depuis `FlagDefinitionModel` + overrides profil
- Émettre `FlagLabelsUpdatedEvent` inchangé

### 5. Mise à jour `DesignTokens` (`src/ankiforge/ui/theme.py`)

- `FLAG_COLORS`, `FLAG_NAMES`, `FLAG_SEARCH_MAP` → propriétés `@classmethod` qui délèguent à `FlagService`
- Ou chargement au démarrage via `FlagService.get_flag_labels()` et cache

### 6. Composants UI impactés

| Composant | Fichier | Changement |
|-----------|---------|------------|
| `FlagItemDelegate` | `src/ankiforge/ui/models/delegates.py` | Utilise `FlagService.get_flag_name()` + `FlagService.get_flag_color()` |
| `EditionView` (filtres, menus drapeaux) | `src/ankiforge/ui/views/edition_view/view.py` | Délégation à `FlagService` |
| `Omnibox` | `src/ankiforge/ui/widgets/omnibox.py` | Délégation à `FlagService` |
| `AnkiSyncTab` (paramètres drapeaux) | `src/ankiforge/ui/widgets/settings_modal/tabs/anki_sync_tab.py` | Lit/écrit via `FlagService` |
| `NoteTableModel` | `src/ankiforge/ui/models/note_table_model.py` | Jointure `flag_definition` dans requête préchargée |

### 7. Import/Export Anki (compatibilité)

- `CardModel.flags` (entier 0-7) conservé pour compatibilité `.apkg` / `.colpkg`
- `flag_definition` (FK) utilisé en interne pour jointures et UI
- Synchronisation bidirectionnelle : `flag_definition.value` ↔ `flags` via `@property` ou `save()` override

## Décisions de Test

### Tests Unitaires (`tests/unit/test_flag_definition.py`)
- Création/migration `FlagDefinitionModel` : 8 lignes, contraintes CHECK
- `ProfileFlagLabelModel` : CRUD, unicité composite, fallback natif
- `FlagService` : `get_flag_labels()`, `get_flag_name()`, `set_flag_labels()`, `reset_to_defaults()`, `get_flag_search_map()`
- Backfill migration : données SettingsService → `ProfileFlagLabelModel`

### Tests d'Intégration (`tests/integration/test_flags_integration.py`)
- Jointure SQL `CardModel` + `FlagDefinitionModel` : sélection cartes par drapeau
- Filtre UI par drapeau personnalisé
- Import `.apkg` : flags 0-7 → `CardModel.flags` + `flag_definition` cohérent
- Export `.apkg` : `CardModel.flags` préservé

### Tests Headless Qt (`tests/ui/test_flags_ui.py`)
- `FlagItemDelegate` : rendu visuel 8 drapeaux + état "aucun"
- Menu contextuel drapeaux dans `EditionView` : libellés personnalisés affichés
- Onglet "Drapeaux" dans `SettingsModal` : édition, sauvegarde, réinitialisation
- Raccourcis `Ctrl+0` à `Ctrl+7` : application drapeau correct

### Fixtures existantes
- `tests/conftest.py` : `db_memory`, `profile`, `note_type`, `deck`, `note`, `card`
- Ajouter `flag_definitions` (session scope) pré-peuplant la table

## Hors Périmètre (Out of Scope)

- **Modification des valeurs Anki natives** : les 8 drapeaux (0-7) et leurs couleurs hex sont figées par le format Anki
- **Drapeaux personnalisés au-delà de 7** : Anki ne supporte que 0-7
- **Interface de création de nouveaux drapeaux** : hors périmètre Anki
- **Synchronisation temps réel multi-instance** : géré par verrou de profil existant
- **Migration des données `FlagService` existantes** : couverte par la migration 049 (backfill JSON → table)

---

## ADRs Applicables

- **ADR 0009** : Provenance par section & Paliers de résolution — principe d'identité durable (ici : `value` canonique)
- **ADR 0013** : Internationalisation Qt Linguist — tous les libellés passent par `tr()`
- **ADR 0016** : Adaptateurs d'instructions unifiés — conformité `script/verify.py`

## Fichiers Cibles (Récapitulatif)

| Fichier | Action |
|---------|--------|
| `src/ankiforge/database/models/flags.py` | **Créer** — nouveaux modèles |
| `src/ankiforge/database/migrations/049_flag_definition_table.py` | **Créer** — migration + seed + backfill |
| `src/ankiforge/database/models/cards.py` | **Modifier** — ajouter `flag_definition` FK |
| `src/ankiforge/services/cards/flag_service.py` | **Refactor** — délégation vers modèles BDD |
| `src/ankiforge/ui/theme.py` | **Modifier** — `DesignTokens.FLAG_*` → `@classmethod` |
| `src/ankiforge/ui/models/delegates.py` | **Modifier** — `FlagItemDelegate` |
| `src/ankiforge/ui/views/edition_view/view.py` | **Modifier** — menus/filtres drapeaux |
| `src/ankiforge/ui/widgets/omnibox.py` | **Modifier** — affichage drapeaux |
| `src/ankiforge/ui/widgets/settings_modal/tabs/anki_sync_tab.py` | **Modifier** — onglet drapeaux |
| `src/ankiforge/ui/models/note_table_model.py` | **Modifier** — préchargement jointure |
| `tests/unit/test_flag_definition.py` | **Créer** |
| `tests/integration/test_flags_integration.py` | **Créer** |
| `tests/ui/test_flags_ui.py` | **Créer** |
---
name: peewee-expert
description: >
  Bonnes pratiques Peewee ORM pour AnkiForge. Activer lorsque l'utilisateur demande
  de "créer un modèle Peewee", "écrire une migration", "corriger une ForeignKey",
  "ajouter on_delete CASCADE", "utiliser db.atomic()", "requête N+1 Peewee",
  "prefetch Peewee", "index Peewee", "NOT NULL Peewee", "BDD SQLite AnkiForge",
  "modèle de données", ou consulte src/ankiforge/database/. Couvre : intégrité
  référentielle, atomicité, migrations, performance des requêtes et isolation des tests.
---

# Expert Peewee ORM — AnkiForge

En tant qu'**expert Peewee ORM** pour le projet AnkiForge, tu appliques les règles ci-dessous extraites de `GEMINI.md` (règles 2, 9, 20) lors de toute création ou modification de modèle, migration ou requête BDD.

## 1. Intégrité Référentielle

- **CASCADE obligatoire** : tout `ForeignKeyField` doit déclarer `on_delete='CASCADE'` (ou `on_delete='SET_NULL'` si la sémantique le justifie — à commenter explicitement).
  ```python
  # ✅ Correct
  deck = ForeignKeyField(DeckModel, backref="cards", on_delete="CASCADE")

  # ❌ Interdit — données orphelines à la suppression du parent
  deck = ForeignKeyField(DeckModel, backref="cards")
  ```
- **NOT NULL** : les champs obligatoires utilisent `null=False` (défaut Peewee). Ne pas stocker de chaîne vide `""` quand `null=True` aurait dû s'appliquer.
- Les suppressions de parent **doivent cascader** jusqu'aux feuilles : `Profil → Deck → Note → Chunk RAG → NoteChunkLink`.

## 2. Atomicité des Écritures

- **`db.atomic()` systématique** pour toute opération impliquant plusieurs `.save()`, `.create()`, `.delete_instance()`, ou `.bulk_create()`.
  ```python
  # ✅ Correct
  with db.atomic():
      card.save()
      audit_record.create(...)

  # ❌ Risque de données partielles en cas d'exception
  card.save()
  audit_record.create(...)
  ```
- Les *context managers* `db.atomic()` sont imbriquables (savepoints SQLite) — les utiliser sans crainte dans les services.
- **Transactions complexes multi-tables & restructurations hiérarchiques (`T-27`)** : toute opération combinant réassignation (ex: déplacement de cartes d'un paquet) et suppression (ex: suppression de paquet) **doit être impérativement enveloppée** dans un unique bloc `with db.atomic():` pour garantir un rollback total si l'une des étapes échoue.

## 3. Performance des Requêtes

- **Éviter le N+1** : ne jamais faire `for note in notes: note.deck.name` en boucle sans join/prefetch.
  ```python
  # ✅ Join
  notes = NoteModel.select(NoteModel, DeckModel).join(DeckModel)

  # ✅ Prefetch multi-relations
  prefetch(NoteModel.select(), ChunkModel.select())
  ```
- **Index** : déclarer `index=True` sur les FK fréquemment requêtées et les champs de recherche (ex: `created_at`, `deck_id`, `status`).
- **`select()` ciblé** : éviter `SELECT *` en listant les champs nécessaires pour les grosses tables.

## 4. Migrations

- Toute modification de schéma (ajout/suppression de colonne, nouvel index) doit s'accompagner d'une **migration peewee-migrate** dans `src/ankiforge/database/migrations/`.
- Les migrations doivent être **idempotentes** (`IF NOT EXISTS` ou `try/except`) pour survivre à un re-démarrage.
- La migration est **appliquée automatiquement au démarrage** dans `__main__.py` — ne pas demander à l'utilisateur de la lancer manuellement.
- **Rollback robuste et double suppression d'index (`T-31`)** :
  - Peewee-migrate nomme automatiquement les index ajoutés via `migrator.add_fields(..., index=True)` sous la forme `<table_name>_<column_name>` (sans préfixe `idx_`).
  - Dans la fonction `rollback()`, supprimer systématiquement les deux variantes de noms (`idx_<table_name>_<column_name>` et `<table_name>_<column_name>`) avant d'exécuter `migrator.drop_columns(...)` pour éviter une erreur SQLite bloquante.
  - Tout test de migration sous `tests/database/` doit obligatoirement tester l'aller-retour complet : application de `migrate(migrator, router.database, fake=False)` suivie de l'exécution de `rollback(migrator, router.database, fake=False)`.

## 5. Isolation des Tests

- **Jamais de `MagicMock`** sur les modèles Peewee en test. Utiliser la fixture `mock_db` de `conftest.py` (SQLite in-memory `mode=memory&cache=shared`).
- Les tests BDD doivent s'exécuter dans un contexte `db.atomic()` rollbacké après chaque test pour garantir l'isolation.
- **Enregistrement obligatoire des nouveaux modèles dans `tests/conftest.py`** :
  - Dès qu'un nouveau modèle Peewee (`*Model`) est créé sous `src/ankiforge/database/models/` :
    1. L'exporter dans `src/ankiforge/database/models/__init__.py` (`ALL_MODELS` et `__all__`).
    2. Déclarer sa migration dans `src/ankiforge/database/migrations/`.
    3. **ET l'ajouter impérativement dans la liste `models = [...]` de la fixture `mock_db()` dans `tests/conftest.py`**. Sans cet ajout, la base SQLite in-memory ne crée pas la table correspondante, provoquant un échec immédiat `sqlite3.OperationalError: no such table: <table_name>` dans les tests de service et d'intégration.

## 6. Règles Métier AnkiForge

- Les modèles **ne font jamais appel à la logique UI** et ne contiennent pas de `print()` — lever des exceptions métier claires (`ValueError`, `IntegrityError`).
- **Rechargement d'une instance Peewee** : ne jamais appeler `instance.refresh_from_db()` (syntaxe Django absente de Peewee qui lève un `AttributeError`). Utiliser systématiquement l'idiome Peewee : `instance = MyModel.get_by_id(instance.id)`.
- **Paquets hiérarchiques (`Parent::Enfant`) et relocalisation (`T-27`)** :
  - Tout déplacement de cartes avant suppression d'un paquet doit interdire une cible qui est un sous-paquet de la source (`target.name.startswith(f"{source.name}::")`).
  - La réassignation doit englober le paquet source ET l'ensemble de ses sous-paquets descendants (`where(CardModel.deck << all_decks_to_delete)`) avant d'appeler `DeckRepository.delete_deck()`.
- Multi-profils : chaque profil a sa propre instance `db` sous `profiles/<name>/ankiforge.db` — ne jamais croiser les instances.
- Référence complémentaire : skill `audit-donnees` pour l'audit d'intégrité global.

## 7. Typage Statique Strict (types-peewee)

- **Accès attributaire plutôt que `.tuples()` / `.dicts()`** :
  - Les stubs `types-peewee` infèrent les requêtes `Model.select(...)` comme des itérables de l'instance du modèle (`ModelSelect[T]`).
  - L'usage de `.tuples()` ou `.dicts()` rompt le typage strict `mypy` (`Value of type "Model" is not indexable [index]`).
  - Privilégier un `select(Model.field)` ciblé et parcourir `for obj in query: val = obj.field`.

## ⛔ Ne PAS utiliser ce skill si...

- La demande porte sur un **autre ORM** (SQLAlchemy, Django ORM, etc.) — ce skill est exclusivement Peewee.
- L'utilisateur veut **auditer** l'ensemble du modèle de données → utiliser le skill `audit-donnees`.
- La demande concerne uniquement la **qualité du code Python** (typage, lint) sans lien avec la BDD → utiliser `audit-qualite-code`.
- Le problème signalé est une **lenteur UI** sans lien confirmé avec les requêtes BDD → commencer par `audit-performance`.

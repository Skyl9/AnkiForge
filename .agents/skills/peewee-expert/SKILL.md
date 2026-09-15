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

## 5. Isolation des Tests

- **Jamais de `MagicMock`** sur les modèles Peewee en test. Utiliser la fixture `mock_db` de `conftest.py` (SQLite in-memory `mode=memory&cache=shared`).
- Les tests BDD doivent s'exécuter dans un contexte `db.atomic()` rollbacké après chaque test pour garantir l'isolation.

## 6. Règles Métier AnkiForge

- Les modèles **ne font jamais appel à la logique UI** et ne contiennent pas de `print()` — lever des exceptions métier claires (`ValueError`, `IntegrityError`).
- Multi-profils : chaque profil a sa propre instance `db` sous `profiles/<name>/ankiforge.db` — ne jamais croiser les instances.
- Référence complémentaire : skill `audit-donnees` pour l'audit d'intégrité global.

## ⛔ Ne PAS utiliser ce skill si...

- La demande porte sur un **autre ORM** (SQLAlchemy, Django ORM, etc.) — ce skill est exclusivement Peewee.
- L'utilisateur veut **auditer** l'ensemble du modèle de données → utiliser le skill `audit-donnees`.
- La demande concerne uniquement la **qualité du code Python** (typage, lint) sans lien avec la BDD → utiliser `audit-qualite-code`.
- Le problème signalé est une **lenteur UI** sans lien confirmé avec les requêtes BDD → commencer par `audit-performance`.

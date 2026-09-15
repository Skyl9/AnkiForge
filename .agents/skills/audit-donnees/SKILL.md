---
name: audit-donnees
description: Audit de l'intégrité du modèle de données et des migrations Peewee d'AnkiForge. Use when the user asks to "audit BDD", "audit base de données", "audit données", "Peewee", "données orphelines", "CASCADE", "db.atomic", "intégrité référentielle", "migrations" or "index manquants". Checks ForeignKeyField cascade, NOT NULL, atomicity, orphaned data and migration coverage; produces a report under audits/.
---

# Audit Données & Modèle Peewee AnkiForge

En tant qu'**Auditeur Modèle de Données (Peewee)**, tu évalues l'intégrité référentielle, l'atomicité des écritures, la complétude des migrations et les risques de données orphelines du modèle de données d'AnkiForge, puis tu produis un rapport priorisé.

## 1. Périmètre & Sources de Vérité

- Modèles : `src/ankiforge/database/models/` (`cards.py`, `ai.py`, `pipelines.py`, `rag.py`, `audit.py`, `system.py`).
- `src/ankiforge/database/base.py` (BaseModel), `database/migration.py`, `database/migrations/` (séquences de migrations peewee-migrate).
- `src/ankiforge/services/peewee.py` ou équivalent : gestion de l'instance `db`.
- `GEMINI.md` règle 2/15 (périmètre Forge), règle 9 (multi-profils, une BDD par profil) ; `docs/Dossier_architecture/03_modele_donnees_synchro.md`.
- Skill complémentaire : `.agents/skills/peewee-expert/SKILL.md`.

## 2. Commandes d'Investigation

```bash
# ForeignKeyField sans on_delete CASCADE (intégrité référentielle)
grep -rInE "ForeignKeyField\(" src/ankiforge/database/ | rg -v "on_delete" || true

# ÉCritures sur le modèle via .save()/.delete_instance() hors db.atomic (contexte à examiner)
grep -rInE "\.save\(\)|\.delete_instance\(\)|\.create\(" src/ankiforge/ --include="*.py" | head -50 || true

# Intégrité SQLite sur la première BDD profil trouvée (si disponible)
find ~/.ankiforge -name "*.db" -maxdepth 4 2>/dev/null | head -1 | while read -r db; do sqlite3 "$db" "PRAGMA integrity_check;"; sqlite3 "$db" ".tables"; done || true

# Migrations : dernières versions
ls src/ankiforge/database/migrations/ | sort | tail -5 || true
```

## 3. Points de Contrôle

1. **Intégrité référentielle** : chaque `ForeignKeyField` doit porter `on_delete='CASCADE'` (ou `SET_NULL` si la sémantique l'exige — à justifier). Une suppression de parent doit cascader vers ses enfants (ex. Profil → Decks → Cartes). Signaler toute FK sans `on_delete` ou dangling.
2. **Contraintes NOT NULL** : les champs obligatoires respectent `null=False` ; absence de `CharField` texte vide stocké quand `null=False` aurait dû s'appliquer ; cohérence `default` vs `null`.
3. **Atomicité** : les écritures/suppressions multiples dans un même service/dialogue doivent être dans `db.atomic()` (rollback global si erreur). Signaler les `.save()`/`delete_instance()` en boucle sans transaction (risque de données partielles).
4. **Données orphelines** : identifier les relations où la suppression parent ne cascaderait pas (cf. 1) et les scénarios d'accumulation (ex. chunks RAG sans note liée, versions de notes sans note parent).
5. **Migrations** : `database/migrations/` doit être séquentielle et appliquée au démarrage (vérifier le boot dans `__main__.py`) ; une modification de modèle sans migration correspondante est une violation ; les migrations récentes doivent être idempotentes.
6. **Index & performances** : index présents sur les FK fréquemment requêtées (decks, notes, pipelines) et sur les champs de recherche/coverage ; `PRAGMA integrity_check` doit être OK ; vérifier le mode WAL le cas échéant.

## 4. Rapport

`audits/audit-donnees.md` :

### 📊 Synthèse
Anomalies par sévérité (Critique/Majeur/Mineur) et par catégorie (Intégrité référentielle, NOT NULL, Atomicité, Orphelines, Migrations, Index).

### 🔍 Violations détaillées
Liens cliquables `[modèle.py:Lnn](file://<abs>/...#Lnn)` · règle · extrait · correction (ex. ajouter `on_delete='CASCADE'`, englober dans `db.atomic()`).

### 🗺️ Plan priorisé
Ordre : cascade manquante/orphelines (critiques) → migrations → atomicité → index.

## 5. Clôture

Résume les risques d'intégrité majeurs dans le chat, indique le chemin du rapport, propose les correctifs (ajout `on_delete`, mise en transaction, migrations).
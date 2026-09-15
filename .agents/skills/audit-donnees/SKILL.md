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
- Répertoire de données présumé `~/.ankiforge` (à confirmer une fois pour l'environnement de dev réel — peut différer sous Windows/macOS).

## 2. Commandes d'Investigation

Toutes les sorties sont conservées brutes sous `audits/raw/` (horodatées) pour permettre une comparaison d'un audit à l'autre.

```bash
mkdir -p audits/raw
STAMP=$(date +%Y-%m-%d)
DB_MODELS="src/ankiforge/database/"

# ForeignKeyField sans on_delete CASCADE — capture le bloc d'appel complet (multi-ligne)
# pour ne pas signaler à tort une FK dont on_delete est sur une ligne suivante.
rg -U -P "ForeignKeyField\([\s\S]*?\)" "$DB_MODELS" --glob "*.py" -n -o \
  | rg -v "on_delete" \
  > "audits/raw/fk-missing-cascade-${STAMP}.txt" || true
# Note : reste une heuristique (parenthèses imbriquées dans les args casseraient la capture) —
# à confirmer manuellement sur chaque occurrence signalée.

# Écritures sur le modèle via .save()/.delete_instance()/.create() — sortie complète, non tronquée
rg -n "\.save\(\)|\.delete_instance\(\)|\.create\(" src/ankiforge/ --glob "*.py" \
  > "audits/raw/writes-outside-atomic-${STAMP}.txt" || true

# Intégrité SQLite + mode journal sur TOUTES les BDD de profil trouvées (pas juste la première)
find ~/.ankiforge -name "*.db" -maxdepth 4 2>/dev/null | while read -r db; do
  echo "== $db =="
  sqlite3 "$db" "PRAGMA integrity_check;"
  sqlite3 "$db" "PRAGMA journal_mode;"
  sqlite3 "$db" ".tables"
done > "audits/raw/sqlite-integrity-${STAMP}.txt" || true

# Migrations : liste complète + signal faible d'idempotence (présence de IF NOT EXISTS / try-except)
ls src/ankiforge/database/migrations/ | sort > "audits/raw/migrations-list-${STAMP}.txt" || true
rg -Ln "IF NOT EXISTS|try:" src/ankiforge/database/migrations/ --glob "*.py" \
  > "audits/raw/migrations-non-idempotent-candidates-${STAMP}.txt" || true
# Note : signal faible, pas une preuve d'idempotence — sert à cibler la revue manuelle
# (les fichiers listés ici sont ceux qui n'ont NI garde IF NOT EXISTS NI try/except).
```

## 3. Points de Contrôle

1. **Intégrité référentielle** : chaque `ForeignKeyField` doit porter `on_delete='CASCADE'` (ou `SET_NULL` si la sémantique l'exige — à justifier). Une suppression de parent doit cascader vers ses enfants (ex. Profil → Decks → Cartes). Signaler toute FK sans `on_delete` ou dangling — croiser avec `audits/raw/fk-missing-cascade-*.txt` et vérifier chaque occurrence à l'œil (heuristique multi-ligne imparfaite).
2. **Contraintes NOT NULL** : les champs obligatoires respectent `null=False` ; absence de `CharField` texte vide stocké quand `null=False` aurait dû s'appliquer ; cohérence `default` vs `null`.
3. **Atomicité** : les écritures/suppressions multiples dans un même service/dialogue doivent être dans `db.atomic()` (rollback global si erreur). Passer en revue `audits/raw/writes-outside-atomic-*.txt` pour repérer les `.save()`/`.delete_instance()` en boucle sans transaction (risque de données partielles).
4. **Données orphelines** : identifier les relations où la suppression parent ne cascaderait pas (cf. 1) et les scénarios d'accumulation (ex. chunks RAG sans note liée, versions de notes sans note parent).
5. **Migrations** : `database/migrations/` doit être séquentielle et appliquée au démarrage (vérifier le boot dans `__main__.py`) ; une modification de modèle sans migration correspondante est une violation. Pour l'idempotence, `audits/raw/migrations-non-idempotent-candidates-*.txt` liste les migrations sans garde apparente (`IF NOT EXISTS`/`try`) — chacune doit être relue manuellement, ce signal n'étant qu'indicatif.
6. **Index & performances** : index présents sur les FK fréquemment requêtées (decks, notes, pipelines) et sur les champs de recherche/coverage ; `PRAGMA integrity_check` doit être OK sur **toutes** les BDD de profil listées dans `audits/raw/sqlite-integrity-*.txt` (pas seulement la première) ; le mode WAL (`PRAGMA journal_mode`) y est également consigné pour chaque profil.

## 4. Rapport

`audits/audit-donnees.md` (écrasé à chaque audit — l'historique brut vit sous `audits/raw/`) :

### 📊 Synthèse
Anomalies par sévérité (Critique/Majeur/Mineur) et par catégorie (Intégrité référentielle, NOT NULL, Atomicité, Orphelines, Migrations, Index).

### 🔁 Évolution depuis le dernier audit
Comparaison avec les fichiers `audits/raw/` les plus récents précédents (nouvelles anomalies, anomalies corrigées) — si un audit précédent existe.

### 🔍 Violations détaillées
Liens cliquables `[modèle.py:Lnn](file://<abs>/...#Lnn)` · règle · extrait · correction (ex. ajouter `on_delete='CASCADE'`, englober dans `db.atomic()`).

### 🗺️ Plan priorisé
Ordre : cascade manquante/orphelines (critiques) → migrations → atomicité → index.

## ⛔ Ne PAS utiliser ce skill si...

- La demande est de **créer un nouveau modèle Peewee** (utiliser le skill `peewee-expert` pour les bonnes pratiques de définition).
- L'utilisateur veut uniquement **optimiser des requêtes lentes** sans vérifier l'intégrité → utiliser `audit-performance`.
- La demande concerne la **qualité du code Python** autour des modèles (typage, lint) → utiliser `audit-qualite-code`.
- Le projet n'utilise pas **Peewee ORM** ou pas de base SQLite.
- L'audit a déjà été effectué et **aucune migration ni modification de modèle** n'a eu lieu depuis.

## 5. Clôture

Résume les risques d'intégrité majeurs dans le chat, indique le chemin du rapport et des sorties brutes, précise les points restés purement indicatifs (idempotence des migrations, FK multi-ligne) qui nécessitent une confirmation manuelle, propose les correctifs (ajout `on_delete`, mise en transaction, migrations).

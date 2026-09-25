---
name: audit-performance
description: Audit de performance et de réactivité Qt/backend d'AnkiForge. Use when the user asks to "audit performance", "lenteur", "réactivité", "blocage thread principal", "N+1 Peewee", "appel réseau bloquant", "imports lourds", "UI qui freeze" or "QThread/QThreadPool". Detects main-thread blocks, N+1 queries, missing db.atomic() and heavy-synchronous work, and produces a report under audits/.
---

# Audit Performance & Réactivité AnkiForge

En tant qu'**Auditeur Performance & Architecture Qt**, tu identifies les causes de lenteur et les blocages de l'interface (thread principal), puis tu produis un rapport de performance exploitable.

## 1. Périmètre & Sources de Vérité

- `GEMINI.md` : règle 7 (A/B lab en `QThreadPool`), règle 8 (lazy loading des dépendances lourdes), règle 19 (logging asynchrone `QueueHandler`/`QueueListener`), règle 13 (éditeur 100 % natif Qt).
- `docs/Dossier_architecture/02_architecture_technique.md` (architecture), `03_modele_donnees_synchro.md` (accès BDD), `07_inventaire_composants_ui.md` (UI).
- `src/ankiforge/` (cible), en particulier `ui/`, `services/`, `utils/`.

## 2. Commandes d'Investigation

```bash
# Appels réseau/IO synchrones dans la couche UI (drapeau rouge si présents)
grep -rInE "(requests\.|urllib\.|http\.|urlopen|trafilatura|yt_dlp|youtube_transcript_api)" src/ankiforge/ui/ || true
# Blocages volontaires dans le code applicatif
grep -rIn "time\.sleep\|\.sleep(" src/ankiforge/ --include="*.py" || true
# Importations SQLAlchemy/séance/DB dans les vues
grep -rInE "^(from|import) .*(peewee|database|faiss|chromadb|numpy|torch)" src/ankiforge/ui/ || true
# Appels à fsync/copy synchrones sur fichiers
grep -rInE "shutil\.(copy|move|rmtree)|os\.remove" src/ankiforge/ui/ || true
```

## 3. Points de Contrôle

0. **Règle d'or « Mesurer avant d'optimiser » (Benchmark First)** : Interdiction d'optimiser au jugé ou de complexifier l'architecture sans preuve chiffrée (mesure de temps avant/après, budget < 16ms pour 60 FPS Qt, < 100ms pour requêtes BDD).
1. **Blocage du thread principal (UI)** : tout I/O réseau ou fichier synchrones dans `ui/` (messages, slots) doit être reporté. Vérifier l'usage correct des workers (`services/batch`, `QThreadPool`, `batch_worker`) pour les opérations longues (import .apkg, OCR Marker, scraping, parsing PDF).
2. **Lazy loading des dépendances lourdes** : Marker/PyTorch/FAISS/Chromadb doivent être importés à la volée (pas en tête de module au chargement de l'app) ; `grep -rInE "^import (torch|marker|faiss|chromadb)" src/ankiforge/` — toute importation de module lourd au niveau d'un `__init__` importé au démarrage est une violation.
3. **N+1 Peewee** : boucles `for x in query: x.related_model.attr` sans préfetch → signaler et recommander `select(Model, related).join(...)` ou prefetch (`docs/Dossier_architecture/03_modele_donnees_synchro.md`).
4. **Transactions** : écritures/suppressions multiples sans `db.atomic()` (`grep -rn "\.save()\|delete_instance()"` contextes) — non-atomicité = lenteur + risque de données incohérentes.
5. **Signaux/slots** : calculs lourds dans un slot connecté GUI ; absence de debounce (`QTimer.singleShot`) sur champs textes avec autocomplétion (KaTeX live, recherche).
6. **WebEngine** : aperçus re-rendus en boucle sans debounce ; vues Web créées/détruites sans `cleanup()` (fuites/segfaults en teardown) ; activation inutile de l'accélération GPU.
7. **Logging bloquant** : tout `print()` dans `src/ankiforge/` (violation T20) ; logs synchrones lourds dans des hot-loops.
8. **Points chauds algorithmiques** : calculs Levenshtein/FSRS dans le thread principal (`c_bridge.py` doit utiliser l'extension C sinon repli Python notifiable).

## 4. Rapport

`audits/audit-performance.md` :

### 📊 Synthèse
Anomalies par sévérité (Critique/Majeur/Mineur) et par catégorie (Thread principal, N+1/BDD, Imports lourds, I/O, WebEngine, Logging, Algorithmique).

### 🔍 Violations détaillées
Liens cliquables `[fichier.py:Lnn](file://<abs>/...#Lnn)` · règle violée · extrait · correction proposée (ex. déplacement en worker, prefetch).

### 🗺️ Plan priorisé
Actions triées par impact (un blocage de thread d'abord), avec mesure de vérification (ex. re-test temps de réponse, profiler).

## ⛔ Ne PAS utiliser ce skill si...

- La demande est un **profiling fin avec des outils externes** (cProfile, py-spy) — ce skill fait de l'analyse statique par grep, pas du profiling dynamique.
- L'utilisateur signale une **lenteur côté réseau externe** (LLM distant, latence API) : hors périmètre du skill (qui couvre le thread principal Qt + BDD).
- La requête concerne les **performances des tests** eux-mêmes → utiliser `audit-tests-ci`.
- La requête est une **demande de refactoring pur** sans diagnostic préalable.
- La lenteur signalée est une **régression après un merge** non encore analysée : commencer par lire les logs de CI.

## 5. Clôture

Résume les principaux bloquants dans le chat, indique le chemin du rapport, et propose des correctifs (déport en `QThreadPool`, prefetch Peewee, lazy import).

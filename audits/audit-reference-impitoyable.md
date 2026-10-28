# ⚖️ Référentiel d'Audit Impitoyable — Architecture Python, PySide6 & IA (AnkiForge)

Ce document constitue la grille d'évaluation normative (Senior Staff Engineer / Principal Architect) pour conduire un **audit de code total, sans complaisance et déterministe** sur AnkiForge.

> **Règle d'Or de l'Auditeur :**
> Aucun constat ne doit être toléré sous une forme abstraite (« code trop complexe », « améliorer la gestion d'erreur »). Chaque violation doit citer :
> 1. Le **fichier exact et la plage de lignes**.
> 2. Le **mécanisme de défaillance réel** (race condition, gel de l'event loop Qt, corruption SQLite, fuite C++/Shiboken, injection XSS/Jinja, dérive de schéma LLM).
> 3. Le **correctif chirurgical attendu** et le **test automatisé (`pytest` / `pytest-qt`)** qui prouve la résolution.

---

## 🏛️ AXE 1 : Architecture Découplée & Frontières MVVM (ADR 0003)

Dans une application desktop riche, l'ennemi numéro un de la maintenabilité est la « Massive View » qui mélange requêtes SQLite, appels LLM et manipulation de widgets Qt.

### 1.1 Pureté de la couche `ui/views/` et `ui/widgets/`
- **Zéro accès direct aux modèles de données ou à la BDD :**
  - *Interdit dans `ui/views/` et `ui/dialogs/`* : `import peewee`, `Model.select()`, `.save()`, `.delete_instance()`, ou instanciation directe de `Repository` / `Service` lourd.
  - *Exigé* : La Vue ne consomme que son `ViewModel` (`ui/viewmodels/`) ou des DTOs/dataclasses immuables, et communique vers le haut par signaux (`Signal`) ou méthodes de commande du ViewModel.
- **Zéro logique métier dans les handlers d'événements Qt :**
  - Un slot `_on_btn_clicked()` ne doit jamais dépasser **15 lignes**. Il valide ou lit l'état immédiat du contrôle UI, délègue au ViewModel, et met à jour l'état visuel local.
- **Injection de dépendances explicite :**
  - Bannir les Singletons globaux implicites cachés au fond des constructeurs de widgets (qui rendent les tests `pytest-qt` flakey ou dépendants de l'ordre d'exécution). Les services doivent être injectés ou résolus via une couture unique testable (`fake_services.py`).

### 1.2 Responsabilité des `ViewModels` (`ui/viewmodels/`)
- **Indépendance vis-à-vis des `QWidget` :**
  - Un `ViewModel` hérite de `QObject` (pour émettre des `Signal`), mais ne doit **JAMAIS** importer `QtWidgets` (`QMessageBox`, `QDialog`, `QTableWidget`, `QApplication`).
  - *Testabilité* : Tout `ViewModel` doit pouvoir être instancié et testé unitairement sans aucun serveur d'affichage graphique.

---

## ⚡ AXE 2 : Concurrence, Event Loop Qt & Cycle de Vie des Workers

Toute opération dépassant **16 ms** sur le thread principal fait chuter l'interface sous les 60 FPS ; au-delà de **100 ms**, l'utilisateur perçoit un gel (micro-freeze).

### 2.1 Interdiction absolue d'I/O synchrone sur le GUI Thread
- **Opérations bannies du thread principal (`MainWindow`, `View`, `ViewModel` direct) :**
  - Requêtes réseau HTTP/SSE (appels LLM Gemini/OpenAI/Ollama, téléchargements `yt-dlp`, vérification de mise à jour).
  - Inférence locale ou calculs lourds (Marker OCR, embeddings vectoriels FAISS/ChromaDB, indexation BM25, synthèse vocale Piper TTS).
  - Manipulations lourdes de fichiers ou d'archives (`.apkg`, `.colpkg`, décompression Zstandard/ZIP, décodage synchrone d'images haute résolution).
  - *Pour les vignettes médias* : Décodage obligatoire hors thread GUI via cache asynchrone (`request_media_thumbnail`).

### 2.2 Sûreté mémoire et cycle de vie des `QThread` / `Worker` (`services/workers/`)
- **Anti-pattern n°1 : Manipulation de `QWidget` depuis un thread secondaire :**
  - *Fatal (Crash C++ segfault aléatoire)* : Appeler `label.setText()`, `progress.setValue()` ou créer un `QPixmap` (objet lié au serveur d'affichage) directement dans `Worker.run()`.
  - *Exigé* : Utiliser `QImage` dans le thread de travail (pur tampon mémoire CPU), et communiquer avec l'UI **exclusivement** via `Signal` avec connexion `Qt.ConnectionType.QueuedConnection` (automatique entre threads).
- **Anti-pattern n°2 : Destruction prématurée du `QThread` (`QThread: Destroyed while thread is still running`) :**
  - Tout worker lancé par une vue ou une modale doit conserver une référence forte jusqu'à l'émission de `finished`, gérer l'annulation coopérative (`requestInterruption()` / drapeau `threading.Event` `_is_cancelled` vérifié à chaque itération de boucle), et nettoyer ses références (`deleteLater()`).
- **Garde-fou de mutation concurrente pendant un Run :**
  - Lorsqu'un worker traite une liste indexée (ex: `BatchQueueTable`, réindexation RAG), toute action UI permettant de supprimer, trier ou réordonner les éléments en cours de traitement doit être **verrouillée** (`setEnabled(False)`) ou routée par identifiant immuable (`_queue_uid`) et non par index de ligne.

---

## 🧠 AXE 3 : Mémoire C++/Python (Shiboken6), Rendu 60 FPS & QWebEngine

PySide6 repose sur un double système de gestion mémoire : le Garbage Collector Python et l'arbre de parenté C++ de `QObject`. Leur désynchronisation provoque soit des fuites mémoire massives, soit des erreurs `RuntimeError: Internal C++ object already deleted`.

### 3.1 Hygiène du Cycle de Vie Shiboken6 / `QObject`
- **Parenté obligatoire :** Tout `QObject`, `QWidget`, `QTimer`, `QAnimation` ou `QAction` instancié dynamiquement doit recevoir un `parent` explicite dès sa construction, ou être attaché immédiatement à un layout.
- **Nettoyage des vues dynamiques (`clear_layout`) :**
  - Retirer un widget d'un layout avec `layout.takeAt(i)` **ne le détruit pas** en C++. Il reste en mémoire et continue de recevoir des signaux globaux.
  - *Exigé* : Appeler systématiquement `widget.setParent(None)` **et** `widget.deleteLater()`, et déconnecter les signaux rattachés à des bus d'événements singletons (`EventBus`, `StyleEngine`, `ReindexActivityService`).
- **Fuites par closures Python (`lambda`) sur signaux longue durée :**
  - Connecter un signal d'un service singleton (ex: `event_bus.subscribe(...)`) à une `lambda` capturant `self` (une modale ou un widget temporaire) empêche le Garbage Collector de libérer la modale à sa fermeture, et déclenchera un `RuntimeError: Internal C++ object already deleted` à la prochaine émission du signal.

### 3.2 Virtualisation Model/View & Délégués `QPainter` (`ui/models/`)
- **Interdiction de `setIndexWidget` / `setCellWidget` sur collections > 50 éléments :**
  - Instancier de vrais `QWidget` dans chaque ligne d'une table de 10 000 notes Anki sature la boucle d'événements Qt.
  - *Exigé* : Utiliser `QAbstractTableModel` / `BasePaginatedPeeweeModel` (`canFetchMore` / `fetchMore`) et peindre les badges, cases à cocher, drapeaux Anki et jauges en **pur `QPainter` vectoriel** via `QStyledItemDelegate` (`FlagItemDelegate`, `BadgeItemDelegate`).
- **Discipline `QPainter` dans `paintEvent()` et `paint()` :**
  - Toujours entourer les modifications d'état du peintre par `painter.save()` / `painter.restore()` (dans un bloc `try...finally` si une exception est possible).
  - Zéro allocation lourde (instanciation de `QFont`, parsing SVG, requête SQLite, lecture disque) à l'intérieur de `paintEvent()` qui est appelé 60 fois par seconde. Pré-calculer et mettre en cache les `QPixmap` d'icônes par `(icon_name, size, color_hex, devicePixelRatio)`.

### 3.3 Gouvernance `QWebEngineView` (`safe_web_preview.py`, `card_preview_widget.py`)
- **Poids mémoire :** Chaque instance de `QWebEngineView` démarre un processus Chromium sous-jacent (~80 à 150 Mo de RAM).
- **Règles strictes :**
  - Ne jamais instancier des dizaines de `QWebEngineView` dans une liste défilante (utiliser le rendu natif `QTextBrowser` ou `KaTeXEditor` / `KatexLivePreviewWidget` quand Chromium n'est pas indispensable).
  - Décharger ou mettre en veille les vues WebEngine invisibles lors de `hideEvent()`.

---

## 🎨 AXE 4 : Intégrité du Design System (`DESIGN.md`) & `StyleEngine`

L'audit doit vérifier mécaniquement le respect des règles de `DESIGN.md` :

1. **Zéro couleur en dur hors exceptions documentées :**
   - Aucune chaîne `#RRGGBB`, `rgb(...)`, `rgba(...)` ou `"white"` dans `src/ankiforge/ui/` hors `themes.py` et des 4 exceptions physiques documentées dans `DESIGN.md` §1.0.
   - Toute icône sur fond accentué doit passer par `load_on_accent_icon()` (`DesignTokens.TEXT_ON_ACCENT`).
2. **Respect de la cascade QSS :**
   - Ne jamais surcharger `border:` ou `background:` localement sur un bouton portant un `role` (`primary`, `secondary`, `danger`, `ghost`) ou une `density="compact"`, sous peine de détruire ses états `:hover`, `:focus` et `:disabled`.
   - Scoper systématiquement les `QFrame` et `QScrollArea` par `#objectName` dans les feuilles de style locales.
   - Ne jamais utiliser `setFont()` pour régler la taille de police d'un widget (écrasé par `QWidget { font-size }` du `StyleEngine` global) ; utiliser `font-size` en QSS.
3. **Réactivité multi-thèmes (`refresh_theme`) :**
   - Tout widget stockant des couleurs ou des icônes teintées à l'initialisation (`__init__`) DOIT implémenter `refresh_theme()` et réappliquer ses tokens et icônes Phosphor lors d'un basculement Sombre 🌙 / Clair ☀️ à chaud.
4. **Internationalisation & Accessibilité (ADR 0013 & ADR 0032) :**
   - 100 % des chaînes utilisateur encapsulées dans `self.tr("...")`.
   - Zéro émoji Unicode dans les labels/boutons (exclusivement des icônes vectorielles Phosphor).
   - Tout `IconButton` sans texte possède un `setToolTip(self.tr(...))` et un `setAccessibleName(self.tr(...))`.
   - Zéro `QShortcut` instancié en dehors du registre central `src/ankiforge/ui/shortcuts/catalog.py`.

---

## 🤖 AXE 5 : Ingénierie IA, Orchestration DAG, RAG & Serveur MCP

Les pipelines LLM sont par nature probabilistes, lents, coûteux et sujets aux hallucinations structurelles. Le code qui les encadre doit être **100 % défensif et déterministe**.

### 5.1 Fiabilité des Sorties Structurées & Parsing Résilient (`services/ai/`)
- **Validation stricte par schémas (`schemas.py` / Pydantic) :**
  - Ne jamais faire confiance à un `json.loads(response)` nu sur une sortie LLM. Passer systématiquement par le parseur tolérant aux artefacts Markdown/troncatures (`robust_json_loads`) suivi d'une validation de schéma typée.
- **Plafonds volumétriques et budgets de tokens (ADR 0039 / ADR 0048) :**
  - Chaque étape du `PipelineOrchestrator` et chaque appel d'outil MCP doit imposer une limite de taille d'entrée/sortie (`context_compactor.py`), tracer précisément les tokens consommés (`usage.py` / `pricing_service.py`) avec le contexte d'exécution, et gérer les dépassements de fenêtre de contexte sans crasher le lot entier.
- **Résilience réseau (`retry.py`) :**
  - Backoff exponentiel avec *jitter* uniquement sur les erreurs transitoires (`429 Too Many Requests`, `502/503/504`, `TimeoutError`), jamais sur les erreurs de validation `400` ou d'authentification `401/403`.
  - Tout appel réseau LLM doit définir un `timeout` explicite (aucun appel bloquant infini).

### 5.2 Gouvernance du Serveur MCP & Garde-Fou Two-Phase Commit (ADR 0043)
- **Séparation stricte Lecture / Écriture directe / Écriture Staged :**
  - Aucun outil MCP de mutation de notes ou d'opérations destructrices (`card_delete`, `deck_delete`, `empty_cards_delete`, `set_tags_bulk`, modification de champs) ne doit écrire directement dans les tables de production sans passer par le registre de staging (`staged_patch_registry.py` / `staged_bundles`) soumis au **Garde-Fou humain (2PC)**, sauf les exceptions explicitement autorisées par l'ADR 0043.
- **Atomicité séquentielle des Staged Bundles (ADR 0043 / ADR 0046) :**
  - Lors de l'application ou du rejet d'un bundle multi-étapes, vérifier que les préconditions en base n'ont pas dérivé depuis la création du patch (détection de conflit d'état / optimistic locking) pour éviter d'écraser silencieusement une édition manuelle de l'utilisateur.
- **Troncature et plafonds des lots MCP (ADR 0048) :**
  - Vérifier que chaque outil MCP pagine ses résultats et rejette avec un message d'erreur actionnable les payloads dépassant les plafonds volumétriques.

### 5.3 Alignement RAG, Provenance & Couverture Documentaire (ADR 0009, 0010, 0018, 0025)
- **Couture unique de résolution visuelle (`VisualPayloadResolver`) :**
  - Toute lecture de figures ou de médias liés aux fragments (`DocumentChunkModel`) doit emprunter exclusivement `VisualPayloadResolver` — zéro requête ad-hoc dupliquée dans les vues ou les workers.
- **Immuabilité et traçabilité des adresses de régions (`region_address.py`) :**
  - Les exclusions (`excluded_headings`) et neutralisations de conteneurs (`neutralized_regions`) doivent être strictement non-destructives et réversibles, et déclencher un recalcul déterministe via `CoverageAlignmentService`.
- **Synchronisation SQLite ↔ Index Vectoriel (FAISS/ChromaDB) ↔ Index BM25 :**
  - Toute suppression ou mise à jour d'un document en SQLite doit purger atomiquement ses vecteurs et ses entrées FTS5/BM25 pour interdire les « fragments fantômes » dans les résultats RAG.

---

## 🗄️ AXE 6 : Base de Données SQLite, Peewee ORM & Migrations

SQLite en environnement desktop multi-threadé (UI + Workers + Démon MCP) exige une discipline transactionnelle rigoureuse.

### 6.1 Concurrence SQLite & Verrous (`database/`)
- **Configuration pragmatique obligatoire :**
  - Vérifier que toute connexion SQLite active `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA foreign_keys=ON;` et un `busy_timeout` suffisant (ex: 5000 ms) pour absorber les écritures concurrentes entre le démon MCP et l'interface.
- **Transactions atomiques (`db.atomic()`) :**
  - Toute opération modifiant plus d'une ligne ou plus d'une table (ex: renommage de paquet hiérarchique `::`, scission de carte Wozniak, import `.apkg`/`.colpkg`, création de note + cartes + tags) DOIT être enveloppée dans un bloc `with db.atomic():`.
  - **Interdiction absolue** d'effectuer un appel réseau (LLM, HTTP) ou d'attendre une confirmation UI (`QDialog.exec()`) *à l'intérieur* d'un bloc `with db.atomic():` (cela verrouille la base SQLite en écriture pendant plusieurs secondes et fait planter le démon MCP avec `OperationalError: database is locked`).

### 6.2 Éradication des requêtes $N+1$ & Pagination
- **Problème $N+1$ :**
  - Traquer toute boucle `for note in notes:` qui exécute une requête SQL par itération (ex: accéder à une clé étrangère non préchargée, compter les cartes liées ou vérifier la couverture section par section).
  - *Exigé* : Utiliser `prefetch()`, `.join()`, ou une requête d'agrégation unique `fn.COUNT(...) ... .group_by(...)` suivie d'un dictionnaire de correspondance en mémoire Python $O(1)$.
- **Écritures en masse :**
  - Utiliser `insert_many()` / `bulk_create()` / `bulk_update()` par lots bornés (ex: chunks de 500) au lieu de `.save()` dans une boucle.

### 6.3 Discipline des Migrations (`database/migrations/`)
- Chaque migration numérotée (`001_` à `048_...`) doit être **idempotente** (vérifier l'existence de la table/colonne/index avant `ALTER TABLE` ou `CREATE INDEX`), rétrocompatible avec les données existantes (backfill explicite sans perte), et couverte par un test dans `tests/database/test_migrations.py`.

---

## 🛡️ AXE 7 : Sécurité, Sandboxing, C-Bridge & Packaging Nuitka

Une application desktop qui importe des paquets communautaires (`.apkg`, `.afmodel`, plugins), rend du HTML/JS dans Chromium et exécute des outils IA est exposée à des vecteurs d'attaque critiques.

### 7.1 Protection Anti-XSS, Injection Jinja2 & Sandbox (`security/`, `utils/`)
- **Assainissement HTML/Markdown (`anki_renderer.py`, `safe_web_preview.py`) :**
  - Tout contenu issu d'un document importé, d'un paquet `.apkg` externe ou d'une réponse LLM doit être assaini avant injection dans un `QWebEngineView` (blocage de `<script>` arbitraire, `onerror=`, `javascript:`, `file://` hors répertoire média autorisé).
- **Templates Jinja2 (`jinja_sandbox.py`) :**
  - Aucun `jinja2.Template(...)` ou `jinja2.Environment()` standard ne doit être utilisé sur des prompts personnalisés ou des modèles de cartes. Utiliser exclusivement l'`ImmutableSandboxedEnvironment` (`jinja_sandbox.py`) pour empêcher l'évasion Python (`__class__.__mro__.__subclasses__()`).
- **Exécution d'outils Python (`tool_sandbox.py`) & Archives (`archive_utils.py`) :**
  - Protection obligatoire contre le **Zip Slip** (traversal `../` ou liens symboliques sortant du dossier cible) lors de l'extraction de `.apkg`, `.colpkg`, `.afmodel` ou plugins ZIP.
- **Gestion des Secrets (`secret_store.py`) :**
  - Aucune clé API LLM ou jeton Bearer MCP ne doit apparaître en clair dans les logs (`logger.py`), les rapports de crash (`crash_reporter_service.py`) ou les exports de diagnostic (`feedback_service.py`).

### 7.2 Sûreté de l'Extension C (`c_ext/levenshtein_distance.c` & `c_bridge.py`)
- Vérifier dans le code C :
  - L'absence de dépassement de tampon (*buffer overflow*) et le contrôle systématique de `malloc`/`calloc` (`if (ptr == NULL) return PyErr_NoMemory();`).
  - L'équilibre strict des compteurs de références Python (`Py_INCREF` / `Py_DECREF`) sur tous les chemins de sortie (y compris les branches d'erreur).
  - La libération du GIL (`Py_BEGIN_ALLOW_THREADS` / `Py_END_ALLOW_THREADS`) pendant le calcul matriciel pur C si les chaînes sont longues, et le repli Python pur transparent dans `c_bridge.py` si l'extension compilée est absente.

### 7.3 Compatibilité Compilation Nuitka & Multi-OS (`build_script/`, `utils/paths.py`)
- **Résolution des chemins de ressources (`paths.py`) :**
  - Bannir tout chemin relatif naïf `open("src/ankiforge/...")` ou `Path(__file__).parent.parent` non protégé qui casse une fois le binaire figé par Nuitka dans un bundle `.app` macOS, AppImage Linux ou installeur Windows.
- **Imports dynamiques :**
  - Tout import dynamique (`importlib.import_module`) pour les migrations ou les plugins doit être déclaré dans `nuitka_config.json` et testé par `script/build_smoke_test.py`.

---

## 🧪 AXE 8 : Qualité des Tests (`pytest`, `pytest-qt`) & Anti-Flakiness

Un test qui passe par chance ou qui teste un mock au lieu du code réel est pire que l'absence de test.

1. **Interdiction des `time.sleep()` et `qtbot.wait(N)` arbitraires :**
   - *Symptôme* : Utiliser `qtbot.wait(200)` pour attendre un worker ou un rendu. C'est lent et flakey sur la CI.
   - *Exigé* : Utiliser `with qtbot.waitSignal(obj.signal, timeout=2000):` ou `qtbot.waitUntil(lambda: ..., timeout=2000)`.
2. **Enregistrement systématique des widgets (`qtbot.addWidget`) :**
   - Tout widget racine ou modale instancié dans un test doit être passé à `qtbot.addWidget(w)` pour garantir sa destruction propre entre deux tests et éviter la pollution d'état global Qt.
3. **Isolation hermétique des tests :**
   - Aucun test ne doit toucher au profil utilisateur réel (`~/.ankiforge/`), au trousseau macOS (`Keychain`) de l'hôte, ni effectuer de requête réseau sortante réelle.
   - Vérifier que chaque test BDD utilise une base SQLite `:memory:` ou un `tmp_path` parfaitement isolé avec fermeture explicite de la connexion en teardown.
4. **Tests d'invariants structurels (Meta-Tests) :**
   - Maintenir et enrichir les tests garde-fous automatiques : dérive des raccourcis (`test_shortcuts_drift.py`), audit i18n (`test_i18n_audit.py`), audit des icônes (`test_icons_audit.py`), protection XSS (`test_xss_protection.py`), et conformité oracle Anki (`test_anki_export_oracle.py`).

---

## 📋 Protocole d'Exécution d'un Audit Impitoyable (Checklist d'Inspection)

Lorsqu'un audit est lancé sur un module ou sur l'ensemble du dépôt, procéder dans cet ordre strict :

1. **Scan Statique & Cartographie des Couplages :**
   - Identifier les fichiers dépassant **500 lignes** (candidats immédiats au découpage de responsabilités).
   - Rechercher les imports croisés illégaux (`ui/` important `peewee` ou `database/models` avec appels d'écriture directs, `services/` important `ui/`).
2. **Traque des Bombes à Retardement Runtime :**
   - Lister tous les `except Exception: pass` ou `except Exception as e: logger.debug(...)` qui avalent silencieusement des corruptions d'état ou des erreurs SQL.
   - Vérifier chaque `QThread` / `Worker` et chaque bloc `db.atomic()`.
3. **Vérification des Contrats UI/UX & Design System :**
   - Croiser les vues avec `DESIGN.md` (couleurs en dur, `refresh_theme` manquant, absence d'`ElidedLabel`, absence d'`EmptyState`, oublis `self.tr()`).
4. **Matrice de Sévérité & Génération des Tickets Obsidian :**
   - Classer chaque anomalie selon la grille de priorité d'AnkiForge :
     - **🔴 P0 (Critique / Bloquant)** : Crash C++/Shiboken, corruption SQLite / `database is locked`, faille XSS/Sandbox, perte de données utilisateur, contournement du Garde-Fou 2PC MCP.
     - **🟡 P1 (Important / Dette Structurelle)** : Gel du thread GUI (I/O synchrone), fuite mémoire `QObject`/`QWebEngineView`, requête $N+1$ sur grande collection, violation majeure MVVM ou `DESIGN.md` (thème Clair/Sombre cassé).
     - **🟢 P2 (Standard / Qualité & Ergonomie)** : Factorisation de widgets dupliqués, amélioration de la hiérarchie visuelle, test `pytest-qt` manquant ou flakey, oubli d'accessibilité/`tr()`.
     - **⚪ P3 (Confort / Cosmétique)** : Micro-ajustement d'espacement, nettoyage de code mort ou typage statique interne.
# Grille d'Analyse Post-Mortem & Typologie des Erreurs Agentiques 🔍

Ce document fournit la typologie canonique des défaillances agentiques observées lors des sessions de développement et les stratégies de remédiation associées pour durcir les compétences dans AnkiForge.

---

## 1. Typologie des Défaillances Agentiques Récurrentes

### T-1 : Biais de Précipitation vers la Clôture (Early Completion Bias)
- **Symptôme** : L'agent voit ses tests et sa porte de vérification passer, et saute immédiatement aux étapes de clôture du ticket ou de proposition de commit, omettant une étape intermédiaire requise (ex: revue de code à deux axes, mise à jour des métadonnées, audit des docstrings).
- **Cause racine** : L'étape de revue est perçue comme "consultative" ou secondaire plutôt que comme une précondition bloquante.
- **Remédiation** : Transformer l'étape en garde-fou bloquant avec formulation impérative :
  > ⛔ **Garde-fou bloquant** : Il est formellement INTERDIT de modifier le statut du ticket à `Terminé` ou de formuler une proposition de commit avant d'avoir formellement exécuté l'étape X et présenté son rapport.

### T-2 : Écrasement Silencieux d'État Concurrent (Blind State Overwrite)
- **Symptôme** : L'agent utilise `edit_file` ou `write_file` sur un fichier partagé ou vivant (comme le Kanban `Avancement du projet.md`) en s'appuyant sur une version obsolète mémorisée dans son contexte, écrasant les modifications manuelles de l'utilisateur ou d'un processus concurrent.
- **Cause racine** : Absence de relecture immédiate de la version disque/Git courante (`HEAD`) juste avant l'écriture, ou édition par gros blocs plutôt que par substitution chirurgicale mono-ligne.
- **Remédiation** : Imposer la vérification préalable de `git diff` / `git status` et restreindre les éditions à des cibles atomiques strictes.

### T-3 : Méconnaissance des Frontières Multi-Dépôts (Multi-Repo Blindness)
- **Symptôme** : L'agent applique des commandes `git` sur la racine du projet en pensant englober un sous-dossier, alors que celui-ci est un sous-dépôt indépendant avec son propre `.git` (ex: `ankiforge_obsidian/` ignoré par le `.gitignore` racine).
- **Cause racine** : Omission de la topologie Git dans la spécification du skill concerné.
- **Remédiation** : Documenter explicitement la structure multi-dépôts dans le `SKILL.md` et interdire les commandes globales transverses aveugles.

### T-4 : Hypothèse Non Vérifiée sur l'i18n (Silently Broken Markers)
- **Symptôme** : Utilisation de `self.tr("Message : %1", val)` dans un widget Qt sans réaliser que `self.tr()` ne supporte pas la substitution de paramètres, conduisant à des marqueurs bruts affichés à l'écran.
- **Cause racine** : Confusion avec les méthodes de formatage classiques.
- **Remédiation** : Audit automatisé fail-fast (`tests/utils/test_i18n_audit.py`) et rappel strict de l'ADR 0013 dans les skills UI.

### T-5 : Biais de Regroupement Hâtif / Cadrage en Vrac (Bulk Decision Bias)
- **Symptôme** : Face à plusieurs axes de refonte ou plusieurs décisions architecturales, l'agent regroupe tout en bloc dans le chat textuel au lieu d'interroger l'utilisateur de manière unitaire et méthodique.
- **Cause racine** : Précipitation à vouloir solder l'ensemble du périmètre en une passe conversationnelle, négligeant l'outil natif interactif de choix.
- **Remédiation** : Imposer la règle d'incrémentalité stricte (une modification = une série de questions ciblées) via l'outil interactif natif (`ask_question` dans Antigravity) avec option recommandée en tête et repli texte si le contexte sature.

### T-6 : Cécité de l'Audit Statique Superficiel (Shallow Audit Blindness)
- **Symptôme** : Un script de gouvernance valide le statut `PASS` en se basant sur des métriques superficielles (présence de balises, longueur), masquant des liens cassés, des références décalées ou du code issu d'autres langages/stacks.
- **Cause racine** : Absence de validation des cibles réelles sur disque (liens Markdown, chemins d'ADRs, détection de patterns de langages interdits).
- **Remédiation** : Enrichir le script d'audit statique (`auditer_coherence_skills.py`) pour vérifier l'existence physique de chaque ADR et lien relatif, et interdire les blocs de langages étrangers (TypeScript/JSX dans un repo Python).

### T-7 : Couplage de Décompte d'Éléments d'Interface (Rigid UI Element Count Assertions)
- **Symptôme** : L'ajout d'un nouvel onglet, bouton ou entrée dans une interface modale (ex: `SettingsModal`) fait échouer plusieurs tests transverses en dur (`assert count == 8`).
- **Cause racine** : Tests de régression écrits avec des constantes numériques absolues plutôt qu'une inspection sémantique des onglets présents.
- **Remédiation** : Documenter la vigilance d'impact dans `ui-pyside6-design/SKILL.md` et mettre à jour de manière synchronisée l'ensemble des galeries et suites de tests de composants (`test_settings_modal.py`, `test_dialog_gallery.py`, etc.).

### T-8 : Émojis Résiduels dans les Composants d'Action (Action Label Emoji Leaks)
- **Symptôme** : L'agent insère spontanément des émoticônes dans le libellé texte d'un bouton (`PrimaryButton("📖 Ouvrir")`) par mimétisme conversationnel, en violation de la Règle 8 du Design System.
- **Cause racine** : Absence de rappel strict dans les compétences de design UI imposant l'exclusivité des icônes Phosphor vectorielles (`load_phosphor_icon`).
- **Remédiation** : Garde-fou bloquant formel dans `ui-pyside6-design/SKILL.md` interdisant tout emoji décoratif dans les boutons et libellés d'interface.

### T-9 : Contexte Linguist Dégradé dans les Méthodes de Classe (Classmethod Linguist Degradation)
- **Symptôme** : Appel de `dlg.tr("...")` sur une variable locale d'une `@classmethod` de fabrique (ex: `open_guide`), assignant un contexte de chaîne invalide (`<name>dlg</name>`) dans les fichiers `.ts`.
- **Cause racine** : Méconnaissance du mécanisme de résolution de métadonnées Qt Linguist où `QObject.tr()` utilise le type statique de l'appelant.
- **Remédiation** : Rappel impératif dans `ui-pyside6-design/SKILL.md` d'utiliser `cls.tr("...")` ou la fonction libre `tr("...")` dans toute méthode de classe.

### T-10 : Biais d'Invocation Prématurée de la Porte Canonique (Premature Verification Gate Invocation)
- **Symptôme** : L'agent lance directement `script/verify.py` après une passe de codage sans effectuer un pré-nettoyage rapide `ruff check --fix . && ruff format .`, provoquant un échec fail-fast précoce sur des imports orphelins ou du formatage trivial.
- **Cause racine** : Omission de la boucle réflexe de pré-nettoyage linter avant d'engager la chaîne complète de vérification (tests + bandit).
- **Remédiation** : Formalisation dans `implement/SKILL.md` de la sous-étape obligatoire de pré-nettoyage linter et de formatage avant l'invocation de la porte.

### T-11 : Fuite de Threads Asynchrones au Teardown de Test Qt (Asynchronous Worker Leak on Qt Teardown)
- **Symptôme** : Un test UI pilotant un widget avec worker d'arrière-plan (`QThread`) s'achève pendant que le thread est actif, provoquant une erreur `sqlite3.OperationalError: database table is locked: sqlite_master` au démontage de la fixture `mock_db`.
- **Cause racine** : Absence d'attente de synchronisation explicite (`worker.wait()` ou `qtbot.waitUntil`) avant la fin du corps de test.
- **Remédiation** : Règle impérative dans `ui-pyside6-design/SKILL.md` et `implement/SKILL.md` imposant la terminaison contrôlée de tout thread asynchrone avant le teardown.

### T-12 : Crash Natif C++ QtMultimedia en Test Headless (Native Thread Segfault Leak)
- **Symptôme** : Un test UI ou un worker pytest xdist plante brutalement avec `Fatal Python error: Segmentation fault (<no Python frame>)` et redémarre en boucle ("workers plantent les uns derrière les autres et se relancent, c'est infini").
- **Cause racine** : Appel de `setSource(...)` sur une vraie instance `QMediaPlayer` dans un test. QtMultimedia (FFmpeg / AVFoundation sous macOS) démarre un pipeline de décodage asynchrone natif. Lors du démontage du widget par `cleanup_qt_widgets`, le thread C++ en arrière-plan tente d'accéder à la mémoire libérée.
- **Remédiation** : Mocker systématiquement `setSource` et `play` sur `player` dans les tests headless. Interdiction formelle de laisser `setSource` s'exécuter nativement en test unitaire/UI. Règle inscrite dans `verification-environnement/SKILL.md` et `ui-pyside6-design/SKILL.md`.

### T-13 : Blocage de Boucle d'Événements Qt par Dialogue Modal Synchrone (Headless QMessageBox Hang)
- **Symptôme** : Un test UI se fige jusqu'au timeout du worker (30s) ou bloque indéfiniment la suite de tests.
- **Cause racine** : Appel direct de méthodes modales synchrones (`QMessageBox.information(self, ...)`, `QMessageBox.warning(...)` ou `box.exec()`) sans possibilité de simulation ou d'interception dans les tests headless.
- **Remédiation** : Découpler systématiquement les dialogues sous forme de méthodes auxiliaires de classe (`_notify_info(title, text)`, `_confirm_delete(...)`) permettant un mock immédiat via `monkeypatch` sans bloquer la boucle Qt.

### T-14 : Présomption de Jetons de Design System Inexistants (DesignTokens Phantom Keys)
- **Symptôme** : Crash à l'exécution ou en test UI avec `AttributeError: type object 'DesignTokens' has no attribute 'BORDER_HOVER'` ou `BG_SECONDARY`.
- **Cause racine** : Biais de familiarité web/CSS où l'agent présume de l'existence de jetons plausibles (`BG_SECONDARY`, `BORDER_HOVER`, `BG_CARD`) sans vérifier la définition réelle dans `src/ankiforge/ui/theme.py`.
- **Remédiation** : Formalisation dans `ui-pyside6-design/SKILL.md` et `implement/SKILL.md` du catalogue exhaustif des jetons réels de `DesignTokens` (`BG_MAIN`, `BG_SIDEBAR`, `BG_PANEL`, `BG_INPUT`, `BG_HOVER`, `BG_ACTIVE`, `BORDER_COLOR`, `BORDER_FOCUS`, `BORDER_LIGHT`) et interdiction d'utiliser un jeton sans inspection préalable de `theme.py`.

### T-15 : Désynchronisation Silencieuse des Catalogues de Traduction `.ts` (Translation Catalog Drift on `tr()` Alteration or Removal)
- **Symptôme** : Échec inattendu en fin de suite de tests sur `tests/utils/test_i18n_audit.py::test_committed_catalog_matches_a_fresh_extraction` avec `AssertionError: Catalogues périmés (ankiforge_fr.ts, ankiforge_en.ts). Régénérer : uv run python script/extract_translations.py`.
- **Cause racine** : L'agent ajoute, modifie OU supprime un appel `tr("...")` (par exemple lors du remplacement d'un bouton textuel `QPushButton(self.tr("+"))` par un bouton d'icône `QToolButton`), mais oublie que la suppression d'une chaîne du code source invalide immédiatement l'exactitude du catalogue `.ts` versionné par rapport à l'extraction à chaud.
- **Remédiation** : Règle impérative dans `ui-pyside6-design/SKILL.md`, `implement/SKILL.md`, `verification-environnement/SKILL.md` et `diagnosing-bugs/SKILL.md` : dès qu'une chaîne traduisible `tr()` est ajoutée, modifiée ou **supprimée/retirée**, ré-exécuter obligatoirement `uv run python script/extract_translations.py` AVANT de lancer la porte `script/verify.py`.

### T-16 : Couplage du Catalogue d'Outils MCP et Tests d'Introspection (MCP Catalog Drift on New Tool Addition)
- **Symptôme** : L'ajout d'un nouvel outil FastMCP `@mcp.tool()` dans `src/ankiforge/services/ai/mcp_server.py` fait échouer `tests/ui/test_mcp_tool_catalog_widget.py::test_introspection_fastmcp_real_tools` (`AssertionError: assert N == M`) ou `test_mcp_dashboard_widget_integration_catalog_tab` (`assert tool_list.count() == M`), et laisse l'outil orphelin sans domaine ni niveau de garde-fou.
- **Cause racine** : Omission de la synchronisation entre le serveur FastMCP et le widget de catalogue d'outils IHM lors de l'extension de l'API MCP, et mise à jour partielle des assertions de décompte sans recherche exhaustive par grep.
- **Remédiation** : Règle impérative dans `pipeline-dag-ia/SKILL.md` et `implement/SKILL.md` : tout nouvel outil FastMCP doit être enregistré dans `TOOL_DOMAIN_MAP` et `TOOL_SAFEGUARDS_MAP` de `src/ankiforge/ui/views/consultant_view/widgets/mcp_tool_catalog_widget.py`, et une recherche grep systématique de l'ancien décompte (`grep -rn "== <ancien_compte>" tests/`) doit être menée pour actualiser simultanément l'ensemble des tests couplés au cardinal du catalogue.

### T-17 : Omission du Nouveau Modèle Peewee dans la Fixture de Test `mock_db` (Missing Model in Shared In-Memory Test DB)
- **Symptôme** : Lors de l'implémentation d'un nouveau modèle Peewee, les tests unitaires ou d'intégration échouent avec `sqlite3.OperationalError: no such table: <table_name>`.
- **Cause racine** : Le modèle a bien été déclaré dans `database/models/` et dans une migration, mais a été omis dans la liste `models` de la fixture `mock_db()` dans `tests/conftest.py`.
- **Remédiation** : Garde-fou explicite dans `peewee-expert/SKILL.md` et `implement/SKILL.md` : tout nouveau modèle Peewee doit être ajouté dans `tests/conftest.py` (`mock_db`) dès sa création. De plus, pour recharger une instance Peewee, utiliser exclusivement `Model.get_by_id(instance.id)` (jamais `refresh_from_db()` hérité de Django).

### T-18 : Test Asynchrone sous Pytest sans Marqueur Déclaré (Undeclared Asyncio Marker in Pytest)
- **Symptôme** : Utilisation du décorateur `@pytest.mark.asyncio` déclenchant des avertissements de marqueurs inconnus ou des erreurs de collection.
- **Cause racine** : Présomption de configuration du plugin pytest-asyncio alors que la convention du dépôt AnkiForge est l'encapsulation synchrone déterministe via `asyncio.run(...)`.
- **Remédiation** : Règle formelle dans `verification-environnement/SKILL.md` et `implement/SKILL.md` : encapsuler systématiquement les tests de coroutines asynchrones dans une fonction synchrone standard `def test_...(): asyncio.run(_run())`.

### T-19 : Boucle de Polling Inutile sur Tâche d'Arrière-Plan (Pointless Background Task Polling)
- **Symptôme** : L'agent appelle `manage_task(Action='status')` à répétition après avoir lancé une commande asynchrone (ex: `script/verify.py`), consommant des tours d'inférence inutiles.
- **Cause racine** : Omission du mécanisme de réveil réactif (Reactive Wakeup) où la plateforme notifie automatiquement l'agent dès la fin d'une tâche d'arrière-plan.
- **Remédiation** : Règle comportementale dans les instructions de vérification : dès qu'une commande est passée en tâche d'arrière-plan, l'agent doit informer brièvement l'utilisateur et clore son tour sans appeler d'outil de polling.

### T-20 : Présomption d'Icônes Phosphor Inexistantes (Phosphor Icon Phantom References)
- **Symptôme** : Échec en fin de chaîne de tests sur `tests/utils/test_icons_audit.py::test_all_codebase_icons_are_manifested` avec `AssertionError: Icônes appelées dans le code mais introuvables dans Phosphor : <nom> (regular)`.
- **Cause racine** : Biais de présomption où l'agent invente un nom plausible d'icône vectorielle (`ph.folder-star`, `ph.deck-edit`) sans vérifier au préalable le catalogue physique des icônes réelles embarquées.
- **Remédiation** : Règle impérative dans `ui-pyside6-design/SKILL.md` et `implement/SKILL.md` : avant tout appel à `load_phosphor_icon("ph.<nom>")`, vérifier impérativement l'existence du fichier SVG dans le manifeste `src/ressources/icons_manifest.txt` (ex: `grep "<nom>" src/ressources/icons_manifest.txt`).

### T-21 : Remplacement Non Unique sous `edit_file` (Ambiguous Context Overwrite)
- **Symptôme** : L'outil `edit_file` applique plusieurs remplacements non souhaités (`Made 2 replacements`) car la chaîne cible `Target` existe à l'identique dans plusieurs classes ou méthodes du même fichier, écrasant silencieusement une autre méthode.
- **Cause racine** : Sélection d'une cible `Target` trop courte sans contexte englobant (ex: signature générique `def refresh_theme(self, profile: Any) -> None: pass` dupliquée entre widgets voisins).
- **Remédiation** : Règle stricte dans `verification-environnement/SKILL.md` et `implement/SKILL.md` : toujours inclure le nom de la classe parente ou la méthode précédente dans `Target` pour garantir un remplacement unique et univoque (`Made 1 replacement`).

### T-22 : Présomption de Clés de Dictionnaires et Contrats de Retour (`API Return Key Guessing`)
- **Symptôme** : Les tests d'intégration ou le code métier échouent avec `KeyError` ou assertion sur `None` car l'agent devine le nom des clés de retour d'une méthode (ex: `applied_steps` vs `applied_steps_count`) ou présume de l'emplacement d'une valeur dans une structure hiérarchique (ex: variable dans `state_dict['variables']` vs `state_dict`).
- **Cause racine** : Biais d'intuition rapide où l'agent invente une clé plausible sans inspecter au préalable la définition de la fonction appelée ou le modèle de données.
- **Remédiation** : Règle impérative dans `verification-environnement/SKILL.md` et `implement/SKILL.md` : avant d'écrire une assertion sur un dictionnaire renvoyé ou d'extraire une valeur, toujours vérifier la structure réelle dans la définition du service ou de la méthode appelante (`read_file` ou inspection).

### T-23 : Rejet de Correspondance Exacte sur Fichiers Markdown Vivants (`Markdown Whitespace Mismatch`)
- **Symptôme** : L'outil `edit_file` échoue avec `target content not found in the file` lors de modifications dans le Kanban (`Avancement du projet.md`) ou les notes de tickets, à cause de variations invisibles dans les sauts de lignes consécutifs (`\n\n\n`) ou espaces de fin de ligne.
- **Cause racine** : Sélection de cibles `Target` multi-lignes englobant des espacements inter-sections variables ou non canoniques.
- **Remédiation** : Règle impérative dans `obsidian-vault/SKILL.md` et `implement/SKILL.md` : restreindre strictement la cible `Target` aux seules lignes stables de l'élément à déplacer ou modifier (ex: uniquement la ligne de la carte `- [ ] [[...]]` et le titre immédiat de la section cible), sans englober les sauts de ligne intermédiaires, ou recourir à une substitution par script Python ciblé en cas de décalage de blanc.

---

## 2. Matrice d'Évolution des Compétences Post-Incident

Lorsqu'un incident survient, appliquer la règle suivante :

| Type d'Incident | Action sur le Catalogue de Skills | Fichiers Cibles |
|---|---|---|
| Omission de revue ou de vérification | Ajout d'une précondition bloquante dans le workflow | `implement/SKILL.md`, `to-spec/SKILL.md` |
| Échec fail-fast linter évitable | Ajout d'une passe de pré-nettoyage ruff check/format | `implement/SKILL.md` |
| Fuite de worker / verrou SQLite en test Qt | Règle d'attente obligatoire des threads avant démontage | `ui-pyside6-design/SKILL.md`, `implement/SKILL.md` |
| Crash natif QtMultimedia / Segfault xdist | Mock obligatoire de `setSource` et `play` sur `QMediaPlayer` | `verification-environnement/SKILL.md`, `ui-pyside6-design/SKILL.md` |
| Blocage modal synchrone en test Qt | Découplage obligatoire des dialogues (`_notify_info`, `_confirm_*`) | `ui-pyside6-design/SKILL.md` |
| Conflit / écrasement dans le vault Obsidian | Clarification du sous-repo Git et renforcement des règles atomiques | `obsidian-vault/SKILL.md` |
| Erreur de Design System ou couleur codée en dur | Rappel de la règle 8, interdiction des émojis et catalogue exhaustif des tokens | `ui-pyside6-design/SKILL.md`, `implement/SKILL.md` |
| Confusion de substitution de paramètres i18n (`self.tr` vs `tr`) | Garde-fou bloquant sur l'utilisation exclusive de `tr()` racine pour `%1` | `ui-pyside6-design/SKILL.md`, `implement/SKILL.md` |
| Typage brisé par `.tuples()` / `.dicts()` Peewee | Convention d'accès direct aux attributs typés | `peewee-expert/SKILL.md` |
| Altération de contexte de traduction Linguist | Directive stricte `cls.tr()` vs `instance.tr()` | `ui-pyside6-design/SKILL.md` |
| Désynchronisation des catalogues `.ts` après modification/suppression `tr()` | Régénération obligatoire via `script/extract_translations.py` | `ui-pyside6-design/SKILL.md`, `verification-environnement/SKILL.md`, `diagnosing-bugs/SKILL.md` |
| Omission de modèle Peewee dans `tests/conftest.py` ou `refresh_from_db` erroné | Inscription obligatoire dans `mock_db` et `get_by_id()` | `peewee-expert/SKILL.md`, `implement/SKILL.md` |
| Dérive du catalogue FastMCP ou décompte de tests non synchronisé | Enregistrement `TOOL_DOMAIN_MAP`/`TOOL_SAFEGUARDS_MAP` et maj de test | `pipeline-dag-ia/SKILL.md`, `implement/SKILL.md` |
| Collision de nom de tests pytest ou syntaxe `@pytest.mark.asyncio` non supportée | Miroir strict d'arborescence et encapsulation `asyncio.run()` | `verification-environnement/SKILL.md`, `implement/SKILL.md` |
| Polling actif répété sur commande asynchrone | Règle de cession de tour pour réveil réactif (Reactive Wakeup) | `verification-environnement/SKILL.md` |
| Présomption d'icône Phosphor non manifestée (`T-20`) | Vérification obligatoire dans `src/ressources/icons_manifest.txt` | `ui-pyside6-design/SKILL.md`, `implement/SKILL.md` |
| Remplacement ambigu multiple sous edit_file (`T-21`) | Contexte englobant strict pour ciblage univoque | `verification-environnement/SKILL.md`, `implement/SKILL.md` |
| Surcharge Qt à arité incompatible sous Mypy Strict | Respect du sous-typage Liskov et signatures d'arité identiques | `ui-pyside6-design/SKILL.md`, `verification-environnement/SKILL.md` |
| Présomption de clés de retour de service (`T-22`) | Inspection obligatoire du contrat de fonction avant assertion de test | `verification-environnement/SKILL.md`, `implement/SKILL.md` |
| Décalage d'espacements Markdown sous edit_file (`T-23`) | Cibles mono-lignes strictes sans sauts de lignes inter-sections variables | `obsidian-vault/SKILL.md`, `implement/SKILL.md` |
| Nouvelle famille d'erreurs récurrente (≥ 3 occurrences) | Admission d'un nouveau skill spécialisé ou script d'audit | `.agents/skills/<nouveau-skill>/` |

---
name: verification-environnement
description: >
  Guide préventif des règles d'ingénierie et de codage pour les agents opérant dans AnkiForge. Énonce les interdits structurels non négociables (annotations complètes, logging sans print, Qt offscreen, exclusion des emojis, isolation des tests LLM) et détaille l'exécution de la porte canonique verify.py.
  Use when preparing code changes, implementing new features or bugfixes, starting a coding task, checking environment constraints, or when asked to "règles d'écriture", "règles de dev", "conventions agent", "non négociables", "vérifier environnement", or "règles projet".
---

# 🛡️ Règles d'Ingénierie & Vérification par Environnement — AnkiForge

En tant qu'**Agent de Développement opérant dans le dépôt AnkiForge**, ton rôle est d'assimiler les règles non négociables d'écriture et de conformité logicielle avant de coder, et d'exécuter la porte de vérification canonique à la fin de tes modifications.

## 1. Principes Directeurs : La Prière et la Contrainte

- **Le skill est une prière, le hook est une contrainte** : ce skill n'interdit rien par caprice ; il explicite le *pourquoi* technique de chaque règle.
- **Ne pas dupliquer la contrainte** : le contrôle automatique est garanti par le hook git pre-push natif (`.githooks/pre-push`) et le script canonique `script/verify.py`. Ce skill te préserve de brûler un cycle d'itération sur un interdit déjà écrit.

## 2. Règles Non Négociables d'Écriture (Le Pourquoi)

1. **Typage statique strict (`disallow_untyped_defs = true`)** :
   - *Pourquoi* : Fiabilité du refactoring et sécurité d'exécution sur tout `ankiforge.*`. Utiliser la syntaxe moderne Python 3.12+ (unions `X | Y`, generics PEP 695). Zéro `type: ignore` non justifié, interdiction absolue des `disable_error_code` globaux masquant les erreurs. Seuls `ui.*` et `database.migrations.*` bénéficient d'overrides ciblés dans `pyproject.toml`.
   - *Garantie automatique* : Mypy strict (`uv run mypy src/ankiforge`), étape 3 de `verify.py`.

2. **Interdiction formelle de `print()` (Règle T20)** :
   - *Pourquoi* : Haute performance sans I/O bloquante grâce au pipeline asynchrone `QueueHandler`/`QueueListener` via `logger = logging.getLogger(__name__)`. Le filtre `SecretRedactionFilter` anonymise automatiquement clés d'API (`sk-*`, `AIza*`), en-têtes et tokens. Un appel à `print()` court-circuite cette sécurité vitale et ralentit l'exécution.
   - *Garantie automatique* : Ruff règle T20 (`uv run ruff check .`), étape 1 de `verify.py`.

3. **Exécution Qt headless (`QT_QPA_PLATFORM=offscreen`)** :
   - *Pourquoi* : Les environnements de test, de CI et d'agents opèrent sans serveur graphique X11/Wayland. Tout widget instancié doit fonctionner en mode headless (`QT_QPA_PLATFORM=offscreen`, `ANKIFORGE_MOCK_WEBENGINE=1`), sans dialogue bloquant, et être systématiquement nettoyé via la fixture `cleanup_qt_widgets` ou `qtbot`.
   - *Garantie automatique* : `conftest.py` + pytest-qt headless, étape 5 de `verify.py`.

4. **Zéro emoji dans le code source** :
   - *Pourquoi* : Préserver la pureté UTF-8, éliminer les risques d'encodage multi-OS (Linux, Windows, macOS) et assurer la rigueur technique dans les noms de variables, fonctions, chaînes internes et logs applicatifs. Les emojis sont réservés aux interfaces graphiques explicites et au Kanban Obsidian.
   - *Garantie automatique* : Contrôle de style Ruff et revues.

5. **Mocks obligatoires pour tout appel LLM & Réseau** :
   - *Pourquoi* : Les tests doivent être déterministes, ultra-rapides (< 15s en fast) et autonomes. Aucun appel réel externe vers des API payantes ou locales (OpenAI, Gemini, Anthropic, Ollama) n'est toléré en test. Les fixtures pytest mockent systématiquement les réponses.
   - *Garantie automatique* : `ANKIFORGE_ENV=testing` + suite de tests mockés.

6. **Conventions d'arborescence et anglais technique** :
   - *Pourquoi* : L'architecture interne s'organise exclusivement en anglais technique (`src/ankiforge/utils/`, `services/`, etc.). L'usage de répertoires francisés alternatifs (ex. `ressources/` au lieu de `utils/`) est banni pour éliminer les divergences d'import constatées dans `initial_seed.py`.

7. **Fixtures audio et conteneurs multimédias valides (Zéro faux MP3 tronqué)** :
   - *Pourquoi* : Les composants de lecture et de synthèse (`QMediaPlayer`, `AudioPlayerWidget`, `TTSSettingsTab`) délèguent le décodage au backend FFmpeg natif. L'injection d'octets arbitraires ou de trames MPEG tronquées (`b"\xff\xfb\x90\x44" * 50`) provoque des avertissements de détection (`Format mp3 detected with low score`, `Failed to find two consecutive MPEG audio frames`) et pollue la sortie de tests.
   - *Garantie automatique* : Utiliser impérativement la constante `MINIMAL_VALID_MP3_BYTES` ou la fixture `minimal_valid_mp3_path` définies dans `tests/conftest.py` (flux ID3v2.3 + 10 trames MPEG-1 Layer 3 valides).

8. **Isolation et mock de `QMediaPlayer.setSource` en test headless (Zéro fuite FFmpeg asynchrone)** :
   - *Pourquoi* : Même avec un conteneur audio valide, dès que `setSource()` est invoqué sur une vraie instance `QMediaPlayer`, QtMultimedia initialise des threads de décodage asynchrones natifs (FFmpeg / AVFoundation sous macOS). Lorsque l'instance du widget ou du player est détruite au teardown du test, le thread d'arrière-plan C++ tente d'accéder à l'objet désalloué, provoquant un `Fatal Python error: Segmentation fault` natif qui tue le worker pytest-xdist et le fait redémarrer indéfiniment.
   - *Garantie automatique* : Dans tout test unitaire ou UI pilotant la synthèse ou la lecture vocale, mocker systématiquement `setSource` (et `play`) sur `QMediaPlayer` pour empêcher tout démarrage de threads natifs asynchrones non maîtrisés.

9. **Synchronisation des catalogues de traduction `.ts` (Zéro dérive Linguist)** :
   - *Pourquoi* : Le test d'intégrité i18n (`tests/utils/test_i18n_audit.py::test_committed_catalog_matches_a_fresh_extraction`) vérifie rigoureusement que les fichiers versionnés `src/ankiforge/resources/translations/ankiforge_{fr,en}.ts` sont strictement identiques à une extraction fraîche du code source. Tout ajout, modification ou **retrait/suppression** d'un appel `tr(...)` (ex: remplacement d'un bouton texte `QPushButton(tr("+"))` par un bouton d'icône `QToolButton`) sans régénération des catalogues entraîne l'échec immédiat de la suite de tests.
   - *Garantie automatique* : Exécuter systématiquement `uv run python script/extract_translations.py` dès qu'un appel `tr(...)` est touché ou retiré.

10. **Exécution des tests asynchrones via `asyncio.run()` (Zéro `@pytest.mark.asyncio`)** :
    - *Pourquoi* : Le projet n'active pas le plugin `pytest-asyncio` avec marqueur personnalisé. L'usage de `@pytest.mark.asyncio` déclenche des avertissements `PytestUnknownMarkWarning` ou des erreurs de collection. La convention unifiée du dépôt est d'encapsuler la coroutine dans une fonction de test synchrone classique `def test_...(): asyncio.run(_run())`.

11. **Miroir strict des répertoires de tests (Zéro collision pytest `import file mismatch`)** :
    - *Pourquoi* : Pour tout module sous `src/ankiforge/path/subpath/module.py`, le fichier de test correspondant doit se situer dans `tests/path/subpath/test_module.py`. Créer des fichiers de même nom dans des répertoires racourcis (ex: `tests/ai/test_staged_bundles.py` en parallèle de `tests/services/ai/test_staged_bundles.py`) provoque une erreur bloquante `import file mismatch` de pytest due à la collision de cache de bytecode `__pycache__`.

12. **Cession de tour sur commande en tâche de fond (Zéro boucle de polling)** :
    - *Pourquoi* : Lorsque la porte canonique ou une commande lourde passe en tâche d'arrière-plan, la plateforme assure un réveil réactif (Reactive Wakeup) automatique dès la fin du processus. Interroger manuellement le statut via des outils de polling consomme des tours de boucle et de l'énergie inutilement. L'agent doit informer brièvement l'utilisateur et terminer son tour sans outil supplémentaire.

13. **Vérification obligatoire des icônes Phosphor (Zéro icône fantôme non manifestée)** :
    - *Pourquoi* : Le test d'audit `tests/utils/test_icons_audit.py::test_all_codebase_icons_are_manifested` vérifie rigoureusement que toute icône appelée dans le code via `load_phosphor_icon("ph.<nom>")` figure dans le manifeste canonique `src/ressources/icons_manifest.txt`. Présumer de l'existence d'une icône vectorielle plausible sans vérification préalable (ex: `folder-star`) entraîne un échec immédiat de la suite de tests.
    - *Garantie automatique* : Toujours vérifier l'existence dans le manifeste (`grep "<nom>" src/ressources/icons_manifest.txt`) avant d'introduire une nouvelle référence d'icône.

14. **Ciblage univoque sous `edit_file` (Zéro remplacement accidentel multiple)** :
    - *Pourquoi* : L'outil `edit_file` remplace sans avertissement l'intégralité des occurrences correspondant à la chaîne `Target`. Si une signature ou un corps de méthode générique (ex: `def refresh_theme(self, profile: Any) -> None: pass`) est dupliqué entre plusieurs classes voisines, une cible trop restreinte écrase silencieusement des classes tierces.
    - *Garantie automatique* : Toujours englober dans `Target` le nom de la classe parente ou la méthode contiguë pour garantir un remplacement unique et univoque (`Made 1 replacement`).

15. **Vérification des contrats de retour de service (Zéro présomption de clé de dictionnaire)** :
    - *Pourquoi* : Deviner le nom d'une clé de dictionnaire renvoyée par un service ou un registre (ex: `applied_steps` vs `applied_steps_count`, ou chercher une variable à la racine plutôt que sous `variables`) provoque des `KeyError` ou des assertions sur `None` en test.
    - *Garantie automatique* : Toujours inspecter la définition physique de la méthode ou du modèle retourné avant d'écrire une assertion ou d'extraire une valeur.

16. **Ciblage chirurgical sur fichiers Markdown vivants (Zéro rejet de correspondance exacte)** :
    - *Pourquoi* : Les fichiers Markdown vivants (comme le Kanban `Avancement du projet.md`) accumulent des sauts de lignes consécutifs (`\n\n\n`) invisibles à la lecture simple, provoquant l'erreur `target content not found in the file` sous `edit_file`.
    - *Garantie automatique* : Restreindre la cible `Target` aux seules lignes strictes de l'élément à déplacer sans englober les espaces blancs ou sauts de ligne inter-sections variables, ou recourir à un script Python chirurgical si nécessaire.

## 3. Commande Canonique Unique de Vérification

Toute modification de code doit impérativement être validée via la porte canonique unique :

```bash
uv run python script/verify.py              # vérification complète rapide (< 30s)
uv run python script/verify.py --fix        # auto-correction ruff avant vérification
uv run python script/verify.py --all-tests  # vérification avec suite complète
```

### Méthodes d'exécution par environnement d'agent

- **Antigravity / Gemini CLI** : Invoquer l'outil `run_command` avec `CommandLine: "uv run python script/verify.py"` et `Cwd` sur le workspace.
- **Claude Code** : Invoquer l'outil `Bash` avec `uv run python script/verify.py`.
- **Terminal & Scripts** : Exécuter la commande directement dans le shell.

### Le hook pre-push versionné

Situé dans `.githooks/pre-push`, il s'exécute automatiquement avant tout `git push`. En cas d'échec d'une seule étape de `script/verify.py`, le push est rejeté.

## ⛔ Ne PAS utiliser ce skill si...

- Tu souhaites auditer la conformité globale ou produire un rapport formel sous `audits/` : utiliser `audit-qualite-code`, `audit-tests-ci` ou `audit-ankiforge`.
- Tu prépares des propositions de commits atomiques à la fin d'une tâche : utiliser `proposer-commits`.
- Tu travailles spécifiquement sur le modèle de données Peewee ou une migration SQLite : utiliser `peewee-expert`.

## Commandes Canoniques & Cycle de Vie

Toutes les opérations d'ingénierie s'exécutent via l'environnement virtuel géré par `uv` (Python 3.12+).

### Installation des Dépendances
```bash
uv sync                         # dépendances d'exécution standard
uv sync --group dev             # dépendances de développement, tests, linters et documentation
```

### Lancement de l'Application
```bash
uv run ankiforge                # environnement de profil par défaut
uv run ankiforge --dev          # environnement isolé de développement (~/.ankiforge-dev)
uv run ankiforge --prod         # forcer l'environnement de production (~/.ankiforge)
uv run ankiforge --smoke-test   # vérification d'intégrité binaire et de démarrage sans interface
uv run ankiforge --clone-prod-to-dev # synchroniser la base prod vers dev pour investigation
```

### Exécution des Tests
```bash
uv run pytest                   # suite complète de tests (headless Qt via pytest-qt)
uv run pytest -m "not slow"     # suite rapide pré-push (< 15s)
uv run pytest -m unit           # tests unitaires purs et algorithmiques (< 2s, sans base ni Qt)
uv run pytest -m integration    # tests d'intégration base de données Peewee et services
uv run pytest -m ui             # tests headless PySide6 (widgets, signaux, formulaires)
uv run pytest tests/path/test_file.py::TestClass::test_method
```

### Porte de Vérification Canonique Unique (Verification Gate)
La commande canonique unique `script/verify.py` applique séquentiellement l'ensemble des garde-fous de qualité avant tout push :
```bash
uv run python script/verify.py              # chaîne canonique : drift, ruff, format, mypy, bandit, pytest fast
uv run python script/verify.py --fix        # auto-correction (instructions, formatage et fix ruff) avant contrôle
uv run python script/verify.py --all-tests  # exécution avec la totalité des tests (sans filtre slow)
uv run python script/verify.py --install-hook # installe et active le hook natif versionné .githooks/pre-push
```

### Gouvernance des Compétences Agentiques & Métadonnées
```bash
uv run python .agents/skills/gouvernance-skills/scripts/auditer_coherence_skills.py # audit statique des 50 skills
```

### Documentation Zensical
```bash
uv run zensical serve           # serveur de documentation local live (http://127.0.0.1:8000)
uv run zensical build           # compilation statique du site documentaire dans site/
```

### Extension C Native (Levenshtein)
```bash
gcc -shared -o c_ext/levenshtein_distance.so -fPIC c_ext/levenshtein_distance.c  # Linux/macOS
```

### Captures & Miniatures de Layouts
```bash
uv run python script/capture_view.py --layout-thumbnails # régénère les miniatures haute résolution
```

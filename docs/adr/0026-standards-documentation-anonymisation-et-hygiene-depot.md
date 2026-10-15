# Standards de documentation, hygiène du dépôt et anonymisation intégrale

Ce document formalise les standards de documentation du code source d'AnkiForge, la purge hygiénique des fichiers inutiles du dépôt Git, la politique d'épuration des commentaires et l'anonymisation intégrale du projet pour un partage ouvert.

## Statut
Accepté

## Décisions

### 1. Standard de documentation de code (Docstrings Google sans redondance de type)
- **Convention** : Adoption stricte du **Google Docstrings Style** (PEP 257 + Google Style Guide), rédigé exclusivement en **français** (règle 1 de `GEMINI.md`).
- **Absence de redondance de typage** : Le projet étant déjà soumis à un typage statique strict à 100% avec `mypy` (`disallow_untyped_defs = true`), les types sont portés nativement par les signatures Python 3.12+ (`def func(param: int) -> str:`). Les docstrings omettent donc la mention du type dans les sections `Args:` (`param: description` et non `param (int): description`), prévenant tout risque de désynchronisation.
- **Granularité & Périmètre (Approche équilibrée)** :
  - Tout **module**, toute **classe publique**, et toute **méthode/fonction publique d'API métier** (services, repositories, modèles de base de données, calculateurs, pipelines DAG) dispose d'une docstring claire explicitant sa finalité, ses arguments et sa valeur de retour.
  - Les accesseurs triviaux et slots d'interface graphique dont le rôle est évident par leur nommage ne sont pas surchargés artificiellement.
  - Les règles de formatage pydocstyle Ruff (`D200`, `D205`, `D212`, `D415` sous convention Google) sont intégrées à la configuration `pyproject.toml`.

### 2. Politique de nettoyage des commentaires (Purge du bruit, sanctuarisation architecturale)
- **Suppression du bruit** : Élimination systématique des commentaires de simple paraphrase (ce que fait le code de façon triviale quand le nom de variable/fonction suffit, ex: `# Initialisation`, `# Importation`).
- **Sanctuarisation architecturale** : Conservation absolue des commentaires explicitant *pourquoi* une implémentation atypique a été retenue : contraintes de verrous SQLite WAL sous Windows avec `closing()`, contournements de packaging macOS/Nuitka pour `sys.path` et certificats SSL, directives d'exclusion de linter (`noqa`, `type: ignore`, `pragma: no cover`), et références aux ADRs.

### 3. Hygiène et assainissement du dépôt Git
- **Suppression des journaux et résidus temporaires** : Retrait immédiat de `log.txt` de l'arbre Git et verrouillage dans `.gitignore` (`*.log`, `log.txt`).
- **Purge des compétences orphelines du template externe** : Suppression intégrale du répertoire `.github/skills/` (contenant des compétences externes résiduelles et 36 liens symboliques brisés). La source unique de vérité des 50 compétences d'AnkiForge demeure `.agents/skills/`.
- **Suppression des scripts jetables (Scratch)** : Élimination des scripts d'analyse de transcripts d'agents (`script/tools/parse_*.py`), des anciens utilitaires de refonte UI (`script/ui_rebuild/`), des tests jetables (`script/dev/`) et des scripts de patch partiels devenus obsolètes.
- **Classement de la documentation racine** : Suppression des plans de refonte déjà intégralement livrés et testés (`plan_modaux_improvements.md`, `refonte_batch_factory.md`), et migration de `user_journeys_documents.md` vers `docs/features/parcours_documents.md` avec indexation dans `zensical.toml`.

### 4. Anonymisation intégrale et neutralité pour l'open-source
- **Chemins absolus** : Élimination de tout chemin local en dur (`/Users/...`) au profit de chemins relatifs basés sur la racine du projet ou de chemins standards `platformdirs`.
- **Mentions légales et maquettes** : Remplacement des mentions nominatives dans `LICENSE.md` par `Skyl9 / AnkiForge Contributors`, et anonymisation des maquettes de démonstration (`Utilisateur`).
- **Neutralisation des compétences d'ingénierie** : Renommage canonique des compétences d'aiguillage et de configuration du flux d'ingénierie :
  - `ask-tristan` devient **`ask-forge`**
  - `setup-tristan-workflow` devient **`setup-forge-workflow`**
  - `Workflow Tristan` devient le **Flux d'ingénierie AnkiForge** (dans l'ADR 0015, le glossaire et la documentation).

## Conséquences
- La base de code devient autonome, propre, et prête à être auditée ou distribuée publiquement sans résidus locaux ni empreinte personnelle.
- La documentation du code est uniforme, rédigée en français, et vérifiable par l'outillage de formatage.
- Le cycle de vie des compétences agentiques et des instructions canoniques est préservé et garanti par les suites d'audits `auditer_coherence_skills.py` et `sync_agent_instructions.py`.

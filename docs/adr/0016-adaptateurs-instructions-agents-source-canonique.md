# Adaptateurs d'instructions unifiés et source canonique par transclusion délimitée

AnkiForge opère avec une multiplicité d'environnements et d'outils d'assistance agentique (Antigravity/Gemini CLI, Anthropic Claude Code, GitHub Copilot, runtimes open-source compatibles `AGENTS.md`). Jusqu'alors, les instructions étaient rédigées de manière éclatée et manuelle dans chaque fichier cible (`GEMINI.md`, `AGENTS.md`, `.github/copilot-instructions.md`, tandis que `CLAUDE.md` était absent). Cette duplication a produit une dérive documentaire silencieuse : commandes parallèles au lieu de la porte canonique `script/verify.py`, omissions des règles non négociables et des faits d'architecture récents, et contradictions de statuts.

Afin de garantir qu'aucun agent ne reçoive d'instructions périmées tout en préservant le format d'orchestration ou de persona propre à chaque outil, nous unifions les instructions du dépôt autour d'une source unique de fragments canoniques injectés par transclusion délimitée sous contrôle déterministe fail-fast.

## Statut
Accepté

## Options considérées

1. **Rédaction manuelle indépendante par fichier cible** : Rejeté. Cause directe de la divergence constatée. Dès qu'une nouvelle commande, un nouvel ADR ou une règle d'ingénierie est introduit, sa propagation manuelle à travers quatre fichiers est statistiquement vouée à l'oubli.
2. **Génération totale à 100% depuis un template unique** : Rejeté. Les différents environnements agentiques ont des contraintes et des attentes syntaxiques incompatibles : `GEMINI.md` est un prompt système d'orchestrateur avec déclaration d'outils, `CLAUDE.md` exige une concision chirurgicale pour le CLI Anthropic, `.github/copilot-instructions.md` guide la complétion contextuelle en IDE, et `AGENTS.md` sert de référence exhaustive au standard multi-agent. Écraser ces fichiers par un clone identique dégraderait la performance cognitive propre à chaque runtime.
3. **Linter passif par analyse syntaxique sans génération** : Rejeté. Contrôler par expressions régulières qu'un fichier manuel mentionne telle ou telle consigne signale l'erreur sans fournir la réparation, et devient un fardeau de maintenance à chaque reformulation de phrase.
4. **Source modulaire sous `.agents/instructions/` et transclusion délimitée par balises** : Retenu. Les règles, commandes et connaissances partagées sont rédigées dans des fragments modulaires indépendants. Chaque adaptateur conserve son en-tête et son persona spécifiques, et intègre les fragments nécessaires entre des balises HTML formelles (`<!-- CANONICAL:START:<bloc> -->` ... `<!-- CANONICAL:END:<bloc> -->`). Le script `script/sync_agent_instructions.py` assure l'injection, et le mode `--check` garantit l'isomorphisme strict.

## Conséquences

### 1. La source unique de vérité (`.agents/instructions/`)

La matière commune vit dans quatre fragments Markdown modulaires sous `.agents/instructions/` :
- `commandes.md` : Les commandes fondamentales du projet (installation `uv`, lancement de l'application, suites de tests, compilation de l'extension C Levenshtein, documentation Zensical, et la porte de vérification canonique unique `script/verify.py`).
- `regles_ingenierie.md` : Les règles d'ingénierie non négociables (restitution et communication exclusivement en français, typage statique strict mypy 100%, interdiction absolue de `print()`, isolation et mocks LLM dans les tests, pas de commit autonome sans validation utilisateur via `proposer-commits`, et internationalisation obligatoire via `tr()` selon l'ADR 0013).
- `architecture_points_cles.md` : Les invariants d'architecture d'AnkiForge (multi-profils, traçabilité par section ADR 0009, adresses de région et exclusion non destructive ADR 0010, moteur de DAG IA `PipelineOrchestrator`, serveur MCP persistant in-process, layouts & miniatures statiques, et RAG déterministe).
- `catalogue_skills.md` : L'inventaire consolidé des 50 compétences agentiques d'AnkiForge réparties par domaines d'ingénierie, avec leurs déclencheurs explicites et rôles canoniques.

### 2. Balises de transclusion délimitées et inviolabilité

Chaque bloc injecté dans un adaptateur cible est strictement délimité par une paire de balises HTML commentées portant le nom du fragment :
```markdown
<!-- CANONICAL:START:<nom_du_bloc> -->
<!-- ⚠️ BLOC AUTO-GÉNÉRÉ DEPUIS .agents/instructions/<nom_du_bloc>.md - NE PAS MODIFIER MANUELLEMENT -->
... contenu exact du fragment ...
<!-- CANONICAL:END:<nom_du_bloc> -->
```
Toute modification manuelle à l'intérieur de ces balises est interdite : le script de vérification compare le contenu interne au fragment source au caractère près.

### 3. Registre des adaptateurs cibles (`script/sync_agent_instructions.py`)

Le script `script/sync_agent_instructions.py` orchestre la projection des fragments selon un registre extensible déclarant pour chaque adaptateur son chemin et la liste ordonnée des blocs attendus :
- `GEMINI.md` : Préambule orchestrateur Antigravity + `commandes`, `regles_ingenierie`, `architecture_points_cles`, `catalogue_skills`.
- `AGENTS.md` : Référence rapide multi-agents + `commandes`, `regles_ingenierie`, `architecture_points_cles`, `catalogue_skills`.
- `CLAUDE.md` : Adaptateur pour Anthropic Claude Code CLI + `commandes`, `regles_ingenierie`, `architecture_points_cles`.
- `.github/copilot-instructions.md` : Adaptateur GitHub Copilot + `commandes`, `regles_ingenierie`, `architecture_points_cles`.

L'ajout ultérieur d'un adaptateur pour Cursor (`.cursorrules`) ou Windsurf (`.windsurfrules`) s'effectue par simple déclaration d'une entrée dans ce registre.

### 4. Porte de vérification canonique et auto-réparation

- **Fail-fast absolu en étape 1** : L'étape `instructions-drift` (`python script/sync_agent_instructions.py --check`) est insérée en tête de `CANONICAL_STEPS` dans `script/verify.py`. Si un adaptateur est altéré ou non synchronisé, le pre-push échoue en moins de 50 ms sans exécuter les étapes lourdes (mypy, bandit, pytest).
- **Auto-réparation sous `--fix`** : `uv run python script/verify.py --fix` invoque `sync_agent_instructions.py` en amont des vérifications, régénérant automatiquement les sections transcluses avant de lancer la suite de contrôles.

### 5. Politique linguistique unifiée

Tous les fragments canoniques et les sections transcluses sont rédigés en **français**. Les modèles d'IA modernes comprennent le français avec la même précision que l'anglais, éliminant ainsi le risque d'introduire des biais ou des retards de traduction entre adaptateurs.

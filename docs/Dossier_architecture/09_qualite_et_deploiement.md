# Qualité, Tests et Déploiement (AnkiForge)

Une application Desktop embarquant des LLMs, de l'ORM, du multi-threading Qt et du C natif est par nature hautement complexe. Voici les standards de vérification de l'industrie mis en place pour garantir la robustesse d'AnkiForge.

## 1. Standards de Code (Linting & Typage)
La qualité commence avant même d'exécuter le code.
* **Le Linter Universel (`ruff`) :** Remplacement de *flake8*, *black* et *isort*. `ruff` formate le code de manière déterministe et détecte les erreurs de syntaxe ou les mauvaises pratiques (ex: variables non utilisées) en quelques millisecondes.
* **Typage Statique (`mypy` ou `pyright`) :** Indispensable dans un projet avec l'ORM Peewee et PySide6. Toutes les fonctions critiques (notamment le moteur DAG et les appels API) doivent avoir des annotations de types strictes (`-> dict`, `-> PipelineStepModel`).

## 2. Stratégie de Tests (Pytest)
Les tests sont séparés en trois strates distinctes :
* **Tests du Core Backend (Peewee & IA) :** Utilisation de `pytest`.
  * *Règle d'or :* Les appels LLM dans les tests automatisés **doivent être mockés** (via `pytest-mock` ou `responses`). La CI ne doit jamais appeler une vraie API OpenAI ni attendre un modèle Ollama, sous peine d'être lente et coûteuse.
* **Tests d'Interface (PySide6) :** Utilisation de l'extension `pytest-qt`. Elle permet de faire des tests "Headless" (sans afficher la fenêtre à l'écran) pour simuler des clics sur des boutons et vérifier que les bons signaux Qt sont émis.
* **Évaluation de l'IA (Evals) :** Un sous-dossier de tests métier (ex: un dataset de 50 cartes Anki volontairement "malades"). Un script vérifie périodiquement que le "Linter Wozniak" généré par le LLM corrige bien ces cartes de manière pertinente.

## 3. Revue Continue Agentique & Arsenal de Skills (`.agents/skills/`)
C'est une exclusivité du projet. L'application dispose d'un catalogue structuré de compétences agentiques spécialisées (`.agents/skills/`) opérant selon le principe de divulgation progressive (Progressive Disclosure) :
* **Gouvernance & Méta-outils :**
  * `mise-a-jour-metadonnees` : Méta-skill de synchronisation des 15 fichiers de documentation/d'architecture ET d'audit/amélioration du catalogue de skills (scoring de maturité, `GEMINI.md`, `AGENTS.md`, Copilot).
  * `documentation-zensical` : Audit technique, enrichissement visuel Mermaid et proposition proactive d'améliorations de la documentation Zensical.
  * `audit-ankiforge` : Audit global de conformité aux 20 règles d'ingénierie de `GEMINI.md`.
* **Audits Techniques Spécialisés :** Huit auditeurs chirurgicaux ciblant les dépendances (`audit-dependances`), le design system (`audit-design-ui`), l'intégrité BDD (`audit-donnees`), le moteur DAG/MCP (`audit-ia-pipeline`), la réactivité Qt (`audit-performance`), la qualité du code (`audit-qualite-code`), la sécurité (`audit-securite`), et la rigueur des tests (`audit-tests-ci`).
* **Expertises Métier :** Conception Peewee avancée (`peewee-expert`) et inspection visuelle headless (`ui-screenshot`).
* *Workflow :* Avant toute PR ou merge majeur, les agents d'audit sont invoqués pour vérifier l'absence de régression architecturale (ex: appel bloquant sur le thread GUI, N+1 SQL, ou violation du typage strict).

## 4. Intégration et Déploiement Continu (CI/CD via GitHub Actions)
L'usine logicielle garantit que ce qui marche sur la machine du développeur marchera chez l'utilisateur.
* **Hooks de Pre-commit :** Interdiction de faire un commit git si le formatage `ruff` échoue.
* **La CI (Continuous Integration) :** À chaque *push* sur GitHub, une machine virtuelle lance :
  1. La compilation de l'extension C (Levenshtein) sur Mac, Windows et Linux.
  2. La suite complète `pytest`.
* **Le Déploiement (Nuitka) :** Lors de la publication d'une release sur GitHub, un workflow dédié déclenche Nuitka. Il compile l'application PySide6 en binaire natif (`.exe`, `.app`, `.AppImage`) et la publie automatiquement dans les *GitHub Releases*, prête à être téléchargée par les utilisateurs finaux (sans la lourdeur des dépendances locales Lazy-loadées).

## 5. Pratiques d'Ingénierie Avancées (God-Tier)
L'application impose des contraintes de test extrêmes pour prévenir toute régression :
* **Mutation Testing (`mutmut`) :** Pour garantir la robustesse des tests unitaires critiques (comme l'algorithme du Smart Merge), la CI modifie délibérément le code source (sabotage) et vérifie que la suite de tests échoue.
* **Fuzzing & Property-Based Testing (`Hypothesis`) :** Les inputs de l'interface PySide6 et les parseurs de paquets Anki sont bombardés par des données extrêmes (emojis, HTML corrompu, strings massives) pour garantir l'absence totale de crash système.
* **Tracing & Observabilité (Moteur DAG) :** Utilisation de logs structurés (`structlog`) ou de traces. Chaque étape de l'IA génère un fichier JSON local répertoriant les temps de réponse, le contexte du RAG, et le prompt exact. C'est vital pour déboguer l'orchestrateur.
* **Red Teaming (LLM-as-a-Judge) :** Les tests d'évaluation de l'IA (Evals) sont corrigés par un modèle de référence (ex: API Cloud puissante). À chaque release, le Linter Wozniak doit traiter un dataset complexe, et le "Juge" note la qualité de la reformulation pour empêcher toute dégradation de l'IA.

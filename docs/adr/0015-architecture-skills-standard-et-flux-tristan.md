# Architecture du parc de skills, standard agentskills.io et flux d'ingénierie Tristan

Le pilotage agentique d'AnkiForge repose sur un parc de 50 compétences autonomes (`.agents/skills/`). Afin de garantir la fiabilité du routage Just-In-Time (JIT), la modularité du code et l'absence de saturation de contexte pour les modèles, nous unifions la gouvernance de ces compétences autour du standard international **agentskills.io**, nous scindons les compétences à responsabilités multiples, nous comblons les angles morts structurels du projet, et nous alignons les flux d'ingénierie sur le gestionnaire de tâches Obsidian du dépôt avec une restitution obligatoirement francophone.

## Statut
Accepté

## Options considérées

1. **Compétences transverses « couteau-suisse » à forte charge documentaire** : Rejeté. Rassembler l'ingestion brute et le RAG déterministe dans un seul skill, ou la synchronisation de documentation et la gouvernance des compétences dans un autre, saturait le contexte (fichiers `SKILL.md` dépassant 400 lignes), diluait les déclencheurs sémantiques et provoquait des collisions Jaccard lors de l'aiguillage automatique.
2. **Format propriétaire libre sans contrainte de taille** : Rejeté. L'absence de limite sur les métadonnées entraînait des descriptions verbeuses (jusqu'à 1500 caractères), pénalisant la découverte au niveau 1 et empêchant l'interopérabilité avec les runtimes agentiques modernes.
3. **Adoption stricte du standard ouvert `agentskills.io` avec Progressive Disclosure à 3 niveaux** : Retenu. Chaque compétence respecte une hiérarchie stricte d'exposition d'information :
   - *Niveau 1 (Découverte JIT)* : Frontmatter YAML valide avec clé `description` concise (≤ 1024 caractères, impératif du standard) contenant des déclencheurs explicites (`Use when...`).
   - *Niveau 2 (Instruction active)* : Fichier `SKILL.md` condensé (≤ 150 lignes), focalisé sur les étapes d'exécution, les garde-fous et une section négative normalisée (`## When NOT to use this skill` ou `## ⛔ Ne PAS utiliser ce skill si...`).
   - *Niveau 3 (Approfondissement & outillage à la demande)* : Déport des guides méthodologiques exhaustifs et catalogues de patrons dans `references/*.md`, et des utilitaires d'automatisation dans `scripts/*.py`.
4. **Scission ciblée des doubles responsabilités** :
   - `ingestion-multimedia` est recentré sur le parsing brut et l'extraction multimédia (Marker OCR, documents, médias).
   - Le skill **`rag-smart-coverage`** prend en charge le découpage sémantique (`ChunkingService`), les vecteurs FAISS/ChromaDB et l'alignement de couverture déterministe (ADR 0009 et ADR 0010).
   - `mise-a-jour-metadonnees` est recentré sur la synchronisation des 15 fichiers de documentation et de configuration du dépôt post-feature.
   - Le skill **`gouvernance-skills`** hérite du méta-audit automatisé (`auditer_coherence_skills.py`), de la grille de maturité 5 axes, de la détection de collisions Jaccard et de la politique d'admission/scission.
5. **Couverture des trois piliers d'AnkiForge non couverts** :
   - **`ui-pyside6-design`** : développement d'interface PySide6, docking multi-fenêtré, tokens `DESIGN.md`, internationalisation `tr()` (ADR 0013) et tests headless `pytest-qt`.
   - **`pipeline-dag-ia`** : moteur d'orchestration `PipelineOrchestrator`, budgets de tokens, surcharge locale `persona_override.py` et intégration des outils du serveur MCP.
   - **`modeles-cartes-jinja`** : cycle de vie `NoteTypeModel`, atelier de styles Jinja2/HTML/CSS, occlusions et linter Wozniak des 20 règles.
6. **Flux Tristan & Intégration native Obsidian** :
   - Le routeur et l'installateur de flux sont baptisés **`ask-tristan`** et **`setup-tristan-workflow`**.
   - Suppression totale des artefacts éphémères non versionnés (`.scratch/`) dans les compétences de flux au profit direct des tickets Obsidian sous `ankiforge_obsidian/Tickets/` et du Kanban `Avancement du projet.md`.
   - Application stricte de la **règle anti-boucle** (one-shot pass) : un agent lit et écrit dans Obsidian de manière atomique, sans jamais relire circulairement une note qu'il vient de créer ou mettre à jour.
7. **Règle absolue de restitution francophone** : Retenu. Bien que les spécifications des compétences de flux puissent employer une terminologie en anglais pour la compatibilité avec les standards internationaux, toute interaction, rapport d'analyse, message d'étape et proposition de commit doit être restitué en **français**.

## Conséquences

### Gouvernance et contrôle continu par outillage
- L'intégrité du parc de 50 skills est vérifiée par `uv run python .agents/skills/gouvernance-skills/scripts/auditer_coherence_skills.py`.
- Le script applique un seuil d'échec sur les liens brisés, l'absence de déclencheurs, le dépassement des 1024 caractères de description, les collisions sémantiques Jaccard (seuil ≥ 0.45) et la synchronisation triangulaire entre les dossiers réels, `GEMINI.md`, `AGENTS.md` et `.github/copilot-instructions.md`.

### Élimination des collisions de routage
- La collision historique entre `grill-me` (exploration libre, sans document, questionnement conceptuel rapide) et `grill-with-docs` (interview exhaustive ancrée dans la documentation et les tickets du repo pour préparer une spec) a été résolue par des périmètres de déclenchement disjoints et des sections d'exclusion explicites.
- Les compétences volumineuses (`code-simplification`, `doubt-driven-development`, `source-driven-development`) ont déporté leurs matrices et patrons dans `references/`, réduisant leur empreinte contextuelle de plus de 60%.

### Alignement sur le cycle de vie du projet
- Le flux d'ingénierie passe de manière fluide de la découverte (`ask-tristan`), au cadrage (`grill-with-docs`), à la spécification (`to-spec`), à la planification Kanban (`to-tickets`), à l'implémentation TDD (`implement`, `tdd`), à la revue contradictoire (`doubt-driven-development`, `code-review`), à la vérification canonique (`verification-environnement`) et à la proposition de commits atomiques (`proposer-commits`).
- Aucune donnée métier ou de documentation d'architecture ne réside dans le vault Obsidian : Obsidian est une todo-list pure, la documentation canonique réside exclusivement dans `docs/` et `docs/adr/`.

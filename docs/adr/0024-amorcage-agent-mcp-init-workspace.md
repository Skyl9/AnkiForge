# Amorçage d'agent MCP : outil init_agent_workspace et génération de fichier d'instructions adapté

Pour permettre aux agents externes connectés via MCP de maximiser immédiatement leurs compétences sur les ~56 outils du serveur, nous introduisons un outil `init_agent_workspace` qui génère un fichier d'instructions méthodologiques directement dans le répertoire de travail de l'agent, adapté au format attendu par chaque plateforme cliente.

## Statut
Proposé

## Options considérées
1. **Ressource MCP pure (sans écriture disque)** : Rejeté comme livrable unique. La ressource est volatile et certains clients (Antigravity CLI, Cursor) bénéficient d'un fichier `instructions.md` / `.cursorrules` persistant. Retenu en complément : la ressource `workspace://agent-guide` expose le même contenu (version `generic`) en lecture temps réel.
2. **Fichier unique universel (`ANKIFORGE_GUIDE.md`)** : Rejeté. Chaque plateforme a ses conventions de fichier d'instructions (`GEMINI.md`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules`). Un fichier universel ne s'intègre nativement dans aucune.
3. **Fichier adapté au type de client avec template Jinja2 et injection dynamique** : Retenu. L'outil accepte un paramètre `agent_type` (`claude` | `gemini` | `cursor` | `generic`) et génère le fichier au format attendu. Le contenu rédactionnel (9 workflows, garde-fous anticipatifs) est rédigé dans des templates Jinja2 statiques versionnés dans `src/ankiforge/services/ai/templates/`, un par type d'agent avec blocs partagés via `{% include %}`. Le catalogue des outils et la liste des agents MCP configurés par l'utilisateur sont injectés dynamiquement à la compilation.
4. **Répertoire dédié sous le profil AnkiForge (`~/.ankiforge/profiles/<nom>/mcp_workspace/`)** : Rejeté. Le fichier est déposé dans le répertoire de travail propre à l'agent externe (son `cwd` ou un `workspace_path` explicite), qui est un dossier de l'OS de l'utilisateur dont AnkiForge ne gère pas le cycle de vie.
5. **Guide exhaustif dupliquant les validations serveur** : Rejeté. Le guide ne documente que les contraintes *anticipatives* (ce que l'agent doit faire en amont pour éviter un rejet), pas celles que le serveur applique déjà (ADR 0017 : contrôle d'hallucination de paquet, StagedPatch obligatoire).
6. **Mécanisme d'extension par répertoire de skills dédié** : Rejeté. L'infrastructure d'agents MCP existante (`create_or_update_mcp_agent` avec prompt Jinja2 et outils assignés) est réutilisée : le guide init référence automatiquement les agents configurés par l'utilisateur et leurs spécialités.

## Conséquences
- **API de l'outil** : `init_agent_workspace(agent_type="generic", workspace_path="", include_catalogue=True) -> str`. Si `workspace_path` est vide, le contenu est renvoyé sans écriture disque (mode ressource). Le retour inclut toujours le contenu intégral du guide et la liste des agents MCP configurés.
- **Mise à jour automatique** : le fichier généré contient un hash de version en en-tête (`<!-- ankiforge-guide-version: sha256:… -->`). Un outil léger `check_guide_version()` permet de comparer le hash sur disque avec la version courante. Le guide lui-même contient une instruction demandant à l'agent d'appeler `init_agent_workspace` en début de session.
- **9 workflows documentés** : Création de cartes, Audit & Qualité Wozniak, Exploration documentaire & RAG, Gestion des modèles de notes, Hygiène des tags, Inspection & Diagnostic, Orchestration des agents MCP, Albums & Planches, Utilitaires — chacun décrit comme une séquence d'outils de 3 à 5 étapes.
- **Divulgation progressive** : le guide suit le pattern du projet (workflows guidés en haut, catalogue catégorisé exhaustif en annexe).
- **Templates versionnés** : `src/ankiforge/services/ai/templates/mcp_init_guide_{agent_type}.md.j2` avec blocs partagés, compilés via l'environnement Jinja2 sandboxé existant (`_PROMPT_ENV`).
- **Ressource MCP complémentaire** : `workspace://agent-guide` sert le même contenu (version `generic`) pour les agents qui ne souhaitent pas écrire de fichier.

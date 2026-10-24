# Architecture du Serveur MCP : Validation 2PC, Routage Réactif et Centrage Harness

**Statut :** accepté (ADR consolidé unifiant les fondations MCP, la validation 2PC de l'ex-ADR 0002, la priorité externe de l'ex-ADR 0014, le routage granulaire de l'ex-ADR 0033 et la dépose du chat in-app de l'ADR 0034)

Afin d'offrir une surface d'outillage sans compromis aux modèles d'IA et agents externes les plus avancés du marché (Claude Code, Antigravity CLI, Cursor) sans risque de corruption des collections, nous établissons le serveur MCP local in-process comme l'unique moteur d'assistance d'AnkiForge, articulé autour du protocole Two-Phase Commit, d'un routage de mutations granulaire et passif, et de la dépose totale du chat conversationnel in-app.

---

## 1. Validation en Deux Phases (Two-Phase Commit) & Verrouillage Optimiste

### Le Problème
Permettre à un agent autonome d'effectuer des modifications directes en base de données sans validation préalable fait courir un risque majeur d'altération silencieuse des notes, modèles de cartes ou paquets. De plus, une boîte de dialogue synchrone (`QDialog.exec()`) est incompatible avec un démon persistant externe (SSE/stdio).

### Décisions & Règles
- **Mutations directes interdites** : Tout outil MCP modifiant des notes, types de cartes ou paquets génère obligatoirement un patch structuré dans la table `staged_patch` (`StagedPatchModel`).
- **Verrouillage optimiste** : Chaque patch consigne une empreinte de révision de la note cible. Si la note a été modifiée concurremment entre la proposition et la validation, l'application est rejetée avec conflit explicite.
- **Validation humaine systématique (Human-In-The-Loop)** : L'application finale requiert un accord explicite : soit par un clic utilisateur dans le tableau de bord AnkiForge, soit via l'outil dédié `apply_patch(patch_id)` après confirmation de l'agent.

---

## 2. Priorité Absolue au Serveur MCP Autonome

### Le Problème
Les agents externes en ligne de commande ou intégrés à l'IDE disposent d'un contexte de travail supérieur (fichiers locaux, terminal, tests, navigation web). Maintenir une ergonomie privilégiant un chat in-app cloisonné restreignait l'expérience utilisateur et introduisait une friction tarifaire.

### Décisions & Règles
- **Entrée de premier niveau** : La barre latérale globale consacre l'entrée de premier niveau **« MCP & Agents »** (`tr("MCP & Agents")`).
- **Autonomie opérationnelle** : Le tableau de bord permet de superviser l'état du serveur, de démarrer, arrêter ou redémarrer le démon SSE, et de régénérer le jeton d'authentification sans passer par les Préférences. Des snippets prêts à copier sont générés à chaud pour Claude Desktop/Code, Antigravity CLI et Cursor.
- **Régime d'écriture asymétrique** : L'accès aux outils de mutation est filtré et conditionné au Two-Phase Commit, garantissant la sécurité des collections.

---

## 3. Décorrélation des Flux, Passivité de `refresh_data()` et Routage Granulaire

### Le Problème
Auparavant, les mutations MCP déclenchaient un rafraîchissement global agressif qui commutait arbitrairement les onglets de l'interface, expulsant l'utilisateur de sa vue de travail en cours.

### Décisions & Règles
- **Passivité stricte de l'interface** : La méthode `refresh_data()` est strictement passive et idempotente. Elle ne doit **jamais** modifier l'onglet actif d'un panneau, ni basculer de vue, ni forcer l'ouverture d'un volet.
- **Routage granulaire par domaine** : L'événement `MCPDataMutatedEvent` transporte un domaine sémantique (`cards`, `decks`, `models`, `docs`) résolu à la source par `resolve_mcp_mutation_domain()`.
- **Réveil ciblé des vues** : Seules les vues abonnées au domaine concerné sont notifiées :
  - `cards` → vues Édition et Analyse,
  - `decks` → vues Création, Batch et Édition,
  - `models` → vues Modèles de cartes et Édition,
  - `docs` → vue Documents.
- Une vue implémentant `apply_mcp_mutation()` applique une mise à jour granulaire sans recharger l'intégralité de son modèle.

---

## 4. Dépose Totale du Chat In-App et Centrage Harness Plein Écran

### Le Problème
Maintenir en parallèle deux clients d'IA (un chat in-app rudimentaire avec ses tables SQLite `consultant_session`/`consultant_message` et un serveur MCP persistant) engendrait une duplication de maintenance et des incohérences d'état.

### Décisions & Règles
- **Suppression du chat in-app** : Retrait définitif des composants de discussion intégrée (`ConsultantChatInput`, `SessionSidebar`, `ContextHubWidget`, `WorkspaceInspectorWidget`).
- **Purge de la base de données** : Les tables SQLite `consultant_session` et `consultant_message` sont supprimées via migration Peewee dédiée.
- **Tableau de bord MCP plein écran** : L'ancien panneau composite est remplacé par `MCPServerDashboardWidget` déployé sur 100 % de la largeur disponible, dédié à la supervision des connexions, au Garde-Fou de validation et à la télémétrie des outils.
- **Extraction du moteur d'outils** : Le registre d'outils (`ConsultantToolRegistry`) devient le moteur autonome `MCPToolRegistry`, totalement décorrélé de toute session de chat.

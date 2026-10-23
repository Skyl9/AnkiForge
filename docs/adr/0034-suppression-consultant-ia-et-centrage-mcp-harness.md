# Suppression du Consultant IA in-app au profit du harness MCP pur

**Statut :** accepté

Afin de maximiser l'efficacité de l'assistance par intelligence artificielle, d'éliminer la duplication de code et d'offrir une surface d'outillage sans compromis aux modèles les plus avancés du marché (Claude Code, Antigravity CLI, Cursor), nous actons la suppression complète du chat Consultant IA in-app au profit exclusif du serveur MCP local persistant, avec purge intégrale des données de chat obsolètes lors de la bascule.

---

## Le Problème

1. **Dualité coûteuse et redondance fonctionnelle** : AnkiForge maintenait en parallèle deux moteurs d'IA conversationnelle :
   - Un client in-app rudimentaire (`ConsultantView`, `ConsultantWorker`, `ConsultantEngine`, `ConsultantSessionModel`), soumis aux limites des fenêtres de contexte et à une ergonomie de chat étroite.
   - Un serveur MCP standardisé persistant (`mcp_server.py`, `MCPServerDaemon`), capable d'outiller n'importe quel agent externe d'élite avec 58 outils métiers et un protocole Two-Phase Commit sécurisé.
2. **Couplage technique parasitaire** : L'IHM tentait de synchroniser les patchs MCP et les diffs de chat dans un même espace, générant des bogues d'éjection d'onglet et de surcharge d'état (traité par l'ADR 0033).
3. **Efficacité supérieure des harnesses externes** : Les agents CLI externes disposent de boucles de raisonnement avancées (subagents, terminal, édition de fichiers, navigation web) très supérieures à une invite in-app embarquée dans Qt. L'utilisateur d'AnkiForge a tout intérêt à piloter son application via un agent externe outillé par MCP.

---

## Options Considérées

1. **Maintenir indéfiniment le chat in-app en second plan** :
   *Rejeté*. Dette technique permanente, maintenance de deux interfaces de validation, code mort volumineux et dispersion des efforts d'ergonomie.
2. **Archivage et conservation en lecture seule des discussions passées** :
   *Rejeté (Option Q4:B écartée par l'arbitrage utilisateur)*. Conserver des tables mortes encombre le schéma Peewee et complexifie les futures migrations.
3. **Chantier en 2 étapes avec purge radicale lors de la bascule** :
   *Retenu*. 
   - Étape 1 : Stabilisation du Garde-Fou universel (scissions, types de note) et décorrélation immédiate.
   - Étape 2 : Dépose totale du chat in-app, suppression des tables SQLite `consultant_session` et `consultant_message`, et conversion de `ConsultantView` en `MCPServerView` plein écran.

---

## Décisions et Règles d'Architecture

### 1. Trajectoire en Deux Étapes
- **Phase transitoire (Courant)** : Décorrélation des flux (ADR 0033), rafraîchissement réactif granulaire et support universel des patchs (`card`, `split`, `note_type_*`) dans le Garde-Fou MCP.
- **Phase de dépose (Cible)** : Retrait physique de tous les composants de chat in-app (`ConsultantChatInput`, `SessionSidebar`, `ContextHubWidget`, `WorkspaceInspectorWidget`).

### 2. Évolution de la Navigation et de la Vue
- La vue `consultant` est renommée en `mcp` (**« Serveur MCP & Agents »**).
- L'`IdePanel` split gauche/droite est supprimé au profit de `MCPServerDashboardWidget` déployé en pleine largeur (100 % de l'espace disponible), offrant une lisibilité optimale pour la Supervision, le Garde-Fou et la Télémétrie.

### 3. Préservation du Moteur d'Exécution Métier
- Le registre d'outils `ConsultantToolRegistry` (hébergé dans `consultant_engine.py`) est extrait ou renommé en `MCPToolRegistry`. Il constitue le moteur métier autonome invoqué par `mcp_server.py` et ne dépend plus d'aucune notion de session de chat.

### 4. Purge des Données et Nettoyage BDD
- Lors de la bascule, les tables `consultant_session` et `consultant_message` font l'objet d'une migration SQLite de suppression (`DROP TABLE`).
- Les raccourcis clavier de chat (`consultant.new_chat`, etc.) sont supprimés du catalogue central des raccourcis.

---

## Conséquences

- **Allègement substantiel de la codebase** : Suppression de plus de 2 000 lignes de code d'interface de chat et de gestion de sessions devenues superflues.
- **Ergonomie Zéro-Compromis pour MCP** : Le serveur MCP dispose de l'intégralité de l'écran, sans volet latéral forcé ni onglet secondaire.
- **Concentration sur l'excellence du protocole MCP** : Toute l'énergie de développement est focalisée sur les outils exposés aux agents (audits Wozniak, génération par lots, hygiène sémantique).

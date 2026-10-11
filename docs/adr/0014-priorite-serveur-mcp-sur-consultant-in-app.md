# Priorité du serveur MCP sur le Consultant IA in-app (Hub MCP & Agents)

Afin d'éliminer les barrières de coût liées aux abonnements LLM et de privilégier les agents externes que les utilisateurs emploient déjà (CLI, éditeurs de code), nous inversons la hiérarchie d'entrée de la vue d'assistance : le serveur MCP local devient le point d'atterrissage premier et autonome, le Consultant IA in-app étant maintenu en second plan.

## Statut
Accepté

## Options considérées
1. **Suppression du Consultant IA in-app au profit du serveur MCP exclusif** : Rejeté car le Consultant in-app reste une fonctionnalité avancée et intégrée précieuse pour les utilisateurs disposant de clés API ou souhaitant interagir sans installer d'agent externe.
2. **Page d'atterrissage temporaire (modal ou landing page à cartes) masquant les outils** : Rejeté car cela ajoute une étape de clic intermédiaire et complexifie la navigation par rapport à des onglets de premier niveau stables.
3. **Deux onglets de premier niveau dédiés avec priorité au serveur MCP** : Retenu. L'`IdePanel` expose désormais deux onglets indépendants : « Serveur MCP » (sélectionné par défaut, pleine largeur, tableau de bord opérationnel complet avec état, pilotage du démon et snippets de configuration) et « Consultant IA » (le studio de discussion existant avec historique de sessions et inspecteur de contexte).
4. **Court-circuit systématique des demandes externes vers le chat** : Rejeté. Les requêtes contextuelles externes (`OpenConsultantRequestedEvent`) atterrissent par défaut sur l'onglet Serveur MCP sous la forme d'un bandeau prêt à copier pour un agent externe (sans redirection forcée), tout en laissant à l'utilisateur la liberté de reconfigurer cette cible vers le chat direct dans les Préférences.

## Conséquences
- **Navigation unifiée** : L'entrée de la barre latérale principale devient « MCP & Agents » (`tr("MCP & Agents")`), clarifiant la disponibilité du protocole MCP directement depuis la navigation de premier niveau.
- **Autonomie et ergonomie du tableau de bord MCP** : L'onglet « Serveur MCP » dispose d'un affichage pleine largeur sans surcharge visuelle. Les contrôles exclusifs au chat (sidebar de sessions, sélecteur de modèle LLM, export, hub de contexte) sont automatiquement masqués lorsqu'il est actif.
- **Pilotage opérationnel direct** : Le tableau de bord MCP permet de démarrer, arrêter, redémarrer le démon et renouveler le jeton d'authentification sans avoir à ouvrir les Préférences. Des snippets prêts à l'emploi (Claude Desktop/Code, Antigravity CLI, Cursor, cURL) simplifient la connexion des agents tiers.
- **Flexibilité et préférences** : Deux réglages sont introduits dans `AiEnginesTab` (`consultant/default_tab` et `consultant/external_prompt_target`), permettant aux utilisateurs intensifs du Consultant IA de retrouver leur comportement habituel sans altérer la découverte du MCP pour les nouveaux utilisateurs.

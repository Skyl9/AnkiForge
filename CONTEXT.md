# CONTEXT.md — Glossaire AnkiForge

Glossaire des termes du domaine. Cette page ne contient **aucun** détail d'implémentation : c'est un lexique partagé, pas un cahier des charges.

## Batch & revue des cartes

- **Tâche batch** : une unité de travail placée dans la file d'attente du lot — un document (ou une partie de document) découpé(e) selon un mode d'articulation, destiné(e) à produire des cartes.
- **Revue (staging)** : l'étape humaine où l'utilisateur tranche le sort des cartes produites par une tâche batch, avant leur enregistrement. Elle s'effectue dans un onglet dédié, toujours visible.
- **Tâche révisable** : tâche dont les cartes attendent une décision humaine (état « À réviser » dans la file). Une seule d'entre elles est *activement* en revue à un instant donné.
- **Rangée ouvrable** : rangée de la file d'attente dont on peut ouvrir la revue — pour *réviser* (cartes pas encore tranchées) ou *relire* (cartes déjà traitées).
- **Décision de revue** :
  - au niveau **carte** : « Validée » ou « Refusée » ;
  - au niveau **tâche** : « Acceptée » (tout est tenu bon) ou « Rejetée » (toute la tâche). Voir `BatchTaskStatus` et les statuts de carte dans le code.
- **Clé de rangée (uid de ligne)** : identité stable d'une tâche dans la file pendant la session. Elle ne dépend pas de la position de la rangée ; elle distingue les tâches même quand des rangées sont supprimées ou réordonnées. Distincte de l'identifiant d'exécution d'une tâche de portée (snapshot).
- **File d'attente** : la liste des tâches batch en attente d'exécution, de revue ou déjà terminées. L'ordre y résulte de l'enchaînement des agrégations (directes ou automatiques).

## Génération IA

- **Génération** : l'exécution d'un pipeline sur une source, produisant des cartes brutes.
- **Étape de validation** : étape du pipeline qui vérifie ou nettoie la sortie d'une génération (aujourd'hui uniquement formelle : mise en forme LaTeX/HTML et schéma JSON).
- **Chaîne de pensée (Raisonnement / Thought)** : flux de réflexion intermédiaire émis par un modèle d'IA à raisonnement explicite (Chain-of-Thought) avant ou pendant la production du contenu cible. Ce flux ne fait pas partie des données structurées des flashcards finales, mais constitue une trace de traçabilité et d'audit pour comprendre la sélection des faits, la formulation ou d'éventuelles hallucinations.

## Documents & Arborescence de classement

- **Dossier de documents** : conteneur logique permettant de classer et organiser les documents de la bibliothèque par matière, niveau ou thématique.
- **Chemin hiérarchique (Séparateur `::`)** : convention standard d'Anki et d'AnkiForge séparant les niveaux arborescents (ex: `Faculté::Semestre 1::Biologie`). Chaque segment du chemin constitue un nœud d'arborescence ayant sa propre existence logique et son identité dans le modèle de données.
- **Sous-dossier** : dossier rattaché à un dossier parent, dont le nom canonique est préfixé par le chemin hiérarchique du parent suivi du séparateur `::`.
- **Surface documentaire** : ensemble cohérent des interactions permettant de sélectionner, importer, structurer, consulter, délimiter, indexer ou auditer un document. Une surface peut traverser plusieurs vues, widgets et dialogues.

## Thèmes, Layouts & Design System

- **Mode d'Apparence** : le régime visuel binaire de l'interface, **Sombre** ou **Clair**. C'est un axe indépendant de l'identité graphique choisie.
  _Avoid_ : thème sombre, thème clair, is_dark, palette

- **Famille de Thème** : l'une des 12 identités graphiques d'AnkiForge. Chaque famille possède **exactement une variante sombre et une variante claire** — c'est une garantie structurelle, pas une convention. C'est le second axe, indépendant du Mode d'Apparence.
  _Avoid_ : thème, preset, palette, style

- **Variante** : un jeu concret de jetons de design, sombre ou clair, appartenant à une Famille. C'est la seule unité qui porte des valeurs de couleur.
  _Avoid_ : thème, profil, template

- **Jetons de design** : les valeurs sémantiques consommées au rendu. Elles sont **toujours dérivées** d'une Variante active : backgrounds, accents, textes, bordures, sémantiques, rayons, typographie, coloration syntaxique, plus les fonds et bordures teintés. Les jetons dérivés ne sont jamais une source de vérité et ne sont jamais échangés.
  _Avoid_ : constantes de thème, variables CSS, couleurs du design system

- **Source du Mode** : l'origine de la valeur du Mode d'Apparence — **Sombre manuel**, **Clair manuel**, ou **Système**. C'est ce qui est persisté côté préférence ; la Variante effective en est calculée.
  _Avoid_ : booléen dark, mode auto, thème système

- **Disposition d'interface (layout)** : l'une des 4 coquilles d'interface interchangeables à chaud, qui redistribue navigation et contenu sans jamais dupliquer les vues métier.
  _Avoid_ : coquille, vue, thème, écran, page

- **Bibliothèque de thèmes** : l'ensemble des Variantes et Familles personnalisées, propre à l'installation et partagé entre tous les profils. Un profil ne *sélectionne* pas dans la bibliothèque, il y *pointe*.
  _Avoid_ : thèmes du profil, registre, cache

## Architecture de l’interface

- **Vue monolithique** : vue qui combine dans une même unité la composition visuelle, la coordination d’état, les opérations métier et la gestion des workers, au point de rendre ses parcours difficiles à isoler.
- **Widget de section** : composant d’interface qui encapsule un parcours cohérent avec son état local, ses signaux et ses règles de validation, plutôt qu’un simple fragment visuel.
- **Tranche de refactoring** : étape livrable qui extrait et teste une responsabilité d’une vue sans modifier le comportement observable des autres parcours.

## Protocole MCP & Agents externes

- **Serveur MCP persistant** : service d'arrière-plan exposant l'outillage interne d'AnkiForge (audits, inspection, mutations de cartes) à des agents tiers via le protocole standardisé MCP.
- **Agent externe (ou Agent CLI)** : agent d'intelligence artificielle autonome s'exécutant dans un processus distinct (terminal, éditeur tiers) et pilotant AnkiForge via les outils MCP.
- **Jeton d'autorisation MCP** : secret d'authentification locale généré par session, requis pour autoriser les requêtes entrantes vers le serveur MCP persistant.
- **Patch en attente (Staged Patch)** : proposition structurée de modification ou de refactorisation (diff avant/après) émise par l'IA ou un outil MCP, maintenue en attente d'une validation humaine explicite avant toute persistance définitive.
- **Validation en deux phases (Two-Phase Commit)** : principe de sécurité selon lequel aucune opération chirurgicale ou destructive initiée par un agent n'altère directement la collection, chaque mutation devant obligatoirement être soumise sous forme de patch intermédiaire puis validée par l'utilisateur.
- **Bloc de réflexion étendu (Extended Thinking / Thought Block)** : flux de raisonnement intermédiaire émis par un modèle d'IA avant de formuler sa réponse finale, streamé en temps réel dans l'interface avec des métriques de temps et de tokens, et distinct du contenu final des cartes.
- **Composant de discussion riche (Rich Chat Widget)** : élément d'interface interactif (tableau de cartes, prévisualisation avec formules KaTeX, sélecteur de modèle) inséré directement dans le fil de conversation du Consultant IA pour manipuler la collection au-delà du simple texte.

## Profils, Sauvegardes & Durcissement

- **Verrou de profil** : mécanisme de protection mono-instance par profil garantissant l'exclusivité d'accès d'un processus à la base de données et aux médias d'un profil donné, tout en autorisant l'exécution simultanée d'instances sur des profils distincts.
  _Avoid_ : verrou global, lock app, instance unique globale
- **Sauvegarde pré-restauration** : instantané de sécurité généré obligatoirement et automatiquement avant le remplacement de la base de données par une sauvegarde antérieure, exclu de la politique de rotation standard pour permettre un retour arrière immédiat.
  _Avoid_ : backup temporaire, dump écrasable
- **Restauration granulaire** : opération permettant à l'utilisateur d'inspecter l'historique complet des sauvegardes horodatées d'un profil et d'en choisir une spécifiquement pour restaurer sa collection.
- **Transfert élargi de contenu** : opération de copie de données (notes, types de notes, cartes, médias dédupliqués) entre deux profils locaux, préservant l'identité canonique (GUID) des notes et assurant la déduplication sans altérer le profil émetteur.

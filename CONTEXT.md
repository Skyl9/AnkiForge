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

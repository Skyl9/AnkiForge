# Disposition à 5 sous-onglets et cockpit sans défilement du serveur MCP

**Statut :** accepté

Afin de transformer le serveur MCP local en un environnement d'administration et de supervision complet pour agents externes, nous éliminons le défilement vertical excessif de la page de supervision au profit d'un cockpit ergonomique en deux colonnes, et nous structurons l'espace Serveur MCP en 5 sous-onglets spécialisés pilotés par le composant `SegmentedTabBar` : **Supervision & Connexion**, **Garde-Fou & Validation**, **Catalogue d'Outils**, **Télémétrie & Activité**, et **Guides & Workspaces**.

---

## Le Problème

1. **Surcharge et défilement vertical excessif** : La page unique de `MCPServerDashboardWidget` empilait verticalement l'en-tête, le bandeau de requête, la carte de cycle de vie, les endpoints, les snippets clients et l'historique d'activité au sein d'une `QScrollArea`. L'utilisateur devait continuellement scroller pour démarrer le serveur, copier un token, consulter un snippet ou inspecter un appel d'outil.
2. **Opacité de l'outillage MCP (58 outils invisibles dans l'UI)** : Bien que le serveur MCP expose 58 outils répartis sur 9 domaines fonctionnels (`mcp_server.py`), l'utilisateur ne dispose d'aucune interface in-app pour consulter leurs signatures, schémas JSON, paramètres obligatoires/optionnels et docstrings descriptives.
3. **Interruption par dialogue modal bloquant lors de l'inspection de télémétrie** : L'historique d'activité utilisait un dialogue modal (`MCPActivityDetailDialog`) bloquant l'UI à chaque clic sur une ligne, rendant impossible l'observation des appels d'outils en cours pendant l'examen d'un payload.
4. **Sous-exploitation de l'amorçage d'agents (ADR 0024)** : Les capacités d'initialisation de workspace (`init_agent_workspace`), de consultation des guides méthodologiques et de détection de dérive (`check_guide_version`) n'étaient accessibles qu'aux agents via le protocole MCP, sans surface dédiée pour l'utilisateur dans l'IHM.

---

## Options Considérées

1. **Scission dans la navigation principale de `MainWindow` (nouvel élément dans la barre latérale)** :
    *Rejeté*. La barre latérale globale compte déjà 8 vues synchronisées sur les 4 dispositions d'interface (`ide`, `macos`, `dashboard`, `glassmorphism`). Ajouter une 9e entrée fragmenterait la navigation et dérogerait à l'ADR 0043 qui unifie l'assistance externe et interne sous la vue « MCP & Agents ».
2. **Condensation en 3 sous-onglets avec accordéons repliables** :
   *Rejeté*. Replier les sections sous des accordéons (`CollapsibleSection`) masque les informations critiques (état, port, endpoints) et requiert des clics supplémentaires.
3. **5 sous-onglets spécialisés avec cockpit 2 colonnes sans défilement et `SegmentedTabBar`** :
   *Retenu*.

---

## Décisions et Règles d'Architecture

### 1. Maintien transitoire dans `ConsultantView` avant dépose finale (ADR 0043)
- La vue de premier niveau « MCP & Agents » conserve ses deux onglets majeurs dans son `IdePanel` : « Serveur MCP » (prioritaire et sélectionné par défaut) et « Consultant IA ».
- Lorsque l'onglet « Serveur MCP » est actif, le panneau droit (`context_panel`) demeure masqué pour allouer 100 % de la largeur d'écran à l'espace MCP.

### 2. Sous-Navigation Canonique via `SegmentedTabBar` (DESIGN.md §1.17)
- La `QTabBar` ad-hoc de `MCPServerDashboardWidget` est remplacée par le composant officiel `SegmentedTabBar` configuré en mode `subtab` avec icônes Phosphor vectorielles.
- Gestion native des badges sémantiques dynamiques :
  - `🛡️ Garde-Fou (N)` : badge d'alerte rouge/orange dès qu'un `StagedPatchModel` est en attente.
  - `📊 Activité (N)` : badge neutre de comptage du nombre d'appels enregistrés.
- Navigation fluide au clavier (touches fléchées) et synchronisation réactive au thème (`refresh_theme`).

### 3. Cartographie des 5 Sous-Onglets Cibles

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  [🔌 Supervision & Connexion]  [🛡️ Garde-Fou (3)]  [🧰 Catalogue]  [📊 Activité]  [🤖 Guides] │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

1. **`🔌 Supervision & Connexion` (Cockpit Zéro-Scroll 2 colonnes)** :
   - *Colonne gauche (50 %)* : Carte de pilotage opérationnel (statut Actif/Arrêté/Erreur, port, protocole Streamable HTTP + SSE, boutons Démarrer / Arrêter / Redémarrer / Renouveler) et carte d'accès réseau (URLs des endpoints avec boutons Copier, champ jeton Bearer 256-bit masqué avec toggle œil et bouton Copier).
   - *Colonne droite (50 %)* : Carte des configurations clients prêtes à l'emploi (barre d'onglets Claude / agy / Cursor / cURL, bloc de code stylisé monospace et bouton « Copier la configuration »).
   - *Haut de page* : En-tête compact et bandeau de demande contextuelle externe rétractable.
   - *Zéro défilement vertical requis* sur écran 1200×720 et supérieur.
2. **`🛡️ Garde-Fou & Validation` (ADR 0029)** :
   - Espace existant maître-détail pour l'examen des propositions de cartes, le diff sémantique mot-à-mot intra-ligne, l'édition en place et la validation/rejet en deux phases (Two-Phase Commit).
3. **`🧰 Catalogue d'Outils` (Exploration des 58 outils MCP)** :
   - Regroupement des outils par 9 domaines fonctionnels (Types de note, Notes & Cartes, Paquets, Tags, Documents & RAG, Albums & Planches, DAG & Pipelines, Agents MCP, Documentation).
   - Barre de recherche textuelle temps réel et filtres par catégorie via `FilterChipButton`.
   - Volet de détail présentant le nom canonique, la description, le schéma JSON des paramètres (avec distinction clair Requis vs Optionnel) et les garde-fous associés.
4. **`📊 Télémétrie & Activité` (Maître-Détail sans modale bloquante)** :
   - *Ruban supérieur de KPIs* : Nombre total d'appels, taux de succès/erreur, durée moyenne d'exécution, bouton « Vider l'historique ».
   - *Splitter horizontal* :
     - Volet gauche (table) : Liste des appels récents en direct (horodatage, nom d'outil, badge de statut, durée, résumé des arguments) avec filtres rapides par statut et recherche par outil.
     - Volet droit (inspecteur) : Affichage instantané au clic de la ligne des arguments JSON complets, du résultat brut retourné ou de la trace d'erreur, avec bouton « Copier le JSON ».
5. **`🤖 Guides & Workspaces` (Amorçage & Personas MCP)** :
   - Interface graphique d'amorçage pour exécuter `init_agent_workspace` vers un répertoire cible au choix (Claude, Gemini, Cursor, agy, generic).
   - Prévisualisation in-app du contenu du guide compilé avec mise en avant des 9 workflows d'assistance.
   - Indicateur d'audit de version de guide (`check_guide_version`) et liste des agents MCP personnalisés configurés.

---

## Conséquences

- **Ergonomie sans friction** : L'élimination du scroll sur la supervision permet de connecter un agent CLI ou un éditeur en quelques secondes sans manipulation d'ascenseur.
- **Transparence et découvrabilité** : L'utilisateur et le développeur visualisent immédiatement la surface fonctionnelle complète des 58 outils du serveur MCP sans avoir à lire le code source Python.
- **Supervision fluide et non bloquante** : L'inspecteur maître-détail de la télémétrie permet de surveiller le déroulement d'une session d'agent autonome sans popups intrusifs.
- **Conformité stricte au Design System** : Réutilisation des composants éprouvés (`SegmentedTabBar`, `DesignTokens`, `load_phosphor_icon`) garantissant le bon fonctionnement sous les 24 thèmes et 4 layouts de l'application.

# 38. Lecteur de documentation embarqué natif et guide visuel du cycle de vie distribué

Date: 2026-10-24

## Statut

Accepté (Issu du cadrage `/grill-with-docs`)

## Contexte

AnkiForge et Anki constituent un système distribué asynchrone gouverné par la complémentarité de deux périmètres d'autorité : AnkiForge pilote la création de connaissances assistée par IA et la traçabilité documentaire (RAG / Smart Coverage), tandis qu'Anki conserve l'autorité exclusive sur l'ordonnancement de répétition espacée (SRS, FSRS / SM-2) et les séances d'étude quotidiennes.

Si les fondations techniques de cette séparation ont été stabilisées par l'ADR 0036 (Importation `.colpkg` par remplacement et préservation du studio) et l'ADR 0037 (Réconciliation des types de note et conformité du moteur de rendu), plusieurs carences ergonomiques subsistaient :

1. **Absence de guidage visuel et didactique pour l'utilisateur** :
   Les utilisateurs ont besoin d'une compréhension limpide et immédiate des flux d'échange (`.apkg` vs `.colpkg`), de la sanctuarisation de leur studio d'authoring et de la garantie d'absence de perte de données ou de prolifération de cartes zombies.
2. **Absence de lecteur applicatif intégré** :
   La documentation était jusqu'ici consultable soit via les outils MCP du consultant IA, soit via le lancement d'un navigateur web externe pointant vers le site Zensical. L'application ne disposait pas d'un dialogue autonome permettant de lire confortablement un guide riche en illustrations directement depuis l'interface Qt.
3. **Contrainte de testabilité headless et isolation de l'environnement** :
   L'utilisation d'un composant de rendu web lourd (`SafeWebEngineView` / Chromium) pose des contraintes strictes en environnement headless CI (`ANKIFORGE_MOCK_WEBENGINE=1`), empêchant la validation automatisée de l'affichage effectif des illustrations et des flux de navigation documentaire.

## Décision

### 1. Lecteur applicatif natif et autonome (`DocReaderDialog`)

Un dialogue modal/autonome `DocReaderDialog` est introduit dans `src/ankiforge/ui/dialogs/doc_reader_dialog.py` :
- **Moteur de rendu natif `QTextBrowser`** : assure un rendu HTML/CSS rapide, léger et autonome, sans dépendance Chromium ni mock WebEngine requis.
- **Support complet des illustrations vectorielles SVG locales** : exploitation du module `QtSvg` et de la résolution de chemins relatifs ou ressources pour afficher des diagrammes nets à toutes les résolutions d'écran et dans tous les thèmes.
- **Confort de lecture** : intégration d'une barre d'outils avec recherche textuelle incrémentale en surbrillance, contrôle du niveau de zoom typographique, et respect des jetons sémantiques de design (`DesignTokens`).
- **Testabilité automatisée** : testable à 100% sous `pytest-qt` avec le drapeau `QT_QPA_PLATFORM=offscreen`.

### 2. Guide pédagogique axé sur l'utilisateur (`docs/guides/cycle_de_vie_distribue.md`)

Le guide visuel est rédigé comme une documentation purement pédagogique, tournée vers l'expérience et le workflow de l'utilisateur :
- **Sanctuarisation du contenu utilisateur** : exclusion délibérée des liens vers les spécifications internes ou les ADRs techniques développeur, afin de maintenir un document clair, concis et actionnable.
- **5 diagrammes vectoriels SVG autonomes et versionnés** (sous `docs/guides/assets/cycle_de_vie/`) :
  1. `cycle_global.svg` : cycle complet (Studio AnkiForge → Staging Review → Export .apkg → Étude Anki → Synchronisation .colpkg).
  2. `sanctuarisation_perimetres.svg` : frontière étanche entre le Périmètre Studio (préservé) et le Périmètre Anki (synchronisé).
  3. `arbre_decision_apkg_colpkg.svg` : arbre de décision d'échange de fichiers (fusion incrémentale vs remplacement contrôlé).
  4. `chronologie_session.svg` : déroulement chronologique d'une session de création puis d'étude.
  5. `prevention_zombies.svg` : mécanisme d'éradication des cartes supprimées dans Anki et règle de génération conditionnelle (recto non vide).
- **3 scénarios pas-à-pas concrets** :
  1. Premier démarrage et importation de sa collection Anki existante.
  2. Création et enrichissement de cours / cartes dans AnkiForge avec export vers Anki.
  3. Rafraîchissement périodique de sa collection après plusieurs semaines d'étude dans Anki.

### 3. Point d'ancrage dans les Paramètres (`HelpTab`)

Un nouvel onglet autonome « Aide & Guides » est intégré dans la modale des Paramètres (`SettingsModal`) :
- Accessible via la sidebar latérale de `SettingsModal` (icône Phosphor `ph.question` ou `ph.book-open`).
- Met en avant une carte visuelle dédiée au Cycle de Vie Distribué avec bouton direct « Ouvrir le guide visuel », ainsi que l'accès aux autres ressources documentaires de l'application.

### 4. Palette de commandes (⌘K)

Enregistrement d'une commande dédiée dans `CommandPalette` :
- Identifiant : `action.lifecycle_guide`.
- Libellé : `Guide visuel du cycle de vie distribué (Anki ↔ AnkiForge)`.
- Catégorie : `Aide`.
- Icône : `ph.arrows-clockwise`.
- Action : instancie et affiche `DocReaderDialog` pré-chargé sur `docs/guides/cycle_de_vie_distribue.md`.

### 5. Indexation et isolation Zensical

- Le guide réside sous `docs/guides/cycle_de_vie_distribue.md` et est automatiquement scanné et indexé dans la table FTS5 en mémoire par `AppDocumentationService`.
- Conformément aux critères d'acceptation, cette page n'est pas ajoutée à la table de navigation `zensical.toml`, préservant le sommaire public Zensical tout en assurant une disponibilité in-app totale.

## Conséquences

- **Sérénité de l'utilisateur** : compréhension intuitive des responsabilités respectives d'Anki et d'AnkiForge, éliminant toute anxiété relative à la perte de progrès SRS ou à la disparition de documents.
- **Composant pérenne et réutilisable** : `DocReaderDialog` constitue désormais le composant canonique pour afficher n'importe quelle documentation ou guide embarqué au sein d'AnkiForge.
- **Fiabilité CI/CD** : compatibilité intégrale avec les tests headless `pytest-qt` sans régression ni instabilité de sandbox WebEngine.

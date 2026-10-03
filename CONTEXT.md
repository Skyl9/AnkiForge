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
- **Surcharge locale de persona** : prompt d'un agent modifié au profit du seul pipeline qui le consomme. Elle n'altère pas la persona : deux pipelines peuvent surcharger le même agent sans jamais se voir, et lever la surcharge rend à l'agent son prompt d'origine. Elle est un réglage du pipeline, pas une version de la persona.
  _Avoid_ : édition de persona, copie de persona, persona de pipeline, fork de persona
- **Chaîne de pensée (Raisonnement / Thought)** : flux de réflexion intermédiaire émis par un modèle d'IA à raisonnement explicite (Chain-of-Thought) avant ou pendant la production du contenu cible. Ce flux ne fait pas partie des données structurées des flashcards finales, mais constitue une trace de traçabilité et d'audit pour comprendre la sélection des faits, la formulation ou d'éventuelles hallucinations.
- **Assistant de création d'agent (Wizard d'agent)** : dialogue guidé permettant d'instancier un nouvel agent IA soit à partir de modèles prédéfinis optimisés pour Anki (pédagogie Wozniak, langues, sciences, format cloze), soit à partir d'une page blanche personnalisée.
  _Avoid_ : modal agent, pop-up agent, dialogue de persona
- **Sélecteur de modèle IA (mode sélection / picker)** : régime compact du dialogue de découverte dédié à la recherche et au choix immédiat d'un moteur pour une tâche ou un champ de configuration, dépourvu de volet de comparaison.
  _Avoid_ : modal modèle, catalogue réduit, combobox modèle
- **Catalogue & Comparateur des modèles IA** : régime complet d'exploration technique permettant d'inspecter les spécifications réelles (vision, thinking, tarification, contexte) et de comparer côte à côte plusieurs moteurs IA.
  _Avoid_ : fenêtre catalogue, comparateur IA

## Documents & Arborescence de classement

- **Dossier de documents** : conteneur logique permettant de classer et organiser les documents de la bibliothèque par matière, niveau ou thématique.
- **Chemin hiérarchique (Séparateur `::`)** : convention standard d'Anki et d'AnkiForge séparant les niveaux arborescents (ex: `Faculté::Semestre 1::Biologie`). Chaque segment du chemin constitue un nœud d'arborescence ayant sa propre existence logique et son identité dans le modèle de données.
- **Sous-dossier** : dossier rattaché à un dossier parent, dont le nom canonique est préfixé par le chemin hiérarchique du parent suivi du séparateur `::`.
- **Surface documentaire** : ensemble cohérent des interactions permettant de sélectionner, importer, structurer, consulter, délimiter, indexer ou auditer un document. Une surface peut traverser plusieurs vues, widgets et dialogues.

## Albums & Planches

- **Album** : document dont chaque page est une **planche** — une image — et non du texte extractible. Il se consulte planche par planche, se transcrit, s'indexe et se compile, mais ne se découpe pas en sections.
  _Avoid_ : livre d'image, livre d'images, scan, PDF image, document visuel
- **Planche** : page d'un album, désignée par son image et son orientation. Elle porte un **état dérivé** — transcription, description dense — et une rotation qui lui est propre.
  _Avoid_ : image, page, illustration, vignette
- **Rotation de planche** : orientation durable d'une planche (`0`/`90`/`180`/`270°`), propriété de la planche et non de son affichage. Elle est appliquée **à la lecture** par une couture unique et n'est jamais inscrite dans le fichier image.
  _Avoid_ : orientation, EXIF, rotation d'affichage, redressement
- **Image source** : fichier dont une planche est tirée. Une planche est une **dérivation** de ses images sources — la rotation lui est appliquée à la lecture et la couture la recompose à chaque passe. Toute propriété qui doit survivre à une rotation ou à une recomposition appartient donc à l'**image source**, jamais à la planche.
  _Avoid_ : média, original, image de planche, planche source
- **Recadrage** : sélection rectangulaire d'une région d'une **image source**, purement restrictive. Il n'altère jamais le fichier et ne réduit jamais la matière : il borne ce qui est lu et rendu, et rien d'autre. Il est conservé sur l'image source, jamais sur la planche — un recadrage porté par la planche se périmerait à la première rotation de sa source.
  _Avoid_ : crop, découpe image, rognage, zoom, cadrage d'affichage, recadrage de planche
- **État dérivé** : contenu produit à partir d'une planche — sa transcription, sa description dense — et **périmé** dès que la planche change. Une planche porteuse d'un état dérivé périmé le dit, plutôt que de servir un contenu faux : un état absent se voit et se corrige, un état dérivé périmé se constate trop tard.
  _Avoid_ : cache, index, données dérivées, transcription
- **Périmètre de transcription (ou Portée de transcription)** : ensemble des planches d'un album ciblées lors d'une passe d'extraction (album complet, planches sans état dérivé, planches périmées, ou intervalle explicite). Le ciblage est exclusif et vérifie dynamiquement le nombre de planches correspondantes pour interdire les passes à vide.
  _Avoid_ : sélection de pages, lot OCR, filtre de transcription
- **Directives de transcription** : ensemble des contraintes formelles (syntaxe LaTeX `$..$`, tableaux Markdown/HTML, descriptions de schémas) et consignes contextuelles injectées dans le prompt du modèle de vision, désactivées pour le moteur matériel (Apple Vision).
  _Avoid_ : prompt système, template OCR, options texte
- **Type de donnée d'image** : nature de ce qu'une image contient — table, pseudocode, schéma, photo, logo, texte imprimé. L'utilisateur le choisit lui-même dans une liste fermée ; il n'est ni déduit, ni proposé, ni deviné. Il ne désigne aucun moteur.
  _Avoid_ : catégorie, catégorie de reconnaissance, classe, type de document, modèle
- **Moteur de vision adapté** : modèle capable de restituer fidèlement un **type de donnée d'image** donné. Le type borne l'ensemble des candidats, il ne les impose pas — le choix du moteur reste une décision distincte et séparée du type.
  _Avoid_ : catégorie, modèle par défaut, moteur de la catégorie
- **Transcription optique matérielle** : extraction optique brute et locale accélérée par puce matérielle (Apple Neural Engine / Vision), sans modèle de langage génératif (VLM). Elle est optimisée pour la prose et les textes continus en bloc, sans interprétation sémantique, ni reconstruction de tableaux complexes, ni formules KaTeX.
  _Avoid_ : OCR IA, vision multimodale, VLM matériel

## Provenance & Couverture

- **Fil d'Ariane (heading path)** : la suite ordonnée des titres traversés pour atteindre un point du document, de la racine à la section. C'est l'identité d'une section.
- **Section** : nœud du document désigné par le couple (document, fil d'Ariane). Son identité est **déterministe et durable** : elle survit à la réingestion, contrairement à celle d'un fragment.
- **Fragment (chunk)** : portion de texte produite par le découpage, porteuse d'un `page_number` éventuellement nul. C'est une désignation **précise mais instable** : l'identifiant change à chaque réingestion.
- **Provenance de note** : l'ensemble de tags décrivant l'origine d'une carte (`doc:`, `source:`, `section:`, `page:`). Elle est écrite par `build_document_tags` ; le rattachement aux fragments est écrit séparément, dans les liens de couverture.
- **Lien de couverture** : l'association entre une note et un fragment de document, porteuse de la mention du fragment et du palier de résolution qui l'a désignée.
- **Palier de résolution** : l'un des quatre régimes de désignation d'un fragment, par ordre de préférence décroissante — `exact` (identité), `section` (fil d'Ariane), `page` (numéro), `lexical` (recouvrement de contenu). Un palier n'abandonne que sur échec, jamais parce qu'une autre route est présente. Il est persisté pour rendre un lien **prouvé** indiscernable d'un lien seulement **présumé**.
- **Couverture** : la part des fragments d'un document effectivement désignés par au moins une carte. Une carte non rattachée est laissée **hors couverture** plutôt que rattachée hors de sa partie : un faux lien est plus trompeur que son absence.
- **Conteneur structural** : portion de document dont le contenu textuel ne justifie pas la création de flashcards, mais qui sert de nœud d'organisation pour des sous-sections substantielles. Un conteneur structural est **neutre** dans le calcul de couverture : il n'est ni un trou, ni une section couverte, ni une section écartée. Il est affiché comme un nœud collapsible dans l'inspecteur documentaire. Son **origine** est *Dérivée* ou *Déclarée*.
  _Avoid_ : section vide, titre fantôme, heading stub
- **Origine du conteneur structural** : l'axe qui distingue le conteneur *Dérivé* — reconnu automatiquement par l'insuffisance de son texte — du conteneur *Déclaré*, désigné par l'utilisateur. Le seuil de 25 mots n'est un critère que pour l'origine *Dérivée* ; pour l'origine *Déclarée*, il n'est qu'une **aide à la déclaration**, jamais une règle de calcul.
  _Avoid_ : type, catégorie, mode de conteneur
- **Adresse de région** : l'une des trois façons durables de désigner une portion d'un document — son **nœud** (le contenu propre d'un titre, distinct de sa lignée), sa **lignée** (le nœud et tous ses descendants), ou sa **page**. Une adresse est réévaluée à chaque réingestion : elle ne mémorise jamais l'identité d'un fragment.
  _Avoid_ : exclusion de section, filtre de page, sélection
- **Écarter** : retirer une région du document — elle ne participe plus ni aux générations, ni à la couverture, ni au rattachement des cartes. L'écartement est **non destructif** : la région demeure consultable et réintégrable.
  _Avoid_ : supprimer, retirer, exclure
- **Neutraliser** : retirer une région du dénominateur de la couverture sans la retirer du document. C'est ce qu'accomplit déjà un conteneur structural, mais **décidé** par l'utilisateur plutôt que dérivé.
  _Avoid_ : masquer, ignorer, exclure
- **Réparation de provenance** : réécriture automatique, lors d'une synchronisation, des tags de provenance obsolètes vers leur forme canonique, sans migration de données.

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

## Mises à jour & Distribution sécurisée

- **Canal de mise à jour** : régime de diffusion déterminant la stabilité et la fréquence des versions distribuées (**Stable** pour les versions éprouvées, **Nightly** pour les builds automatisés récents).
  _Avoid_ : branche de mise à jour, feed, release channel en vrac
- **Manifeste d'intégrité** : fichier consolidé (`checksums.txt`) recensant les empreintes cryptographiques déterministes (SHA-256) de l'ensemble des artefacts distribués pour une release donnée.
  _Avoid_ : hash list, fichier sha, digest file
- **Signature d'autorité** : preuve cryptographique asymétrique (Ed25519) attestant de l'authenticité et de l'intégrité du manifeste d'intégrité, produite lors du build de release via une clé privée protégée et vérifiée par le client via son trousseau de confiance.
  _Avoid_ : hash signé, certificat SSL, signature binaire
- **Trousseau de confiance** : ensemble des clés publiques Ed25519 réputées fiables et immuables, embarquées dans le code compilé de l'application, autorisées à valider la signature d'autorité.
  _Avoid_ : trousseau de clés OS, keychain, liste de certs
- **Fenêtre de cache (TTL de vérification)** : durée minimale s'écoulant entre deux interrogations distantes de l'API de distribution, configurable par l'utilisateur pour ménager les quotas et la bande passante.
  _Avoid_ : intervalle réseau, timeout, délai
- **Notarisation système** : certification externe délivrée par le système hôte (Apple Notary Service) garantissant l'absence de logiciels malveillants identifiés avant l'exécution du binaire.
  _Avoid_ : signature Ed25519, code signing interne

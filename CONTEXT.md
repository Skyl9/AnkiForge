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

## Types de note, Notes & Cartes

- **Type de note** : le gabarit Anki qui définit les champs d'une note, les gabarits de ses cartes (recto/verso) et son CSS. Une note lui est conforme ; ses cartes en dérivent.
  _Avoid_ : modèle, modèle de notes, modèle de carte, card model, note model
- **Type de note par défaut** : type de note préférentiel mémorisé dans les préférences du profil utilisateur (`card_models/default_note_type_id`), pré-sélectionné automatiquement lors des créations manuelles ou de l'extraction par lot lorsqu'aucun type n'est spécifié. Il est mis en évidence dans l'interface par un indicateur visuel dédié (étoile ou badge).
  _Avoid_ : note type actif, gabarit par défaut
- **Ordre de tri des types de note** : critère d'ordonnancement appliqué à l'affichage des types de note dans la liste latérale et les fenêtres modales de sélection (`Nom (A-Z)`, `Nom (Z-A)`, `Plus récents`, `Plus anciens`, `Nombre de gabarits`), persisté par profil utilisateur (`card_models/sort_order`).
  _Avoid_ : filtre de note, ordre BDD
- **Menu contextuel de type de note** : menu d'actions déclenché par clic droit sur un type de note dans les vues et sélecteurs de l'application, regroupant les opérations sur son cycle de vie (Renommer, Dupliquer, Exporter, Définir par défaut, Filtrer les notes rattachées, Supprimer).
- **Note** : l'unité de contenu d'une collection — un jeu de valeurs conforme à un type de note. Elle ne porte aucun état de révision.
  _Avoid_ : fiche, item
- **Carte** : l'unité de révision dérivée d'une note à partir d'un gabarit de son type de note. Elle appartient à un paquet et **héberge** les compteurs SRS d'observation (`ivl`, `reps`, `lapses`, drapeaux, suspension) importés d'Anki, dont l'ordonnancement relève exclusivement d'Anki (voir *Ordonnancement*).
  _Avoid_ : flashcard, question, verso
- **Carte sangsue (ou Sangsue)** : carte dont le nombre d'échecs répétés lors des révisions (`lapses`) atteint ou dépasse le seuil critique configuré, signalant une anomalie cognitive ou de formulation (surcharge informationnelle, ambiguïté, interférence) nécessitant un diagnostic et une scission atomique.
  _Avoid_ : carte difficile, carte échouée, leech, mauvaise carte
- **Rôle IA (d'un type de note)** : directive sémantique et heuristique attachée à un type de note (`NoteTypeModel.description`), injectée dans la balise `{{ available_card_models }}` des prompts d'extraction pour orienter le choix du type de note le plus pertinent face à chaque concept identifié.
  _Avoid_ : rôle du modèle, description du modèle de carte
- **Modèle basique amorce (Seed Note Type)** : l'unique type de note minimaliste injecté à la création d'un profil vierge (`"Basique"`), sans identifiant Anki préempté (`anki_id: None`), conçu pour fusionner de façon transparente et adopter l'identité du premier modèle équivalent importé.
  _Avoid_ : gabarits par défaut multiples, pack de démarrage forcé
- **Isomorphisme structurel (de type de note)** : relation d'équivalence entre deux types de notes dont la liste ordonnée des champs et la finalité sémantique sont identiques (ex: `["Recto", "Verso"]` et `["Front", "Back"]`), permettant leur réutilisation conjointe sans instancier de clone artificiel `(Importé)`.
  _Avoid_ : doublon toléré, clone de modèle, alias flou
- **Règle de génération conditionnelle (de carte)** : règle officielle du moteur Anki selon laquelle un gabarit de carte `i` n'engendre une carte physique que si son recto (`qfmt`), après résolution de toutes les directives conditionnelles (`{{#Champ}}` / `{{^Champ}}`), contient au moins un champ non vide et du texte visible. Une note ne produit jamais de carte au recto vide.
  _Avoid_ : génération aveugle, carte vide par défaut, quantificateur passif
- **Champ orphelin archivé** : mécanisme de préservation non destructive sauvegardant les données d'un champ supprimé dans Anki lors d'une mise à jour de schéma dans une clé de repli (`_orphaned_fields`), évitant toute perte irrémédiable de texte rédigé dans la Forge.
  _Avoid_ : champ supprimé, purge silencieuse, troncature de note
- **Enveloppement de balise (Wrapping)** : opération d'encadrement non destructif d'une sélection textuelle au sein d'un gabarit de type de note par une balise HTML (`<span>` en ligne, `<div>` en bloc), une règle CSS ou une directive conditionnelle Anki (`{{#Champ}}...{{/Champ}}`), préservant l'intégrité du contenu existant.
  _Avoid_ : remplacement de sélection, écrasement de balise, injection destructrice

## Rétention SRS & Charge

- **Stabilité estimée** : approximation de la stabilité d'oubli d'une carte, dérivée de son intervalle courant sous l'hypothèse d'une rétention cible de 90 %. Ce n'est pas la stabilité calculée par Anki, que la Forge ne stocke pas.
  _Avoid_ : stabilité FSRS, stabilité réelle, stabilité mémorisée, stability

- **Rétention projetée (courbe d'oubli)** : probabilité de rappel d'une carte en fonction du nombre de jours écoulés **depuis une révision**, gouvernée par la loi de puissance FSRS. Elle vaut 100 % à l'instant de la révision et décroît ensuite. Ce n'est jamais la prédiction d'une date du calendrier.
  _Avoid_ : rétention future, rétention prédictive, courbe de rétention, taux de rétention

- **Charge à l'équilibre** : estimation du nombre de révisions par jour d'une collection parvenue à son régime stable, obtenue en sommant l'inverse de l'intervalle de chaque carte. Ce n'est pas une projection calendaire fondée sur des dates d'échéance, que la Forge ne stocke pas.
  _Avoid_ : charge prévisionnelle, charge projetée, charge future, charge de travail future, workload

- **Ordonnancement (propriété d'Anki)** : l'état de révision *actif* d'une carte — date d'échéance (`due`), facteur de facilité, journal de révision (`revlog`) et paramètres d'algorithme (FSRS/SM-2). Il relève **exclusivement d'Anki** : la Forge ne le modélise, ne le calcule ni ne le reconstitue. Un export ne fabrique jamais d'état d'ordonnancement ; les cartes exportées redémarrent leur flux dans Anki.
  _Avoid_ : planification, scheduling, ordonnancement AnkiForge, SRS de la Forge

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

## Paquets, Documents & Arborescences de classement

- **Paquet (Deck)** : conteneur logique de cartes d'une collection Anki, pouvant être organisé en sous-paquets selon une arborescence délimitée par le séparateur canonique `::`.
  _Avoid_ : deck, dossier de cartes, classeur de cartes
- **Sous-paquet** : paquet rattaché à un paquet parent, dont le nom canonique est préfixé par le chemin hiérarchique du parent suivi du séparateur `::`.
  _Avoid_ : sous-deck, child deck, sous-dossier de cartes
- **Dossier de documents** : conteneur logique permettant de classer et organiser les documents de la bibliothèque par matière, niveau ou thématique.
- **Chemin hiérarchique (Séparateur `::`)** : convention standard d'Anki et d'AnkiForge séparant les niveaux arborescents (ex: `Faculté::Semestre 1::Biologie`). Chaque segment du chemin constitue un nœud d'arborescence ayant sa propre existence logique et son identité dans le modèle de données.
- **Sous-dossier** : dossier rattaché à un dossier parent, dont le nom canonique est préfixé par le chemin hiérarchique du parent suivi du séparateur `::`.
- **Autocomplétion hiérarchique** : mécanisme de complétion contextuelle guidé par le séparateur `::`, qui propose dynamiquement à la frappe les branches parentes et les sous-conteneurs existants sous le préfixe courant.
  _Avoid_ : complétion texte brute, autocomplete simple
- **Fil d'Ariane prévisionnel (de création)** : composant d'interface décomposant en temps réel les segments d'un chemin hiérarchique en cours de saisie, distinguant visuellement les conteneurs déjà existants de ceux qui seront créés à la validation.
  _Avoid_ : breadcrumb passif, prévisualisation texte, indicateur de chemin
- **Surface documentaire** : ensemble cohérent des interactions permettant de sélectionner, importer, structurer, consulter, délimiter, indexer ou auditer un document. Une surface peut traverser plusieurs vues, widgets et dialogues.

## Ingestion & Parsing documentaire

- **Passe d'extraction Marker** : exécution du moteur d'apprentissage profond `marker_single` convertissant un document PDF en Markdown structuré KaTeX et extrayant ses illustrations, pilotée par un jeu d'options d'exécution typées (`MarkerOptions`).
  _Avoid_ : OCR complet, run marker, parse job
- **Options d'extraction Marker (`MarkerOptions`)** : contrat de configuration technique encapsulant les drapeaux d'exécution du binaire Marker (portée de pages, forçage ou contournement de l'OCR, filtrage KaTeX, résolution DPI et cible d'accélération matérielle).
  _Avoid_ : config OCR, marker flags, paramètres PDF

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
- **Génération visionnée** : mode de génération dans lequel le modèle de langage reçoit directement le rendu visuel conforme des planches ou illustrations en entrée multimodale (VLM), sans injection de balise fabriquée dans le corps textuel.
  _Avoid_ : génération album, prompt image, injection visuelle
- **Résolution visuelle de fragment** : opération déterminant et rendant l'image conforme associée à un fragment de document pour l'analyse multimodale ou la consultation (planche pivotée via la couture pour un album, fichier d'illustration lié pour un document textuel).
  _Avoid_ : extraction d'image, chargement de planche, fetch media

## Figures de documents

- **Figure** : image extraite d'un document textuel (PDF, DOCX, PPTX, Markdown, page web) et rattachée au fragment de texte dont elle dépend. Elle se distingue de la **Planche** — page d'un album — en ce qu'elle n'est jamais une page autonome : elle ne porte ni transcription propre, ni rotation durable, ni recadrage.
  _Avoid_ : illustration, image liée, image de document, vignette, figure de planche
- **Fragment de figure** : fragment documentaire (`DocumentChunkModel`) porteur d'une clé média non nulle et de son contexte textuel immédiat (fil d'Ariane, numéro de page, légende ou extrait), matérialisant l'unité d'ancrage déterministe pour l'Image Occlusion et l'analyse visuelle.
  _Avoid_ : chunk image, fragment visuel, nœud média
- **Filtrage de figure** : règle déterministe d'exclusion géométrique et dimensionnelle éliminant les artéfacts décoratifs (puces, icônes, séparateurs) lors de l'ingestion native selon un seuil de surface minimale (22 500 px²), un côté minimal (60 px) et des bornes de ratio d'aspect (entre 1:8 et 8:1).
  _Avoid_ : seuil de taille, nettoyage d'images, crop auto
- **Galerie de figures** : surface présentant les figures d'un document ou de la **section courante**, offrant leur consultation et l'action directe vers le masquage d'occlusion. Sa portée suit celle de la section affichée, avec une vue étendue possible à tout le document.
  _Avoid_ : panneau médias, bibliothèque d'images, collection d'images

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

## Indexation & Réindexation RAG

- **Réindexation (d'un document)** : la ré-ingestion structurante d'un document — re-découpage, ré-indexation vectorielle (FAISS/BM25) et re-synchronisation de sa couverture — qui le remet en conformité avec la stratégie de découpage courante. C'est l'acte portant sur **un** document.
  _Avoid_ : réindex, ré-index, vectorisation, re-embedding, rebuild index
- **Passe de réindexation** : l'exécution qui réindexe un ensemble de documents et dont l'avancement global est rapporté à l'utilisateur. C'est l'unité de la surface d'avancement, indépendamment du chemin qui l'a déclenchée (démarrage, commande manuelle, rév vectorisation de délimitation).
  _Avoid_ : lot de réindexation, batch RAG, job d'indexation, file d'indexation
- **Réindexation migratoire** : la passe de réindexation déclenchée automatiquement au démarrage lorsqu'une nouvelle version de stratégie de découpage rend obsolètes des documents indexés avec l'ancienne.
  _Avoid_ : migration de schéma, upgrade d'index, rattrapage

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
- **Bandeau d'activité global** : indicateur d'avancement unique et persistant, hébergé **hors** des dispositions enfichables (au niveau de la fenêtre), de sorte qu'une passe de réindexation reste visible quel que soit l'écran actif. C'est un composant transversal, jamais un widget de vue.
  _Avoid_ : barre de statut, barre de progression globale, footer, overlay
- **Contenu d'onglet Paramètres adaptatif** : règle de mise en page selon laquelle le contenu des onglets de la modale Paramètres se comprime pour tenir dans la zone disponible **sans jamais imposer de barre de défilement horizontale ni tronquer un libellé**, de la largeur minimale du modal (820px) jusqu'à l'infini. Les grilles denses (miniatures de layouts, métriques de stockage) se replient en une seule colonne sous leur seuil de lisibilité. Le conteneur (modale, redimensionnable) reste fixe : c'est le contenu qui s'adapte, jamais l'inverse.
  _Avoid_ : largeur minimale rigide, setFixedWidth, sidebar élargie, conteneur adaptatif
- **Lecteur de documentation embarqué (`DocReaderDialog`)** : boîte de dialogue autonome native basée sur `QTextBrowser` et `AppDocumentationService`, permettant de consulter les guides et la documentation officielle de l'application hors-ligne, avec rendu des illustrations vectorielles SVG locales, recherche textuelle incrémentale et zoom typographique, sans dépendre d'un moteur Chromium lourd ni d'une connexion réseau.
  _Avoid_ : webview de doc, browser externe obligatoire, aide en ligne, visionneuse web

## Clavier & Raccourcis

- **Raccourci clavier (shortcut)** : association déclarée entre une Séquence et une action nommée du Catalogue de raccourcis, à une Portée donnée. Un raccourci n'existe jamais sous la forme d'un `QShortcut` isolé dans une vue.
  _Avoid_ : hotkey, keybind, touche raccourcie
- **Catalogue de raccourcis (registre)** : déclaration exhaustive et unique des raccourcis de l'application (`src/ankiforge/ui/shortcuts/`), source de vérité de tout binding, de tout libellé affiché et de la page de référence documentaire générée.
  _Avoid_ : table de raccourcis, config clavier, keymap
- **Séquence** : combinaison physique de touches (`QKeySequence`) déclenchant un raccourci, distincte de l'action qu'elle sert — une même séquence peut porter des actions différentes selon la Portée.
  _Avoid_ : touche, combo, binding
- **Portée de raccourci** : niveau de résolution hiérarchique d'un raccourci — **Dialogue > Widget > Vue > Application** — où la portée la plus spécifique active l'emporte ; les bindings d'une vue masquée sont inactifs.
  _Avoid_ : contexte de raccourci, priorité clavier, niveau
- **Surcharge de raccourci** : séquence personnalisée substituée par l'utilisateur à la séquence par défaut d'une action, persistée dans les paramètres du profil (`SettingsService`) et réinitialisable.
  _Avoid_ : remap, keymap utilisateur, personnalisation clavier
- **Séquence réservée** : séquence de la liste noire, non remappable, protégeant l'édition de texte (`Ctrl+C`/`X`/`V`/`Z`/`Y`/`A` dans les champs, `Ctrl+W`, `Ctrl+Q`).
  _Avoid_ : raccourci système, raccourci protégé, touche interdite
- **Touche nue** : séquence d'une seule touche (`E`, `Espace`, `V`, `R`, `Suppr`, `Retour`, `!`), admise **uniquement** en portée Widget sur une liste ou une table focalisée.
  _Avoid_ : raccourci simple, touche seule, raccourci direct
- **Règle du texte prioritaire** : toute saisie de texte focalisée absorbe les touches nues et les séquences d'édition avant toute résolution de raccourci.
  _Avoid_ : garde de champ, exception de saisie, priorité du focus
- **Routeur d'action primaire** : définition unique de portée Application (`Ctrl+S`, `Ctrl+Entrée`) qui délègue l'exécution à l'action principale de la vue active, supprimant toute redondance locale.
  _Avoid_ : handler global, dispatcher clavier, action par défaut

## Protocole MCP & Agents externes

- **Serveur MCP persistant** : service d'arrière-plan exposant l'outillage interne d'AnkiForge (audits, inspection, mutations de cartes) à des agents tiers via le protocole standardisé MCP.
- **Agent externe (ou Agent CLI)** : agent d'intelligence artificielle autonome s'exécutant dans un processus distinct (terminal, éditeur tiers) et pilotant AnkiForge via les outils MCP.
- **Jeton d'autorisation MCP** : secret d'authentification locale généré par session, requis pour autoriser les requêtes entrantes vers le serveur MCP persistant.
- **Patch en attente (Staged Patch)** : proposition structurée de modification ou de refactorisation (diff avant/après) émise par l'IA ou un outil MCP, maintenue en attente d'une validation humaine explicite avant toute persistance définitive.
- **Validation en deux phases (Two-Phase Commit)** : principe de sécurité selon lequel aucune opération chirurgicale ou destructive initiée par un agent n'altère directement la collection, chaque mutation devant obligatoirement être soumise sous forme de patch intermédiaire puis validée par l'utilisateur.
- **Bloc de réflexion étendu (Extended Thinking / Thought Block)** : flux de raisonnement intermédiaire émis par un modèle d'IA avant de formuler sa réponse finale, streamé en temps réel dans l'interface avec des métriques de temps et de tokens, et distinct du contenu final des cartes.
- **Composant de discussion riche (Rich Chat Widget)** : élément d'interface interactif (tableau de cartes, prévisualisation avec formules KaTeX, sélecteur de modèle) inséré directement dans le fil de conversation du Consultant IA pour manipuler la collection au-delà du simple texte.
- **Hub MCP & Agents** : interface centrale de supervision et d'accueil orientant en premier lieu vers le serveur MCP local pour outiller les agents externes sans surcoût d'API, tout en maintenant l'accès au Consultant IA in-app en second plan.
- **Création staged de note** : proposition de création d'une ou plusieurs notes et de leurs cartes physiques associées sous forme de patch en attente (`note_create` ou `batch_note_create`), soumise à validation humaine ou confirmation explicite avant insertion en base.
  _Avoid_ : note préliminaire, brouillon de carte, création différée
- **Contrôle d'hallucination de paquet** : garde-fou interdisant la création implicite ou accidentelle de paquets inexistants lors de la soumission de notes par un agent externe, exigeant l'existence préalable du paquet ou sa création délibérée.
  _Avoid_ : vérification de deck, filtre de paquet, validation de cible
- **Amorçage d'agent (Init)** : opération par laquelle un agent externe demande au serveur MCP de générer un fichier d'instructions méthodologiques dans son répertoire de travail, afin de maximiser ses compétences pour piloter AnkiForge. Le fichier produit est un adaptateur d'instructions au format attendu par le client (`GEMINI.md`, `CLAUDE.md`, `ANKIFORGE_GUIDE.md`, etc.), contenant les workflows d'usage, le catalogue des outils MCP et les garde-fous anticipatifs.
  _Avoid_ : bootstrap, setup, onboarding, workspace init, init workspace
- **Garde-Fou MCP (ou Espace de Validation MCP)** : sous-onglet dédié et autonome au sein de l'onglet Serveur MCP, centralisant l'examen, la comparaison haute fidélité et l'arbitrage (validation, retouche directe, rejet) des patchs chirurgicaux émis par des agents externes sans redirection vers le Consultant IA in-app.
- **Décorrélation des flux de validation** : séparation hermétique entre les propositions issues d'agents MCP externes (administrées exclusivement dans le Garde-Fou MCP) et les suggestions issues du chat in-app (visibles dans l'Espace de Travail du Consultant IA). Les rafraîchissements de données (`refresh_data`) consécutifs à une mutation MCP sont strictement passifs et n'entraînent aucune commutation automatique d'onglet.
  _Avoid_ : file de patch unifiée avec saut d'écran, bascule implicite d'inspecteur
  _Avoid_ : inspecteur consultant, onglet diff, panneau de chat
- **Comparateur sémantique de note (ou Diff sémantique de note)** : composant visuel présentant les modifications d'une note champ par champ avec deux colonnes synchronisées, surlignage mot à mot intra-ligne (*word-level diff*) et prévisualisation Anki en direct, sans exposition de syntaxe JSON brute.
  _Avoid_ : diff JSON, inspecteur textuel brut, raw diff viewer
- **Cockpit de connexion MCP (ou Supervision MCP)** : surface opérationnelle de pilotage direct du serveur MCP local agencée en deux colonnes sans défilement, réunissant le cycle de vie du démon, les adresses des points de terminaison (Streamable HTTP, SSE), le jeton Bearer et la génération de snippets de configuration client prêts à copier.
  _Avoid_ : panneau serveur, config mcp, page mcp, onglet settings
- **Catalogue interactif des outils MCP** : surface d'exploration des 58 outils exposés par le serveur MCP d'AnkiForge, organisés par domaine fonctionnel, permettant de rechercher et d'inspecter les schémas JSON, paramètres obligatoires et facultatifs, descriptions et règles de garde-fous.
  _Avoid_ : liste des outils, registre des fonctions, menu outils
- **Télémétrie d'activité MCP** : espace de supervision en temps réel des invocations d'outils par les agents externes, présentant les métriques d'exécution (durée, statut, fréquence) et un inspecteur maître-détail d'arguments et de retours JSON sans blocage modal.
  _Avoid_ : logs MCP, journal d'appels, historique brut
- **Espace Guides & Workspaces MCP** : interface d'amorçage et de suivi des environnements de travail d'agents, permettant de générer les adaptateurs méthodologiques (`init_agent_workspace`), d'auditer la dérive de version des guides (`check_guide_version`) et de visualiser les personas MCP configurées.
  _Avoid_ : setup agents, dossier guides, onboarding mcp


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

## Soutien & Financement communautaire

- **Dialogue de soutien** : boîte de dialogue invitant l'utilisateur à contribuer au financement bénévole du projet via une plateforme tierce (Ko-fi).
  _Avoid_ : pop-up ko-fi, modal don, fenêtre de donation, popup de soutien
- **Rappel de soutien au démarrage** : préférence d'application déterminant si le dialogue de soutien est présenté de façon temporisée lors du lancement de l'application.
  _Avoid_ : popup de démarrage, nag screen, notif ko-fi, prompt démarrage

## Tags & Hygiène taxonomique

- **Grappe de tags (cluster)** : un ensemble de variantes d'un tag (différences de casse ou proximité typographique Levenshtein) identifiées comme se rapportant au même concept.
  _Avoid_ : groupe de tags, famille de tags, doublons de tags
- **Tag canonique (forme cible)** : le libellé unique retenu pour remplacer l'ensemble des variantes d'une grappe lors d'une fusion.
  _Avoid_ : tag pivot, tag maître, tag de remplacement
- **Fusion de tags** : l'opération atomique remplaçant sur toutes les notes concernées les variantes d'une grappe par leur tag canonique unique, sans duplication ni altération des tags de provenance.
  _Avoid_ : renommage de tags, écrasement de tags

## Compétences agentiques & Flux d'ingénierie AnkiForge

- **Catalogue de compétences (Skill catalog)** : l'ensemble des modules d'expertise procédurale (`SKILL.md`) situés sous `.agents/skills/`, conformes au standard ouvert `agentskills.io` et chargés à la demande par divulgation progressive.
  _Avoid_ : plugins, prompts système, extensions, prompts agents
- **Divulgation progressive (Progressive disclosure)** : le mécanisme d'activation cognitive à trois paliers d'une compétence — Niveau 1 (découverte minimale par nom et description dans le contexte initial), Niveau 2 (activation du corps procédural `SKILL.md` sur correspondance de tâche), Niveau 3 (exécution ciblée des ressources spécialisées dans `references/` ou `scripts/`).
  _Avoid_ : chargement paresseux, lazy loading, prompt caching
- **Aiguilleur de flux (`ask-forge`)** : le routeur décisionnel guidant l'agent et l'utilisateur à travers le réseau des compétences d'ingénierie (`idée → cadrage → spécification → tickets → implémentation → revue`), ancré exclusivement sur le gestionnaire de tâches Obsidian du projet.
  _Avoid_ : routeur Matt, ask-tristan, ask-matt, copilote, superviseur
- **Règle anti-boucle Obsidian** : le protocole d'interaction atomique imposé aux agents sur le tableau Kanban et les tickets (`Lecture → Écriture/Déplacement → Arrêt immédiat`), interdisant formellement toute auto-vérification circulaire ou relecture non sollicitée.
  _Avoid_ : validation en boucle, boucle de contrôle, vérification du Kanban

## Documentation & Hygiène du Dépôt

- **Docstring Google sans redondance** : standard de documentation en français décrivant la finalité métier (`Args:`, `Returns:`, `Raises:`) sans répéter les types de paramètres déjà portés de façon stricte par la signature Python 3.12+ vérifiée par `mypy`.
  _Avoid_ : docstring sphinx, docstring numpy, types dans docstring
- **Commentaire de justification architecturale** : commentaire de code explicitant le pourquoi non évident d'un choix technique (verrous WAL SQLite sous Windows, contournements de packaging macOS/Nuitka, directives de linters), sanctuarisé contre toute suppression.
  _Avoid_ : paraphrase de code, commentaire trivial, commentaire de bruit

## Instructions & Adaptateurs d'Agents

- **Source canonique d'instructions (Canonical Instructions Source)** : ensemble de fragments modulaires sous `.agents/instructions/` définissant la source unique de vérité pour les règles d'ingénierie, commandes canoniques, faits d'architecture et compétences du dépôt.
  _Avoid_ : règles globales, doc agent, méta-instructions
- **Adaptateur d'instructions (Instruction Adapter)** : fichier cible propre à un environnement d'agent (`AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `GEMINI.md`), conservant ses spécificités d'orchestration ou de persona tout en transcluant fidèlement les fragments canoniques entre balises de synchronisation.
  _Avoid_ : prompt fichier, instruction template, config agent
- **Balise de transclusion (Transclusion Tag)** : paire de balises HTML/Markdown délimitant strictement une section synchronisée (`<!-- BEGIN CANONICAL:... -->` / `<!-- END CANONICAL:... -->`), interdisant l'édition manuelle directe dans l'adaptateur au profit de la source canonique.
  _Avoid_ : marker, placeholder, slot, include tag
- **Contrôle de dérive des instructions (Instruction Drift Check)** : étape déterministe intégrée à la porte de vérification canonique (`script/verify.py`) et au pre-push, vérifiant sans régénération que chaque adaptateur est strictement isomorphe à sa projection canonique, avec correction automatique sous `--fix`.
  _Avoid_ : linter de doc, sync check, contrôle markdown

## Synthèse Vocale (TTS) & Multimédia Audio

- **Synthèse vocale (TTS)** : génération d'extraits audio prononçant le contenu textuel d'une carte (recto/verso) selon un moteur (in-process, sidecar local autonome ou moteur système OS).
  _Avoid_ : text-to-speech brut, voix IA, audio flashcard
- **Fournisseur TTS (TTS Provider)** : abstraction modulaire découplée (`TTSProvider`) pilotant un moteur vocal spécifique (`EdgeTTSProvider`, `PiperSidecarProvider`, `KokoroSidecarProvider`, `SystemSpeechProvider`).
  _Avoid_ : backend TTS, driver audio, moteur vocal
- **Sidecar vocal local** : exécutable ou runner déporté autonome placé hors du bundle applicatif dans `~/.ankiforge/tools/tts/` (ex: Piper, Kokoro), évitant d'alourdir le binaire Nuitka et s'exécutant en processus isolé.
  _Avoid_ : binaire interne, dépendance embarquée, plugin TTS

## Paramètres de l'application & Drapeaux Anki

- **Modale de paramètres (SettingsModal)** : surface de configuration du profil utilisateur organisée en onglets thématiques, protégée contre les fermetures intempestives (neutralisation d'autoDefault, interception de la touche Entrée, sauvegarde explicite en place et raccourci global `Ctrl+S` / `Cmd+S`).
  _Avoid_ : fenêtre settings, popup préférences, dialogue options
- **Libellé de drapeau (Flag label)** : nom personnalisé attribué à l'un des 7 drapeaux colorés d'Anki (indices 1 à 7) pour le profil actif. Un libellé non défini ou vide applique un repli automatique strict vers la désignation native du jeton Anki (`DesignTokens.FLAG_NAMES`).
  _Avoid_ : tag couleur, nom de couleur, drapeau custom

## Échanges, Imports & Synchronisation Anki

- **Import de collection (`.colpkg`)** : opération de remplacement intégral et atomique du périmètre de cartes Anki d'un profil par le reflet exact d'une collection Anki, avec sanctuarisation stricte de la matière de travail propre à AnkiForge (documents sources, fragments RAG, personas, agents IA, prompts, pipelines).
  _Avoid_ : fusion de collection, merge colpkg, restore database
- **Import de paquet (`.apkg`)** : apport partiel et fusionnel d'un sous-ensemble de notes, cartes et médias au sein de la collection existante, avec détection des conflits de contenu selon la Règle 11 et arbitrage éventuel dans le dialogue Smart Merge.
  _Avoid_ : import global, écrasement de paquet
- **Périmètre Collection Anki** : sous-ensemble des entités de données directement issues du modèle Anki et gouvernées par la collection (`DeckModel`, `NoteTypeModel`, `CardModel`, `NoteModel`, `NoteVersionModel`, `MediaModel`), intégralement remplacé lors d'un import de collection `.colpkg`.
  _Avoid_ : données globales, base complète
- **Périmètre Studio / Forge** : ensemble des entités d'authoring, d'indexation et d'orchestration créées dans AnkiForge (`DocumentModel`, `FolderModel`, `DocumentPageModel`, `DocumentChunkModel`, `PersonaModel`, `PromptModel`, `PipelineModel`, `SettingModel`), strictement préservées lors d'un remplacement de collection.
  _Avoid_ : configuration système, métadonnées
- **Sauvegarde pré-importation** : instantané de sécurité de la base SQLite créé automatiquement et obligatoirement avant tout remplacement de collection par un `.colpkg`, exclu de la politique de rotation standard pour permettre un retour arrière immédiat.
  _Avoid_ : backup temporaire, snapshot volatile
- **Réconciliation de types de note (Note Type Reconciliation)** : protocole d'alignement entre un type de note entrant et la base locale, privilégiant l'autorité d'`anki_id` (`mid`), reconnaissant l'isomorphisme structurel pour éviter les doublons et archivant les champs retranchés sans altérer les notes existantes.
  _Avoid_ : écrasement de schéma, copie systématique, suffixage infini
- **Périmètre d'autorité distribuée (Distributed Authority Perimeter)** : frontière de responsabilité gouvernant les échanges entre Anki et AnkiForge — Anki détenant l'autorité sur l'ordonnancement SRS et l'état révisé des cartes, AnkiForge détenant l'autorité sur les sources, la traçabilité documentaire (RAG) et les cartes en cours de conception.
  _Avoid_ : maître-esclave rigide, base dupliquée sans rôle, sync bidirectionnelle naïve
- **Guide visuel du cycle de vie distribué** : documentation pédagogique embarquée illustrée de 5 diagrammes vectoriels (SVG), guidant l'utilisateur dans l'articulation de ses sessions de travail entre la création dans le Studio AnkiForge et les révisions quotidiennes dans Anki, clarifiant la sanctuarisation des périmètres et l'élimination des cartes zombies sans jargon technique développeur.
  _Avoid_ : manuel technique, spec cycle de vie, doc interne






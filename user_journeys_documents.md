# 📚 Fonctionnalités & Parcours Utilisateur (Documents)

L'écosystème **AnkiForge** a été bâti autour de l'idée que le **Document Source** est la vérité absolue (Single Source of Truth). Voici la cartographie complète des fonctionnalités liées aux documents et les deux principaux parcours d'utilisation (Journeys).

---

## 🛠️ 1. Inventaire des Features "Documents"

### A. Ingestion & Conversion (Le "Pipeline d'Entrée")
- **Import Local Rapide :** Glisser-déposer d'un PDF local. Stockage du fichier brut dans l'espace isolé (`~/.ankiforge/profiles/`).
- **Web Scraping & YouTube :** Import d'une URL web (extraction propre via `trafilatura`) ou d'une vidéo YouTube (téléchargement natif de l'audio + extraction des sous-titres/transcription IA).
- **Moteur d'Extraction OCR (Marker IA) :** Si le PDF est complexe (mathématiques, colonnes), lancement d'un traitement asynchrone lourd (Marker) avec affichage de la progression en direct dans l'onglet **Terminal** --> Création d'un fichier markdown associé pour pouvoir passer les informations sous forme de texte et de ne pas utiliser les modèles de visions plus couteux.

### B. Interface d'Édition et de Lecture (`DocumentsView`)
- **Arborescence Dynamique :** Gestion des fichiers via des dossiers virtuels (`FolderModel` / `DocumentModel`).
- **Slider Multi-Vues (Le Triptyque) :**
  1. **Vue PDF Native :** Intégration haute performance (`QPdfView`) pour lire le document original sans latence.
  2. **Éditeur Markdown & KaTeX :** Un éditeur de texte avec son propre sous-slider (Brut / Mixte / Rendu Final). Coloration syntaxique, rendu HTML/LaTeX en direct (via `markdown` Python) sans surcharge mémoire (zéro Chromium).
- Onglet **Terminal Marker :** Console en temps réel pour suivre les longs traitements d'OCR.

### C. Découpage & Structuration (La mécanique des Chunks et Facettes)

Le découpage manuel par balises `[SPLIT]` est abandonné au profit d'une approche transparente et hybride. Il est crucial de faire la distinction entre un "Repère Visuel" (la Page) et l'unité de base de données (le Chunk).

**1. De la Page au Chunk (L'Extraction)**
- **Les Repères Visuels (Pages) :** Pour les PDF, Marker IA injecte des balises invisibles de pagination (ex: `<!-- PAGE:12 -->`) lors de la conversion Markdown.
- **La Découpe Sémantique (Chunks) :** En arrière-plan, un script découpe le long texte Markdown à chaque double saut de ligne (`\n\n`) pour former des paragraphes logiques. Chaque paragraphe devient un objet `DocumentChunkModel` dans SQLite.
- **L'Attachement :** Chaque Chunk est scanné pour déterminer à quelle `PAGE` ou quel `TITRE` Markdown il appartient. L'interface peut ainsi agréger des dizaines de petits Chunks pour afficher à l'Étudiant un simple résumé : *"La Page 12 est verte"*.

**2. Le Choix des Facettes (Le Dictionnaire Global & L'IA Découverte)**
L'application s'appuie sur un **Dictionnaire Global** de facettes (Définition, Cause, Mécanisme, Théorème, etc.) stocké dans `CognitiveFacetModel`.
Cependant, pour éviter que le moteur d'analyse ne s'épuise à tester 50 facettes inutiles sur chaque paragraphe, le profilage s'opère en deux temps :
- **L'IA Découverte (Le Scan initial) :** Lors de l'importation d'un document, une IA très rapide lit un échantillon de 5 pages et consulte le Dictionnaire Global existant. Elle propose ensuite à l'utilisateur : *"Ce document traite de Biologie. Je te suggère d'activer ces 4 facettes pour le profilage : [Définition, Mécanisme, Étiologie, Conséquence]."*. L'utilisateur peut valider, décocher des propositions ou en ajouter.
- **Le Profilage Granulaire :** Une fois la sous-sélection validée pour ce document, l'IA de profilage lit chaque Chunk et **pioche librement** parmi ces 4 facettes pour dresser la checklist du paragraphe.

### D. Exploitation IA, Qualité & Mises à Jour (V2)

#### 1. Espaces de Création
- **Vue de Création (Privilégiée) :** L'utilisateur choisit un document, cible une plage de pages ou un chapitre, choisit le pipeline IA et valide les cartes générées.
- **Consultant IA (Rapide) :** Un chat libre où l'utilisateur copie-colle un texte et cible un *Persona* (ex: "Professeur").

#### 2. Le Smart Coverage (Diagnostic Documentaire)
Le "Coverage" garantit qu'aucune notion clé d'un cours ne passe à la trappe. Au lieu d'avoir un simple pourcentage, le système propose un diagnostic visuel granulaire.

**A. Profilage par l'IA (La Checklist)**
- Lorsqu'un utilisateur demande le profilage d'un document, l'IA (le "Profileur Cognitif") lit chaque paragraphe ou sous-chapitre (`DocumentChunkModel`).
- L'IA génère une **Checklist d'exigences (Facettes)** pour chaque morceau. Par exemple, si l'IA lit un paragraphe sur une maladie, elle va exiger la création de cartes répondant à 3 facettes : *Définition*, *Symptômes*, *Traitement* (`ChunkFacetRequirementModel`).

**B. La Heatmap (Visualisation du Coverage)**
L'interface affiche le document sous forme de "Heatmap" :
- **Gris :** Le paragraphe n'a pas encore été analysé par le Profileur IA.
- **Orange :** L'IA a dressé une Checklist, mais il manque des cartes Anki pour satisfaire toutes les facettes requises. C'est un appel à l'action.
- **Vert :** Couverture parfaite. Des cartes Anki ont été créées et liées mathématiquement (`NoteChunkLinkModel`) à toutes les facettes exigées pour ce paragraphe. L'apprentissage est verrouillé.

**C. L'Inspecteur Cognitif & Le Juge (Fact-Checker)**
- En cliquant sur un paragraphe "Orange", l'utilisateur voit exactement quelles facettes manquent (ex: "Il te manque une carte pour les *Symptômes*").
- Le **Fact-Checker (Le Juge)** est un agent optionnel qui vérifie si les cartes liées au paragraphe sont justes et ne contiennent pas d'hallucinations par rapport au texte source.

#### 3. Smart Merge & Tolérance OCR (Levenshtein)
Lors de l'importation d'une version V2 d'un document (ex: mise à jour du cours) :
- **Fuzzy Matching :** L'OCR n'étant pas déterministe (Marker peut générer de petites variations d'espaces ou de caractères), le hachage MD5 strict est remplacé par un calcul de distance de **Levenshtein** (via extension C native).
- Si la similarité entre un paragraphe V1 et V2 est > 95%, le "Coverage" et les cartes associées sont conservés automatiquement.
- Si le texte a sémantiquement changé, l'interface propose à l'utilisateur de valider si la carte existante est toujours pertinente, ou s'il faut la mettre à jour.

---

## 🛤️ 2. Les Parcours Utilisateurs (User Journeys)

### 🎓 Parcours "Étudiant Standard"
*L'étudiant classique veut aller vite. Il a un cours de 20 pages en PDF et son examen est dans 2 semaines.*

1. **Importation :** Il glisse-dépose son PDF de cours dans AnkiForge.
2. **Lecture Rapide :** Il lit son cours via la **vue PDF** native.
3. **Ciblage :** Il repère que les concepts clés sont sur les pages 12 à 15.
4. **Génération (Forge) :** Il ouvre la Vue de Création, indique "Pages 12 à 15", et choisit un prompt simple.
5. **Synchronisation (Autonome) :** L'application génère un fichier `.apkg` qu'il importe manuellement dans son logiciel Anki (aucune connexion directe à la base Anki n'est requise).

> **Le bénéfice :** Gain de temps massif. L'interface masque la complexité (pipelines IA, Levenshtein, etc.) et sécurise l'environnement via l'export fichier.

---

### ⚡ Parcours "Power User" (Ton Profil)
*Le Power User gère des milliers de cartes, des cours denses avec des maths (KaTeX), et veut 100% de rétention.*

1. **Ingestion Lourde (OCR) :** Import d'un énorme PDF scientifique. Lancement de l'**Analyse Marker IA**.
2. **Monitoring :** L'UI bascule sur l'onglet **Terminal**. Suivi des logs de traitement CPU/GPU locaux.
3. **Révision KaTeX :** L'analyse finit. L'UI bascule sur l'**Éditeur Markdown**. Vérification du rendu mathématique (sans surcharge Chromium).
4. **Orchestration BDD (Pipelines) :** Lancement du **Pipeline IA de Profilage** sur l'ensemble des pages. Génération de centaines de cartes via RAG Vectoriel et ciblage de facettes (Quoi, Pourquoi, Comment).
5. **Audit & Linter :** Passage dans l'onglet **Analyse & Audit (Wozniak)**. Le Fact-Checker vérifie la cohérence des cartes face aux *DocumentChunkModels*.
6. **Mise à Jour V2 (Smart Merge) :** Lors de l'arrivée d'un nouveau polycopié, importation de la V2. L'algorithme de Levenshtein (en C) transfère le "Coverage" des pages inchangées, et l'UI met en exergue les nouveautés exigeant une fusion manuelle intelligente.
7. **Exportation :** Exportation d'un `.colpkg` complet avec les médias inclus, prêt à être déployé.
# Hub Documentaire & Multimodalité 📚

Le **Hub Documentaire** d'AnkiForge centralise et valorise toutes vos sources d'apprentissage. Il ne s'agit pas d'un simple gestionnaire de fichiers, mais d'une infrastructure complète d'ingestion sémantique, d'indexation multimodale et de suivi de couverture des connaissances.

---

## 📥 1. Sources Documentaires Prises en Charge

AnkiForge supporte une grande diversité de formats bruts grâce à des moteurs d'extraction spécialisés :

| Type de Source | Moteur Principal | Fonctionnalités & Spécificités |
| :--- | :--- | :--- |
| **Documents PDF** | **Marker OCR** (Deep Learning) | Restitution parfaite de la structure, des tableaux et conversion native des formules mathématiques en syntaxe **LaTeX**. Fallback rapide sur `pdfplumber`. |
| **Vidéos YouTube** | **API Sous-titres + yt-dlp** | Récupération instantanée des sous-titres officiels/automatiques. En cas d'absence de sous-titres, téléchargement du flux audio et transcription locale par **Whisper**. |
| **Pages Web** | **Trafilatura / BeautifulSoup + Rendu JS** | Extraction épurée du corps d'article, suppression automatique des bannières, menus et publicités, préservation des balises de code et des titres. Le **Web Importer** sait déclencher un **rendu JavaScript headless** pour les pages dynamiques (SPA, contenus chargés après interaction), avec retombée automatique sur le HTML statique en cas d'échec. |

!!! note "Formats récents"
    Le support des **notebooks Jupyter (`.ipynb`)** et des **fichiers source Python (`.py`)** a été ajouté pour rapprocher AnkiForge de la documentation technique et scientifique vivante : vos notebooks d'expérimentation deviennent directement des sources de flashcards.
| **Bureautique** | **python-docx / python-pptx** | Parsing structuré des documents Word (`.docx`) et présentations PowerPoint (`.pptx`), extraction des diapositives et des notes du présentateur. |
| **Notebooks Jupyter (`.ipynb`)** | **Parser Natif** | Conversion des cellules Markdown, code et sorties textuelles en Markdown structuré, en préservant les blocs exécutables. |
| **Code Source Python (`.py`)** | **Parser AST (`ast`)** | Génération d'une documentation Markdown structurée par arbre syntaxique (docstrings, fonctions, classes, constantes). |
| **EPUB** | **`EpubParser`** | Extraction des chapitres EPUB 2/3 en Markdown paginé avec conversion MathML → LaTeX. Support `.epub`. |
| **Fichiers Markdown & Texte** | **Parsers Natifs** | Traitement instantané des notes personnelles et documentations techniques brutes. |

---

## ✂️ 2. Découpage Sémantique (*Chunking*)

Lors de l'ingestion, le service `ChunkingService` découpe les textes longs selon une stratégie respectueuse du contexte :
- **Respect de la hiérarchie** : Les coupures s'effectuent prioritairement aux frontières des titres (`H1`, `H2`, `H3`) et des paragraphes logiques.
- **Fenêtres glissantes avec recouvrement (*Overlap*)** : Un chevauchement paramétrable (ex. 10 à 15% de tokens) est conservé entre les segments contigus pour préserver la continuité du raisonnement.
- **Préservation des blocs insécables** : Les tableaux, blocs de code et formules mathématiques complexes ne sont jamais tronqués au milieu de leur structure.

---

## 🎯 3. Délimitation Documentaire Intelligente

Pour éviter de surcharger vos modèles de langage ou de générer des cartes sur des sections inutiles (sommaire, bibliographie, remerciements), AnkiForge propose la modale de **Délimitation Documentaire** (`DocumentDelimitationDialog`) :
- **Sélection par pagination** : Choisissez un intervalle précis de pages (ex. pages 14 à 42).
- **Sélection par chapitres** : Cochez/décochez les sections dans l'arborescence du document.
- **Estimation des coûts & tokens** : Visualisez en direct le volume de tokens estimé et le coût associé selon le modèle LLM sélectionné.

---

## 📊 4. Couverture Intelligente (*Smart Coverage*) & Gap Analysis

L'une des innovations majeures d'AnkiForge est la traçabilité continue entre les flashcards créées et leurs sources documentaires d'origine :
- **Liaison déterministe `NoteChunkLinkModel`** : Chaque carte porte des tags de traçabilité (`doc:<id>`, `source:<slug>`, `page:<num>`, `section:<slug>`) ; une synchronisation par tags (`CoverageAlignmentService`) les associe au fragment (*chunk*) précis du document source — aucun matching lexical instable n'est utilisé.
- **Jauge de Smart Coverage** : Pour chaque document de votre bibliothèque, un indicateur de pourcentage affiche la proportion du cours effectivement couverte par des flashcards. Le KPI global du Tableau de Bord est une **moyenne pondérée** par unités (pages/sections), le ratio brut chunks liés étant exposé séparément.
- **Analyse des Lacunes (*Gap Analysis*)** : Un surlignage coloré dans la liseuse de documents met en valeur les passages du cours qui n'ont encore donné lieu à aucune carte, vous garantissant de ne laisser aucune impasse dans vos révisions.

---

## 🖼️ 5. Galerie Visuelle & Albums d'Images

AnkiForge extrait automatiquement toutes les images, diagrammes, schémas anatomiques et graphiques contenus dans vos documents :
- **Visualiseur d'Albums** : Explorez l'ensemble des médias extraits sous forme de grille haute résolution.
- **Occlusion d'Images (*Image Occlusion*)** : Masquez des zones clés (légendes d'un schéma, organes, éléments de circuit électronique) pour créer des cartes d'occlusion visuelle conformes au standard Anki.
- **Gestionnaire de Médias Intégré** : Les images sélectionnées sont automatiquement copiées dans le sous-dossier médias du profil actif lors de l'association à une carte.

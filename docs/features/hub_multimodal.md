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
- **Modes exclusifs (Pages / Chapitres / Sections)** : un seul mode gouverne la délimitation à la fois. Cocher un chapitre ou une section active son mode sans passer par la barre d'onglets, et le panneau de pages disparaît hors mode *Pages* : aucun filtrage croisé ne peut plus rogner la portée retenue.
- **Réouverture fidèle** : les bornes de pages, les pages exclues (`page:N`) et les sections écartées sont restaurées telles quelles ; une exclusion de section mémorisée rouvre le dialogue sur le mode *Sections* plutôt que d'être silencieusement effacée.

---

## 📊 4. Couverture Intelligente (*Smart Coverage*) & Gap Analysis

L'une des innovations majeures d'AnkiForge est la traçabilité continue entre les flashcards créées et leurs sources documentaires d'origine :
- **Liaison déterministe `NoteChunkLinkModel`** : Chaque carte porte des tags de traçabilité (`doc:<id>`, `source:<slug>`, `page:<num>`, `section:<slug>`) ; une synchronisation par tags (`CoverageAlignmentService`) les associe au fragment (*chunk*) précis du document source — aucun matching lexical instable n'est utilisé.
- **Jauge de Smart Coverage** : Pour chaque document de votre bibliothèque, un indicateur de pourcentage affiche la proportion du cours effectivement couverte par des flashcards. Le KPI global du Tableau de Bord est une **moyenne pondérée** par unités (pages/sections), le ratio brut chunks liés étant exposé séparément.
- **Analyse des Lacunes (*Gap Analysis*)** : Un surlignage coloré dans la liseuse de documents met en valeur les passages du cours qui n'ont encore donné lieu à aucune carte, vous garantissant de ne laisser aucune impasse dans vos révisions.

---

## 🖼️ 5. Galerie Visuelle & Albums d'Images

AnkiForge extrait et organise les images, diagrammes, schémas anatomiques et planches scannées au sein d'albums dédiés :
- **Visualiseur d'Albums & Planche-Contact** : Explorez l'ensemble des planches sous forme de grille interactive haute résolution, avec réordonnancement par glisser-déposer, réorientation (rotation 90°) et inspection détaillée.
- **Recadrage Non Destructif par Image Source** : Isolez précisément une sous-région d'intérêt (schéma, formule, figure) directement depuis l'inspecteur de planche :
    - *Repère source invariant* : Le rectangle de recadrage `[x, y, w, h]` est calculé et mémorisé dans le repère natif de l'image source, survivant fidèlement à toute rotation ultérieure de la planche.
    - *Zéro altération disque & réversibilité intégrale* : L'image source originale sur le disque n'est jamais écrasée ni modifiée ; un bouton « Retirer le recadrage » restitue instantanément la planche intégrale.
    - *Convergence stricte* : La couture centrale de rendu (`AlbumService.render_page_image`) gouverne l'ensemble des consommateurs — la vue inspecteur, les vignettes de planche-contact, la transcription OCR par vision IA et l'indexation RAG visuel opèrent sur la même zone cadrée.
    - *Invalidation propre des états dérivés* : Toute modification ou suppression du recadrage purge les fragments textuels associés et marque la planche comme `Périmé` (`stale`), garantissant qu'aucun résidu de transcription obsolète ne soit conservé ou exporté.
- **Occlusion d'Images (*Image Occlusion*)** : Masquez des zones clés (légendes d'un schéma, organes, éléments de circuit électronique) pour créer des cartes d'occlusion visuelle conformes au standard Anki.
- **Transcription Ciblée d'Albums** : Modal dédié (`AlbumTranscriptionDialog`) permettant d'orienter la transcription IA selon des périmètres précis (tout l'album, planches non transcrites, planches périmées ou intervalle de pages), avec tolérance aux pannes et relance chirurgicale des échecs.
- **Gestionnaire de Médias Intégré** : Déduplication MD5, archivage sécurisé et isolation complète par profil utilisateur.

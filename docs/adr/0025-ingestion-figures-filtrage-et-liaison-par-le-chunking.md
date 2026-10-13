# Ingestion des figures : filtrage géométrique et liaison déterministe par le chunking

**Statut :** Accepté

Afin de permettre l'exploitation multimodale des cours illustrés (PDF, PPTX, EPUB, Markdown) et d'alimenter la Galerie de figures pour le masquage d'occlusion (ADR 0018, ADR 0023), nous établissons une chaîne d'ingestion native des figures avec filtrage géométrique des artéfacts décoratifs, et nous unifions la liaison Peewee `DocumentChunkModel.media` au niveau du moteur de découpage (`ChunkingService`).

## Le problème

Jusqu'alors, seuls les albums d'images (`file_type == "album"`) renseignaient la clé `DocumentChunkModel.media` via `VisualRAGService`. Pour les documents textuels :
1. Le parseur PDF natif rapide (`_parse_pdf_with_pypdf`) n'extrayait aucune image, limitant l'extraction de figures au seul moteur Marker OCR (qui nécessite un environnement lourd avec modèles Deep Learning).
2. Même lorsque Marker, `PptxParser` ou `EpubParser` extrayaient des images vers `MediaManager` et inséraient des balises Markdown, aucun fragment `DocumentChunkModel` ne se voyait attribuer de `media_id` en base Peewee.
3. La Galerie de figures (`FiguresGalleryWidget`) et la création de cartes Image Occlusion avec traçabilité `exact` (ADR 0023) restaient donc totalement vides pour l'ensemble des documents textuels.

## Options considérées

1. **Moteur PDF natif : `pypdf` vs PyMuPDF (`fitz`)** :
   - *Option A — `pypdf` + Pillow* : Rejeté. `pypdf` ne fournit pas facilement les coordonnées géométriques (bounding boxes) des images sur la page et présente des performances moindres sur les gros volumes.
   - *Option B — PyMuPDF (`fitz`)* : **Retenu**. PyMuPDF extrait le texte et les flux d'images avec leurs dimensions natives et leurs rectangles englobants réels (`rect` / bounding box), tout en étant extrêmement véloce. La chaîne de parsing PDF devient hiérarchique : Marker OCR (prioritaire si disponible pour le LaTeX complexe) > PyMuPDF (moteur natif rapide par défaut) > `pypdf` (ultime repli de sécurité).

2. **Cardinalité Fragment <-> Figures : Table N:N vs Fragments de figure dédiés (1:1)** :
   - *Option A — Table de liaison N:N `DocumentChunkMediaModel`* : Rejeté. Cela imposerait une migration de schéma lourde et romprait le contrat d'ADR 0023 où un clic d'occlusion cible un unique `chunk_id` pour résoudre le rattachement de provenance au palier `exact`.
   - *Option B — Élection d'une seule figure par fragment* : Rejeté. Les figures surnuméraires d'une page ou d'une diapositive seraient invisibles dans la Galerie de figures.
   - *Option C — Fragments de figure dédiés (1:1)* : **Retenu**. Le contenu textuel du cours constitue le fragment principal (dédié à la couverture textuelle et aux cartes Q/R/Cloze). Chaque figure détectée génère son propre fragment de figure dédié portant le fil d'Ariane, le numéro de page, la légende Markdown, sa clé `media` et sa bounding box.

3. **Filtrage des artéfacts décoratifs** :
   - *Option A — Seuil strict sur chaque dimension ($L \ge 150\text{ px}$ et $H \ge 150\text{ px}$)* : Rejeté. Éliminerait les schémas panoramiques étroits (frises chronologiques) ou verticaux allongés.
   - *Option B — Filtrage géométrique combiné* : **Retenu**. Une image est admise comme figure si et seulement si :
     - Sa surface est supérieure ou égale à $22\,500\text{ px}^2$ (équivalent $150 \times 150\text{ px}$).
     - Ses deux dimensions respectent un plancher minimal : $\min(\text{largeur}, \text{hauteur}) \ge 60\text{ px}$.
     - Son ratio d'aspect est borné entre $1:8$ et $8:1$ (élimine les filets et lignes de séparation).

4. **Point de liaison Peewee : Parseurs ad-hoc vs Chunking unifié** :
   - *Option A — Liaison dans chaque parseur* : Rejeté. Imposerait de dupliquer la création et la persistance des chunks dans Marker, PyMuPDF, PPTX, EPUB et l'import web.
   - *Option B — Résolution centralisée par détection des balises d'images dans `ChunkingService`* : **Retenu**. Les parseurs n'ont qu'à archiver les images via `MediaManager` et émettre des balises Markdown conformes (`![Légende](filename.ext)` ou `<img src="filename.ext">`). Lors de l'extraction des fragments (`ChunkingService`) et de leur synchronisation (`DocumentRepository.sync_extracted_chunks`), le moteur détecte les références de médias existants dans `MediaModel`, instancie les fragments de figures dédiés et renseigne `DocumentChunkModel.media`.

5. **Positionnement dans le Markdown PyMuPDF** :
   - Les blocs de texte et les images filtrées sont entrelacés dans le document Markdown selon leur coordonnée verticale native ($y_0$) sur la page, garantissant la proximité entre une figure et sa légende ou son paragraphe descriptif.

## Conséquences

- **Ajout de dépendance** : `pymupdf>=1.24.0` dans `pyproject.toml`.
- **Rétrocompatibilité et migration** : Bump de `ChunkingService.CHUNKING_VERSION` de 6 à 7. Au démarrage ou lors d'une réindexation, les documents déjà ingérés (Marker, PPTX, EPUB) voient leurs fragments réalignés et leurs figures instantanément peuplées dans la Galerie sans réimportation des sources.
- **Galerie de figures & Image Occlusion** : `FiguresGalleryWidget` affiche immédiatement les vignettes des figures des documents textuels, et le bouton d'action directe « Image Occlusion » crée des notes rattachées au fragment de figure exact (ADR 0023).

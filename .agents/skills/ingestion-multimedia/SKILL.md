---
name: ingestion-multimedia
description: >-
  Expert en extraction et conversion de documents multimédia pour AnkiForge. Convertit PDF (Marker OCR / pypdf), audio/transcription STT, vidéos YouTube, pages web, DOCX, PPTX, EPUB, notebooks et code source en Markdown propre avec extraction des médias associés.
  Use when the user asks to "ingérer un document", "parser un pdf/docx/epub/pptx", "importer une vidéo youtube", "transcrire un audio", "extraire un site web", "installer Marker", "OCR un pdf", "extraire les images d'un document", or needs to parse a source into Markdown.
  When NOT to use: Do not use for semantic chunking, vector indexing, document delimitation, or card coverage alignment (use rag-smart-coverage).
---

# 🎬 Ingestion Multimédia — AnkiForge

En tant qu'**Expert Ingestion & Parsing**, tu transformes toute source brute (fichiers, médias, URLs) en Markdown propre avec extraction des images associées via `MediaManager`.

> **Référence** : `references/catalogue_parsers.md` — mapping format → parseur, entrées/sorties, options et fallbacks.
> Code source : `src/ankiforge/services/parsing/`.

## 1. Périmètre & Principes

- **Périmètre** : `src/ankiforge/services/parsing/` (`DocumentParser`, `MarkerService`, `AudioParser`, `YouTubeParser`, `WebImporter`, `EpubParser`, `PptxParser`) et gestion des médias extraits (`src/ankiforge/services/cards/media_manager.py`).
- **Sortie standard** : Markdown propre (`str`) avec références relatives aux médias extraits dédupliqués.
- **Règles non négociables** :
  - Aucun appel réseau ou extraction lourde bloquante sur le thread principal de l'interface (déléguer aux workers `QThread` / `DocumentBatchWorker`).
  - Aucun secret ou token d'API en log (tokens STT, clés de transcription).
  - Marker est un processus externe lourd (venv dédié sous `.ankiforge/marker_env`) : vérifier la disponibilité (`is_marker_available()`) avant de forcer une installation.

## 2. Procédure d'extraction

1. **Identifier la source** (extension / URL / type MIME) → sélectionner le parseur via `references/catalogue_parsers.md`.
2. **Parser** : `DocumentParser().parse_document(path, progress_callback=..., check_cancel=...)` ou parseur spécialisé direct.
3. **Persister les médias extraits** : `MediaManager.store_document_source()`, `store_media_bytes()`, déduplication MD5, liens relatifs propres dans le Markdown produit.
4. **Valider** : vérifier la structure du Markdown produit (titres, tables, images) et la suite de tests :
   ```bash
   uv run pytest tests/services/parsing/
   ```

## 3. Cas Particuliers

- **PDF complexe** : Marker OCR privilégié (`MarkerService`) si disponible, sinon repli automatique pypdf.
- **YouTube** : extraire en priorité les sous-titres (`extract_subtitles()`) avant tout téléchargement audio (`yt-dlp`) + transcription Whisper.
- **Web** : `WebImporter.analyze_url()` avec détection des paywalls et conversion propre des tableaux HTML en Markdown.

## When NOT to use this skill

- L'objectif est de **découper en chunks, indexer dans FAISS/ChromaDB ou calculer la couverture de révision** → utiliser `rag-smart-coverage`.
- Le besoin porte sur l'**import/export de paquets Anki (.apkg/.colpkg)** → utiliser `export-synchro-anki`.
- L'objectif est de **générer des flashcards via un pipeline IA** → utiliser `pipeline-dag-ia`.
- La demande concerne une **modification d'interface graphique de l'import** → utiliser `ui-pyside6-design`.

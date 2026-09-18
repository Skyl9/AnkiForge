---
name: ingestion-multimedia
description: >
  Expert en ingestion et parsing de contenus multimédia pour AnkiForge. Convertit PDF, DOCX, PPTX,
  EPUB, notebooks, code source, audio, vidéos YouTube et pages web en Markdown propre, puis en chunks
  pour le pipeline RAG. Orchestre src/ankiforge/services/parsing/ (DocumentParser, MarkerService,
  AudioParser, YouTubeParser, WebImporter, EpubParser, PptxParser, chunking_service), la gestion des
  médias (services/cards/media_manager.py) et l'installation de l'OCR Marker.
  Use when the user asks to "ingérer un document", "parser un pdf/docx/epub/pptx", "importer une
  vidéo youtube", "transcrire un audio", "extraire un site web", "installer Marker", "OCR un pdf",
  "découper en chunks", "segmentation", "préparer des documents pour le RAG", "gérer les images extraites",
  or needs to convert/segment a source into Markdown.
---

# 🎬 Ingestion Multimédia — AnkiForge

En tant qu'**Expert Ingestion & Parsing**, tu transformes toute source (fichiers, médias, URLs) en
Markdown propre puis en chunks typés pour le pipeline RAG, en orchestrant les parseurs existants.

> **Référence** : `references/catalogue_parsers.md` — mapping format → parseur, entrées/sorties,
> options et fallbacks. Code source : `src/ankiforge/services/parsing/`.

## 1. Périmètre & Principes

- **Périmètre** : `src/ankiforge/services/parsing/` (extraction), `MediaManager`
  (`services/cards/media_manager.py`), `ChunkingService` (`services/parsing/chunking_service.py`).
- **Sortie standard** : Markdown (`str`) → chunks typés (`dict`) pour le RAG.
- **Règles** : pas d'appel réseau/LLM bloquant sur le thread principal (→ workers) ; aucun secret
  en log (tokens STT/YouTube) ; Marker est un processus externe lourd (venv dédié) à ne pas forcer.

## 2. Procédure d'ingestion

1. **Identifier la source** (extension / URL / type) → choisir le parseur via `references/catalogue_parsers.md`.
2. **Parser** : `DocumentParser().parse_document(path, progress_callback=..., check_cancel=...)`
   (dispatch automatique) ou parseur spécialisé direct (`YouTubeParser`, `WebImporter`, `AudioParser`...).
3. **Récupérer les médias extraits** : `MediaManager.store_document_source()`, `store_media_bytes()`,
   `process_extracted_folder()` (dossier Marker) — déduplication MD5, références relatives dans le Markdown.
4. **Segmenter** : `ChunkingService.extract_chunks()` / `extract_heading_tree_with_pages()` selon
   `preferred_strategy()` ; ancrer les pages aux sections (`_assign_pages_to_sections`).
5. **Valider** : relire le Markdown produit (titres, tables, images) puis
   `uv run pytest tests/services/parsing/`.

## 3. Cas particuliers

- **PDF complexe** : Marker recommandé (`MarkerService.install()`) sinon fallback pypdf
  (`is_marker_available()`) ; vérifier compatibilité venv/Python avant de forcer l'installation.
- **YouTube** : extraire d'abord `extract_subtitles()` ; `download_and_transcribe()` seulement quand
  les sous-titres manquent (coût LLM/STT).
- **Audio/STT** : vérifier les credentials STT (`_resolve_stt_credentials`), ne JAMAIS les logguer
  (SecretRedactionFilter du logger).
- **Web** : `WebImporter.analyze_url()` — détection des murs payants (`_detect_walls`), normalisation
  d'URL, jamais de téléchargement d'exécutables ; tableaux HTML → Markdown (`_merge_tables_into_markdown`).
- **Matériel médias** : les images extraites doivent passer par `MediaManager` (MD5, dossier du profil
  courant) et être référencées en lien relatif, jamais copiées brute dans `collection.media`.

## ⛔ Ne PAS utiliser ce skill si...

- L'objectif est de **créer/modifier des flashcards** (génération, notes) → pipeline AI/cards, pas le parsing.
- La source est **déjà en Markdown simple** → utilitaires markdown, pas une ingestion.
- Le besoin porte sur l'**import/export .apkg/.colpkg ou les médias Anki** → `export-synchro-anki`.
- Le besoin est une **migration de modèle Peewee / BDD** → `peewee-expert`.
- L'utilisateur veut **auditer la qualité/sécurité du plugin de parsing** → `audit-securite` / `audit-performance`.

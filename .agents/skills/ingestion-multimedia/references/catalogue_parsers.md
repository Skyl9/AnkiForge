# Catalogue des Parseurs — Ingestion Multimédia

Mapping source → parseur (`src/ankiforge/services/parsing/`), entrées/sorties, options et fallbacks.
Tous les parseurs renvoient du **Markdown** (`str`), sauf indication contraire.

---

## 1. Dispatch central

| Entrée | Parseur | Points d'entrée |
|---|---|---|
| PDF / DOCX / PPTX / EPUB / Audio / ipynb / .py / texte / URL | `DocumentParser` | `parse_document()`, `_parse_<format>()` |
| PDF avec OCR | `DocumentParser` + `MarkerService` | `parse_document`, `_parse_pdf_with_marker` |
| PowerPoint (`.pptx`) | `PptxParser` | `parse()` |
| EPUB | `EpubParser` | `parse()`, `convert_mathml_to_latex` |
| Audio (mp3/wav...) | `AudioParser` | `parse()`, `_transcribe_audio` (STT) |
| YouTube | `YouTubeParser` | `parse()`, `extract_subtitles()`, `download_and_transcribe()` |
| URL/page web | `WebImporter` | `analyze_url()` → `WebImportResult` |
| Fichier brut/non reconnu | `DocumentParser._parse_text` | `parse_document` |

## 2. Formats & options

### PDF
- **pypdf** (fallback) : `_parse_pdf_with_pypdf(file, progress_callback, check_cancel)`.
- **Marker** (OCR haute fidélité) : `MarkerService.install(progress_callback)` → venv dédié ;
  préréquis vérifiés via `is_marker_available()`, `get_executable()` ; sortie dossier `process_extracted_folder()`.

### PowerPoint (PptxParser)
- `parse()` → markdown par slide (`_process_slide`), tableaux `_format_table_markdown`.
- Media extraits → `MediaManager`.

### EPUB (EpubParser)
- `parse()` ; conversion MathML → LaTeX (`convert_mathml_to_latex`), localisation `_locate_opf_path`, `_parse_opf`.

### Audio (AudioParser)
- `parse()` : découpage en segments (`_group_segments`, cible ~50s), timestamps
  (`format_seconds_to_timestamp`).
- STT : credentials `_resolve_stt_credentials` — ne jamais logguer les clés.

### YouTube (YouTubeParser)
- Sous-titres : `extract_subtitles()` ; transcription : `download_and_transcribe(url, ai_manager)`.
- Formatage timestamps : `format_timestamp`.

### Web (WebImporter)
- `analyze_url(request, progress_callback)` → `WebImportResult` ; classification du type
  (`_detect_kind` : youtube / wikipedia / article / html), extraction Markdown
  (`_extract_markdown`, MathML→LaTeX `_mathml_to_latex`, tables `_merge_tables_into_markdown`),
  pagination `_follow_pagination`, murs payants `_detect_walls`.

## 3. Segmentation (ChunkingService)

| Méthode | Usage |
|---|---|
| `preferred_strategy(file_type)` | Choix de stratégie par type de fichier |
| `extract_chunks(text, ...)` | Chunks génériques (options : pages, sections, max_tokens) |
| `extract_chunks_markdown_ast(content, max_tokens)` | Découpage par AST Markdown |
| `extract_heading_tree_with_pages(content)` | Arbre de titres avec ancres de pages → `HeadingTreeNode.to_dict()` |
| `hash_content(text)` | Empreinte stable de contenu (coverage tracking) |

## 4. Médias (MediaManager — services/cards/media_manager.py)

| Méthode | Rôle |
|---|---|
| `store_document_source(file_path)` | Enregistre le fichier source |
| `store_media_bytes(data, name, mime_type)` | Stocke un média extrait (MD5, dossier profil) |
| `process_extracted_folder(source_folder, markdown_content)` | Intègre un dossier extrait (Marker) + rebase liens |
| `clean_orphaned_media()` | Supprime les médias non référencés (destructif — sur demande) |
| `decompress_all_zstd_media(profile_name)` | Décompresse les médias zstd du profil |

## 5. Validation

```bash
uv run pytest tests/services/parsing/          # parsers + chunking
uv run pytest tests/services/cards/test_import_media.py  # intégration médias
```

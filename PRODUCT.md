# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Primary users are students, medical/STEM learners, academics, and power Anki users processing dense source materials (PDFs, YouTube videos, web pages) into structured flashcards.

## Product Purpose
AnkiForge automates, optimizes, and orchestrates flashcard generation, batch editing, auto-tagging, and quality control using AI, delivering high-quality `.apkg` packages and seamless Anki synchronization.

## Positioning
**Forge Pure**: AnkiForge focuses strictly on card generation, rich Qt editing, AI-assisted extraction, and 3-way merge conflict resolution. Flashcard review and SRS study remain 100% inside the official Anki application.

## Operating Context
- Native Desktop Application environment built with Python 3.12+ and PySide6 (Qt WebEngine for preview).
- Multi-profile workspaces with isolated SQLite databases (`~/.ankiforge/profiles/<profile_name>/ankiforge.db`) and media assets.
- Background worker daemon for long-running OCR (Marker PDF), web scraping, YouTube transcript processing, and batch LLM card generation.

## Capabilities and Constraints
- **Multi-dock Interface**: JetBrains-style multi-window environment with detachable panels.
- **Native Qt Editor**: 100% native Qt note editor with live KaTeX/LaTeX math rendering, HTML support, Jinja2 templating, and autocomplete for math macros.
- **AI Parsing**: Local OCR (`marker-pdf`), Cloud Vision fallback (Gemini/OpenAI), YouTube subtitle API with `yt-dlp` + Whisper fallback, clean static web scraping (`trafilatura`/`BeautifulSoup`).
- **Anki Sync & Merge**: Automatic sync or manual IntelliJ-inspired 3-panel merge dialog (Local, Merged, Remote).
- **Performance**: Native C extension for ultra-fast Levenshtein duplicate detection (`levenshtein_distance.c`), with pure Python fallback (`difflib`).
- **Target Export**: 100% native Anki `.apkg` package format compatibility via `genanki`.

## Brand Commitments
- Name: AnkiForge
- Identity: JetBrains IDE-style technical aesthetic — dark mode, multi-panel dock widgets, high-density layout, precise typography, live KaTeX preview.
- Tone & Persona: Technical, powerful, reliable orchestrator.

## Evidence on Hand
- Architectural directive and project constraints: `GEMINI.md`
- Documentation and setup guide: `README.md`
- Codebase: `src/ankiforge/` (PySide6 Qt views, models, background tasks)

## Product Principles
1. **Forge, Don't Study**: Keep SRS study strictly in Anki; optimize AnkiForge 100% for high-speed creation, editing, and versioning.
2. **Native Performance First**: Native Qt UI controls and C extension fallbacks ensure fluid desktop experience even when handling thousands of cards.
3. **Resilient AI Pipeline**: Structured JSON output parsing and local background daemon guarantee tasks never drop progress upon app closure.
4. **IntelliJ-Grade Quality Control**: Provide power users with explicit 3-way merge tools and duplicate detection to protect deck integrity.

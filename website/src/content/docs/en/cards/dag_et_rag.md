---
title: Generation Pipelines and Smart Coverage
description: Automate multi-step flashcard creation and fill knowledge gaps across your textbooks.
---

# Generation Pipelines and Smart Coverage

For large textbooks and courses, AnkiDraft combines two engines: **Generation Pipelines** (DAG workflows) and **Smart Coverage** (local RAG alignment).

## 1. Automating Multi-Step Workflows (DAG Pipelines)

A pipeline chains multiple steps automatically across your selected chapters:
1. **Retrieve key passages** from your course material.
2. **Extract flashcards** matching your target note type.
3. **Run automatic quality checks** (filtering overly long cards) and **TTS audio generation**.
4. **Queue cards for human staging review** before saving.

## 2. Spotting Uncovered Chapters (Smart Coverage)

Using local semantic indexing and provenance links (`NoteChunkLinkModel`), AnkiDraft compares your existing flashcards against your entire course:
- It highlights sections that have zero flashcards yet.
- You can ask the AI to **generate only the missing cards** without duplicating concepts you have already covered.

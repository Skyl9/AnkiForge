---
title: Exporting Your Decks to Anki (.apkg)
description: Generate a ready-to-study .apkg file for Anki Desktop, AnkiWeb, and AnkiMobile without losing review history.
---

# Exporting Your Decks to Anki (.apkg)

Once your flashcards are created and reviewed in AnkiDraft, transfer them to Anki in seconds using the `.apkg` exporter.

## 1. Exporting a Deck or Selection

1. Press <kbd>Ctrl+Alt+E</kbd> or click **Export (.apkg)** in the toolbar.
2. Pick the deck (or hierarchical sub-decks `Subject::Chapter`) to export.
3. Keep **Include media files** checked if your flashcards contain diagrams, images, or TTS audio.
4. Click **Export** and choose where to save the `.apkg` file.

## 2. Opening in Anki Without Resetting Your Progress

Double-click the generated `.apkg` file:
- Every card carries a **stable unique identifier (GUID)**.
- If you re-export a deck after fixing a typo in AnkiDraft, Anki updates the card text **while keeping your FSRS / SM-2 scheduling history completely intact** (intervals, due dates, ease factor).
- Card color flags and suspended status are also preserved.

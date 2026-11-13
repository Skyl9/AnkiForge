---
title: Synchronization, Duplicates, and Smart Merge
description: Resolve conflicts during Anki imports and clean up duplicate flashcards.
---

# Synchronization, Duplicates, and Smart Merge

When collaborating on a shared deck or editing a flashcard in both Anki and AnkiDraft, **Smart Merge** protects your work.

## 1. How Smart Merge Works on `.apkg` Import

When an incoming flashcard shares the same identifier as an existing card in AnkiDraft:
- **If only review statistics changed in Anki**: no conflict is raised and the update happens seamlessly.
- **If the card text was edited on both sides**: a 3-pane comparison dialog (*Local Version*, *Common Base*, *Incoming Version*) lets you pick which wording to keep or combine both.

## 2. Finding and Merging Duplicates

From the Editor or through the AI Consultant, scan your decks for duplicates:
- **Exact duplicates**: flashcards sharing the exact same front field.
- **Near-duplicates**: flashcards phrased slightly differently that test the same definition, detected rapidly with built-in similarity matching.

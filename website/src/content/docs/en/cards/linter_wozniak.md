---
title: Quality Audit and Wozniak's 20 Rules
description: Detect and split overloaded, vague, or hard-to-remember flashcards with the Wozniak Linter.
---

# Quality Audit and Wozniak's 20 Rules

A poorly formulated flashcard (too long, testing multiple facts at once, or lacking context) quickly turns into a "leech" that you repeatedly fail in Anki.

AnkiDraft includes a built-in **Pedagogical Linter** based on **Piotr Wozniak's 20 rules of formulating knowledge** (creator of SuperMemo).

## 1. What the Quality Audit Checks

In the **Quality & Audit** view (<kbd>Ctrl+5</kbd>) or right inside the editor, AnkiDraft scores each card and highlights:
- **Information overload (non-atomicity)**: answers exceeding the recommended word threshold or mixing several independent facts.
- **Vague or ambiguous prompts**: open-ended questions like *"Describe..."* where the expected answer is unclear.
- **Blind enumerations**: lists of more than 3 or 4 items that are difficult to recall in order.
- **Overly broad cloze deletions**: cloze tags hiding an entire sentence instead of a single key concept.

## 2. Splitting Complex Cards in One Click

When a card is flagged as overloaded, click **Split into Atomic Cards**: the assistant proposes breaking it down into 2 or 3 short, focused flashcards that are much easier to retain long-term.

---
title: Note Editor, KaTeX Math, and Cloze Deletions
description: Write and format flashcards with live KaTeX math preview, cloze deletions, and revision history.
---

# Note Editor, KaTeX Math, and Cloze Deletions

The AnkiDraft Note Editor (<kbd>Ctrl+2</kbd>) provides a fast writing environment with real-time Anki card preview.

## 1. Writing Math and Chemistry Formulas (KaTeX)

AnkiDraft renders your LaTeX equations live without waiting for an Anki export:
- **Inline formula**: wrap your expression in `\( ... \)` or `$ ... $` (e.g., `$E = mc^2$`).
- **Centered block formula**: use `\[ ... \]` or `$$ ... $$`.
- **LaTeX Autocompletion**: type `\` followed by the first letters of a symbol (`\alpha`, `\frac`, `\sum`) to open the completion popup.

## 2. Creating Cloze Deletions

Cloze cards are great for memorizing precise definitions or short lists:
1. Highlight the word or phrase you want to hide.
2. Click the **Cloze** toolbar button to wrap it in `{{c1::your text}}`.
3. Add an optional hint using `{{c1::answer::hint}}`.

## 3. Revision History (Time Machine)

Edited a card by mistake? Every save (<kbd>Ctrl+S</kbd>) stores a local snapshot in the note history so you can compare and restore previous wording in one click.

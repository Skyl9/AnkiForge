---
title: Note Types, Templates, and CSS Styling
description: Customize Front/Back, Cloze note types, and visual styling for Anki.
---

# Note Types, Templates, and CSS Styling

AnkiDraft supports all standard Anki note types and lets you customize their visual layout.

## 1. Built-In Note Types

- **Basic (Front / Back)**: a focused question on the front, the answer and optional lecture notes on the back.
- **Basic (and reversed card)**: automatically generates cards in both directions (ideal for bilingual vocabulary).
- **Cloze Deletion**: hides one or more key terms `{{c1::...}}` inside a context sentence.

## 2. Customizing Fields and CSS

Add custom fields (e.g., *Source*, *Mnemonic*, *Audio*, *Diagram*) and tweak the card CSS stylesheet with instant preview in both light and dark modes.

## 3. Smart Note Type Reconciliation on Import

When you import an `.apkg` deck whose note type already exists in your collection, AnkiDraft automatically matches it instead of cluttering your collection with duplicate note types (`Basic-12345`).

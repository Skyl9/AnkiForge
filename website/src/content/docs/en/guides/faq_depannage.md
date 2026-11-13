---
title: FAQ and Troubleshooting
description: Answers to frequently asked questions and common troubleshooting steps for AnkiDraft.
---

# FAQ and Troubleshooting

Find answers to the most common questions about AnkiDraft.

## 1. General Questions

### Does AnkiDraft replace Anki?
No—AnkiDraft and Anki complement each other. **AnkiDraft** is the authoring and quality-auditing studio where you turn textbooks and lectures into atomic flashcards, while **Anki** (Desktop, AnkiWeb, AnkiMobile, AnkiDroid) is the spaced-repetition engine where you do your daily reviews.

### Can I use AnkiDraft for free and offline?
Yes. AnkiDraft is free, runs offline on your computer, and supports free local AI models via [Ollama](/en/ai-setup/local-models-ollama/) without any paid API subscription.

### Are my PDFs and flashcards uploaded to the cloud?
No. Your PDFs, SQLite database, and media files stay locally on your drive (`~/.ankidraft/`). If you configure a cloud AI provider (OpenAI, Gemini, Claude), only the text passages you explicitly select for card generation are sent directly to your API account.

## 2. Troubleshooting

### macOS shows a security prompt on first launch
Make sure you dragged **AnkiDraft** into your **Applications** folder from the `.dmg` disk image. If macOS asks for confirmation on first open, right-click the **AnkiDraft** icon and select **Open**.

### My math formulas do not render in Anki
Verify that your equations use standard MathJax/KaTeX delimiters (`\( ... \)` for inline math and `\[ ... \]` for centered block equations).

### How do I report a bug or request a feature?
Inside AnkiDraft, open **Settings** (<kbd>Ctrl+,</kbd>) > **Help** > **Report an Idea or Bug**, or open an issue on the [official GitHub repository](https://github.com/Skyl9/AnkiDraft/issues).

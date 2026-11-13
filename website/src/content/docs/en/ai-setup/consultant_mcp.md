---
title: AI Consultant and MCP Assistant Connection
description: Chat with the built-in AI Consultant or connect Claude Desktop and Cursor to AnkiDraft.
---

# AI Consultant and MCP Assistant Connection

The **AI Consultant** (<kbd>Ctrl+6</kbd>) is your interactive study assistant inside AnkiDraft. You can also control AnkiDraft from your favorite external AI client via the standard **MCP (Model Context Protocol)**.

## 1. What the AI Consultant Can Do

Ask in plain English:
- *"Find chapters in my cardiology textbook that don't have any flashcards yet"*
- *"Search for duplicate cards in my Anatomy deck and propose a merge"*
- *"Shorten the 10 longest flashcards in this deck following Wozniak's rules"*

## 2. Safety Safeguard: Two-Phase Human Validation

Neither the built-in AI Consultant nor an external MCP agent can modify or delete your cards without your explicit confirmation:
1. The assistant prepares proposed changes inside a **Staged Bundle**.
2. You inspect a clear before/after diff of every card added, edited, or deleted.
3. Click **Apply** or **Reject**: you remain in complete control of your collection.

## 3. Connecting External Clients (Claude Desktop, Cursor, etc.)

In **AI Consultant** > **MCP Server**, enable the local server and copy the configuration snippet in one click to let your external assistant query your decks and study documents safely.

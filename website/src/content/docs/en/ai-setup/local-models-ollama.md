---
title: Using a Free Local Model with Ollama
description: Generate flashcards 100% offline and for free on your computer using Ollama.
---

# Using a Free Local Model with Ollama

Prefer not to use paid cloud APIs, or studying confidential documents offline? AnkiDraft integrates natively with **Ollama**.

## 1. Install Ollama in 2 Minutes

1. Download and install Ollama from [ollama.com](https://ollama.com).
2. Open a terminal and pull a model suited to your computer's RAM:
   - **8 GB RAM**: `ollama pull llama3.2:3b` or `ollama pull qwen2.5:3b`
   - **16 GB+ RAM (e.g., Apple Silicon M1/M2/M3/M4)**: `ollama pull qwen2.5:7b` or `ollama pull mistral`

## 2. Enable Ollama in AnkiDraft

1. Open **Settings** (<kbd>Ctrl+,</kbd>) > **AI Providers**.
2. Select **Ollama (Local)**: the default local endpoint `http://localhost:11434` is detected automatically.
3. Click **Refresh Models** and choose the model you just downloaded.
4. You can now generate and audit flashcards for free and completely offline!

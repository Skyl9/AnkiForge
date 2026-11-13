---
title: Configuring AI Providers (OpenAI, Gemini, Claude)
description: Securely connect your API keys and manage your token budget in AnkiDraft.
---

# Configuring AI Providers (OpenAI, Gemini, Claude)

AnkiDraft is **provider-agnostic**: you are free to use the AI service of your choice or switch models depending on the task.

## 1. Supported Providers

In **Settings** (<kbd>Ctrl+,</kbd>) > **AI Providers**, you can configure:
- **OpenAI** (GPT-4o, GPT-4o-mini, etc.)
- **Google Gemini** (Gemini 2.5 Flash, Gemini 2.5 Pro)
- **Anthropic Claude** (Claude Sonnet, Claude Haiku)
- **Any OpenAI-Compatible Endpoint** (Mistral, OpenRouter, university server)
- **Ollama (100% Free & Offline)**: see [Using a Free Local Model with Ollama](/en/ai-setup/local-models-ollama/).

## 2. API Key Security

- Your API keys are stored in your **operating system's secure keychain** (macOS Keychain, Windows Credential Manager, Linux Secret Service).
- Keys never pass through any middleman server: AnkiDraft connects directly from your computer to your chosen provider.
- Application logs automatically redact any secret key (`sk-*`, `AIza*`).

## 3. Token Budget Control

Before running a batch generation across a large textbook, AnkiDraft estimates the required token count and lets you set a strict per-run token cap to prevent unexpected API bills.

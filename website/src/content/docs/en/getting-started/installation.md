---
title: Installing AnkiDraft
description: Download, install, and update AnkiDraft on macOS, Windows, and Linux.
---

# Installing AnkiDraft

AnkiDraft is a standalone desktop application. You do not need to install Python or any developer tools on your computer.

## 1. Download the Installer

Visit the [AnkiDraft homepage](https://ankidraft.app/en/#download) and download the package matching your operating system:

| Operating System | Installer File | System Requirements |
| :--- | :--- | :--- |
| **macOS** | `AnkiDraft-macos-arm64.dmg` | macOS 13 (Ventura) or newer, Apple Silicon chip (M1/M2/M3/M4) |
| **Windows** | `AnkiDraft-Setup-x64.exe` | Windows 10 or Windows 11 (64-bit) |
| **Linux** | `AnkiDraft-x86_64.AppImage` | Modern 64-bit Linux distribution (Ubuntu 22.04+, Fedora, Arch) |

## 2. Step-by-Step Setup

### On macOS
1. Double-click the downloaded `AnkiDraft-macos-arm64.dmg` file.
2. Drag the **AnkiDraft** icon into your **Applications** folder.
3. Launch AnkiDraft from Launchpad or Spotlight.

### On Windows
1. Double-click `AnkiDraft-Setup-x64.exe`.
2. Follow the setup wizard (no administrator rights required for a user-level installation).
3. Launch AnkiDraft from the Start menu or Desktop shortcut.

### On Linux (AppImage)
1. Make the file executable:
   ```bash
   chmod +x AnkiDraft-x86_64.AppImage
   ```
2. Launch it by double-clicking or running `./AnkiDraft-x86_64.AppImage`.

## 3. Where Is Your Data Stored?

All your study data stays locally on your drive inside `~/.ankidraft/profiles/<profile_name>/`:
- `ankidraft.db`: your local SQLite database of cards, documents, and history.
- `media/`: images and audio clips attached to your flashcards.

## 4. Automatic Updates

AnkiDraft automatically checks for official releases and verifies both the cryptographic signature (Ed25519) and SHA-256 checksum before installing any update.

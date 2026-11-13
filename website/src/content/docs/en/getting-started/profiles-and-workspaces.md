---
title: Managing Profiles and Your Collection
description: Create separate study profiles and protect your local data in AnkiDraft.
---

# Managing Profiles and Your Collection

AnkiDraft lets you completely isolate multiple collections using **user profiles**.

## 1. Why Use Multiple Profiles?

Each profile has its own SQLite database and dedicated media folder (images, audio):
- Create separate profiles for distinct fields of study (e.g., *Medical School*, *Bar Exam*, *Japanese*).
- Share a computer between multiple people without ever mixing flashcards or documents.

## 2. Creating or Switching Profiles

1. Open the profile selector from the application header or at startup.
2. Click **New Profile** and give it a clear name.
3. Switch between profiles in one click: AnkiDraft automatically locks the active profile to prevent concurrent write conflicts.

## 3. Automatic Backups

Before any sensitive operation (such as replacing your collection from a `.colpkg` archive or applying an update), AnkiDraft automatically creates a timestamped backup of your local database inside your profile folder.

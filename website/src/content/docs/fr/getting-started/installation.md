---
title: Installer AnkiDraft
description: Télécharger, installer et mettre à jour AnkiDraft sur macOS, Windows et Linux.
---

# Installer AnkiDraft

AnkiDraft est une application de bureau autonome. Vous n'avez pas besoin d'installer Python ni aucun outil de développement sur votre ordinateur.

## 1. Télécharger l'installateur

Rendez-vous sur la [page d'accueil d'AnkiDraft](https://ankidraft.app/fr/#telecharger) et téléchargez le paquet adapté à votre système :

| Système | Fichier à télécharger | Configuration requise |
| :--- | :--- | :--- |
| **macOS** | `AnkiDraft-macos-arm64.dmg` | macOS 13 (Ventura) ou supérieur, puce Apple Silicon (M1/M2/M3/M4) |
| **Windows** | `AnkiDraft-Setup-x64.exe` | Windows 10 ou Windows 11 (64 bits) |
| **Linux** | `AnkiDraft-x86_64.AppImage` | Distribution Linux 64 bits moderne (Ubuntu 22.04+, Fedora, Arch) |

## 2. Procédure par système d'exploitation

### Sur macOS
1. Double-cliquez sur le fichier `AnkiDraft-macos-arm64.dmg` téléchargé.
2. Faites glisser l'icône **AnkiDraft** vers le dossier **Applications**.
3. Lancez AnkiDraft depuis le Launchpad ou Spotlight.

### Sur Windows
1. Double-cliquez sur `AnkiDraft-Setup-x64.exe`.
2. Suivez l'assistant d'installation (aucun droit administrateur n'est requis pour une installation dans votre session).
3. Ouvrez AnkiDraft depuis le menu Démarrer ou le raccourci sur le Bureau.

### Sur Linux (AppImage)
1. Rendez le fichier exécutable :
   ```bash
   chmod +x AnkiDraft-x86_64.AppImage
   ```
2. Lancez l'application en double-cliquant dessus ou via `./AnkiDraft-x86_64.AppImage`.

## 3. Où sont stockées vos données ?

Toutes vos données restent localement sur votre disque dur dans le dossier `~/.ankidraft/profiles/<nom_du_profil>/` :
- `ankidraft.db` : votre base de cartes, documents et historiques.
- `media/` : les images et fichiers audio attachés à vos flashcards.

## 4. Mises à jour automatiques

AnkiDraft vérifie automatiquement la disponibilité d'une nouvelle version officielle et vérifie la signature cryptographique (Ed25519) ainsi que l'empreinte SHA-256 avant toute mise à jour.

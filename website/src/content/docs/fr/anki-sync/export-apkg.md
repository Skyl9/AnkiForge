---
title: Exporter vos Paquets vers Anki (.apkg)
description: Générer un fichier .apkg prêt à l'emploi pour Anki Desktop, AnkiWeb et AnkiMobile sans perdre votre progression.
---

# Exporter vos Paquets vers Anki (.apkg)

Une fois vos cartes créées et relues dans AnkiDraft, vous pouvez les transférer vers Anki en quelques secondes grâce à l'export `.apkg`.

## 1. Exporter un paquet ou une sélection

1. Appuyez sur <kbd>Ctrl+Alt+E</kbd> ou cliquez sur **Exporter (.apkg)** dans la barre d'outils.
2. Choisissez le paquet (ou les sous-paquets hiérarchiques `Matière::Chapitre`) à exporter.
3. Cochez **Inclure les fichiers médias** si vos cartes contiennent des schémas, des images ou de l'audio TTS.
4. Cliquez sur **Exporter** et choisissez l'emplacement du fichier `.apkg`.

## 2. Ouvrir le paquet dans Anki sans écraser vos révisions

Double-cliquez sur le fichier `.apkg` généré :
- Chaque carte possède un **identifiant unique durable (GUID)**.
- Si vous réexportez un paquet après avoir corrigé une faute d'orthographe dans AnkiDraft, Anki met à jour le texte de la carte **tout en conservant intact votre historique de révision FSRS / SM-2** (intervalles, échéances, facteur de facilité).
- Les drapeaux de couleur (*flags*) et l'état suspendu de vos cartes sont également respectés.

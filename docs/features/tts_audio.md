# Synthèse Vocale (TTS) & Audio 🎙️

L'apprentissage auditif renforce considérablement la rétention mnésique, en particulier pour les langues étrangères, la terminologie médicale ou les définitions denses. AnkiForge intègre un sous-système de synthèse vocale (*Text-to-Speech*) complet et hybride.

---

## 🔊 1. Moteurs Vocaux Disponibles

AnkiForge offre le choix entre deux moteurs complémentaires pour s'adapter à toutes les situations :

### Edge-TTS (En ligne - Qualité Studio)
- **Technologie** : Modèles neuronaux Microsoft Azure Cognitive Services (utilisés par Microsoft Edge).
- **Avantages** : Qualité vocale exceptionnelle, prosodie ultra-naturelle, intonation fluide.
- **Accès** : 100% gratuit et prêt à l'emploi, **aucune clé d'API requise**.
- **Voix Recommandées** :
  - Français : `fr-FR-VivienneMultilingualNeural` (voix féminine naturelle), `fr-FR-HenriNeural` (voix masculine posée), `fr-FR-DeniseNeural`.
  - Anglais : `en-US-AriaNeural`, `en-US-GuyNeural`, `en-GB-SoniaNeural`.

### Piper TTS (Local & Hors-ligne)
- **Technologie** : Moteur de synthèse neuronale ONNX open source léger et ultra-rapide.
- **Avantages** : Fonctionne de manière **100% autonome et hors-ligne**, zéro télémétrie, aucune donnée envoyée sur Internet, génération quasi-instantanée.
- **Gestion Automatisée** : AnkiForge télécharge automatiquement le binaire adapté à votre système d'exploitation et votre architecture processeur (`macOS aarch64/x64`, `Linux x64/arm64`, `Windows x64`) ainsi que les modèles vocaux initiaux dans `~/.ankiforge/sidecars/piper/`.
- **Résilience** : Le service vérifie la viabilité fonctionnelle du binaire (`is_functional()`) et bascule avec élégance sur Edge-TTS si une dépendance dynamique système est manquante.

---

## 🎛️ 2. Routage Audio et Périphériques de Sortie

Il arrive fréquemment que les systèmes d'exploitation (notamment macOS ou Linux) routent par défaut le son vers un casque Bluetooth (ex. *AirPods*) alors que l'utilisateur souhaite écouter sur les haut-parleurs internes, ou inversement.

AnkiForge intègre un sélecteur matériel dédié dans **Paramètres ➔ Audio & TTS** :
- **Détection Automatique** : Interroge `QMediaDevices.audioOutputs()` pour lister l'ensemble des cartes son et sorties actives.
- **Sélection Forcée** : Choisissez manuellement votre périphérique (ex: *Haut-parleurs MacBook Pro*, *AirPods*, *Casque USB*).
- **Persistance** : Votre choix est enregistré dans les préférences du profil (`tts.device_name`) et appliqué uniformément au bouton de test et au lecteur de l'éditeur de cartes.
- **Contrôle de Lecture** : Le bouton de test bascule dynamiquement en **"Arrêter la lecture"** (icône carrée rouge `ph.stop`) et un message toast vous confirme en temps réel le périphérique utilisé.

---

## ⚡ 3. Vocaliser une Flashcard dans l'Éditeur

1. Dans la vue **Édition de Notes**, écrivez votre texte dans le champ Question ou Réponse.
2. Cliquez sur l'icône **Synthèse Vocale (TTS)** dans la barre d'outils du champ concerné.
3. AnkiForge exécute la synthèse en arrière-plan (sans bloquer l'interface).
4. Le fichier audio MP3 est stocké dans le répertoire médias du profil actif (`~/.ankiforge/profiles/<profil>/media/tts_xxx.mp3`).
5. La balise standard d'Anki est automatiquement insérée à l'emplacement de votre curseur :
   ```text
   Quelle est la fonction principale du nerf vague ? [sound:tts_a8f9c1.mp3]
   ```
6. Le widget lecteur audio natif intégré sous le champ vous permet d'écouter l'extrait immédiatement.

Lors de l'export en paquet `.apkg`, les fichiers audio MP3 sont automatiquement packagés dans l'archive pour être lus nativement sur Anki Desktop et AnkiMobile.

# 🧪 Plan de Test IA - Fonctionnalités Générales (Hors Consultant)

Ce document rassemble les scénarios de test manuel pour valider que tous les modules annexes d'AnkiForge utilisent l'IA correctement sans provoquer de crash.

---

## 1. 🎬 Module YouTube (Extraction Vidéo)

**Objectif :** Valider que le `YouTubeParser` parvient à récupérer les sous-titres, et que le `YouTubeWorker` les traite via l'IA pour générer des cartes.

1. Allez dans le module de **Création**.
2. Dans le bloc d'import ou la barre d'entrée URL, collez un lien YouTube valide contenant des sous-titres (ex: une courte vidéo TEDx).
3. Cliquez sur le bouton pour lancer l'analyse (Générer depuis YouTube).
4. **Comportement attendu :**
   - L'application affiche un statut de progression.
   - Les imports Python que nous avons corrigés ne causent pas de crash silencieux.
   - Des cartes Anki apparaissent en sortie (le LLM a transformé la transcription en cartes structurées).

---

## 2. 📝 Module Création / Batch (Pipelines IA)

**Objectif :** Valider le système de chaînage (Agents qui travaillent à la chaîne : Extracteur -> Linter -> ...).

1. Allez dans le module d'**Édition** ou de **Création** depuis un texte libre.
2. Copiez-collez un petit texte scientifique (ex: un paragraphe de Wikipédia sur la photosynthèse).
3. Dans la liste déroulante des pipelines, sélectionnez : **Excellence Math/Info (Archiviste + Linter)** ou un équivalent.
4. Lancez la génération par lot.
5. **Comportement attendu :**
   - Le premier agent (`Extracteur`) lit le texte et crée une structure JSON temporaire.
   - Le deuxième agent (`Contrôleur Qualité`) prend ce JSON, le nettoie (ajoute les `&nbsp;`, vérifie le LaTeX) et crache le JSON final.
   - L'interface affiche finalement des cartes toutes prêtes dans le tableau de bord sans aucune alerte JSONDecodeError.

---

## 3. 🧹 Le Linter IA (Audit de qualité sur cartes existantes)

**Objectif :** Valider l'agent `LinterWorker` qui audite votre paquet selon les "20 règles de Piotr Wozniak".

1. Allez dans l'explorateur de vos cartes (**Documents** / **Paquets**).
2. Sélectionnez une ou plusieurs cartes qui sont délibérément mal formulées (ex: une question ultra longue avec beaucoup de texte au recto).
3. Cliquez sur l'action de l'interface qui permet d'auditer ces cartes via l'IA (le Linter).
4. **Comportement attendu :**
   - L'application traite la demande en arrière-plan.
   - L'agent doit renvoyer un statut signalant "Pass" ou "Fail" avec une suggestion d'amélioration pour la carte (le JSON généré est correctement parsé par l'interface qui vous le montre).

---

## 4. 🏷️ L'Auto-Tagging (Si activé)

**Objectif :** Valider la petite pop-up de suggestion de tags via l'IA.

1. Sélectionnez une carte existante, puis cliquez sur le bouton d'ajout de Tags assisté par IA.
2. **Comportement attendu :**
   - Une requête simple est envoyée au moteur IA.
   - La fenêtre vous propose 3-4 mots-clés pertinents par rapport au contenu de la carte.

---

### ⚠️ Comment me reporter les erreurs :
Si une fonctionnalité "tourne dans le vide" (freeze), ou affiche une bulle rouge d'erreur critique, copie le texte de l'erreur ou décris-moi l'étape à laquelle l'interface s'est bloquée.

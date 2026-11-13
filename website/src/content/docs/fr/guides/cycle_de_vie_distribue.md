---
title: Guide Visuel du Cycle de Vie Distribué AnkiDraft et Anki
description: Comprendre la complémentarité entre le studio de création AnkiDraft et le moteur de révision Anki (.apkg et .colpkg).
---

# Guide Visuel du Cycle de Vie Distribué AnkiForge ↔ Anki 🔄

Bienvenue dans le guide d'utilisation du système distribué d'AnkiDraft (anciennement AnkiForge).

AnkiDraft et Anki fonctionnent main dans la main comme un duo complémentaire :
- **AnkiDraft est votre Studio d'Authoring** : c'est votre atelier de création intellectuelle assisté par intelligence artificielle. Vous y organisez vos cours, vos livres, vos découpages RAG, vos personas d'extraction et vous y concevez des flashcards fidèles à vos sources avec une validation humaine rigoureuse.
- **Anki est votre Moteur de Mémorisation (SRS)** : c'est le logiciel dédié à vos répétitions quotidiennes. Anki détient l'autorité exclusive sur vos intervalles de révision, vos dates d'échéance et les algorithmes de mémoire espacée (FSRS ou SM-2).

Grâce à cette séparation étanche, **vous ne risquez jamais de perdre vos progrès de révision dans Anki, ni d'altérer vos cours et vos modèles d'IA dans AnkiDraft**.

---

## 1. Le Cycle Global de Travail

Le schéma ci-dessous illustre la boucle vertueuse de travail entre la conception dans AnkiDraft et la mémorisation dans Anki :

![Cycle Global Distribué](assets/cycle_de_vie/cycle_global.svg)

Le cycle s'articule en quatre temps :
1. **Studio AnkiDraft** : Importez vos documents sources (PDF, articles, vidéos, cours audio). L'application segmente les textes et mesure en continu votre taux de couverture documentaire. L'IA extrait des propositions de cartes ciblées.
2. **Revue en Staging** : Chaque carte générée passe par une étape de relecture humaine obligatoire. Vous ajustez la formulation, appliquez les principes de concision atomique de Piotr Wozniak et validez. Chaque carte validée reçoit un identifiant durable immuable (GUID).
3. **Export vers Anki (.apkg)** : Exportez vos nouvelles cartes au format `.apkg` et ouvrez le paquet dans Anki. Anki intègre les cartes, charge les médias associés et planifie vos premières révisions.
4. **Révision & Rafraîchissement (.colpkg)** : Vous révisez quotidiennement dans Anki. Régulièrement (par exemple une fois par mois ou après une session d'apprentissage intensive), exportez votre collection `.colpkg` depuis Anki et déposez-la dans AnkiDraft pour actualiser vos statistiques de rétention et synchroniser vos suppressions.

---

## 2. Sanctuarisation des Données : Périmètre Studio vs Périmètre Anki

Pour garantir une sérénité totale, AnkiDraft sépare formellement vos données en deux périmètres distincts au sein de votre profil :

![Sanctuarisation des Périmètres](assets/cycle_de_vie/sanctuarisation_perimetres.svg)

### 🛡️ Le Périmètre Studio (Strictement Préservé)
Ce périmètre vous appartient exclusivement et n'est **jamais** écrasé par vos imports de collection Anki :
- **Vos documents originaux** : PDF, transcriptions audio, fichiers Markdown, planches d'albums.
- **Vos index RAG** : découpages sémantiques, fragments de texte et représentations vectorielles locales.
- **Vos agents IA & Personas** : modèles de prompts personnalisés, configurations Ollama / cloud.
- **Vos pipelines DAG & usine de lots (Batch)** : règles d'automatisation, historique de génération.
- **Vos réglages d'application** : thèmes graphiques, dispositions d'écran, raccourcis personnalisés.

### 🗂️ Le Périmètre Collection Anki (Synchronisé & Remplacé)
Ce périmètre est le reflet exact de votre collection Anki :
- Vos paquets de cartes (`Decks`) et sous-paquets hiérarchiques.
- Vos types de notes (`Note Types`), gabarits Recto/Verso et styles CSS.
- Vos notes et vos cartes physiques d'apprentissage.
- Vos compteurs d'observation SRS (historique d'échecs, drapeaux de couleur, cartes suspendues).

---

## 3. Quel Format d'Échange Choisir : .apkg ou .colpkg ?

AnkiDraft distingue nettement les deux formats d'archive de l'écosystème Anki :

![Arbre de Décision .apkg vs .colpkg](assets/cycle_de_vie/arbre_decision_apkg_colpkg.svg)

| Critère | Export / Import de Paquet (`.apkg`) | Import de Collection (`.colpkg`) |
| :--- | :--- | :--- |
| **Finalité** | Échange ciblé de cartes nouvelles ou d'appoint | Remplacement intégral pour alignement parfait |
| **Comportement** | **Fusion collaborative incrémentale** : ajoute les nouvelles fiches sans toucher aux autres | **Remplacement complet du périmètre Anki** : votre profil adopte l'exact état d'Anki |
| **Gestion des suppressions** | Ne supprime aucune carte locale | **Purge définitive des cartes supprimées dans Anki** |
| **Gestion des conflits** | Boîte de dialogue *Smart Merge* en cas de modification concurrente | L'archive Anki entrante fait foi (remplacement fidèle) |
| **Protection de sécurité** | Détection d'isomorphisme de types de notes (zéro clone inutile) | **Sauvegarde SQLite de secours créée automatiquement** |

---

## 4. Chronologie d'une Session Type

![Chronologie d'une Session Type](assets/cycle_de_vie/chronologie_session.svg)

1. **Jalon 1 (0 min)** : Déposez votre support de cours dans le Hub Documentaire.
2. **Jalon 2 (+5 min)** : Découpez le document en sections clés avec le Batch Slice Composer et lancez l'extraction IA.
3. **Jalon 3 (+15 min)** : Relisez les cartes en Staging, validez les meilleures formulations.
4. **Jalon 4 (+20 min)** : Exportez le paquet `.apkg` généré et ouvrez-le dans Anki.
5. **Jalon 5 (Semaines suivantes)** : Étudiez chaque jour dans Anki selon le rythme fixé par l'algorithme SRS.
6. **Jalon 6 (Périodique)** : Exportez une sauvegarde `.colpkg` depuis Anki et glissez-la dans AnkiDraft pour mettre à jour vos indicateurs de maîtrise et nettoyer les cartes obsolètes.

---

## 5. Prévention des Cartes Zombies et Rendu Fidèle

![Prévention des Cartes Zombies](assets/cycle_de_vie/prevention_zombies.svg)

### 🧟 1. Éradication des Cartes Zombies
Dans un système d'importation incrémentale classique, si vous supprimez une carte obsolète ou ratée directement dans Anki, le logiciel d'authoring n'en a pas connaissance. Au prochain export, il réinjecte la carte fantôme dans votre deck Anki.

Dans AnkiDraft, l'importation de collection (`.colpkg`) procède par **remplacement atomique exact**. Toute carte supprimée dans Anki est immédiatement retirée d'AnkiDraft. Vous gardez une collection saine et synchronisée, sans résidu fantôme.

### 📄 2. Règle Officielle Anki du Recto Non-Vide
AnkiDraft intègre le **moteur de rendu conditionnel conforme d'Anki** : si le recto généré d'une carte ne contient aucun texte visible, la carte physique n'est jamais créée.

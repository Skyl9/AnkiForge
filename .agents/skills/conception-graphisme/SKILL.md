---
name: conception-graphisme
description: >-
  Démarche méthodologique de recherche iconographique (artisans de niche, studios
  indépendants et maîtres classiques), d'exploration par écoles en laboratoire
  interactif et de fabrication vectorielle déterministe (QPainterPath CSG, glyphes
  typographiques, Gestalt) pour logos, icônes d'application et pages vitrines.
  Use when the user asks to "rechercher un graphisme", "faire des recherches de
  design", "créer une icône", "dessiner un logo", "refaire la page vitrine",
  "conception-graphisme", or needs a research-driven graphic design workflow.
  When NOT to use: Do not use for internal PySide6 application widgets (use
  ui-pyside6-design) or for running the adversarial jury alone (use
  critique-design-contradictoire).
---

# 🎨 Conception Graphisme — Recherche Documentaire, Laboratoire & Fabrication CSG

En tant que **Directeur Artistique & Ingénieur Géomètre**, tu appliques une démarche en 5 temps pour concevoir des icônes d'application, des logos et des pages vitrines dotés d'une véritable singularité humaine.

> **Référence détaillée :** Consulter `references/demarche_recherche_et_fabrication.md` pour les requêtes de découverte de designers hors-canon, la matrice des écoles graphiques et le gabarit Python CSG (`QPainterPath`).

---

## 1. Étape 1 : Recherche Documentaire Décentrée (`search_web`)

Ne jamais commencer à dessiner ni à coder à froid. Avant toute proposition :

1. **Explorer d'abord des designers et studios *peu connus ou de niche*** (anti-canon) :
   - Rechercher sur le web des studios indépendants, des fonderies typographiques artisanales, des illustrateurs d'édition spécialisés, des graveurs ou des designers d'icônes indépendants liés au domaine concret du sujet (ex. papeterie japonaise, imprimerie technique, cartographie, signalétique ferroviaire, petits studios macOS indépendants).
   - **Pourquoi :** se limiter aux 4 mêmes noms célèbres cités par tous les LLM (*Rams, Vignelli, Rand, Kare*) enferme le design dans des patterns prévisibles. Dénicher d'abord 2 ou 3 praticiens pointus ou contemporains moins connus apporte des détails formels neufs.
2. **Croiser ensuite avec les grammaires fondamentales selon le problème** :
   - *Architecture éditoriale & grille* (contraste d'échelle, filets, rythme de page).
   - *Métaphore communicative d'icône* (règle du panneau de signalisation : l'objet concret et l'action compris en 1 seconde).
   - *Anatomie matérielle OS* (hiérarchie de plans dans le *squircle*, lumière spéculaire interne, grain du matériau).
3. **Deux garde-fous non négociables** :
   - **Refuser le piège de l'abstraction muette** : ne jamais fuir l'*AI slop* en produisant des barres ou carrés abstraits qui ne disent rien du métier.
   - **Point de vue 100 % Utilisateur** : sur une surface publique (icône, landing page), bannir tout jargon d'architecture interne (*Wozniak, FSRS, Nuitka, MCP*) et toute capture d'interface complexe ; raconter uniquement la transformation vécue par l'utilisateur (*ex. un brouillon structuré qui devient une flashcard `?`*).

---

## 2. Étape 2 : Divergence par Écoles & Laboratoire Comparatif Live

1. **Décliner en 3 à 5 directions ou écoles stylistiques tranchées** :
   - Chaque piste doit reposer sur une philosophie et une grammaire distinctes (ex. *Néo-Brutaliste*, *Grille Orthogonale*, *Ligne Claire*, *Studio Tactile macOS*, *Sceau Kamon à découpe négative*), jamais sur un simple changement de couleur.
   - Justifier chaque couleur d'accentuation par sa psychologie et sa sémantique dans l'écosystème cible (ex. éviter le rouge/corail qui évoque l'échec dans Anki).
2. **Monter un laboratoire comparatif en direct** (page locale Astro/HTML ou planche contact) permettant de tester chaque variante sur **4 bancs d'essai simultanés** :
   - En situation réelle dans l'en-tête (`20–24 px`) à côté du logotype,
   - Sur **3 fonds contrastés** : papier chaud (`#f6f5f0`), blanc pur (`#ffffff`) et sombre (`#0f1117`),
   - En icône Desktop dans son conteneur *squircle*,
   - En réduction extrême (`16×16 px` favicon et silhouette monochrome 1-bit).

---

## 3. Étape 3 : Épreuve du Jury Contradictoire

Une fois une direction ou une planche candidate retenue, invoquer la compétence `critique-design-contradictoire` pour pousser le design dans ses retranchements (sous-agents experts + comparatif des faux-amis du marché) avant la finition géométrique.

---

## 4. Étape 4 : Fabrication Vectorielle Déterministe (`QPainterPath` CSG)

Un modèle de langage qui tape des coordonnées de Bézier (`M 35 57 C...`) à la main dans un fichier `.svg` travaille à l'aveugle et produit du *LLM Vector Slop* (courbes « fil de fer », tangentes aveugles, faux contours baveux).

Dès que le graphisme comporte des courbes typographiques, des superpositions de plans ou un conteneur *squircle*, **basculer vers un script générateur Python/Qt (`PySide6.QtGui.QPainterPath`)** :

1. **Extraction de vrais glyphes typographiques (`QPainterPath.addText`)** : extraire les contours dessinés par des typographes humains (*Helvetica Neue Bold*, *Avenir Next*, *Futura*, *Newsreader*) plutôt que de coder un `?` ou une lettre à la main.
2. **Soustraction booléenne CSG réelle (`back_path.subtracted(cutter)`)** : creuser une tranchée franche et transparente entre le premier plan et l'arrière-plan, sans jamais utiliser de `stroke` sombre qui bave sur le fond ni d'ombre portée grise qui salit les calques.
3. **Superellipse continue & Liseré interne (*Inset Rim*)** :
   - Échantillonner la superellipse $|x/a|^{4.6} + |y/b|^{4.6} = 1$ sur `256` pas avec un fond 100 % opaque (`fill` seul, sans `stroke`).
   - Tracer le liseré spéculaire sur une **seconde superellipse interne** (`rayon - 0.9`) pour éviter tout halo semi-transparent sur fond blanc.
4. **Loi de Proximité de la Gestalt & Centre Optique** :
   - Pour représenter du texte sur une fiche, appliquer la **Règle de 3** (jamais 5 lignes fines « code-barres »).
   - Regrouper **1 Titre + 1 Paragraphe de 2 lignes** : l'interligne entre les deux lignes de corps doit être **~2 fois plus petit** que l'écart sous le titre, avec des longueurs asymétriques (ex. `68 %` / `100 %` / `56 %`, ratio largeur/hauteur `> 3:1` pour éviter l'effet bouton) et un léger décalage optique vers le haut (`-1.2` unité).

---

## 5. Étape 5 : Contrôle Optique Multi-Échelles & Déploiement

1. Rendre le SVG en PNG via `QSvgRenderer` aux tailles `1024`, `512`, `128`, `64`, `32` et `16 px` sur **fond sombre ET fond blanc transparent**.
2. Inspecter visuellement les rendus avec `read_file` pour vérifier l'absence de collision de bordure, de tangente aveugle ou de halo.
3. Déployer sur toutes les cibles du projet via :
   ```bash
   QT_QPA_PLATFORM=offscreen uv run python script/generate_app_icons.py
   ```

---

## ⛔ Ne PAS utiliser ce skill si...

- L'objectif est de coder ou styliser un widget PySide6 interne de l'application → utiliser `ui-pyside6-design` ou `impeccable-pyside6`.
- L'objectif est uniquement de soumettre un design existant au jury contradictoire → utiliser `critique-design-contradictoire`.
- L'objectif est une recherche documentaire technique ou logicielle hors graphisme → utiliser `research`.

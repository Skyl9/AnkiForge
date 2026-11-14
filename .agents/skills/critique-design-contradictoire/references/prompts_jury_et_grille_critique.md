# Prompts du Jury & Grille de Détection du « LLM Vector Slop » (`critique-design-contradictoire`)

Ce référentiel fournit la configuration prête à l'emploi pour instancier le jury de 3 sous-agents designers ainsi que la grille d'inspection optique.

---

## 1. Définition du Sous-Agent (`define_subagent`)

Utiliser `define_subagent` avec `EnableWriteTools: False` pour créer le profil `icon-design-critic` :

```text
Name: icon-design-critic
Description: Directeur Artistique et Iconographe Senior qui critique sans complaisance les icônes SVG, logos et pages vitrines face aux principes optiques, aux lois de la Gestalt, aux contraintes d'OS et aux marqueurs de LLM Vector Slop.
SystemPrompt:
Tu es un Directeur Artistique et Iconographe Senior. Tu combines :
1. La rigueur éditoriale et systémique (grille, hiérarchie, test de réduction à 16x16 px où 1 px = 8 unités sur une viewBox 128, silhouette 1-bit, espace négatif).
2. L'artisanat des icônes OS modernes et des studios indépendants (anatomie du squircle macOS, padding de sécurité interne, optique des courbes de Bézier à pleins et déliés, découpe CSG franche sans artefact d'ombre, liseré spéculaire interne sans halo sur fond blanc).
3. La psychologie cognitive et la sémiotique produit (règle du panneau routier "Traffic Sign", détection des faux-amis visuels par comparaison aux icônes connues du marché, sémantique des couleurs dans l'écosystème Anki, et Loi de Proximité de la Gestalt).

Ton rôle est d'inspecter le code SVG réel ET les rendus PNG multi-échelles, puis de produire en français une critique chirurgicale, honnête, sans aucune complaisance ("penser contre"), assortie de corrections géométriques chiffrées.
```

---

## 2. Mandats des 3 Experts Parallèles (`invoke_subagent`)

Lancer simultanément 3 instances via `invoke_subagent` :

| Instance | Rôle (`Role`) | Angle d'attaque prioritaire |
| :--- | :--- | :--- |
| **Expert 1** | `Critique Système, Grille & 16px` | Cohérence avec la page d'accueil, calcul arithmétique de survie à `16×16 px` et `22×22 px`, test monochrome, détection des pincements d'espace négatif. |
| **Expert 2** | `Critique Anatomie OS & Optique Bézier` | Qualité des courbes (glyphe typographique vs courbe codée à la main), *padding* dans le *squircle*, artefacts d'ombre portée, halo de `stroke` sur fond clair, harmonie géométrique des rayons `rx`. |
| **Expert 3** | `Critique Métaphore, Faux-Amis & Gestalt` | Comparaison aux icônes connues (*Raycast, Linear, Notion, Things 3, Quizlet*), élimination des faux-amis (smartphone, To-Do list), contresens chromatiques (rouge = échec Anki), et **Loi de Proximité de la Gestalt** sur les blocs de texte. |

---

## 3. Les 6 Marqueurs Techniques du « LLM Vector Slop » à Éradiquer

Un œil exercé reconnaît immédiatement un SVG généré par du code à l'aveugle grâce à ces 6 symptômes :

1. **Collision ou frôlement de bordure (*Out-of-bounds*) :**
   - *Symptôme :* Un coin de carte interne touche ou mord le liseré du conteneur *squircle*.
   - *Remède :* Réduire l'échelle du groupe central de `10 à 12 %` et abaisser le centre optique pour garantir au moins `40 à 50 unités` de marge (sur base `1024`, soit `5 à 6 unités` sur base `128`).
2. **Effet « Code-Barres » et vide inférieur :**
   - *Symptôme :* 4 ou 5 lignes fines horizontales imitant une page A4, qui fusionnent en une tache grise sous `32×32 px` et laissent un trou vide en bas de la carte.
   - *Remède :* Appliquer la **Règle de 3** (3 barres épaisses aux coins légèrement adoucis `rx=1.6`).
3. **Violation de la Loi de Proximité (Effet « Formulaire » & Symétrie) :**
   - *Symptôme :* Espacement vertical strictement identique entre la barre de titre et les deux barres de corps, combiné à une longueur égale entre la 1re et la 3e barre (`Court / Long / Court`). L'œil perçoit 3 boutons empilés ou une icône d'alignement centré.
   - *Remède :* Resserrer l'interligne entre les barres 2 et 3 (`~2×` plus petit que l'écart sous le titre), différencier les longueurs (`68 %` / `100 %` / `56 %`) et maintenir un ratio largeur/hauteur `> 3:1` sur la dernière ligne.
4. **Tangente aveugle sur glyphe :**
   - *Symptôme :* La tranchée de découpe de la carte avant mord l'extrémité gauche du `?`, laissant un micro-triangle résiduel et faisant ressembler le `?` à un `7` ou un chevron `>`.
   - *Remède :* Décaler le centre optique du glyphe vers la droite (`q_offset_x`) pour que sa crosse gauche soit 100 % entourée de la couleur de fond de sa carte.
5. **Fausse gouttière (`stroke` extérieur) ou bug d'ombre portée :**
   - *Symptôme :* Une bordure sombre autour de la carte avant déborde sur le fond du *squircle*, ou une ombre grise assombrit un glyphe blanc sur la carte arrière.
   - *Remède :* Utiliser une **soustraction booléenne CSG réelle** (`back_world.subtracted(cutter)`).
6. **Halo de `stroke` semi-transparent sur fond blanc :**
   - *Symptôme :* Un `stroke` semi-transparent appliqué directement sur le `<path>` du *squircle* déborde de `50 %` à l'extérieur sur les pixels transparents, créant une frange lavande sur fond clair.
   - *Remède :* Séparer le fond opaque (`half_size = 59.5`, sans `stroke`) et le liseré spéculaire interne (`half_size = 58.6`, `fill="none"`).

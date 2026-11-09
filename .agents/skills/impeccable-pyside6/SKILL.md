---
name: impeccable-pyside6
description: >-
  Craft UI de précision et éradication méthodique du slop Qt pour PySide6 selon la
  philosophie Impeccable (distill, typeset, arrange, harden, polish, quieter, bolder).
  Transforme les widgets bruts en interfaces desktop de qualité studio (Linear/Raycast)
  conformes à DESIGN.md. Use when the user asks to "impeccable", "craft ui",
  "finition ui", "anti-slop qt", "distill", "typeset", "polish", "harden",
  "quieter", "bolder", "passes de finition", "sublimer l'ui" or wants to refine
  a PySide6 view through systematic finishing passes. When NOT to use: Do not use
  for exploring conceptual UX directions (use ui-anti-slop), one-off layout bugfixes
  (use ui-visual-polish), or general component coding from scratch (use ui-pyside6-design).
---

# Impeccable PySide6 — Craft UI & Passes de Finition

Tu agis comme un designer-ingénieur senior obsédé par la qualité d'exécution (Craft UI).
Ton objectif est de transformer tout composant ou vue PySide6 en une interface desktop
de niveau studio (Linear, Raycast), débarrassée des tics d'implémentation des LLM
(le "PySide6 AI Slop"), en appliquant des passes chirurgicales progressives.

---

## 1. Principes Fondamentaux & Éradication du Slop

Ne jamais tolérer le code d'interface paresseux généré par les LLM :
- **Zéro boîte gravée dans la boîte** : bannir l'empilement de `QGroupBox`.
- **Zéro couleur hexadécimale codée en dur** : toujours exploiter `DesignTokens`.
- **Zéro pop-up bloquante native** : privilégier `ToastManager` ou bannières inline.
- **Zéro layout cassé au redimensionnement** : `setWordWrap(True)` et résilience 1280×800.
- Consulter impérativement la grille des remèdes dans `references/anti-patterns-qt-slop.md`.

---

## 2. Les 6 Passes Chirurgicales

Chaque commande applique une transformation ciblée et mesurable :

1. `/distill` : **Épuration radicale**. Supprime le bruit visuel, les bordures étouffantes,
   les séparateurs redondants et les arrière-plans incohérents.
2. `/typeset` : **Hiérarchie typographique**. Impose les tailles (16px titre, 11px section
   uppercase, 12px corps, 10px aide), contrastes et polices (`FONT_MAIN`, `FONT_CODE`).
3. `/arrange` : **Rythme spatial & Alignements**. Aligne tout sur la grille de 4px
   (`SPACING_SM=8`, `SPACING_MD=12`, `SPACING_LG=16`, `SPACING_XL=24`), équilibre
   les marges (`setContentsMargins`), et place les spacers verticaux élastiques.
4. `/harden` : **Robustesse desktop**. Éprouve le redimensionnement (1280×800 et 820×560),
   élimine tout scrollbar horizontal, sécurise les débordements de traduction i18n (+30%).
5. `/polish` : **Micro-affordances & Craft**. Pointeur main sur clics, états complets
   (`:hover`, `:pressed`, `:disabled`), ombres subtiles (`apply_shadow`), icônes Phosphor.
6. `/quieter` ou `/bolder` : **Pondération visuelle**. Atténue la saturation visuelle
   (boutons ghost, textes secondaires) ou affirme l'action primaire focalisée.

Détail des protocoles d'exécution dans `references/workflows-commands.md`.

---

## 3. Matrice Métrique & Typographique

- **Typographie** : échelle stricte 5 niveaux documentée dans `references/typography-and-spatial-rhythm.md`.
- **Grille Spatiale** : multiples de 4px obligatoires, zéro marge impaire aléatoire.
- **Rayons de Courbure** : `RADIUS_SM=6px` (badges), `RADIUS_MD=10px` (cartes/inputs),
  `RADIUS_LG=16px` (modales).
- **Hauteurs des Contrôles** : 36px pour boutons et inputs standards, 32px pour compacts.

---

## 4. Protocole de Validation & QA

Avant de conclure une passe Impeccable :
1. **Contrôle Headless** : exécuter le test ciblé avec `uv run pytest tests/ui/test_<vue>.py`.
2. **Inspection Visuelle** : capturer l'état offscreen avec `script/capture_view.py` et
   vérifier l'harmonie sur thèmes sombre et clair.
3. Consulter les techniques de fiabilisation dans `references/harden-and-polish.md`.

---

## Ne pas utiliser ce skill si...

- la demande vise à inventer de nouvelles directions UX conceptuelles :
  utiliser `ui-anti-slop` ;
- il s'agit de corriger un bogue ponctuel d'alignement ou de CSS existant :
  utiliser `ui-visual-polish` ;
- le besoin est une implémentation logicielle complète depuis zéro :
  utiliser `ui-pyside6-design` ;
- la demande concerne uniquement les performances ou freezes du thread GUI :
  utiliser `audit-performance` ;
- la tâche porte uniquement sur une capture d'écran sans modification :
  utiliser `ui-screenshot`.

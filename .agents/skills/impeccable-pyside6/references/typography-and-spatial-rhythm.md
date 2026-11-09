# Typographie et Rythme Spatial — AnkiForge

Ce guide formalise l'échelle métrique, les tokens typographiques et la grille spatiale d'AnkiForge, définis dans `DESIGN.md`. Ces règles garantissent une harmonie visuelle sans couture entre toutes les vues de l'application.

---

## 1. Familles de Polices

| Token | Famille Système Recommandée | Usage |
| :--- | :--- | :--- |
| `DesignTokens.FONT_MAIN` | `Inter`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, sans-serif | Interface, libellés, boutons, titres, dialogues |
| `DesignTokens.FONT_CODE` | `JetBrains Mono`, `Fira Code`, `SF Mono`, `Consolas`, monospace | Éditeur de prompts, logs, JSON, variables, IDs |

---

## 2. Échelle Typographique Studio

L'échelle respecte une hiérarchie stricte en 5 niveaux pour guider l'œil sans ambiguïté :

```text
Display / Vue Title      16px / Semibold 600    COLOR_TEXT_PRIMARY
Section Header           11px / Bold 600        COLOR_TEXT_MUTED + Uppercase + 0.5px letter-spacing
Card Title / Subtitle    13px / Medium 500      COLOR_TEXT_PRIMARY
Body Text / Form Input   12px / Regular 400     COLOR_TEXT_PRIMARY ou SECONDARY
Caption / Helper / Meta  10px / Regular 400     COLOR_TEXT_MUTED
```

### Règles Typographiques Fondamentales
1. **Titres de Section Épurés** : Tout en-tête de groupe ou sous-panneau adopte impérativement `11px`, majuscules, graisse 600, et couleur atténuée (`COLOR_TEXT_MUTED`).
2. **Éviter le gras excessif** : Réserver la graisse `600` (Semibold) aux titres et boutons primaires. Le corps de texte reste toujours en `400` (Regular) pour préserver la légèreté visuelle.
3. **Hauteur de Ligne & Alignement** : Aligner verticalement le texte sur les icônes d'action associées (`Qt.AlignmentFlag.AlignVCenter`).

---

## 3. Grille Spatiale Modulaire (Multiples de 4px)

Toutes les marges (`setContentsMargins`), espacements de layout (`setSpacing`) et rembourrages intérieurs dérivent de la grille mathématique de 4px.

| Constante | Valeur | Usage Précis dans AnkiForge |
| :--- | :--- | :--- |
| `SPACING_XS` | **4px** | Écart entre icône et texte inline, espacement interne micro-badge |
| `SPACING_SM` | **8px** | Espacement standard entre contrôles consécutifs, marges compactes |
| `SPACING_MD` | **12px** | Rembourrage interne des cartes (`MetricCard`, `StatCard`), espacement de sous-groupes |
| `SPACING_LG` | **16px** | Marges de fenêtres, dialogues modaux (`setContentsMargins(16, 16, 16, 16)`), écart entre formulaires |
| `SPACING_XL` | **24px** | Séparation franche entre blocs fonctionnels majeurs |
| `SPACING_XXL`| **32px** | Aération des écrans d'accueil et des états vides (`EmptyStateWidget`) |

### Règles de Rythme
- **Interdiction formelle des valeurs impaires ou aléatoires** : Bannir les marges à 7, 9, 11 ou 13px issues des réflexes LLM.
- **Règle de Proximité** : L'espacement entre un libellé et son champ associé (ex. 4-6px) doit toujours être inférieur à l'espacement séparant ce groupe du champ suivant (ex. 12-16px).

---

## 4. Rayons de Courbure (Border Radius)

| Token | Valeur | Éléments Cibles |
| :--- | :--- | :--- |
| `DesignTokens.RADIUS_SM` | **6px** | `Badge`, `TagButton`, `FilterChipButton`, contrôles compacts |
| `DesignTokens.RADIUS_MD` | **10px** | `PrimaryButton`, `SecondaryButton`, `StyledLineEdit`, `QFrame` de carte, panneaux |
| `DesignTokens.RADIUS_LG` | **16px** | Dialogues modaux majeurs, conteneurs maîtres, cartes vedettes |

---

## 5. Hauteurs et Dimensions Normalisées des Contrôles

Pour éviter l'effet "accordéon" ou les boutons écrasés :

- **Bouton Standard (`PrimaryButton`, `SecondaryButton`)** : `height = 36px` (`padding: 8px 16px`).
- **Bouton Compact (`apply_compact_style`)** : `height = 32px` (`padding: 2px 10px`, `font_size_sm`).
- **Bouton Icône Carré (`IconButton`)** : `32×32px` ou `28×28px` (icône 16×16px centrée).
- **Champs de saisie (`StyledLineEdit`, `StyledComboBox`)** : `height = 36px` (`padding: 6px 12px`).
- **Zone de saisie code / multiline (`StyledTextEdit`)** : Hauteur minimale `80px`, police `FONT_CODE`.

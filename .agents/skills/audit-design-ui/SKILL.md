---
name: audit-design-ui
description: Audit de conformité au design system et de l'accessibilité de l'UI d'AnkiForge. Use when the user asks to "audit design", "audit UI", "conformité DESIGN.md", "design system", "tokens", "couleurs codées en dur", "thèmes", "accessibilité", "WCAG" or "nouveau widget non documenté". Checks DesignTokens usage, hardcoded colors, stylesheets, theme/layout inventory and WCAG basics; produces a report under audits/.
---

# Audit UI & Design System AnkiForge

En tant qu'**Auditeur Design System & Accessibilité**, tu vérifies que l'interface respecte la source de vérité `DESIGN.md` (tokens sémantiques, 12 thèmes, 4 layouts) et les règles WCAG de base, puis tu produis un rapport d'écarts.

## 1. Périmètre & Sources de Vérité

- `DESIGN.md` : design system, matrice des tokens (`DesignTokens` / `ThemeProfile`), inventaire des 12 thèmes et 4 layouts, consignation obligatoire des nouveaux widgets.
- `GEMINI.md` règle 18 : toute nouvelle UI s'appuie sur `docs/Dossier_architecture/07_inventaire_composants_ui.md` ; zéro couleur ou style codé en dur.
- `src/ankiforge/ui/` + `src/ankiforge/theme/` (ou équivalent) et `src/ankiforge/styles/`.

## 2. Commandes d'Investigation

```bash
# Couleurs codées en dur (hex) dans le code UI hors fichiers de thème
grep -rInE "#[0-9a-fA-F]{3,8}\b|rgba?\([0-9]+" src/ankiforge/ui/ --include="*.py" || true
# Styles inline Shopify/locaux risquant de contourner les tokens
grep -rIn "setStyleSheet" src/ankiforge/ui/ --include="*.py" || true
# Couleurs nommées interdites
grep -rInE "(red|blue|green|yellow|white|black|transparent)[\"']" src/ankiforge/ui/ --include="*.py" || true
# Anti-patterns de layout : marges CSS sur QLabel + AlignTop header
grep -rInE "margin(-[a-z]+)?\s*:\s*[0-9]+|setAlignment\(" src/ankiforge/ui/ --include="*.py" || true
# Nouveaux widgets éventuellement non consignés dans DESIGN.md (classes QWidget custom)
grep -rInE "^class .*\(QWidget\)" src/ankiforge/ui/ --include="*.py" || true
```

## 3. Points de Contrôle

1. **Tokens sémantiques** : aucune couleur hexadécimale hors fichiers de thème (`theme.py`, profils `ThemeProfile`). Toute couleur en dur dans les vues/widgets est une violation à remplacer par un token `DesignTokens.*`.
2. **`setStyleSheet` local** : autorisé seulement pour des styles simples/éphémères ; interdit pour surcharger les styles natifs complexes (doit passer par `StyleEngine.generate_stylesheet()`).
3. **Inventaire thèmes/layouts** : croiser `DESIGN.md` avec la liste réelle des thèmes déclarés dans le code (12 thèmes, 4 layouts) ; signaler tout thème ajouté non documenté.
4. **Documentation des widgets** : chaque classe `QWidget`/composant nouveau doit être consigné dans `DESIGN.md` (tokens associés, correspondances) et déclaré dans `StyleEngine` ; vérifier les récents (`grep` classes custom) et les croiser avec `DESIGN.md`.
5. **Anti-patterns de layout** (connues AnkiForge) :
   - Marges CSS appliquées à des `QLabel` placés dans un `QVBoxLayout` → remplacer par les outils de layout Qt (`setContentsMargins`, `addSpacing`).
   - Utilisation de `AlignTop` pour tasser les headers → préférer l'agencement natif.
   - `setMinimumWidth()` excessifs qui cassent le responsive des panneaux détachables `IdePanel`.
   - `splitter.setChildrenCollapsible(False)` systématique sur les splitters.
   - Ombres portées uniquement via `QGraphicsDropShadowEffect` natif.
6. **Accessibilité WCAG de base** :
   - Contraste texte/fond respectant AA (vérifier les paires de tokens clair/sombre).
   - Focus visible : `QPushButton`/champs avec focus outline ; navigation clavier possible dans les dialogues complexes.
   - `toolTip`/`accessibleName` sur les icônes seules et boutons icon-only.
   - Tailles min cibles cliquables (~24px) et états hover/active cohérents avec le thème.

## 4. Rapport

`audits/audit-design-ui.md` :

### 📊 Synthèse
Écarts par sévérité (Critique/Majeur/Mineur) et par catégorie (Tokens, Styles locaux, Thèmes/Layouts, Documentation, Layout anti-patterns, Accessibilité).

### 🔍 Écarts détaillés
Liens cliquables `[fichier.py:Lnn](file://<abs>/...#Lnn)` · règle violée (réf. DESIGN.md/GEMINI.md) · extrait · correction (ex. remplacer `#2b2b2b` par `DesignTokens.TEXT_PRIMARY`).

### 🗺️ Plan priorisé
Actions ordonnées (accessibilité + couleurs en dur d'abord), puis documentation manquante.

## 5. Clôture

Résume les écarts principaux dans le chat, indique le chemin du rapport, propose d'appliquer les correctifs (remplacements de tokens, mises à jour DESIGN.md).
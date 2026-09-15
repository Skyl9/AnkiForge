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
- `theme.py` vit à la racine du package (`src/ankiforge/theme.py`), pas sous `src/ankiforge/ui/` : il est donc hors du périmètre scanné par les commandes de la section 2 et n'a pas besoin d'être exclu explicitement. Les profils `ThemeProfile` sont la source légitime de couleurs en dur.

## 2. Commandes d'Investigation

Les sorties sont conservées sous `audits/raw/` (horodatées) pour permettre une comparaison d'un audit à l'autre.

```bash
mkdir -p audits/raw
STAMP=$(date +%Y-%m-%d)
UI_SRC="src/ankiforge/ui/"
EXCLUDES="--exclude-dir=tests --exclude-dir=__pycache__ --exclude-dir=.venv --exclude-dir=build"
# theme.py n'a pas besoin d'être exclu : il vit hors de $UI_SRC (src/ankiforge/theme.py)

# Couleurs codées en dur (hex) dans le code UI hors fichiers de thème, hors commentaires purs
grep -rInE "#[0-9a-fA-F]{3,8}\b|rgba?\([0-9]+" $UI_SRC --include="*.py" $EXCLUDES \
  | grep -vE "^\S+:\d+:\s*#" \
  > "audits/raw/hardcoded-hex-${STAMP}.txt" || true

# Styles inline risquant de contourner les tokens
grep -rIn "setStyleSheet" $UI_SRC --include="*.py" $EXCLUDES \
  > "audits/raw/setstylesheet-${STAMP}.txt" || true

# Couleurs nommées interdites — \b pour éviter les faux positifs (ex. "required", "expired")
grep -rInE "\b(red|blue|green|yellow|white|black|transparent)\b[\"']" $UI_SRC --include="*.py" $EXCLUDES \
  > "audits/raw/named-colors-${STAMP}.txt" || true

# Anti-patterns de layout : marges CSS sur QLabel + AlignTop header
grep -rInE "margin(-[a-z]+)?\s*:\s*[0-9]+|setAlignment\(" $UI_SRC --include="*.py" $EXCLUDES \
  > "audits/raw/layout-antipatterns-${STAMP}.txt" || true

# Anti-patterns supplémentaires connues AnkiForge (setMinimumWidth excessif, splitter figé)
grep -rInE "setMinimumWidth\([0-9]{3,}\)|setChildrenCollapsible\(False\)" $UI_SRC --include="*.py" $EXCLUDES \
  > "audits/raw/layout-antipatterns-extra-${STAMP}.txt" || true

# Nouveaux widgets éventuellement non consignés dans DESIGN.md (classes QWidget custom)
grep -rInE "^class .*\(QWidget\)" $UI_SRC --include="*.py" $EXCLUDES \
  > "audits/raw/new-widgets-${STAMP}.txt" || true
```

> Notes :
> - `\b` autour des couleurs nommées évite qu'un mot comme `"required"` ou `"expired"` soit compté comme une couleur `red`.
> - `setMinimumWidth(...)` et `setChildrenCollapsible(False)` restent des heuristiques grossières (elles ne distinguent pas un usage légitime d'un abus) — à confirmer manuellement pour chaque occurrence, pas à traiter comme des violations automatiques.
> - Aucune commande fiable n'existe pour le contraste WCAG ou le focus visible (point 6) : ces vérifications restent manuelles, voir section 3.6.

## 3. Points de Contrôle

1. **Tokens sémantiques** : aucune couleur hexadécimale hors fichiers de thème (`theme.py`, profils `ThemeProfile`). Toute couleur en dur dans les vues/widgets est une violation à remplacer par un token `DesignTokens.*`.
2. **`setStyleSheet` local** : autorisé seulement pour des styles simples/éphémères ; interdit pour surcharger les styles natifs complexes (doit passer par `StyleEngine.generate_stylesheet()`).
3. **Inventaire thèmes/layouts** : croiser `DESIGN.md` avec la liste réelle des thèmes déclarés dans le code (12 thèmes, 4 layouts) ; signaler tout thème ajouté non documenté.
4. **Documentation des widgets** : chaque classe `QWidget`/composant nouveau doit être consigné dans `DESIGN.md` (tokens associés, correspondances) et déclaré dans `StyleEngine` ; vérifier les récents (`audits/raw/new-widgets-*.txt`) et les croiser avec `DESIGN.md`.
5. **Anti-patterns de layout** (connues AnkiForge) :
   - Marges CSS appliquées à des `QLabel` placés dans un `QVBoxLayout` → remplacer par les outils de layout Qt (`setContentsMargins`, `addSpacing`).
   - Utilisation de `AlignTop` pour tasser les headers → préférer l'agencement natif.
   - `setMinimumWidth()` excessifs qui cassent le responsive des panneaux détachables `IdePanel` (voir `audits/raw/layout-antipatterns-extra-*.txt`, à confirmer au cas par cas).
   - `splitter.setChildrenCollapsible(False)` systématique sur les splitters.
   - Ombres portées uniquement via `QGraphicsDropShadowEffect` natif.
6. **Accessibilité WCAG de base** (revue manuelle — pas d'outil automatisé dans ce skill) :
   - Contraste texte/fond respectant AA (ratio ≥ 4.5:1 pour texte normal, ≥ 3:1 pour texte large) : extraire les paires de tokens clair/sombre depuis `DesignTokens` et calculer le ratio (ex. via un petit script `wcag_contrast_ratio(fg, bg)` si disponible dans `utils/`, sinon calcul manuel).
   - Focus visible : `QPushButton`/champs avec focus outline ; navigation clavier possible dans les dialogues complexes.
   - `toolTip`/`accessibleName` sur les icônes seules et boutons icon-only.
   - Tailles min cibles cliquables (~24px) et états hover/active cohérents avec le thème.

## 4. Rapport

`audits/audit-design-ui.md` (écrasé à chaque audit — l'historique brut vit sous `audits/raw/`) :

### 📊 Synthèse
Écarts par sévérité (Critique/Majeur/Mineur) et par catégorie (Tokens, Styles locaux, Thèmes/Layouts, Documentation, Layout anti-patterns, Accessibilité).

### 🔁 Évolution depuis le dernier audit
Comparaison avec les fichiers `audits/raw/` les plus récents précédents (nouveaux écarts, écarts corrigés) — si un audit précédent existe.

### 🔍 Écarts détaillés
Liens cliquables `[fichier.py:Lnn](file://<abs>/...#Lnn)` · règle violée (réf. DESIGN.md/GEMINI.md) · extrait · correction (ex. remplacer `#2b2b2b` par `DesignTokens.TEXT_PRIMARY`).

### 🗺️ Plan priorisé
Actions ordonnées (accessibilité + couleurs en dur d'abord), puis documentation manquante.

## ⛔ Ne PAS utiliser ce skill si...

- La demande porte sur une **implémentation de fonctionnalité UI** (pas d'audit nécessaire pour l'instant).
- L'utilisateur demande uniquement de **corriger un bug visuel ponctuel** déjà identifié, sans besoin d'audit global.
- La vérification WCAG demandée nécessite un **outil automatisé spécialisé** (ex: axe-core, Accessibility Insights) — ce skill ne couvre que les règles de base.
- La demande concerne les **performances de rendu Qt** → utiliser `audit-performance`.
- Aucun composant UI n'a été ajouté ou modifié depuis le dernier audit design.

## 5. Clôture

Résume les écarts principaux dans le chat, indique le chemin du rapport et des sorties brutes, précise que les vérifications d'accessibilité (contraste, focus) restent en partie manuelles, propose d'appliquer les correctifs (remplacements de tokens, mises à jour DESIGN.md).

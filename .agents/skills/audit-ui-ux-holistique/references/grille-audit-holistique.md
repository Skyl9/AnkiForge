# Grille d'Audit UI/UX Holistique - Référentiel Senior AnkiForge

Ce document détaille les points de contrôle techniques et ergonomiques à vérifier lors d'un audit transversal multi-fichiers d'AnkiForge (`PySide6` + `StyleEngine`).

---

## Axe 1 : Conformité au Design System (`DESIGN.md`) & Anti-Dérive

Lorsqu'une interface produite par un développeur donne l'impression de "manquer de finition design", la cause n°1 sur une grande codebase est la **dérive locale** entre les vues.

### 1.1 Contournement de `DesignTokens` et `StyleEngine`

- **Couleurs codées en dur** : Chercher toute occurrence de `#[0-9a-fA-F]{3,6}`, `rgb(`, `rgba(`, ou noms de couleurs CSS (`white`, `black`, `red`, `gray`) dans les `.setStyleSheet(...)` ou `QPainter`.
  - *Correction* : Remplacer par les tokens `DesignTokens` (`BG_MAIN`, `BG_PANEL`, `BG_INPUT`, `BG_HOVER`, `BG_ACTIVE`, `TEXT_PRIMARY`, `TEXT_SECONDARY`, `TEXT_MUTED`, `BORDER_COLOR`, `BORDER_LIGHT`, `ACCENT_PRIMARY`) et les 18 tokens de surfaces teintées §1.0 (`ACCENT_BG`/`ACCENT_BORDER`, `COLOR_RED_BG`/`COLOR_RED_BORDER`/`COLOR_RED_TEXT`, etc.).
- **Contraste sur fond accentué** : Toute icône ou texte posé sur `ACCENT_PRIMARY` ou un fond saturé doit utiliser `DesignTokens.TEXT_ON_ACCENT` et `load_on_accent_icon(name)` - jamais `color="white"` (qui casse sur certains thèmes clairs ou inversés).
- **Écrasement accidentel du QSS global** :
  - Ne jamais redéclarer `border` ou `background` en QSS inline sur `PrimaryButton`, `SecondaryButton`, `DangerButton`, `IconButton` ou un bouton en `apply_compact_style()` (`density="compact"`), car cela détruit les états `:hover`, `:focus`, `:pressed` et `:disabled` gérés par `StyleEngine`.
  - Dans les conteneurs (`QFrame`, `QScrollArea`), toujours scoper les sélecteurs par `objectName` (ex: `QFrame#monConteneur { ... }`) pour éviter que le style ne cascade sur tous les widgets enfants.
  - Rappel hiérarchie typographique : `StyleEngine` impose `QWidget { font-size }` globalement. Utiliser `setFont()` pour changer la taille d'un `QLabel` est écrasé par le QSS global (seul le `bold` survit). La taille doit être déclarée en QSS (`font-size: ...px`).

### 1.2 Duplication ou non-utilisation des composants canoniques (`ui/components/`)

Vérifier systématiquement si une vue réinvente un composant existant :

- **Sous-onglets / Barres segmentées** : Doivent utiliser `SegmentedTabBar(mode="subtab" | "segmented")` (`ui/components/segmented_tab_bar.py`), et non des `SubTabButton` locaux dupliqués par vue.
- **Filtres capsules / Chips** : Doivent utiliser `FilterChipButton` (hauteur 26px, `border-radius: 9999px`, icône Phosphor réactive, zéro émoji).
- **Menus contextuels** : Doivent utiliser `StyledMenu` (`ui/components/`). Règle absolue : la couleur sémantique est portée **uniquement par l'icône** (`load_phosphor_icon(..., color=...)`), le texte reste `TEXT_PRIMARY`, et les actions indisponibles restent présentes mais grisées via `setEnabled(False)` (menu à forme stable, jamais de "menu à trous").
- **Boutons d'action inline denses** : Utiliser `apply_compact_style()` (`COMPACT_BUTTON_HEIGHT = 32px`, `density="compact"`) plutôt que des `setFixedHeight(24)` ou des paddings bricolés qui rognent les icônes.
- **Sélecteurs modaux riches** : Privilégier `ModalField` / `DocumentPickerButton` ouvrant `DeckSelectWindow`, `ModelSelectWindow`, `PersonaSelectWindow`, `PipelineSelectWindow` ou `TagSelectWindow` plutôt que des `QComboBox` surchargés quand la collection dépasse 15 éléments ou possède une hiérarchie `::`.

---

## Axe 2 : Hiérarchie Visuelle, Syndrome du "Box-in-Box" & Charge Cognitive

C'est le défaut classique des interfaces conçues par des développeurs : vouloir matérialiser chaque structure logique du code (`QVBoxLayout` / `QFrame`) par une boîte visible avec bordure et fond distinct.

### 2.1 Syndrome des cadres imbriqués ("Box-in-Box")

- **Symptôme** : Un `QFrame` (`bg_panel` + `border_color`) contenant une `QScrollArea` (avec bordure) contenant des cartes (`bg_input` + `border_color`) contenant elles-mêmes des sous-cadres encadrés. L'œil est saturé de lignes parallèles à 4px d'intervalle.
- **Correction Senior Designer** :
  - Désencadrer les en-têtes de section et les conteneurs structurels intermédiaires (`background: transparent; border: none;` sur les `QScrollArea` et conteneurs de mise en page).
  - Créer la hiérarchie par **la typographie et l'espace blanc** : un titre de section en `14px/15px bold TEXT_PRIMARY` ou un label de groupe en `10px uppercase letter-spacing: 0.5px TEXT_MUTED` avec un `addSpacing(12)` sépare mieux deux blocs qu'un `QFrame` borduré supplémentaire.
  - Utiliser `border_light` uniquement pour les liserés décoratifs internes ou le relief haut, jamais comme contour d'isolation principal (ratio de contraste 1.00:1 à 1.24:1 sur `bg_panel`).

### 2.2 Compétition des appels à l'action (CTA)

- **Symptôme** : Plusieurs `PrimaryButton` (ou boutons colorés saturés) visibles simultanément sur le même écran ou dans la même barre d'outils.
- **Correction** :
  - **Un seul `PrimaryButton` par surface logique** (ex: "Forger", "Enregistrer", "Lancer le lot").
  - Toutes les actions compagnes ("Tester l'étape", "Affiner les liens", "Exporter", "Filtrer") passent en `SecondaryButton`, `FilterChipButton` ou `IconButton` (`role="ghost"`).
  - Les actions destructrices passent en `DangerButton` ou dans un menu trois-points (`dots-three-vertical`).

### 2.3 Divulgation progressive (Progressive Disclosure)

- Si un écran expose simultanément les paramètres d'inférence avancés (température, budgets tokens, règles de découpage, overrides de prompt) et le flux principal :
  - Replier les réglages secondaires dans un `CollapsibleSection` / `_CollapsiblePanel` (replié par défaut) ou déporter la configuration complexe dans un flux 2-étapes / tiroir / inspecteur latéral.
  - Conserver un résumé compact sous forme de badges (`FlowLayout` + `Badge` / `ConfigSummaryBar`) lorsque le panneau est replié.

---

## Axe 3 : Alignement Optique, Rythme Spatial & Responsivité (MacBook 13")

### 3.1 Rythme des marges et espacements

- **Constats fréquents** : Une vue utilise `setContentsMargins(20, 20, 20, 20)` et `setSpacing(15)`, tandis que la vue voisine utilise `(8, 8, 8, 8)` et `spacing(6)`. En passant d'un onglet à l'autre, l'interface "saute".
- **Grille recommandée (multiple de 4px)** :
  - Marges de vue racine : `16px` ou `20px` (ou `0px` si barre d'action supérieure pleine largeur `ResponsiveTopActionBar` + conteneur interne margé).
  - Marges internes de carte (`SettingsCard`, `IdePanel`) : `12px 16px` ou `16px`.
  - Espacement entre cartes : `10px` ou `12px`.
  - Espacement interne d'une rangée de contrôles inline : `6px` ou `8px`.

### 3.2 Alignement optique horizontal

- Sur une même barre horizontale (`QHBoxLayout`), tous les contrôles interactifs (`QLineEdit`, `StyledComboBox`, `PrimaryButton`, `SecondaryButton`) doivent partager **la même hauteur cible** (ex: 32px en mode compact ou 36px en mode standard) et être alignés sur `Qt.AlignmentFlag.AlignVCenter`.
- Un label de métadonnées monospace (`FONT_CODE`) placé en face d'un bouton d'action doit être aligné sur le même axe optique médian.

### 3.3 Invariants Responsives & Anti-Troncature

- **Zéro défilement horizontal** (`horizontalScrollBar().isVisible() == False`) aux résolutions compactes cibles (`820x560`, `880x620`, `1200x720` pour les cockpits).
- Bannir tout `setMinimumWidth(> 500)` rigide sur les panneaux ou cartes.
- Activer `setWordWrap(True)` sur tous les labels descriptifs.
- Utiliser `ElidedLabel` ou `QSizePolicy.Ignored` sur les titres de documents, chemins hiérarchiques et noms de modèles pour qu'ils n'expulsent jamais les boutons d'action situés à droite de la rangée.
- Utiliser `FlowLayout` / `FlowWidget` pour toute collection de pilules, tags ou badges susceptible de déborder sur une seule ligne.

---

## Axe 4 : États du Cycle de Vie, Asynchronisme & Gouvernance des Erreurs

1. **État Vide (Empty State)** :
   - Une table, un arbre ou un inspecteur vide ne doit jamais afficher un rectangle gris muet.
   - Présenter un état vide centré et explicite (icône Phosphor `40-52px` en `TEXT_MUTED` ou `ACCENT_PRIMARY`, titre court, explication en 1 phrase, et 1 ou 2 CTA directs si applicable, sur le modèle de `PersonaEmptyStateWidget` ou de l'état vide tri-state de `FiguresGalleryWidget`).
2. **État de Chargement / Workers en arrière-plan** :
   - Toute action lançant un `QThread` / `Worker` doit fournir un feedback immédiat (jauge, spinner ou bandeau type `ReindexActivityBanner` / `batch_progress_container`) et désactiver uniquement les mutations conflictuelles (garde-fou de run) sans geler la navigation globale.
3. **Interdiction des contrôles grisés muets** :
   - Comme codifié pour `VisionCapabilityNotice`, un contrôle désactivé (`setEnabled(False)`) dont la cause n'est pas évidente doit être accompagné d'un indice visuel persistant (badge ou bandeau court explicatif) ou, a minima, d'un `toolTip` explicite posé sur le conteneur parent.

---

## Axe 5 : Affordances, Clavier & Hygiène AnkiForge

- **Vraies vs Fausses Affordances** :
  - Si un élément n'est pas cliquable (ex: carte de KPI passif comme `_make_kpi_stat`), il ne doit avoir **ni `CursorShape.PointingHandCursor`, ni effet `:hover` sur la bordure, ni forme de capsule `FilterChipButton`**.
  - Inversement, toute carte cliquable (ex: `LinkedNoteCard`, `StepPickerCard`, `LayoutThumbnailCard`) doit exposer `PointingHandCursor`, un `:hover` clair (`border-color: accent_primary` ou `bg_hover`), un `:focus` clavier et une activation par `Entrée`/`Espace`.
- **Zéro Émoji Texte dans l'UI** :
  - Traquer les émojis Unicode (`⚠️`, `✅`, `🗑️`, `🔍`, `📁`, `✨`, `📥`) utilisés dans les `QPushButton`, `QLabel` d'en-têtes ou `QTabBar`. Les remplacer systématiquement par des icônes vectorielles Phosphor via `load_phosphor_icon("ph.xxx", color=...)`.
- **Internationalisation & Accessibilité (ADR 0013)** :
  - Toutes les chaînes visibles par l'utilisateur doivent passer par `self.tr("...")`.
  - Chaque `IconButton` sans texte doit définir un `setToolTip(self.tr("..."))` et un `setAccessibleName(self.tr("..."))`.
- **Raccourcis Clavier (ADR 0032)** :
  - Aucun `QShortcut` sauvage codé en dur hors du registre central `src/ankiforge/ui/shortcuts/catalog.py` (vérifié par `script/check_shortcuts_drift.py`).
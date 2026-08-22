# 🎨 Guide du Design System & Référentiel des Styles — AnkiForge

Ce document constitue la **source unique de vérité (Single Source of Truth)** pour l'architecture visuelle, le système de design, la gestion des modes **Sombre 🌙 / Clair ☀️**, la matrice de correspondance des tokens pour chaque composant UI et l'inventaire des **12 Familles de Thèmes bivalentes (24 thèmes au total)** d'AnkiForge.

> [!IMPORTANT]
> **Règle d'or de Contribution UI & Nouveaux Composants :**
> Toute création d'un nouveau type de composant, widget interactif ou panneau dans AnkiForge **DOIT IMPÉRATIVEMENT** être répertoriée dans la **Partie 1** de ce document avec la spécification exacte des variables de styles et `DesignTokens` à consommer. Aucun style ni code couleur hexadécimal ne doit être codé en dur dans le code source Qt PySide6.

---

# 📐 PARTIE 1 : Référentiel des Tokens & Standards par Composant

Le moteur de style centralisé (`StyleEngine`) et la classe `DesignTokens` (`src/ankiforge/ui/theme.py`) exposent des constantes sémantiques dynamiques. Lors d'un changement de thème ou de mode (Sombre 🌙 / Clair ☀️), ces tokens sont réassignés à chaud et le QSS global est recompilé.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           StyleEngine & ThemeFamily                         │
│             Mode : 🌙 Sombre / ☀️ Clair ⟷ 12 Familles Bivalentes            │
│                                      │                                      │
│                                      ▼                                      │
│           DesignTokens (bg_main, bg_panel, accent_primary, is_dark...)      │
│                                      │                                      │
│             ┌────────────────────────┴────────────────────────┐             │
│             ▼                                                 ▼             │
│    Global QSS (generate_stylesheet)            Widgets Spécifiques (Qt)     │
│    - QPushButton[role="..."]                   - TabButton / IdeTabBar      │
│    - QLineEdit, QTextEdit, QComboBox           - StyledMenu / Context Menu  │
│    - QTabWidget, QTabBar, QTableView           - Badges, Sliders, Docks     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1.1 Matrice de Correspondance : Composants ➔ Tokens Sémantiques

| Famille de Composant | Classe / Sélecteur Qt | Propriété Visuelle | Variable de Style / Token Requis | Description & Règle Métier |
| :--- | :--- | :--- | :--- | :--- |
| **Boutons Primaires** | `PrimaryButton`, `QPushButton[role="primary"]` | Arrière-plan<br>Arrière-plan Hover<br>Texte<br>Bordure / Radius | `accent_primary`<br>`accent_hover`<br>`#ffffff`<br>`border: none`, `radius_sm` (6px) | Action principale d'une vue (ex: Forger, Sauvegarder). Toujours mis en valeur avec l'accent. |
| **Boutons Secondaires** | `SecondaryButton`, `QPushButton[role="secondary"]` | Arrière-plan<br>Hover<br>Bordure<br>Texte | `bg_input`<br>`bg_hover`<br>`border_color`<br>`text_primary` | Actions neutres / secondaires (ex: Annuler, Parcourir, Filtrer). |
| **Boutons Danger** | `DangerButton`, `QPushButton[role="danger"]` | Arrière-plan<br>Hover<br>Texte / Bordure | `rgba(239, 68, 68, 0.14)`<br>`rgba(239, 68, 68, 0.28)`<br>`color_red` | Actions destructrices (ex: Supprimer la note, Éliminer le doublon). |
| **Boutons Fantômes / Icônes** | `IconButton`, `QPushButton[role="ghost"]` | Arrière-plan<br>Hover<br>Icône / Texte | `transparent`<br>`bg_hover`<br>`text_secondary` ➔ `text_primary` | Boutons compacts de barres d'outils, fermetures et toggles. |
| **Champs de Texte & Épis** | `QLineEdit`, `QTextEdit`, `QPlainTextEdit`, `StyledTextEdit` | Arrière-plan<br>Bordure normale<br>Bordure focus<br>Texte / Sélection | `bg_input`<br>`border_color`<br>`border_focus`<br>`text_primary` / `accent_primary` | Saisie de code, prompts, filtres de recherche et texte de cartes. |
| **Listes Déroulantes** | `QComboBox`, `StyledComboBox` | Arrière-plan champ<br>Menu Popup<br>Item Hover / Select | `bg_input`, bordure `border_color`<br>`bg_panel`, bordure `border_color`<br>`bg_hover`, texte `accent_primary` | Sélecteurs de modèles IA, paquets, pipelines et formats. |
| **Onglets de Panneaux IDE** | `TabButton`, `IdeTabBar` | Inactif<br>Hover<br>Actif (`:checked`) | Fond `bg_sidebar`, texte `text_secondary`<br>Fond `bg_hover`, texte `text_primary`<br>Fond `bg_panel`, texte `accent_primary`, barre supérieure 2px `accent_primary` | Titre et indicateur de l'onglet actif dans les panneaux multifenêtres. |
| **Onglets Documents** | `TabButton[variant="document"]` | Inactif<br>Actif (`:checked`) | Fond `transparent`, bordures `border_color`<br>Fond `bg_input`, texte `accent_primary`, barre haute `accent_primary` | Onglets de documents ouverts dans l'éditeur de cours. |
| **Onglets Pill / Segments** | `PillTabBar`, `QTabBar::tab` | Inactif<br>Actif (`:selected`) | Fond `bg_input`, texte `text_secondary`<br>Fond `bg_main`, texte `accent_primary`, bordure basse 2px `accent_primary` | Sous-navigation interne (ex: onglets de persona, onglets de pipeline). |
| **Menus Déroulants & Contextuels** | `QMenu`, `StyledMenu` | Arrière-plan menu<br>Bordure<br>Item normal<br>Item sélectionné<br>Séparateur | `bg_panel`<br>`1px solid border_color`, `radius_md` (10px)<br>Texte `text_primary`, padding 7px 20px 7px 32px<br>Fond `bg_hover`, texte `accent_primary`<br>`1px solid border_color` | Menus clic-droit (onglets, tableaux de cartes, personas, pipelines). |
| **Panneaux & Docks IDE** | `IdePanel`, `QFrame[card-style="panel"]` | Fond conteneur<br>En-tête (header)<br>Bordure globale | `bg_panel`<br>`bg_sidebar`, bordure basse `border_color`<br>`1px solid border_color`, `radius_md` (10px) | Panneaux modulaires détachables et empilables style JetBrains. |
| **Tableaux & Grilles** | `QTableWidget`, `QTableView`, `StyledTableWidget` | Fond grille<br>En-têtes colonnes<br>Cellule sélectionnée<br>Lignes de grille | `bg_panel`, texte `text_primary`<br>`bg_sidebar`, texte `text_muted`, bordure `border_color`<br>`bg_active`, texte `text_primary`<br>`border_color` | Tableau des cartes générées, liste des règles de linter, historique. |
| **Arborescences & Listes** | `QTreeWidget`, `QListWidget`, `QTreeView` | Fond<br>Item Hover<br>Item Sélectionné | `bg_panel` (ou `transparent` dans sidebar)<br>`bg_hover`<br>`bg_active`, texte `accent_primary` (ou `text_primary`) | Explorateur de documents, hiérarchie de dossiers de personas. |
| **Cases à Cocher & Radios** | `QCheckBox`, `QRadioButton` | Décoché<br>Hover<br>Coché (`:checked`) | Fond `bg_input`, bordure `border_color`<br>Bordure `accent_primary`<br>Fond `accent_primary`, bordure `accent_primary` | Sélections multiples, options de prompt, filtres d'état. |
| **Curseurs & Sliders** | `QSlider` | Gorge (groove)<br>Partie active (sub-page)<br>Curseur (handle)<br>Handle Hover | `bg_input`, bordure `border_color`<br>`accent_primary`<br>`#ffffff`, bordure 2px `accent_primary`<br>`accent_hover` | Réglages continus (Température LLM, Max Tokens, Ratios). |
| **Barres de Défilement** | `QScrollBar:vertical`, `QScrollBar:horizontal` | Fond rail<br>Curseur (handle)<br>Handle Hover | `transparent`, largeur 10px<br>`border_color`, `radius: 5px`<br>`text_muted` | Ascenseurs discrets et harmonieux pour le contenu long. |
| **Badges Sémantiques** | `Badge` | Variantes `neutral`, `success`, `warning`, `danger`, `info` | Fond `bg_active` ou teinté sémantique (`color_green`, `color_yellow`, `color_red`, `color_blue`), texte contrasté | Étiquettes d'état (ON/OFF, Validé, Conflit, Erreur, IA). |
| **Fenêtres & Modales** | `QDialog`, `QMainWindow` | Fond de fenêtre<br>En-tête modale | `bg_main`<br>`bg_panel`, bordure basse `border_color` | Paramètres généraux, History Time Machine, Modale de fusion. |
| **Disposition Fluide & Wrap** | `FlowLayout`, `FlowWidget` | Marges & Espacements | `h_spacing: 6px`, `v_spacing: 6px` | Disposition fluide avec passage à la ligne automatique et propagation `heightForWidth` pour les pilules, tags et badges dans les `QScrollArea`. |
| **Barres d'Actions Responsives** | `ResponsiveTopActionBar` | Arrière-plan<br>Bordure<br>Boutons compacts | `bg_sidebar`<br>`1px solid border_color`, `border-top: 1px solid border_light`<br>Bascule automatique en icônes seules sous 480px | Barre supérieure compacte (38px) avec titre et actions qui s'adaptent dynamiquement aux petits écrans (13" MacBook). |
| **Éditeurs de Code Professionnels** | `CodeEditorWithGutter`, `NativeCodeEditor`, `LineNumberArea`, `LintStatusBar` | Gouttière numéros<br>Ligne courante<br>Linter soulignements<br>Barre statut linter | `bg_sidebar`, bordure droite `border_color`, numéros `text_muted` / `accent_primary`<br>Fond `bg_hover`<br>`color_red` (erreurs) / `color_yellow` (warnings) en `WaveUnderline`<br>Fond `bg_sidebar`, bordure haute `border_color`, pastilles sémantiques | Éditeur HTML/CSS avec gouttière native QPainter, pastilles de couleur interactives, auto-fermeture de balises (<test> -> <test></test>), autocomplétion contextuelle (`{{...}}`, `<...>`, CSS) et formateur de code. |
| **Coloration Syntaxique Code** | `HTMLSyntaxHighlighter`, `CSSSyntaxHighlighter` | Balises & Sélecteurs<br>Attributs & Propriétés<br>Chaînes & Textes<br>Mots-clés & Conditions<br>Variables & Champs Anki<br>Commentaires<br>Nombres & Unités | `syntax_tag`<br>`syntax_attr`<br>`syntax_string`<br>`syntax_keyword`<br>`syntax_variable`<br>`syntax_comment`<br>`syntax_number` | Tokens thématiques pour la coloration syntaxique temps réel dans les éditeurs HTML / Jinja2 / CSS. |
| **Pastilles & Formateurs de Code** | `CSSFormatter`, `HTMLFormatter`, `extract_colors_from_text` | Pastilles de couleur gouttière<br>Bouton Formater (barre statut)<br>Raccourcis | Rendu dynamique de la couleur réelle avec bordure 1px<br>Bouton compact `bg_panel`, hover `accent_primary`<br>`Ctrl+Alt+L` (JetBrains), `Ctrl+Shift+I`, `Shift+Alt+F` | Aperçu visuel immédiat des couleurs hex/rgb/hsl et formateur automatique réordonnant indentation, sauts de ligne et espacements. |

---

# 🌓 PARTIE 2 : Architecture Bivalente Sombre 🌙 / Clair ☀️

L'interface repose sur une séparation claire entre :
1. **Le Mode d'Apparence :** 🌙 Sombre ou ☀️ Clair.
2. **La Famille de Thème :** L'une des 12 identités graphiques d'AnkiForge.

Lorsqu'un utilisateur change de mode ou de thème :
* Le `StyleEngine` bascule vers la variante (sombre ou claire) de la famille active via `set_color_mode()` ou `toggle_color_mode()`.
* `DesignTokens` est réassigné à chaud.
* La palette Qt (`QPalette`) et la feuille de style QSS globale sont réinjectées sur `QApplication`.
* Les ombres portées s'adaptent dynamiquement (45% d'opacité en mode sombre, 12% en mode clair).

---

# 🎨 PARTIE 3 : Les 12 Familles de Thèmes Bivalentes (24 Thèmes)

| Famille | Identifiant | Icône | Description | 🌙 Variante Sombre | ☀️ Variante Claire |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **JetBrains IDE** | `jetbrains` | `ph.code` | Style IDE haute densité avec accent Indigo vif. | `JETBRAINS_DARK` (`ide`) | `JETBRAINS_LIGHT` (`jetbrains_light`) |
| **Modern SaaS Emerald** | `emerald` | `ph.chart-line-up` | Tableau de bord contemporain avec accent vert Émeraude. | `EMERALD_DASHBOARD` (`dashboard`) | `EMERALD_LIGHT` (`emerald_light`) |
| **Cyber Glass** | `glassmorphism` | `ph.sparkle` | Verre dépoli translucide et reflets Améthyste. | `CYBER_GLASS` (`glassmorphism`) | `CYBER_GLASS_LIGHT` (`cyber_glass_light`) |
| **Apple macOS Native** | `macos` | `ph.apple-logo` | Épure et élégance Apple avec accent Bleu Cupertino. | `MACOS_DARK` (`macos`) | `MACOS_LIGHT` (`macos_light`) |
| **Synthwave '84** | `synthwave` | `ph.sun-horizon` | Rétro-futurisme néon et ambiance coucher de soleil. | `SYNTHWAVE_84` (`synthwave_84`) | `SYNTHWAVE_LIGHT` (`synthwave_light`) |
| **Monokai Pro** | `monokai` | `ph.lightning` | Contraste précis de référence avec accent Or / Ambre. | `MONOKAI_PRO` (`monokai_pro`) | `MONOKAI_LIGHT` (`monokai_light`) |
| **Catppuccin Pastel** | `catppuccin` | `ph.coffee` | Harmonie pastel apaisante (Mocha & Latte). | `CATPPUCCIN_MOCHA` (`catppuccin_mocha`) | `CATPPUCCIN_LATTE` (`catppuccin_latte`) |
| **Nord Arctic** | `nord` | `ph.snowflake` | Clarté scandinave ardoise et cyan (Polar & Snow Storm). | `NORD_POLAR` (`nord_polar`) | `NORD_LIGHT` (`nord_light`) |
| **Dracula / Alucard** | `dracula` | `ph.moon-stars` | Style gothique vampire sombre et brume mauve claire. | `DRACULA_OFFICIAL` (`dracula_official`) | `DRACULA_LIGHT` (`dracula_light`) |
| **Tokyo Night / Day** | `tokyo` | `ph.buildings` | Lumières tokyoïtes nocturnes et éclat matinal. | `TOKYO_NIGHT` (`tokyo_night`) | `TOKYO_DAY` (`tokyo_day`) |
| **Solarized** | `solarized` | `ph.sun` | Précision colorimétrique éprouvée bleu canard et parchemin. | `SOLARIZED_DARK` (`solarized_dark`) | `SOLARIZED_LIGHT` (`solarized_light`) |
| **One Pro Atom** | `one_pro` | `ph.atom` | Le standard Atom/VSCode neutre et équilibré. | `ONE_DARK_PRO` (`one_dark_pro`) | `ONE_LIGHT_PRO` (`one_light_pro`) |

---

# 📐 PARTIE 4 : Les Dispositions d'Interface (Layouts)

AnkiForge supporte **4 architectures de disposition** interchangeables à chaud (`LayoutManager`) :

1. **Concept IDE (`ide`) :** Barre latérale rétractable (68px à 260px), multi-fenêtrage détachable (`IdePanel`), omnibox `Ctrl+K`.
2. **Concept Dashboard (`dashboard`) :** Présentation en grille réactive sans barre latérale permanente, cartes d'actions rapides.
3. **Concept Glassmorphism (`glassmorphism`) :** Navigation par pilules flottantes, conteneurs effet verre givré.
4. **Concept macOS (`macos`) :** Barre supérieure compacte (54px) avec sélecteur segmenté horizontal.

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
| **Interrupteurs & Lignes d'Options** | `ToggleSwitch`, `OptionToggleRow` | Track OFF / ON<br>Bordure / Thumb<br>Carte hover | `bg_input` / `accent_primary`<br>`border_color` / `#ffffff`<br>Fond `bg_panel`, hover `border-color: accent_primary` | Toggles modernes style iOS/macOS pour réglages, vision multimodale et validation automatique. |
| **Curseurs & Sliders** | `QSlider` | Gorge (groove)<br>Partie active (sub-page)<br>Curseur (handle)<br>Handle Hover | `bg_input`, bordure `border_color`<br>`accent_primary`<br>`#ffffff`, bordure 2px `accent_primary`<br>`accent_hover` | Réglages continus (Température LLM, Max Tokens, Ratios). |
| **Barres de Défilement** | `QScrollBar:vertical`, `QScrollBar:horizontal` | Fond rail<br>Curseur (handle)<br>Handle Hover | `transparent`, largeur 10px<br>`border_color`, `radius: 5px`<br>`text_muted` | Ascenseurs discrets et harmonieux pour le contenu long. |
| **Badges Sémantiques** | `Badge` | Variantes `neutral`, `success`, `warning`, `danger`, `info` | Fond `bg_active` ou teinté sémantique (`color_green`, `color_yellow`, `color_red`, `color_blue`), texte contrasté | Étiquettes d'état (ON/OFF, Validé, Conflit, Erreur, IA). |
| **Fenêtres & Modales** | `QDialog`, `QMainWindow` | Fond de fenêtre<br>En-tête modale | `bg_main`<br>`bg_panel`, bordure basse `border_color` | Paramètres généraux, History Time Machine, Modale de fusion. |
| **Disposition Fluide & Wrap** | `FlowLayout`, `FlowWidget` | Marges & Espacements | `h_spacing: 6px`, `v_spacing: 6px` | Disposition fluide avec passage à la ligne automatique et propagation `heightForWidth` pour les pilules, tags et badges dans les `QScrollArea`. |
| **Barres d'Actions Responsives** | `ResponsiveTopActionBar` | Arrière-plan<br>Bordure<br>Boutons compacts | `bg_sidebar`<br>`1px solid border_color`, `border-top: 1px solid border_light`<br>Bascule automatique en icônes seules sous 480px | Barre supérieure compacte (38px) avec titre et actions qui s'adaptent dynamiquement aux petits écrans (13" MacBook). |
| **Éditeurs de Code Professionnels** | `CodeEditorWithGutter`, `NativeCodeEditor`, `LineNumberArea`, `LintStatusBar` | Gouttière numéros<br>Ligne courante<br>Linter soulignements<br>Barre statut linter | `bg_sidebar`, bordure droite `border_color`, numéros `text_muted` / `accent_primary`<br>Fond `bg_hover`<br>`color_red` (erreurs) / `color_yellow` (warnings) en `WaveUnderline`<br>Fond `bg_sidebar`, bordure haute `border_color`, pastilles sémantiques | Éditeur HTML/CSS avec gouttière native QPainter, pastilles de couleur interactives, auto-fermeture de balises (<test> -> <test></test>), autocomplétion contextuelle (`{{...}}`, `<...>`, CSS) et formateur de code. |
| **Éditeurs de Champs de Notes & IntelliSense** | `NoteFieldEditorWidget`, `NoteFieldTextEdit`, `NoteKaTeXHighlighter`, `NoteKaTeXCompleter` | Gouttière compacte<br>Coloration KaTeX/HTML/Cloze<br>Popup autocomplétion<br>En-tête pliable | `bg_panel`, bordure droite `border_color`<br>HTML (`#38bdf8`), LaTeX (`#34d399`), Jinja2 (`#fbbf24`), Cloze (`#c084fc`)<br>Popup `bg_panel`, hover `bg_active`<br>`bg_panel`, texte `text_primary` / `accent_primary` | Champs d'édition 100% natifs Qt pour les modèles de cartes Anki avec IntelliSense (LaTeX sur `\`, HTML sur `<`, champs/Cloze sur `{{`), auto-fermeture de balises et raccourcis universels. |
| **Barre d'Outils d'Édition Extensible** | `EditorToolbarWidget`, `ToolbarAction` | Fond barre<br>Boutons d'action<br>Séparateurs verticaux | `bg_panel`, bordure `border_color`<br>`IconButton` 24px avec infobulle enrichie et raccourci<br>`1px solid border_color` | Barre d'outils unifiée au sommet de l'éditeur agissant sur le champ actif (Gras, Italique, Souligné, Barré, Code, Math, Cloze, Liens, Images, Listes) avec API d'extension publique `register_action()`. |
| **Machine à Remonter le Temps** | `TimeMachineDialog`, `DiffViewerWidget` | Timeline latérale<br>Diff comparatif<br>Aperçu rendu | `bg_panel`, items avec bordure active `accent_primary`<br>Fond `bg_input`, ajouts `rgba(16, 185, 129, 0.15)` (+), suppressions `rgba(239, 68, 68, 0.15)` (-)<br>`CardPreviewWidget` intégré | Modale moderne d'historique de versions avec timeline chronologique, diff interactif champ par champ et bouton de restauration 1-clic mettant à jour la BDD et l'éditeur en direct. |
| **Disposition Progressive Disclosure** | `EditionView`, `main_splitter (Vertical)`, `nav_ribbon` | Tableau haut (Pleine largeur)<br>Ruban compact (30px)<br>Éditeur / Preview bas (50/50) | Fond `bg_main`, tableau avec texte épuré sans HTML brut et tags colorés<br>Ruban `bg_panel` avec boutons Précédent/Suivant et dépliage<br>Fond `bg_sidebar`, split 50/50 champs et `CardPreviewWidget` | Architecture supérieure/inférieure ergonomique combinant tableau pleine largeur et repliement 1-clic en ruban de navigation (30px) libérant 100% de la hauteur utile pour l'éditeur de champs et le rendu live. |
| **Smart Merge 3 Panneaux** | `SmartMergeDialog`, `SmartMergeView`, `ConflictFieldRow` | Panneau Local (Gauche)<br>Panneau Fusionné (Centre)<br>Panneau Entrant (Droite)<br>Badge similarité | Fond `rgba(239, 68, 68, 0.06)`, bordure rouge (30%)<br>Fond `bg_input`, bordure `accent_primary`<br>Fond `rgba(16, 185, 129, 0.06)`, bordure verte (30%)<br>Badge sémantique vert/jaune/rouge selon ratio C-Bridge | Dialogue de résolution de conflits de contenu selon la Règle 11 avec transfert par champ `[◀ Local]` / `[▶ Entrant]` et pagination de conflits. |
| **Dialogues d'Importation & Exportation** | `ImportDialog`, `ImportDropZone`, `ExportDialog` | Zone Glisser-Déposer<br>Options & Radios<br>Boutons d'action | Fond `bg_input`, bordure tiretée `border_color`, hover `accent_primary`<br>Cadre `bg_panel`, bordure `border_color`<br>`PrimaryButton` avec icônes Phosphor | Modales unifiées pour l'ingestion (.apkg, .colpkg, .txt) et l'exportation sélective avec médias Zstandard. |
| **Coloration Syntaxique Code** | `HTMLSyntaxHighlighter`, `CSSSyntaxHighlighter` | Balises & Sélecteurs<br>Attributs & Propriétés<br>Chaînes & Textes<br>Mots-clés & Conditions<br>Variables & Champs Anki<br>Commentaires<br>Nombres & Unités | `syntax_tag`<br>`syntax_attr`<br>`syntax_string`<br>`syntax_keyword`<br>`syntax_variable`<br>`syntax_comment`<br>`syntax_number` | Tokens thématiques pour la coloration syntaxique temps réel dans les éditeurs HTML / Jinja2 / CSS. |
| **Pastilles & Formateurs de Code** | `CSSFormatter`, `HTMLFormatter`, `extract_colors_from_text` | Pastilles de couleur gouttière<br>Bouton Formater (barre statut)<br>Raccourcis | Rendu dynamique de la couleur réelle avec bordure 1px<br>Bouton compact `bg_panel`, hover `accent_primary`<br>`Ctrl+Alt+L` (JetBrains), `Ctrl+Shift+I`, `Shift+Alt+F` | Aperçu visuel immédiat des couleurs hex/rgb/hsl et formateur automatique réordonnant indentation, sauts de ligne et espacements. |
| **Graphique d'Activité 7 Jours** | `ActivityChartWidget` | Barres créées (accent)<br>Barres modifiées (bleu)<br>Rails colonnes<br>Labels jours | `accent_primary`<br>`color_blue`<br>`border_light` (hover: `bg_hover`)<br>`text_muted` (hover: `accent_primary`), `font_size_small` | Rendu 100% natif QPainter sans dépendance lourde, affichant le volume quotidien de cartes créées vs modifiées avec infobulle interactive au survol. |
| **Diagnostics & Actions Proactives** | `ProactiveDiagnosticsWidget`, `DiagnosticCardWidget` | Cartes d'alertes<br>Bordures sémantiques<br>Boutons d'action | `bg_panel` (hover: `bg_hover`)<br>`color_yellow` (warning), `color_red` (danger), `border_color` (info)<br>`PrimaryButton` / `SecondaryButton` compacts | Cockpit de supervision proactive avec détection automatique des violations Wozniak, lacunes RAG, doublons et surcoûts avec redirection 1-clic. |
| **Menu de Notifications & Diagnostics** | `NotificationMenuPopup`, `NotificationItemWidget` | Menu Popup<br>Badges de sévérité<br>Bouton cloche | `bg_panel`, bordure `border_color`, ombre portée `shadow_glass_blur`<br>`bg_active`, pastille colorée<br>`IconButton` avec infobulle dynamique | Menu déroulant rattaché à la cloche TopBar listant les anomalies actives avec pastille de comptage et routage interactif vers les vues et sous-onglets. |
| **Gestionnaire d'Addons & Extensions** | `AddonManagerWidget`, `AddonDetailWidget`, `AddonConfigForm` | Liste addons<br>Formulaire dynamique<br>Badges de statut<br>Documentation | `bg_panel`, bordure `border_color`<br>Champs `bg_input`, bordures `border_color`<br>`Badge` sémantique (`success`, `neutral`, `danger`)<br>`bg_panel`, texte `text_primary` | Vue de gestion des extensions sous Nuitka avec formulaire interactif généré automatiquement depuis `config.json`, visualiseur de doc `config.md` et installateur ZIP. |
| **Historique des Personas (Time Machine IA)** | `PersonaHistoryDialog`, `PersonaPromptDiffViewer`, `PersonaVersionItemWidget` | Timeline versions<br>Diff de prompt<br>Paramètres & Métas | `bg_panel`, items avec bordure `border_light` et hover `accent_primary`<br>Fond `bg_input`, ajouts `rgba(16, 185, 129, 0.15)` (+), suppressions `rgba(239, 68, 68, 0.15)` (-)<br>Tableau de métas `bg_input` | Modale d'historique de versions pour les Personas/Agents IA avec comparaison de diffs colorés et restauration en 1 clic. |
| **Modèles Communautaires & Paquets .afmodel** | `ModelExportDialog`, `ModelImportDialog`, `StarterPackDialog`, `StarterModelCardWidget` | Formulaire export<br>Aperçu import WebEngine<br>Catalogue Starter Pack | `bg_panel`, bordure `border_color`<br>Splitter 50/50 avec `CardPreviewWidget`<br>Grille responsive de cartes avec badges `accent_primary` | Suite modale complète pour exporter, inspecter et importer des gabarits de cartes (.afmodel, .json) avec résolution de collisions de styles et catalogue de 4 packs intégrés. |
| **Boutons & Pastilles Jinja2 (Pipelines)** | `TagPillButton` | Fond teinté<br>Bordure pill<br>Texte monospace | `field` (indigo), `cloze` (violet), `warning` (ambre), `success` (émeraude), `info` (cyan)<br>`border-radius: 12px`, `padding: 1px 10px`<br>`font_code`, hover `1.5px solid accent_primary` | Pastilles d'insertion rapide de snippets de variables Jinja2 avec retours visuels et disposition fluide `FlowWidget`. |
| **Sous-Onglets IDE & Navigation Interne** | `SubTabButton` | Inactif<br>Hover<br>Actif (`is_active=True`) | `transparent`, texte `text_secondary`<br>Fond `bg_hover`, texte `text_primary`<br>Fond `bg_panel`, texte `text_primary`, bordure basse `2px solid accent_primary` | Boutons d'onglets compacts (32px) avec icônes Phosphor pour la navigation dans l'inspecteur d'étape et les panneaux modulaires. |
| **Bannière de Flux DAG & Diagnostic** | `DagFlowOverviewWidget`, `StatusPillBadge` | Nœuds d'étapes<br>Chevrons de liaison<br>Badge de santé DAG | Fond `bg_input` (actif: `rgba(99, 102, 241, 0.15)`), bordure `border_color`<br>Icône Phosphor `ph.caret-right` (12x12)<br>Badge pill (`border-radius: 9999px`) vert (Valide) ou rouge (Alerte) | Visualisation interactive du graphe orienté acyclique avec navigation instantanée par clic sur nœud et linter de variables. |
| **Cartes d'Étapes de Workflow (Maître)** | `StepItemWidget`, `InlineInsertButton` | Ligne 1 : En-tête<br>Ligne 2 : I/O & Actions<br>Sélectionné (`is_selected=True`)<br>Bouton d'insertion `+` | Poignée `dots-six-vertical` + Icône Phosphor + Titre bold + Badge de rôle pill<br>Flux `📥 in ➔ 📤 out` monospace + boutons compacts (20px) `▲`, `▼`, `🗑`<br>Fond `bg_active`, `border-left: 3px solid accent_primary`<br>Bouton rond 20px centré `+` avec trait pointillé | Ligne de liste de workflow compacte (2 lignes ergonomiques) sans débordement horizontal avec manipulation drag/reorder/delete. |
| **Catalogue & Tuiles d'Étapes** | `StepPickerDialog`, `StepPickerCard` | Recherche rapide<br>Tuile d'étape / Agent<br>Badges de catégorie | `GlowLineEdit` avec loupe intégrée<br>Fond `bg_panel`, bordure `border_color`, hover `border-color: accent_primary`<br>`Badge` pill stylé selon le rôle (LLM, RAG, Parallèle, Pause, Outil) | Modale de sélection d'étape en 2 colonnes (Agents IA vs Actions Système) avec filtrage instantané temps réel. |
| **Bannière KPIs de Branche A/B** | `BranchKpiWidget`, `apply_pill_style` | Titre Branche<br>Métriques (temps, cartes, tokens, coût)<br>Badge Vainqueur (Winner)<br>Statut | Capsule pill teinté (violet `#8b5cf6` pour A, cyan `#06b6d4` pour B)<br>Labels monospace `text_secondary` avec icônes Phosphor (`ph.timer`, `ph.cards`, `ph.coins`, `ph.currency-dollar`)<br>Badge pill vert (`color_green`) `⚡ Plus rapide` / `💰 Plus économique`<br>Badge pill `bg_input` / `border_color` | Bandeau structuré en 2 lignes (En-tête de branche + Ruban de métriques) affichant en temps réel les performances comparatives avec détection du gagnant. |
| **Cockpit & Tiroirs du Laboratoire A/B** | `ABTestsView`, `SourceBox`, `AdvDrawer` | Cockpit 2 lignes<br>Tiroir texte source repliable<br>Presets d'exemples rapides<br>Tiroir paramètres d'inférence | `bg_panel`, bordure `border_color`, sélecteurs `StyledComboBox`<br>Zone `bg_input`, compteur de caractères et toggle `ph.caret-up`<br>`TagPillButton` interactifs (Médical, Maths, Droit, Anglais)<br>Curseurs `QSlider` (Température, Tokens) masquables | Laboratoire comparatif A/B haute performance (Modèle vs Modèle, Prompt vs Prompt, Pipeline vs Pipeline) avec synchronisation de vue 1-clic et import direct dans la Forge. |
| **Centre de Configuration & Paramètres** | `SettingsModal`, `SettingsCard`, `SettingsNavButton`, `PasswordLineEdit`, `StorageMetricCard`, `AnkiSyncTab`, `StorageMaintenanceTab` | Fenêtre 960x640px<br>Cartes avec scoping QSS strict<br>Boutons sidebar avec bordure accent<br>Champs mot de passe avec œil<br>Cartes métriques de stockage | `bg_main`, `bg_panel`, bordure `border_color`<br>`QFrame#SettingsCard` évitant les cascades parasites<br>`border-left: 3px solid accent_primary`<br>`PasswordLineEdit` avec bouton toggle `ph.eye`<br>Statistiques réelles (BDD SQLite, Médias, Time Machine) avec actions VACUUM, nettoyage orphelins et snapshots | Fenêtre de paramètres modulaire en 5 onglets thématiques (Général, Moteurs IA, Anki & Synchro, Maintenance, Extensions) réactive à chaud aux 24 thèmes sombres/clairs. |

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

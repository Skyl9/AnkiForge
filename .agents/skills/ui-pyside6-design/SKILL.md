---
name: ui-pyside6-design
description: >-
  Expert en développement, refactorisation et styling des composants d'interface PySide6 / Qt pour AnkiForge. Conçoit et intègre les widgets selon DESIGN.md (StyleEngine, DesignTokens, 12 thèmes, 4 layouts), gère le fenêtrage JetBrains (IdePanel), applique l'i18n ADR 0013 (tr) et assure les tests headless pytest-qt.
  Use when the user asks to "créer un widget", "modifier l'UI", "refactorer une vue Qt", "appliquer un thème", "styliser un composant", "ajouter un layout", "traduire l'interface", "VirtualTableView", or develops or modifies PySide6 components.
  When NOT to use: Do not use for static design system auditing only (use audit-design-ui) or offscreen visual snapshot capture only (use ui-screenshot).
---

# 🎨 Développement UI & Composants PySide6 — AnkiForge

En tant qu'**Architecte Frontend PySide6 / Qt**, tu développes, refactorises et intègres les interfaces de l'application en respectant strictement l'architecture découplée, le design system et l'isolation des tests headless.

> **Références de référence** :
> - `DESIGN.md` : Source unique de vérité du design system, matrice des tokens sémantiques et inventaire des 12 thèmes et 4 layouts.
> - `docs/adr/0013-internationalisation-qt-linguist.md` : Règles impératives d'internationalisation Qt Linguist (`tr()`).
> - `docs/Dossier_architecture/07_inventaire_composants_ui.md` : Inventaire des widgets, dialogues et panneaux.

## 1. Règles Cardinales de Conception UI

1. **Zéro couleur ou style codé en dur** :
   - Tout style passe par `StyleEngine.generate_stylesheet()` et les tokens sémantiques de `DesignTokens` (`bg_primary`, `border_focus`, `text_secondary`, etc.).
   - Tout nouveau composant doit être déclaré dans `DESIGN.md` et stylé dans `StyleEngine`.
2. **Internationalisation stricte (`ADR 0013`)** :
   - Toute chaîne affichée à l'utilisateur passe par `self.tr("...")` (dans un `QObject`) ou `tr("...")` (ailleurs).
   - **`tr(f"...")` est strictement interdit** (l'expression est évaluée avant l'appel et n'entre pas au catalogue).
   - Les valeurs interpolées utilisent les marqueurs Qt Linguist : `tr("Enregistré : %1/%2", faits, total)`.
3. **Multi-fenêtrage & Layouts** :
   - Panneaux détachables style JetBrains via `IdePanel`.
   - Compatibilité totale avec les 4 dispositions d'interface (`ide`, `macos`, `dashboard`, `glassmorphism`).
4. **Synchronisation d'arborescence (`QTreeWidget`)** :
   - Pour les cellules avec widget personnalisé : synchroniser explicitement `item.setCheckState()` et `widget.set_check_state()`.
   - Pour les propagations hiérarchiques, mettre à jour les parents en parcours inverse (`reversed(all_items())`).
5. **Héritage de style QSS & isolation des bordures (Vigilance critique)** :
   - Dans Qt StyleSheet, les sélecteurs de conteneurs (ex: `QFrame`, `QWidget`, ou sélecteurs sans sélecteur d'enfant direct `>`) se propagent en cascade à tous les enfants imbriqués (`QLabel`, `QFrame`, boutons).
   - **Garde-fou bordures** : ne jamais appliquer de bordure générique (`border: 1px solid/dashed ...`) sur un conteneur sans ciblage strict par `setObjectName` (`#mon_widget`), sans sélecteur strict d'enfant direct (`#conteneur > QWidget`), ou sans réinitialiser explicitement `border: none;` sur les enfants pour éviter l'héritage parasite de bordures (ex: retour d'expérience `AgentsView`).
6. **Cycle de vie des conteneurs dynamiques à défilement (`QScrollArea` & `QVBoxLayout`)** :
   - Ne **JAMAIS** ajouter de `addStretch()` à la construction d'un layout scrollable dynamique alimenté à chaud. Le stretch se retrouverait à l'index 0 et repousserait les widgets ajoutés vers le bas.
   - Pour vider intégralement un layout dynamique sans widgets orphelins résiduels :
     ```python
     while layout.count() > 0:
         item = layout.takeAt(0)
         w = item.widget()
         if w:
             w.deleteLater()
     ```
   - Ajouter les widgets/cartes, puis insérer `layout.addStretch()` **à la toute fin** pour maintenir l'alignement vers le haut (*top-aligned*).
7. **Puits d'affichage i18n & Symboles typographiques (`ADR 0013`)** :
   - Tout puits d'affichage (`QLabel`, `QPushButton`, etc.) recevant une chaîne constante (même un symbole comme `➔` ou `•`) doit être wrappé dans `tr()` ou instancié sans argument puis configuré via `.setText("...")` pour satisfaire le test d'audit `test_every_display_sink_wraps_its_literal`.
   - Lors de l'ajout ou de la modification de chaînes `tr()`, toujours exécuter `uv run python script/extract_translations.py` pour régénérer et compiler les catalogues `.ts` / `.qm` avant le passage de la porte canonique `script/verify.py`.
8. **Interdiction stricte des émojis dans l'UI** :
   - Ne **JAMAIS** préfixer ou décorer les boutons (`PrimaryButton`, `SecondaryButton`, `QPushButton`), cartes ou en-têtes avec des émojis texte (ex: `📖 Ouvrir`, `⌨️ Raccourcis`).
   - Utiliser exclusivement les icônes Phosphor vectorielles (`load_phosphor_icon("ph.<nom>", color=...)`) ou un libellé textuel sobre traduit sans symbole superflu.
9. **CSS embarqué dans `QTextBrowser` et `QTextDocument`** :
   - Les styles HTML/CSS injectés dans les documents textuels doivent dériver rigoureusement de `DesignTokens` via interpolation (ex: `background-color: {DesignTokens.BG_PANEL};`, `border: 1px solid {DesignTokens.BORDER_COLOR};`).
   - Interdiction formelle de coder des couleurs hexadécimales en dur (ex: `#181825`, `#ffffff`) dans ces blocs.
10. **Contextes d'internationalisation dans les méthodes de classe (`@classmethod`)** :
    - Dans une `@classmethod` d'un composant Qt (`QDialog`, `QWidget`), utiliser `cls.tr("...")` ou la fonction racine `tr("...")`.
    - Ne **JAMAIS** utiliser `instance.tr("...")` sur une variable locale : cela corrompt le contexte Linguist en nommant le contexte d'extraction d'après le nom de variable (`<name>dlg</name>`) au lieu de la classe réelle.

## 2. Composants Clés & Bonnes Pratiques

- **`VirtualTableView`** : vue tableau optimisée pour les gros volumes de notes, sélection étendue (`ExtendedSelection`), synchronisation stricte entre surlignage et coches de la colonne 0.
- **Workers asynchrones** : aucune opération lourde ou réseau sur le thread principal de rendu Qt. Déléguer systématiquement à un `QThread` ou au pool de workers (`QThreadPool`).
- **Accessibilité & Navigation clavier** : gérer `:focus`, `:hover` et les raccourcis clavier standards.
- **Lecteur de documentation embarqué léger sans Chromium (`DocReaderDialog`)** : pour afficher des guides Markdown riches intégrant des images SVG/PNG relatives sans le poids de WebEngine, alimenter un `QTextBrowser` et définir impérativement l'URL de base du document :
  ```python
  text_browser.document().setBaseUrl(QUrl.fromLocalFile(str(base_dir) + "/"))
  ```
- **Vigilance modales à onglets transverses (`SettingsModal`)** : toute addition ou modification de la liste d'onglets modifie la valeur de `stacked_widget.count()` (par ex. 9 onglets en production, 10 en mode développement). Mettre à jour de manière coordonnée l'ensemble des tests transverses de fenêtres et de galeries (`test_settings_modal.py`, `test_dialog_gallery.py`, `test_addon_settings.py`).

## 3. Discipline de Test (`pytest-qt`)

- Tous les tests UI s'exécutent en mode **100% headless** (`QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`).
- Utiliser systématiquement `qtbot` pour simuler les clics et interactions utilisateur, et annoter explicitement `qtbot: QtBot` (`from pytestqt.qtbot import QtBot`).
- Nettoyage obligatoire de chaque widget via la fixture `cleanup_qt_widgets` de `conftest.py`.
- **Attente impérative des workers asynchrones** : tout test pilotant un widget qui lance un thread (`QThread`, worker d'arrière-plan) doit impérativement attendre sa fin (`if widget.worker and widget.worker.isRunning(): widget.worker.wait()` ou `qtbot.waitUntil(...)`) avant la fin du test, pour empêcher tout verrouillage SQLite concurrent (`database table is locked: sqlite_master`) lors du teardown de `mock_db`.
- **Zéro test de snapshot visuel instable** : tester la logique métier, les signaux/slots et la validation des formulaires.

## When NOT to use this skill

- L'objectif est uniquement d'auditer statiquement la conformité au design system sans coder → utiliser `audit-design-ui`.
- L'objectif est de capturer une capture d'écran offscreen d'une vue → utiliser `ui-screenshot`.
- La tâche concerne un service backend pur ou un parseur sans interface graphique → utiliser le skill de service dédié.

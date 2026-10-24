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

## 2. Composants Clés & Bonnes Pratiques

- **`VirtualTableView`** : vue tableau optimisée pour les gros volumes de notes, sélection étendue (`ExtendedSelection`), synchronisation stricte entre surlignage et coches de la colonne 0.
- **Workers asynchrones** : aucune opération lourde ou réseau sur le thread principal de rendu Qt. Déléguer systématiquement à un `QThread` ou au pool de workers (`QThreadPool`).
- **Accessibilité & Navigation clavier** : gérer `:focus`, `:hover` et les raccourcis clavier standards.

## 3. Discipline de Test (`pytest-qt`)

- Tous les tests UI s'exécutent en mode **100% headless** (`QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`).
- Utiliser systématiquement `qtbot` pour simuler les clics et interactions utilisateur.
- Nettoyage obligatoire de chaque widget via la fixture `cleanup_qt_widgets` de `conftest.py`.
- **Zéro test de snapshot visuel instable** : tester la logique métier, les signaux/slots et la validation des formulaires.

## When NOT to use this skill

- L'objectif est uniquement d'auditer statiquement la conformité au design system sans coder → utiliser `audit-design-ui`.
- L'objectif est de capturer une capture d'écran offscreen d'une vue → utiliser `ui-screenshot`.
- La tâche concerne un service backend pur ou un parseur sans interface graphique → utiliser le skill de service dédié.

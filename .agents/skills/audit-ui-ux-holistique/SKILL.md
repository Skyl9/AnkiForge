---
name: audit-ui-ux-holistique
description: Audit transversal Senior UI/UX et architecture front PySide6 pour AnkiForge. Use when the user asks to critique, audit, review, or improve UI/UX across multiple views, dialogs, widgets, or screenshots, detect design drift against DESIGN.md, evaluate visual hierarchy and cognitive load, or generate actionable Obsidian Kanban tickets from a holistic UI/UX review.
---

# Audit UI/UX Holistique & Générateur de Tickets Obsidian

Effectue une revue critique de niveau Senior UI/UX Designer & Architecte PySide6 en croisant simultanément plusieurs vues, dialogues, composants et captures d'écran d'AnkiForge, puis convertit les constats en tickets atomiques conformes au vault Obsidian du dépôt.

## ⛔ Ne PAS utiliser ce skill si...

- L'utilisateur demande d'implémenter directement un composant ou de corriger un bug unique déjà spécifié (utiliser `ui-pyside6-design` ou `implement`).
- La demande porte sur un audit purement backend, base de données Peewee, RAG ou orchestration DAG sans impact sur l'interface graphique.
- La tâche consiste à vérifier l'intégrité documentaire post-feature (utiliser `mise-a-jour-metadonnees`).

## Étapes d'exécution

### 1. Collecte multi-surfaces (Interdiction de la vue en tunnel)

Ne jamais auditer un fichier isolé sans son contexte d'intégration. Pour chaque parcours ou groupe d'écrans soumis :

- Comparer au moins 2 à 3 fichiers liés : la vue parente (`src/ankiforge/ui/views/...`), ses sous-widgets ou modales (`dialogs/`, `widgets/`), son `ViewModel` (`ui/viewmodels/`) et les composants partagés (`ui/components/`).
- Si des captures d'écran (`script/capture_*.py`) sont fournies, croiser systématiquement le rendu visuel réel avec le code source PySide6/QSS.
- Consulter `references/grille-audit-holistique.md` pour appliquer les 6 axes d'inspection Senior UI/UX.

### 2. Inspection selon les 6 axes systémiques AnkiForge

Passer les éléments inspectés au crible des 6 axes suivants :

1. **Dérive du Design System (`DESIGN.md` & `StyleEngine`)** : Traquer les couleurs hexadécimales/`rgba()` en dur, les `QPushButton` ou `QComboBox` natifs non typés, les `border`/`background` locaux qui écrasent les états `:hover`/`:focus` du QSS global, et les composants réinventés localement au lieu d'utiliser `ui/components/` (`SegmentedTabBar`, `FilterChipButton`, `Badge`, `ElidedLabel`, `StyledMenu`).
2. **Hiérarchie visuelle & Charge cognitive** : Repérer l'effet "cockpit d'avion" (trop d'actions primaires en concurrence, absence de `CollapsibleSection` ou de divulgation progressive, empilement de cadres `QFrame` imbriqués créant du bruit visuel au lieu d'utiliser la typographie et l'espacement).
3. **Échelle d'espacement, Alignement optique & Responsivité** : Vérifier l'harmonie des `setContentsMargins` et `setSpacing`, l'alignement sur un même axe optique (ex: boutons compacts 32px `apply_compact_style()`), l'absence de `minimumWidth > 500px` bloquant les écrans 13" (820x560), l'usage d'`ElidedLabel` et le comportement des `QSplitter`.
4. **États du cycle de vie & Feedback utilisateur** : Vérifier les 4 états de chaque surface : *Vide* (présence d'un `EmptyState` actionnable), *Chargement asynchrone* (retour visuel pendant les `workers/`, désactivation propre des actions mutantes), *Succès/Partiel* (`Toast` approprié), et *Erreur* (bannière ou motif explicite à l'écran - jamais un contrôle grisé sans explication visible).
5. **Ergonomie Clavier, Affordances & Accessibilité** : Vérifier l'enregistrement dans `ui/shortcuts/catalog.py`, le `ComboBoxWheelFilter` (anti-piège de scroll), les fausses affordances (métriques passives qui ressemblent à des boutons cliquables), les `accessibleName` en français via `tr()` (ADR 0013), et l'usage exclusif d'icônes Phosphor (`load_phosphor_icon` / `load_on_accent_icon`, zéro émoji texte).
6. **Invariants Multi-Layouts & 24 Thèmes** : Vérifier que la vue supporte le switch à chaud (`refresh_theme()`) entre Sombre et Clair, et ne casse ni dans `ide_layout`, ni dans `macos_layout`, `dashboard_layout` ou `glass_layout`.

### 3. Restitution du Diagnostic Senior (en français)

Structurer la critique avant de générer les tickets :

- **Synthèse Architecturale & Ressenti Visuel** : Ce qui fonctionne bien et où se situe la friction visuelle ou cognitive globale ("pourquoi ça fait dev UI").
- **Matrice des frictions systémiques** : Classer les problèmes par impact (Critique / Structurel / Polish visuel) en citant les fichiers et lignes exacts.

### 4. Génération des Tickets Obsidian Kanban (`ankiforge_obsidian/`)

Regrouper les corrections cohérentes en tranches verticales atomiques (éviter les micro-tickets d'une ligne comme les tickets fourre-tout `🟣 XL`).

- Respecter strictement le gabarit de `references/gabarit-tickets-obsidian.md` (en-tête canonique à 7 champs, sections Contexte, Constats, User Story, Critères d'Acceptation vérifiables par `pytest-qt`, et bloc `DESIGN.md`).
- Générer les lignes prêtes à insérer dans `ankiforge_obsidian/Avancement du projet.md`.
- **Règle One-Shot Action & Stop** (si écriture directe sur disque) : écrire les notes dans `ankiforge_obsidian/Tickets/<Nom>.md` et mettre à jour `Avancement du projet.md` en une seule passe atomique, sans jamais toucher au bloc `%% kanban:settings` ni relire circulairement les fichiers écrits.

## Garde-fous & Gotchas

- **Zéro conseil vague** : Ne jamais écrire "améliorer l'espacement" ou "rendre plus moderne". Prescrire la valeur exacte (`setContentsMargins(12, 10, 12, 10)`, remplacement d'un `QFrame` encadré par un en-tête typographique `background: transparent; border: none`, migration vers `SegmentedTabBar(mode="subtab")`, etc.).
- **Conformité `DESIGN.md`** : Si l'audit recommande la création ou la modification structurelle d'un composant réutilisable, inclure systématiquement dans les critères d'acceptation du ticket la mise à jour de la Partie 1 de `DESIGN.md` et de la `WidgetGalleryWindow` (ADR 0049).
- **Langue** : Toute l'analyse et tous les tickets générés doivent être rédigés intégralement en **français** (ADR 0015).
# Gabarit Canonique des Tickets UI/UX Obsidian - AnkiForge

Ce référentiel garantit que chaque critique UI/UX issue de `audit-ui-ux-holistique` produit des notes de tickets 100 % compatibles avec `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` et le workflow d'implémentation (`/implement`, `/tdd`).

---

## 1. Granularité & Règles de Découpage des Tickets UI/UX

Pour que les tickets soient directement actionnables par un agent ou le développeur sans saturer le contexte :

1. **Un ticket = une préoccupation UI/UX cohérente** (taille cible : `🟢 XS`, `🟢 S` ou `🟡 M`, plus rarement `🔴 L`).
2. **Factorisation d'abord (Prérequis)** : Si l'audit révèle qu'un composant (ex: `SubTabButton` ou `TagPillButton` ou un `EmptyStateWidget`) est dupliqué dans 3 vues différentes, créer :
   - Un **Ticket 1 (Fondation / Unification)** dans `src/ankiforge/ui/components/` + `DESIGN.md` + `widget_gallery`.
   - Un **Ticket 2 (Migration des vues)** avec `**Prérequis :** [[Tickets/<NomTicket1>]]`.
3. **Vérifiabilité automatisée (`pytest-qt`)** : Chaque critère d'acceptation visuel ou structurel doit pouvoir être vérifié par une assertion déterministe en mode `offscreen` (ex: absence d'hexadécimal hors tokens dans le `styleSheet()`, `horizontalScrollBar().isVisible() is False` à `820x560`, présence d'`accessibleName()`, visibilité des états vides/erreurs, etc.).

---

## 2. Structure Stricte d'une Note Ticket (`ankiforge_obsidian/Tickets/<Nom>.md`)

Respecter **exactement** l'ordre des 7 champs d'en-tête ci-dessous :

```markdown
# 🎨 UI/UX - <Titre Court et Actionnable du Ticket>

**Statut :** 🎯 Prêt pour Agent · ready-for-agent
**Prérequis :** Aucun
**Difficulté :** 🟡 M
**Priorité :** 🟡 P1 (important)
**Piliers & Modules :** UI & Design System / <Nom de la Vue ou du Module>
**Lien Tableau :** [[Avancement du projet]]
**Fichiers Cibles :** `src/ankiforge/ui/...`, `DESIGN.md`, `tests/ui/test_...py`

---

## 🎯 Contexte

<Expliquer en 2-4 phrases le problème ergonomique ou visuel du point de vue de l'utilisateur et de la cohérence globale d'AnkiForge. Préciser pourquoi l'implémentation actuelle crée une friction cognitive, une rupture de hiérarchie visuelle ou une dérive par rapport à `DESIGN.md`.>

## 🔍 Constats (Analyse de code)

- **`src/ankiforge/ui/.../fichier1.py` (Lignes ~X-Y)** : <Constat précis : ex. utilisation d'un `QFrame` imbriqué avec couleurs `rgba(...)` codées en dur, ou `SubTabButton` local dupliqué au lieu de `SegmentedTabBar(mode="subtab")`.>
- **`src/ankiforge/ui/.../fichier2.py` (Lignes ~X-Y)** : <Constat croisé sur un second fichier montrant l'incohérence inter-vues (marges, hauteurs de boutons, absence d'état vide ou d'élision `ElidedLabel`).>
- **Impact Multi-Thèmes / Layouts** : <Préciser l'effet lors d'un switch Sombre/Clair (`refresh_theme`) ou à la résolution compacte 820×560.>

## 👤 User Story

En tant qu'utilisateur d'AnkiForge, je veux <bénéfice ergonomique concret : ex. distinguer immédiatement l'action principale des réglages secondaires sans surcharge visuelle>, afin de <gain d'usage dans le flux de travail>.

## 📋 Critères d'Acceptation

- [ ] **Tokens & StyleEngine** : Supprimer tout code couleur en dur (`#...`, `rgba(...)`) dans `<fichiers>` et consommer exclusivement `DesignTokens` (dont les tokens de teintes alpha §1.0 et `load_phosphor_icon` / `load_on_accent_icon`).
- [ ] **Composants & Hiérarchie** : <Instruction technique précise : ex. Remplacer X par `SegmentedTabBar`, désencadrer tel `QFrame` intermédiaire, appliquer `apply_compact_style()` (`COMPACT_BUTTON_HEIGHT = 32px`), ou replier tel bloc dans `CollapsibleSection`.>
- [ ] **Responsivité & États** : Garantir l'absence de défilement horizontal sous `820x560`, l'élision propre via `ElidedLabel`, et la prise en charge complète de `refresh_theme()`.
- [ ] **Accessibilité & i18n (ADR 0013 / ADR 0032)** : Toutes les chaînes passent par `self.tr()`, zéro émoji texte (icônes Phosphor uniquement), `accessibleName` et `toolTip` renseignés sur les `IconButton`.
- [ ] **Documentation & Gouvernance** : Mettre à jour la matrice de la **Partie 1** de `DESIGN.md` (et `src/ankiforge/ui/widget_gallery/registry.py` si un composant partagé est créé ou modifié).
- [ ] **Tests `pytest-qt` (`tests/ui/...`)** : Ajouter/mettre à jour les tests unitaires headless vérifiant les invariants visuels et comportementaux ci-dessus.
```

---

## 3. Format d'Insertion dans le Tableau Kanban (`ankiforge_obsidian/Avancement du projet.md`)

À la fin de chaque revue, fournir un bloc récapitulatif prêt à être copié ou inséré dans `ankiforge_obsidian/Avancement du projet.md` sous la colonne correspondant au statut (généralement `## 🚀 Features · Prêtes pour Agent` ou `## 🐞 Bugs · Prêts pour Agent`, ou `## 🎯 Prêt pour Spécification · ready-for-spec` si une décision d'architecture majeure reste ouverte) :

```markdown
- [ ] [[Tickets/<Nom_Du_Fichier_Sans_Extension>|🎨 UI/UX - <Titre Court>]] #ui-ux #<module> ⚡<P0|P1|P2|P3>
```

> **Rappel Règle d'or One-Shot Action & Stop (`docs/agents/issue-tracker.md`)** :
> Lors d'une exécution par un agent local ayant accès au système de fichiers, écrire chaque fichier `ankiforge_obsidian/Tickets/<Nom>.md`, ajouter la ligne dans `ankiforge_obsidian/Avancement du projet.md` sans altérer `%% kanban:settings`, et **s'arrêter immédiatement sans relire le Kanban**.
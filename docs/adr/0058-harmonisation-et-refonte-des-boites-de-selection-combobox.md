# ADR 0058 — Harmonisation et Refonte des Boîtes de Sélection ComboBox

**Statut** : Accepté  
**Date** : 2026-11-10  
**Décideurs** : Tristan Rigaud-Humbert, Agent Antigravity  
**Contexte** : Cadrage `/grill-with-docs` sur le ticket `UI - Harmonisation et Refonte des Boites de Selection ComboBox`

---

## Contexte & Problématique

Les listes déroulantes de sélection (`QComboBox`) constituent un composant fondamental des formulaires, dialogues et barres d'outils d'AnkiForge (sélection de modèles IA, de paquets, de modes d'ingestion, de filtres, etc.).

L'audit du code a révélé trois disparités critiques nuisant à l'homogénéité visuelle et technique :

1. **Rendu graphique incomplet dans `StyleEngine`** :
   - Aucune règle `QComboBox::down-arrow` n'était définie : la flèche de déroulement dépendait du moteur de rendu système natif de l'OS, produisant des chevrons flous, pixélisés ou invisibles sur certains des 24 thèmes sombres/clairs.
   - Absence d'états d'interaction `:hover` et `:on` (déroulé), conférant une allure statique et une affordance insuffisante.
   - Menu popup (`QAbstractItemView`) sans stylisation fine des items (absence de `min-height`, de padding d'items et d'arrondis sur la sélection au survol).
2. **Sous-utilisation et rigidité du composant canonique `StyledComboBox`** :
   - `StyledComboBox` (`src/ankiforge/ui/components/inputs.py`) intègre la protection contre le défilement accidentel à la molette (`ComboBoxWheelFilter`), mais n'était utilisé que dans ~55 % des cas, le reste du code instanciant directement `QComboBox` brut sans protection.
   - `StyledComboBox` imposait un `self.setFixedHeight(36)` rigide dans son constructeur, empêchant son intégration dans des barres d'outils ou panneaux latéraux nécessitant une densité compacte.
3. **Prolifération de styles locaux concurrents** :
   - Plus de 15 fichiers de vues et dialogues (`change_note_type_dialog.py`, `document_scope_dialog.py`, `album_transcription_dialog.py`, `rag_test_dialog.py`, `documents_view/view.py`, etc.) définissaient leurs propres blocs CSS `QComboBox { ... }` ou `QComboBox::drop-down { ... }`, avec des couleurs codées en dur ou des dimensions incompatibles avec le Design System.

---

## Décisions & Architecture

### 1. Rendu Vectoriel du Chevron via SVG Phosphor dans `StyleEngine`
- Remplacement du chevron système par l'icône vectorielle officielle **Phosphor `ph.caret-down`** injectée dynamiquement sous forme de SVG teinté dans la règle `QComboBox::down-arrow` :
  - Teinte de repos : `profile.text_secondary`.
  - Teinte au focus / ouvert (`:on`) : `profile.accent_primary`.
  - Teinte désactivée (`:disabled`) : `profile.text_muted`.
- Dimensions calibrées : flèche de 12×12 px centrée dans une zone de déclenchement `QComboBox::drop-down` de 26 px de large sans bordure latérale parasite.

### 2. États Visuels Complets et Menu Déroulant « Studio »
- **États du bouton ComboBox** :
  - Repos : fond `bg_input`, bordure 1px `border_color`, coins arrondis `radius_sm`.
  - Survol (`:hover`) : surbrillance de bordure 1.5px `accent_primary`, fond `bg_hover`.
  - Focus et Ouvert (`:focus`, `:on`) : halo `accent_primary`, fond `bg_panel`.
  - Désactivé (`:disabled`) : fond `bg_main`, texte `text_muted`, bordure `border_light`.
- **Menu Popup Déroulant (`QComboBox QAbstractItemView`)** :
  - Fond `bg_panel`, bordure nette 1px `border_color`, coins `radius_sm` avec légère marge d'espacement.
  - Items stylisés via `QAbstractItemView::item` : hauteur minimale de 28 px, padding horizontal de 10 px, coins arrondis au survol (`radius_xs` / 4 px).
  - État sélectionné / survolé : fond `bg_hover` avec texte `text_primary` ou accentué `accent_primary`.

### 3. Système Bivalent à Deux Densités (`normal` vs `compact`)
- Standardisation de deux régimes de densité pilotés par la propriété dynamique Qt `density` :
  - **Densité `normal` (par défaut)** : hauteur 36 px, padding `6px 10px`, taille de police standard (`FONT_SIZE_BASE`), adaptée aux formulaires généraux et dialogues modaux.
  - **Densité `compact` (`density="compact"`)** : hauteur 28 px, padding `2px 8px`, taille de police réduite (`FONT_SIZE_SM`), adaptée aux barres d'outils, inspecteurs latéraux et en-têtes de tableaux.
- Assouplissement de `StyledComboBox` :
  - Suppression du `setFixedHeight(36)` immuable au profit d'un réglage dynamique dépendant de la propriété `density` ou de `sizeHint()` paramétrable (`set_density(density: str)`).

### 4. Assainissement Transverse et Migration Exhaustive
- **Remplacement à 100 %** : Toutes les instanciations de `QComboBox` dans le code UI de l'application sont converties en `StyledComboBox` (ou `DBComboBox` / `ModelComboBox` pour les cas spécialisés).
- **Purge intégrale des styles locaux** : Élimination systématique de tous les blocs `setStyleSheet` locaux contenant des sélecteurs `QComboBox`, confiant la totalité de la responsabilité stylistique à `StyleEngine`.
- **Garde-fou et test automatisé** : Mise en place d'un test unitaire statique vérifiant qu'aucune vue ou dialogue n'injecte de règle `QComboBox` concurrente en dehors de `StyleEngine`.

---

## Conséquences

- **Cohérence esthétique absolue** : Le composant de sélection s'aligne rigoureusement sur le langage visuel des 24 thèmes sombres et clairs de [DESIGN.md](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/DESIGN.md).
- **Affordance et réactivité** : L'état d'interaction au survol et à l'ouverture offre un feedback tactile immédiat à l'utilisateur.
- **Fiabilité ergonomique** : L'utilisation universelle de `StyledComboBox` garantit la neutralisation des changements accidentels d'option à la molette via `ComboBoxWheelFilter`.
- **Maintenabilité** : La suppression des styles locaux élimine la duplication de code et facilite les évolutions graphiques futures au point unique `StyleEngine`.

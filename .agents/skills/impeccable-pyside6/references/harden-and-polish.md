# Durcissement & Finition Studio — PySide6

Ce guide détaille les techniques avancées de durcissement structurel (Harden) et de finition esthétique (Polish) pour délivrer des interfaces PySide6 sans défaut visuel, fluides et résilientes.

---

## 1. Durcissement Structurel (Harden Checklist)

### A. Résilience aux Résolutions Réduites
Une interface desktop professionnelle ne doit jamais dépendre d'un écran 4K pour être utilisable.
- **Cible Fenêtre Principale** : Parfaitement exploitable en **1280×800** (écran standard d'ordinateur portable).
- **Cible Dialogues Modaux** : Parfaitement exploitables et non tronqués en **820×560**.
- **Zéro Scroll Horizontal** : Toute apparition d'un ascenseur horizontal dans un formulaire ou une vue standard est considérée comme un bug bloquant.

```python
# Configuration infaillible pour conteneur défilant
scroll_area = QScrollArea(parent)
scroll_area.setWidgetResizable(True)
scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
scroll_area.setFrameShape(QFrame.Shape.NoFrame)
scroll_area.viewport().setStyleSheet("background: transparent;")
```

### B. Résilience au Contenu Dynamique & Traduction (i18n)
- **Règle du +30% de longueur** : Les traductions (notamment en allemand) peuvent être 30% plus longues que la chaîne française d'origine. Les boutons ne doivent pas avoir de `setFixedWidth` rigide quand ils contiennent du texte traduit.
- **Word Wrap Obligatoire** : Tout `QLabel` contenant une explication ou un message variable doit être configuré avec `label.setWordWrap(True)`.
- **Politique de Taille Élastique** : Définir `label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)`.

### C. Accessibilité Clavier et Anneaux de Focus
- **Navigation par Tabulation** : L'ordre de tabulation (`setTabOrder`) doit suivre la logique naturelle de lecture (de haut en bas, de gauche à droite).
- **Focus Visible** : Ne jamais supprimer l'anneau de focus (`outline: none` en CSS est proscrit). Le thème d'AnkiForge applique un liseré d'accent (`ACCENT_PRIMARY`) élégant lors de la prise de focus.

---

## 2. Finition de Qualité Studio (Polish Techniques)

### A. Affordance Tactile et États Interactifs
Chaque élément interactif doit réagir immédiatement et sans ambiguïté :
- **Curseur Pointeur** : `widget.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))`.
- **Règle des 4 États** : Toujours vérifier le rendu dans les 4 états canoniques :
  1. *Normal* : Lisible, reposant, contrasté.
  2. *Hover* : Éclaircissement subtil du fond (`BG_HOVER`) ou intensification du contour.
  3. *Pressed / Active* : Enfoncement léger (`BG_ACTIVE`) ou réduction de l'offset.
  4. *Disabled* : Opacité réduite (ex. 0.45 à 0.5), curseur par défaut, désactivation du glow.

### B. Ombres et Élévation Délicate (`apply_shadow`)
Au lieu d'ombres portées noires et brutales de l'époque Windows 95, AnkiForge utilise des ombres colorées, diffuses et élégantes :

```python
from ankiforge.ui.theme import DesignTokens, apply_shadow

# Ombre diffuse d'élévation sur une carte
apply_shadow(card, blur=16, offset_y=4, color=DesignTokens.COLOR_SHADOW)

# Glow signature pour un bouton primaire
apply_shadow(primary_btn, blur=12, offset_y=0, color=DesignTokens.ACCENT_GLOW)
```

### C. Gestion des États Vides (Empty States)
Ne jamais laisser un panneau vide afficher un rectangle grisâtre désert. Utiliser `EmptyStateWidget` (`src/ankiforge/ui/components/panels.py`) :
- Une icône Phosphor thématique en taille 32×32 ou 48×48px.
- Un titre clair (13-14px, Semibold).
- Un court texte explicatif orienté action (11-12px, Muted).
- Un bouton d'action principal optionnel invitant à créer ou importer.

---

## 3. Protocole de Validation & Assurance Qualité

### A. Test Headless avec `pytest-qt`
Tout widget poli doit être validé par un test unitaire ou d'intégration headless :
- Vérifier que le widget s'instancie sans avertissement ni fuite.
- Tester le déclenchement des signaux au clic ou au changement de sélection.
- Vérifier le nettoyage via la fixture `cleanup_qt_widgets`.

```bash
uv run pytest tests/ui/test_<nom_de_vue>.py
```

### B. Inspection Visuelle Headless (`script/capture_view.py`)
Avant de livrer une passe de finition :
1. Générer une capture d'écran haute résolution de la vue modifiée.
2. Vérifier visuellement le cadrage, l'absence de coupure de texte, l'harmonie des espacements et la fidélité au thème.
3. Valider le rendu sur au moins 2 thèmes contrastés (ex: `midnight` et `paper_light`).

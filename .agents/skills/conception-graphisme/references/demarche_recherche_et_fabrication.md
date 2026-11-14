# Référentiel : Recherche Documentaire Décentrée, Laboratoire & Moteur CSG (`conception-graphisme`)

Ce document détaille la boîte à outils opérationnelle de la compétence `conception-graphisme`.

---

## 1. Protocole de Recherche de Designers Peu Connus (Anti-Patterns Communs)

Lorsque tous les agents IA sollicitent uniquement les mêmes figures tutélaires (*Dieter Rams, Massimo Vignelli, Paul Rand*), ils convergent vers une esthétique standardisée. Pour briser ce biais :

### A. Requêtes de découverte préalables (`search_web`)
Avant de citer un grand classique, effectuer au moins 2 recherches ciblées vers des praticiens contemporains, indépendants ou spécialisés :
- **Icônes & artisanat logiciel indépendant :**
  - `"indie macOS icon designer" OR "craft app icon"process bezier metaphor`
  - `"Matthew Skiles" OR "Louie Mantia" OR "Gavin Nelson" OR "Sebastiaan de With" OR "Michael Flarup" icon anatomy`
  - Chercher des créateurs d'ateliers indépendants (Panic, Tapbots, Bjango, Iconfactory, Linear, Raycast, Amie, Cron) en analysant *comment* ils traitent la matière, l'angle de vue et la découpe des plans.
- **Édition, papeterie & systèmes de signes hors-canon :**
  - Explorer l'esthétique des **fiches d'archives et papeteries techniques** (Zettelkasten de Niklas Luhmann, carnets japonais *MD Paper / Midori*, formulaires postaux suisses, spécimens de fonderies indépendantes comme *Klim Type Foundry*, *Dinamo*, *Grilli Type*, *Commercial Type*).
  - Explorer l'illustration par **espace négatif et pochoir** (emblèmes *Kamon* japonais, gravure sur bois moderne, *Ligne Claire* franco-belge, constructivisme typographique).

### B. Synthèse de la recherche avant conception
Toujours présenter à l'utilisateur :
1. **Les références de niche découvertes** (quel détail singulier on en retient : un chanfrein, un point carré, une asymétrie de marge, un contraste papier crème / encre profonde).
2. **La grammaire structurelle classique** qui assure la solidité (grille, test de réduction `16×16 px`, règle du *Traffic Sign*).

---

## 2. Les 5 Écoles de Déclinaison pour le Laboratoire Comparatif

Lorsqu'une métaphore centrale est validée (ex. deux cartes exprimant le passage du *Brouillon* à la *Question*), l'explorer à travers 5 écoles contrastées :

| École stylistique | ADN formel | Force principale | Vigilance optique |
| :--- | :--- | :--- | :--- |
| **1. Néo-Brutaliste & Pop** | Contours noirs épais constants, angles francs, ombre portée dure en aplat noir sans flou. | Très lisible en logo détouré web ou sticker. | Peut paraître « hors-système » dans un Dock macOS sans conteneur *squircle*. |
| **2. Grille Orthogonale (`0°`)** | Alignement strict à `90°`, zéro inclinaison, filets d'encre, point typographique carré. | Rigueur éditoriale maximale, accord direct avec une page vitrine suisse. | Attention au « piège du smartphone » si une carte verticale a une bordure inférieure épaisse. |
| **3. Ligne Claire & Bristol** | Coins adoucis, papier crème chaud (`#faf8f5`), détail de papeterie humaine. | Chaleur immédiate, proximité émotionnelle avec l'étudiant. | Bannir les réglures fines qui deviennent grises et brouillonnes sous `64 px`. |
| **4. Studio Tactile macOS** | Conteneur *squircle* sombre (`#191736 → #0d0e14`), liseré spéculaire interne, plans en lévitation. | Intégration native irréprochable dans le Dock macOS / barre Windows. | Remplacer les ombres portées floues entre cartes par une découpe CSG franche. |
| **5. Sceau Kamon (Pochoir)** | Aplats purs séparés par une tranchée négative de la couleur exacte du fond. | Lisibilité imbattable à `16×16 px` et en monochrome 1-bit. | Vérifier la hiérarchie lumineuse entre la carte avant et la carte arrière. |

---

## 3. Architecture du Moteur Géométrique Déterministe (`PySide6.QtGui.QPainterPath`)

Ne jamais coder à la main des courbes de glyphes ou des fausses bordures de découpe en SVG. Utiliser le patron suivant (voir `script/generate_app_icons.py`) :

```python
# 1. Extraction d'un vrai glyphe typographique (crosse + point séparés)
raw_path = QPainterPath()
raw_path.addText(QPointF(0, 0), QFont("Helvetica Neue", weight=QFont.Weight.Bold), "?")

# 2. Soustraction booléenne CSG réelle (tranchée franche sans halo)
stroker = QPainterPathStroker()
stroker.setWidth(trench_w)
stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
cutter = front_world.united(stroker.createStroke(front_world))
back_cut = back_world.subtracted(cutter)
glyph_cut = glyph_world.subtracted(cutter)

# 3. Superellipse Apple continue (256 pas) + Inset Rim (zéro halo sur fond blanc)
squircle_outer_d = _apple_superellipse_path(64.0, 64.0, 59.5, exponent=4.6, steps=256)
squircle_inset_d = _apple_superellipse_path(64.0, 64.0, 58.6, exponent=4.6, steps=256)
```

### Règles de proportion optique vérifiées :
- **Marge de sécurité interne (*Padding*) :** Le groupe central doit laisser au moins `8 à 10 %` d'espace libre par rapport au liseré du *squircle* (aucun coin de carte ne doit frôler ou mordre la bordure).
- **Dégagement des glyphes :** Si un glyphe (`?`) figure sur la carte arrière, décaler son centre optique pour que son arche gauche reste 100 % entourée de la couleur de la carte arrière, sans tangente aveugle avec la tranchée CSG.
- **Loi de Proximité de la Gestalt sur les barres de texte :**
  - **Barre 1 (Titre) :** largeur `~68 %`, hauteur `7.4`.
  - **Saut sous titre :** `10.2` unités.
  - **Barre 2 (Corps 1) :** largeur `100 %`, hauteur `6.4`.
  - **Interligne de corps :** `5.4` unités (`~2×` plus serré que le saut sous le titre).
  - **Barre 3 (Corps 2) :** largeur `~56 %`, hauteur `6.4` (ratio largeur/hauteur `> 3:1` pour ne jamais ressembler à un bouton, et longueur distincte du titre pour briser la symétrie `Court / Long / Court`).
  - **Centre de gravité :** remonter le bloc de `-1.2` unité au-dessus du milieu géométrique pour compenser le vide en bas à droite.

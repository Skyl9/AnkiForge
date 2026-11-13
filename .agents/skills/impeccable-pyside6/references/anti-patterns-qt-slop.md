# Anti-patterns PySide6 : Éradication du Qt AI Slop

Ce guide recense les réflexes médiocres fréquemment générés par les LLM lors de la création d'interfaces PySide6 / Qt, ainsi que leurs remèdes de précision conformes à `DESIGN.md` et aux standards de qualité studio (Linear, Raycast, Craft).

---

## 1. L'empilement de `QGroupBox` aux bordures gravées (Etched GroupBoxes)

### Le réflexe "Slop"
L'IA emballe chaque groupe de champs dans un `QGroupBox("Titre")`. Résultat : des bordures grises d'1px qui se superposent dans tous les sens, créant un effet "boîte dans la boîte" lourd, vieillot et visuellement saturé.

```python
# ❌ SLOP : Boîte gravée vieillotte
group = QGroupBox("Configuration du modèle")
layout = QVBoxLayout(group)
layout.addWidget(QLabel("Température"))
layout.addWidget(QDoubleSpinBox())
```

### Le remède "Impeccable Craft"
- **Surfaces pures ou espacements aérés** : Privilégier une hiérarchie purement spatiale (séparation de 16-24px) avec un en-tête typographique discret.
- **Cartes unifiées (`QFrame`)** : Si un encadrement est réellement requis, employer un `QFrame` stylisé avec fond `BG_PANEL`, bordure subtile `BORDER_COLOR` d'1px et `border-radius: 10px` (`RADIUS_MD`).
- **En-tête de section typographique** : Un `QLabel` discret (11px, majuscule, graisse 600, couleur `COLOR_TEXT_MUTED`, espacement de lettres).

```python
# ✅ IMPECCABLE : Hiérarchie typographique et surface sobre
section_container = QWidget()
section_layout = QVBoxLayout(section_container)
section_layout.setContentsMargins(0, 0, 0, 0)
section_layout.setSpacing(8)

header = QLabel(self.tr("CONFIGURATION DU MODÈLE"))
header.setProperty("headingLevel", "section")
header.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.COLOR_TEXT_MUTED}; letter-spacing: 0.5px; text-transform: uppercase;")
section_layout.addWidget(header)
# Intégration directe des contrôles sans bordure étouffante
```

---

## 2. Les `QMessageBox` paresseuses et intrusives

### Le réflexe "Slop"
Pour chaque succès, avertissement ou confirmation mineure, l'IA dégaine un `QMessageBox.information()` ou `QMessageBox.warning()` modal qui bloque le fil utilisateur, fait apparaître une boîte OS non stylisée et détruit le sentiment d'application fluide.

```python
# ❌ SLOP : Boîte modale bloquante pour un simple succès
QMessageBox.information(self, "Succès", "Le prompt a été enregistré.")
```

### Le remède "Impeccable Craft"
- **Notifications discrètes (Toasts)** : Pour les confirmations asynchrones, utiliser le `ToastManager` (`src/ankidraft/ui/widgets/toast.py`) qui empile des alertes légères, fluides et élégantes avec barre de progression et auto-dismiss.
- **Bannières d'état inline** : Afficher les avertissements non bloquants directement dans la vue, au-dessus de l'action concernée.
- **Dialogues modaux dédiés** : Pour les confirmations critiques destructives (suppression irréversible), employer un dialogue custom dérivé du design system, jamais une boîte système native.

```python
# ✅ IMPECCABLE : Toast élégant et non bloquant
from ankidraft.ui.widgets.toast import ToastLevel, ToastManager

ToastManager.get_instance().show_toast(
    title=self.tr("Enregistré"),
    message=self.tr("Le prompt a été mis à jour avec succès."),
    level=ToastLevel.SUCCESS,
    duration=3500,
)
```

---

## 3. Couleurs codées en dur (Hardcoded Hex/RGB)

### Le réflexe "Slop"
L'IA écrit des chaînes QSS avec des codes hexadécimaux arbitraires (`#2b2b2b`, `#ffffff`, `#ff4444`) injectés directement dans `setStyleSheet()`. Résultat : les styles cassent dès que l'utilisateur bascule entre les 12 thèmes d'AnkiForge (Midnight, Forest, Nord, Solarized, Paper Light...).

```python
# ❌ SLOP : Hexadécimal codé en dur, casse au changement de thème
btn.setStyleSheet("background-color: #3b82f6; color: white; border-radius: 6px;")
```

### Le remède "Impeccable Craft"
- **Rôles sémantiques QSS** : Définir la propriété dynamique `btn.setProperty("role", "primary")` et laisser `StyleEngine` injecter les règles de thème.
- **Composants d'infrastructure** : Utiliser `PrimaryButton`, `SecondaryButton`, `IconButton`, `Badge` (`src/ankidraft/ui/components/`).
- **DesignTokens** : Si un style programmatique est impératif, importer `DesignTokens` depuis `ankidraft.ui.theme` ou interroger le profil de thème actif.

```python
# ✅ IMPECCABLE : Composant sémantique branché sur le Design System
from ankidraft.ui.components.buttons import PrimaryButton

btn = PrimaryButton(self.tr("Générer les cartes"), parent=self)
# Tout le style, le hover, le glow et le focus proviennent de DESIGN.md
```

---

## 4. Layouts rigides qui explosent au redimensionnement

### Le réflexe "Slop"
L'IA utilise des dimensions fixes (`setFixedSize(600, 400)`), des `minimumWidth` démesurées (> 500px), ou oublie le retour à la ligne automatique (`setWordWrap(True)`) sur les `QLabel` textuels. En conséquence, la fenêtre ne peut pas rétrécir sur un écran portable standard (1280×800) et des barres de défilement horizontales parasites apparaissent.

```python
# ❌ SLOP : Largeur forcée qui déborde et bloque le redimensionnement
desc_label = QLabel("Ce prompt permet d'extraire les définitions clés d'un document complexe...")
desc_label.setFixedWidth(500)  # Déborde sur écran étroit !
```

### Le remède "Impeccable Craft"
- **Word wrap systématique** : Tout label de description ou d'aide doit posséder `setWordWrap(True)`.
- **Politiques de taille élastiques** : Utiliser `QSizePolicy.Policy.Expanding` horizontalement et `QSizePolicy.Policy.Preferred` verticalement.
- **QScrollArea étanche** : Pour tout panneau à contenu variable, configurer la zone de défilement avec `setWidgetResizable(True)` et masquer impérativement le défilement horizontal.

```python
# ✅ IMPECCABLE : Adaptatif et élastique
desc_label = QLabel(self.tr("Ce prompt permet d'extraire les définitions clés d'un document complexe..."))
desc_label.setWordWrap(True)
desc_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

scroll = QScrollArea()
scroll.setWidgetResizable(True)
scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
scroll.setFrameShape(QFrame.Shape.NoFrame)
```

---

## 5. Absence d'états interactifs et de micro-feedback

### Le réflexe "Slop"
Boutons et listes statiques : aucun changement visuel au survol (`:hover`), aucune affordance au clic (`:pressed`), curseur par défaut (flèche floue au lieu du pointeur de main), indicateur de focus inexistant pour la navigation clavier.

```python
# ❌ SLOP : Bouton mort sans feedback tactile
btn = QPushButton("Valider")
```

### Le remède "Impeccable Craft"
- **Curseur main** : `btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))`.
- **Propriété de survol Qt** : `btn.setAttribute(Qt.WidgetAttribute.WA_Hover, True)`.
- **Micro-transitions et ombres** : `apply_shadow(btn, blur=10, color=DesignTokens.ACCENT_GLOW)`.
- **États complets** : Toujours garantir les règles QSS pour normal, `:hover`, `:pressed`, `:focus-visible` et `:disabled`.

---

## 6. Icônes hétérogènes, colorées ou émojis

### Le réflexe "Slop"
L'IA colle des émojis directement dans les libellés (`QPushButton("💾 Enregistrer")`) violant les règles strictes d'ingénierie du projet, ou utilise des icônes système Qt (`QStyle.StandardPixmap`) au rendu pixelisé et non harmonisé.

### Le remède "Impeccable Craft"
- **Zéro émoji dans l'interface**.
- **Phosphor Icons monochrome** : Utiliser `load_phosphor_icon(name, color=...)` ou `load_on_accent_icon(name)` avec dimensions normalisées (16×16px pour inline/boutons, 20×20px pour en-têtes, 24×24px pour barres d'outils).

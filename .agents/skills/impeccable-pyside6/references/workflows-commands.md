# Workflows & Commandes Chirurgicales Impeccable pour PySide6

Ce guide détaille l'exécution méthodique des passes de finition inspirées du framework Impeccable. Chaque commande constitue une opération de haute précision applicable à un composant, un dialogue ou une vue PySide6 complète.

---

## Vue d'Ensemble des 6 Passes Chirurgicales

| Commande | Intention Clé | Question d'Évaluation |
| :--- | :--- | :--- |
| `/distill` | **Élimination du bruit visuel** | *Quel élément graphique n'apporte aucune information fonctionnelle ?* |
| `/typeset` | **Hiérarchie & Rythme typographique** | *Le texte guide-t-il l'œil instantanément vers l'essentiel ?* |
| `/arrange` | **Alignement & Grille spatiale (4px)** | *Les marges et espacements suivent-ils un rythme mathématique strict ?* |
| `/harden` | **Robustesse & Responsive desktop** | *Le layout survit-il au redimensionnement extrême (1280×800 et 820×560) ?* |
| `/polish` | **Affordance & Micro-interactions** | *L'interface réagit-elle au survol, au clic et au focus avec fluidité ?* |
| `/quieter` ou `/bolder` | **Pondération & Contraste d'attention** | *L'intensité visuelle est-elle équilibrée ou surcharge-t-elle l'esprit ?* |

---

## 1. Passe `/distill` : Épuration et Clarté Radicale

### Objectif
Supprimer les ornements superflus, les bordures étouffantes, les fonds hétérogènes et les lignes de séparation redondantes pour laisser respirer le contenu.

### Protocole d'Exécution
1. **Éradiquer les `QGroupBox`** : Remplacer les cadres gravés par de simples espacements ou des conteneurs sans bordure.
2. **Nettoyer les séparateurs (`QFrame.HLine`)** : Remplacer les barres horizontales parasites par des espacements rythmés (`setSpacing(16)`).
3. **Unifier les fonds** : S'assurer que le contenu repose sur `BG_PANEL` ou `BG_MAIN`, sans sous-boîtes contrastées inutiles.
4. **Débruiter les icônes** : Supprimer les icônes purement décoratives qui n'aident pas à l'action.

```python
# Exemple distill
# Avant : 3 QGroupBox, 2 séparateurs HLine, fond hétérogène
# Après : 1 conteneur fluide, titres en-tête clairs, 0 séparateur inutile
```

---

## 2. Passe `/typeset` : Hiérarchie Typographique Studio

### Objectif
Imposer une typographie lisible, hiérarchisée et élégante, guidant l'attention de l'utilisateur avec précision.

### Protocole d'Exécution
1. **Titres Majeurs (14-16px, Semibold 600)** : `COLOR_TEXT_PRIMARY`, marge inférieure nette.
2. **Sous-titres & Sections (11-12px, Bold 600, Uppercase)** : `letter-spacing: 0.5px`, couleur `COLOR_TEXT_MUTED`.
3. **Corps & Formulaires (12-13px, Regular 400)** : `COLOR_TEXT_PRIMARY` ou `SECONDARY`, lisibilité optimale sur `FONT_MAIN`.
4. **Aides & Métadonnées (10-11px, Muted)** : `COLOR_TEXT_MUTED`, placé sous les champs sans encombrer.
5. **Code & Données Précises (11-12px, Monospace)** : Utiliser systématiquement `FONT_CODE` (JetBrains Mono / monospace).

---

## 3. Passe `/arrange` : Rythme Spatial et Alignements Optiques

### Objectif
Harmoniser toutes les dimensions selon la grille de 4px d'AnkiForge (`4, 8, 12, 16, 24px`) et aligner optiquement les composants.

### Protocole d'Exécution
1. **Marges de Conteneur** :
   - Panneaux et dialogues majeurs : `setContentsMargins(16, 16, 16, 16)`.
   - Cartes et sous-panneaux internes : `setContentsMargins(12, 12, 12, 12)`.
   - Barres d'outils et en-têtes : `setContentsMargins(16, 8, 16, 8)`.
2. **Espacements entre Contrôles (`setSpacing`)** :
   - Entre éléments étroitement liés (icône + libellé, champ + aide) : `4px` ou `6px`.
   - Entre champs d'un même groupe : `8px`.
   - Entre groupes de formulaires : `16px`.
   - Entre sections majeures : `24px`.
3. **Alignement des Lignes de Base** :
   - Vérifier que les boutons, inputs et labels sur une même ligne horizontale partagent un alignement vertical centré (`Qt.AlignmentFlag.AlignVCenter`).
4. **Spacers Élastiques (`addStretch`)** :
   - Placer judicieusement `layout.addStretch()` en bas de formulaire pour maintenir les contrôles groupés en haut plutôt que dilués verticalement.

---

## 4. Passe `/harden` : Résilience et Responsive Desktop

### Objectif
Garantir que le widget ne casse jamais, ne tronque pas de texte et s'adapte sans faille aux dimensions d'écran critiques.

### Protocole d'Exécution
1. **Épreuve du 1280×800** : La fenêtre principale doit fonctionner sans défilement horizontal.
2. **Épreuve du 820×560** : Tout dialogue modal doit rester parfaitement manipulable et lisible à cette taille.
3. **Word Wrap Systématique** : Appliquer `setWordWrap(True)` sur tous les `QLabel` textuels.
4. **Taille Minimum Saine** : Pas de `setMinimumWidth` arbitraire > 400px.
5. **Résilience aux Traductions (`ADR 0013`)** : Prévoir 20 à 30 % de longueur supplémentaire pour les textes traduits (allemand/anglais) sans tronquer les boutons.

---

## 5. Passe `/polish` : Affordance et Micro-Détails

### Objectif
Donner à l'interface le toucher soigné d'un produit professionnel : curseurs, ombres d'élévation, transitions et retours visuels.

### Protocole d'Exécution
1. **Curseurs Interactifs** : Assigner `Qt.CursorShape.PointingHandCursor` sur tous les boutons, liens, onglets et cartes cliquables.
2. **Attribut de Survol** : Activer `setAttribute(Qt.WidgetAttribute.WA_Hover, True)` sur les contrôles personnalisés.
3. **Élévation et Ombres Douces** : Appliquer `apply_shadow(widget, blur=12, offset_y=2, color=...)` sur les cartes flottantes.
4. **Normalisation des Icônes** : Vérifier que toutes les icônes proviennent de `load_phosphor_icon` et adoptent des teintes sémantiques cohérentes.

---

## 6. Commandes d'Ajustement : `/quieter` & `/bolder`

### `/quieter` (Atténuer la Charge Cognitive)
À utiliser lorsqu'une vue est visuellement agressive ou encombrée :
- Remplacer un bouton plein (`PrimaryButton`) secondaire par un bouton ghost ou contour (`SecondaryButton`).
- Passer la couleur d'un texte de `PRIMARY` à `SECONDARY` ou `MUTED`.
- Réduire l'épaisseur d'une bordure ou la rendre plus transparente.
- Réduire le corps de police d'une note d'aide d'1px.

### `/bolder` (Affirmer le Point Focal)
À utiliser lorsqu'une action essentielle se perd dans l'interface :
- Valoriser l'action principale unique avec `PrimaryButton` et son glow signature.
- Ajouter un badge d'état contrasté (`StatusBadge`).
- Accentuer la taille ou la graisse du libellé clé.
- Structurer un résumé métrique via une `StatCard` percutante.

---
name: ui-screenshot
description: Permet à l'agent de capturer des captures d'écran (screenshots) haute résolution de n'importe quelle vue d'AnkiForge en mode headless/offscreen et de les inspecter visuellement avec view_file.
---

# 📸 Compétence : Inspecteur Graphique & Capture d'Écran Autonome (AnkiForge UI Inspector)

Cette compétence permet à l'agent d'inspecter visuellement l'application **AnkiForge**, de vérifier le rendu des composants Qt (PySide6) et de valider les refontes d'interfaces sans intervention de l'utilisateur.

---

## 🛠️ 1. Outil de Capture (`script/capture_view.py`)

Le script `script/capture_view.py` permet de générer des captures PNG en environnement headless (`QT_QPA_PLATFORM=offscreen`).

### Commandes usuelles :

#### A. Capturer une vue spécifique :
```bash
uv run python script/capture_view.py --view creation --output temp/screens/creation.png
```

#### B. Capturer avec un thème ou un layout particulier :
```bash
uv run python script/capture_view.py --view analysis --theme catppuccin_mocha --layout macos --output temp/screens/analysis_macos.png
```
*Layouts supportés :* `ide` (défaut), `macos`, `dashboard`, `glassmorphism`.
*Thèmes supportés :* `ide`, `dark_modern`, `catppuccin_mocha`, `dracula`, `nord`, `solarized_dark`, `cyberpunk`, `monokai`, `tokyo_night`, `light_clean`, `github_light`, `sepia_warm`.

#### C. Capturer l'intégralité des 11 vues de l'application :
```bash
uv run python script/capture_view.py --all --output temp/screens/
```

---

## 👁️ 2. Inspection Visuelle avec `view_file`

Une fois le screenshot généré, **appelle impérativement l'outil `view_file`** sur le chemin absolu du fichier `.png` :

```json
{
  "AbsolutePath": "/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/temp/screens/creation.png",
  "toolAction": "Inspecting UI screenshot",
  "toolSummary": "Inspect UI screenshot"
}
```

L'outil retournera directement l'image dans ton contexte visuel pour analyse.

---

## 🔄 3. Workflow de Refonte « Menu par Menu »

Pour chaque menu à refondre :

1. **📸 État des Lieux (Before) :**
   - Capturer la vue avec `script/capture_view.py --view <view_id>`.
   - Inspecter l'image avec `view_file`.
   - Dresser un diagnostic ergonomique (hiérarchie des panneaux, encombrement, lisibilité des polices, contrastes, affordance des boutons).

2. **💡 Vision & Architecture Cible :**
   - Structurer les zones fonctionnelles : Barre d'outils / En-tête de contexte, Zone de travail principale (cartes / inputs / prévisualisation), Panneau latéral contextuel ou tiroir repliable.
   - S'appuyer sur les composants du Design System : `DesignTokens`, `IdePanel`, `GlowLineEdit`, `IconButton`, `PillBadge`, `GlowButton`.

3. **💻 Implémentation du Composant :**
   - Modifier les fichiers cibles dans `src/ankiforge/ui/views/<view_name>_view.py` et sous-composants dans `src/ankiforge/ui/widgets/`.
   - Respecter les standards Qt (Signaux/Slots, layouting avec `setContentsMargins` et `setSpacing`, typage strict `mypy`).

4. **📸 Validation Graphique (After) :**
   - Capturer à nouveau la vue.
   - Inspecter le screenshot et vérifier l'alignement visuel, le responsive et l'absence de coupures de texte.

5. **🧪 Validation Technique :**
   - Lancer `uv run pytest tests/ui/test_<view_name>_view.py`.
   - Valider `mypy`, `bandit`, et les hooks `pre-commit`.

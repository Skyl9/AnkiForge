# Plan d'Amélioration — `DocumentDelimitationDialog` & `DocumentScopeDialog`

## État actuel

````carousel
![Délimitation (état actuel)](/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/76ed5664-3646-432e-835b-4b8205a28beb/delimitation_before.png)
<!-- slide -->
![Portée de génération (état actuel)](/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/76ed5664-3646-432e-835b-4b8205a28beb/scope_before.png)
````

## Objectif

Améliorer l'ergonomie, la lisibilité et les fonctionnalités des deux modaux de délimitation et de portée documentaire, en conservant la philosophie actuelle (splitter gauche/droite, arborescence, aperçu synchronisé).

---

## Diagnostic visuel

### Problèmes UX identifiés (communs aux 2 modaux)

| # | Zone | Problème |
|---|------|----------|
| 1 | **En-tête** | L'en-tête (titre + badge + description) prend trop de hauteur verticale, réduisant l'espace pour l'arborescence |
| 2 | **Badge diagnostics** | "⚠️ Quasi vide" apparaît pour tous les sous-chapitres — peu utile pour un cours normal, trop de bruit visuel |
| 3 | **Badges H1/H2** | Les badges de niveau (H1, H2, H3) sont bleus pour H1, bleus clairs pour H2 — hiérarchie peu lisible, devrait être plus contrastée |
| 4 | **Items arborescents** | La hauteur fixe de 36px est trop compacte, il n'y a pas d'indentation visuelle supplémentaire entre niveaux |
| 5 | **Aperçu droit** | Sur le modal de portée, l'aperçu ne scroll pas automatiquement vers la section sélectionnée (seulement dans délimitation) |
| 6 | **KPI section** | Le compteur de sections est peu lisible (tout en petit texte bleu, pas de distinction visuelle par type de doc) |
| 7 | **"Vue Finale Assemblée"** | Ce bouton n'existe que dans le modal Portée, mais pas dans Délimitation — incohérence entre les deux |
| 8 | **Barre de navigation** | La barre de mode (Tout / Plage / Par Chapitres) est trop petite et peu distinctive quand un seul mode est actif |
| 9 | **Footer** | La checkbox "Réindexer FAISS" dans Délimitation est noyée dans le footer à gauche — pas assez mise en valeur |
| 10 | **Scroll de l'aperçu** | Il n'y a pas de mise en surbrillance (highlight) de la section active dans l'aperçu Markdown |
| 11 | **Scope — pied de page** | Les KPI de résumé (tokens, mots, cartes) sont en bas à gauche dans un format texte peu lisible — pas de badges visuels |
| 12 | **Délimitation — bouton "Enregistrer"** | Le bouton principal de Délimitation est peu distinctif dans le contexte destructif (jaune/warning devrait dominer) |

---

## Propositions d'amélioration

### A. UI — Améliorations visuelles (priorité haute)

#### A1. En-tête condensé — économiser 30px de hauteur
**Fichiers** : `delimitation_dialog.py` + `document_scope_dialog.py`

Fusionner le titre et le badge sur la même ligne, réduire la description à une seule ligne en italique au lieu de deux lignes de texte.

```python
# AVANT : 2 blocs QVBoxLayout (titre + desc séparés)
h_layout = QVBoxLayout(header_card)
header_top = QHBoxLayout()
...
h_layout.addLayout(header_top)
h_layout.addWidget(desc_lbl)  # 2 lignes de texte

# APRÈS : Tout sur une ligne, desc en tooltip
header_layout = QHBoxLayout(header_card)
icon_lbl = QLabel()
title_lbl = QLabel(f"<b>{doc.title}</b> &nbsp; {badge_html}")
desc_lbl.setToolTip("Éliminez définitivement...")  # → tooltip au hover
header_layout.addWidget(icon_lbl)
header_layout.addWidget(title_lbl, 1)
```

#### A2. Badges H1/H2/H3 — meilleure hiérarchie visuelle
**Fichier** : `delimitation_dialog.py` → `SectionRowWidget.__init__`

Utiliser une couleur distincte selon le niveau (H1 indigo, H2 bleu-vert, H3 gris), et ajouter une indentation supplémentaire dans le widget lui-même (pas seulement celle du QTreeWidget) :

```python
# H1 → indigo vif
# H2 → teal/vert-bleu
# H3 → gris neutre
LEVEL_COLORS = {
    1: {"bg": "rgba(99, 102, 241, 0.25)", "fg": "#a5b4fc", "border": "rgba(99,102,241,0.5)"},
    2: {"bg": "rgba(20, 184, 166, 0.2)", "fg": "#5eead4", "border": "rgba(20,184,166,0.4)"},
    3: {"bg": "rgba(148, 163, 184, 0.15)", "fg": "#94a3b8", "border": "rgba(148,163,184,0.3)"},
}
```

#### A3. Diagnostic plus intelligent — supprimer le bruit "⚠️ Quasi vide"
**Fichier** : `delimitation_dialog.py` → `SectionRowWidget.__init__`

Le badge "⚠️ Quasi vide" s'affiche pour tout chapitre parent (qui agrège ses enfants mais dont le texte propre est court). Filtrer ce cas : seules les **feuilles** (sans enfants) avec peu de mots doivent afficher le warning.

```python
# Nouveau paramètre is_leaf dans SectionRowWidget
is_leaf: bool = True  # nouveau param
# Afficher le warning seulement si is_leaf=True and word_count < 25
```

#### A4. Hauteur des items — passer de 36px à 40px + indentation visuelle dans le widget
**Fichier** : `delimitation_dialog.py` → `SectionRowWidget`

```python
self.setFixedHeight(40)  # 36 → 40
# Ajouter un padding-left selon le niveau dans le layout
layout.setContentsMargins(4 + (level - 1) * 12, 2, 8, 2)
```

#### A5. Barre de mode plus visible — pill buttons avec icônes
**Fichiers** : `delimitation_dialog.py` + `document_scope_dialog.py`

Remplacer les boutons texte par des "pill" buttons avec icône + texte plus lisibles :

```python
# Tout le document → ✅ Tout
# Plage de pages   → 📐 Plage
# Par Chapitres    → 🌳 Chapitres
```

Et ajouter une transition animée sur le `QFrame` de contenu visible (show/hide avec `setMaximumHeight`).

#### A6. Footer du modal Portée — badges KPI visuels au lieu du texte brut
**Fichier** : `document_scope_dialog.py`

Remplacer la ligne texte de résumé en bas par des badges colorés (tokens, mots, sections) bien visibles :

```
┌──────────────────────────────────────────────────────┐
│ 🔤 6 sections  │ 📝 ~22 mots  │ 🤖 ~29 tokens  │ 🎴 ~1 carte estimée │
└──────────────────────────────────────────────────────┘
```

---

### B. Fonctionnalités — Nouvelles capacités (priorité haute)

#### B1. 🔍 Barre de recherche/filtre dans l'arborescence
**Fichiers** : `delimitation_dialog.py` + `document_scope_dialog.py`

Ajouter un `QLineEdit` de filtrage au-dessus de l'arborescence. En temps réel, masque les items ne correspondant pas au texte saisi. Permet de retrouver rapidement une section dans un document long (50+ chapitres).

```python
self.filter_input = QLineEdit()
self.filter_input.setPlaceholderText("🔍 Filtrer les sections...")
self.filter_input.textChanged.connect(self._on_filter_changed)


def _on_filter_changed(self, text: str) -> None:
    for i in range(self.sections_list.count()):
        item = self.sections_list.item(i)
        w = self.sections_list.itemWidget(item)
        title = self._section_meta.get(i, {}).get("title", "")
        item.setHidden(bool(text) and text.lower() not in title.lower())
```

#### B2. ⚡ "Vue Finale Assemblée" dans le modal Délimitation
**Fichier** : `delimitation_dialog.py`

Uniformiser avec le modal Portée. Ajouter les boutons `📄 Document Source` / `👁️ Vue Finale Assemblée` dans le panneau droit de Délimitation également. La "Vue Finale" montre le contenu tel qu'il sera stocké dans les chunks après `_on_apply()`.

```python
# Ajouter le même view_switch_group que dans document_scope_dialog.py
# Page 0 : DocumentPreviewWidget (existant)
# Page 1 : QTextBrowser avec assemblage des chunks retenus
```

#### B3. 🎨 Surbrillance de la section active dans l'aperçu Markdown
**Fichier** : `delimitation_dialog.py` → `DocumentPreviewWidget`

Quand l'utilisateur clique sur une section dans l'arborescence, la section correspondante dans l'aperçu Markdown est surlignée temporairement (via `QTextBrowser.find()` + sélection CSS).

```python
def _highlight_section(self, heading_text: str) -> None:
    """Surligne temporairement le titre dans l'aperçu Markdown."""
    cursor = self.markdown_viewer.document().find(heading_text)
    if not cursor.isNull():
        extra_selections = [...]  # QTextEdit.ExtraSelection
        self.markdown_viewer.setExtraSelections(extra_selections)
        # Reset après 2 secondes via QTimer
        QTimer.singleShot(2000, lambda: self.markdown_viewer.setExtraSelections([]))
```

#### B4. 🔄 Bouton "Réinitialiser à l'état original" dans Délimitation
**Fichier** : `delimitation_dialog.py`

Ajouter un bouton secondaire "↩ Réinitialiser" dans le footer qui remet `start_page=None`, `end_page=None`, `excluded_headings=[]` en base, permettant à l'utilisateur de repartir de zéro sans devoir tout reconstruire manuellement.

```python
btn_reset = SecondaryButton("↩ Réinitialiser")
btn_reset.setToolTip("Remettre la délimitation à zéro (tout le document)")
btn_reset.clicked.connect(self._on_reset)
```

#### B5. 📊 Indicateur de progression tokens dans le modal Portée
**Fichier** : `document_scope_dialog.py`

Ajouter une mini barre de progression visuelle indiquant le pourcentage de la fenêtre de contexte LLM utilisée par la sélection actuelle (basé sur les tokens estimés vs la limite du modèle actif dans `SettingsService`).

```python
# Barre de tokens contexte (vert < 50%, jaune < 80%, rouge > 80%)
self.token_progress = QProgressBar()
self.token_progress.setMaximum(context_limit)
self.token_progress.setValue(selected_tokens)
```

#### B6. 🔗 Lien direct vers Délimitation depuis Portée
**Fichier** : `document_scope_dialog.py`

Ajouter dans le header de Portée un bouton `🔧 Modifier la délimitation` qui ouvre `DocumentDelimitationDialog(self.doc)` — permettant à l'utilisateur d'aller modifier les bornes globales sans devoir fermer la modale courante.

```python
btn_goto_delim = SecondaryButton("🔧 Délimitation")
btn_goto_delim.setToolTip("Modifier la délimitation globale du document")
btn_goto_delim.clicked.connect(self._open_delimitation_dialog)
```

---

## User Review Required

> [!IMPORTANT]
> **B2 — "Vue Finale Assemblée" dans Délimitation** : dans Délimitation, la "vue finale" représente les chunks *après* la sauvegarde, donc un état futur (pas encore en BDD). L'assemblage sera fait à partir de `_all_chunks` filtré selon les cases cochées. Est-ce bien ce que tu veux ? Ou préfères-tu garder uniquement la vue source dans Délimitation ?

> [!IMPORTANT]
> **B5 — Indicateur de tokens** : nécessite de connaître la limite du modèle LLM actif (`SettingsService.get("ai/context_limit")`). Si cette valeur n'est pas configurée, le widget se comporterait comment ? (masqué, ou avec une valeur par défaut de 128k ?)

> [!WARNING]
> **B4 — Réinitialiser** : l'action supprime définitivement `excluded_headings` et les bornes en BDD. Faut-il une confirmation (`QMessageBox`) avant de réinitialiser ?

---

## Open Questions

> [!IMPORTANT]
> **Priorité** : dans quelle ordre veux-tu implémenter ces améliorations ? Je suggère de commencer par les améliorations UI (A1→A6) qui sont rapides, puis les fonctionnalités (B1, B2, B6 en priorité haute, B3→B5 en priorité moyenne).

> [!IMPORTANT]
> **A3 — Diagnostic** : tu veux conserver le badge "⚠️ Quasi vide" pour les sections feuilles (chapitres terminaux), ou le supprimer entièrement et laisser seulement le compteur de mots ? Le badge est utile pour détecter des chapitres très courts (résumés, titres sans contenu), mais génère du bruit quand tout le document est normal.

---

## Proposed Changes

### Fichiers concernés

#### [MODIFY] `delimitation_dialog.py`
- `SectionRowWidget.__init__`: A2 (couleurs badges), A3 (is_leaf filtering), A4 (hauteur + indentation)
- `DocumentDelimitationDialog.__init__` / UI: A1 (header condensé), A5 (pill buttons), B2 (Vue Finale Assemblée), B4 (bouton Reset)
- `DocumentPreviewWidget.jump_to_heading`: B3 (surbrillance)
- Nouveau widget `_build_filter_row()`: B1 (barre de filtre)

#### [MODIFY] `document_scope_dialog.py`
- `_build_ui`: A1 (header condensé), A5 (pill buttons), A6 (footer badges KPI), B1 (barre de filtre), B5 (barre tokens), B6 (lien vers Délimitation)
- `_update_kpi`: A6 (badges visuels tokens/mots/sections)

---

## Verification Plan

### Automated Tests
```bash
uv run pytest tests/ui/test_document_selection_flow.py -v   # 21 tests
uv run pytest tests/services/audit/test_delimitation_coverage.py tests/ui/test_documents_view.py -v  # 13 tests
uv run ruff check --fix . && uv run ruff format .
uv run mypy src/ankiforge
uv run bandit -c pyproject.toml -r src/
```

### Manual Verification (screenshots avant/après)
```bash
QT_QPA_PLATFORM=offscreen ANKIFORGE_ENV=testing uv run python script/capture_dialogs.py temp/screens/after/
```

- Vérifier que l'arborescence reste lisible sur un document avec 20+ sections
- Vérifier que la barre de filtre masque/affiche correctement les items
- Vérifier que la surbrillance Markdown fonctionne en mode texte
- Vérifier que le bouton Reset ouvre bien une confirmation

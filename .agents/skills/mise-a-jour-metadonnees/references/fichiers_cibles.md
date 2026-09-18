# Référence : Fichiers Cibles & Patterns de Détection

Ce fichier documente la structure attendue de chaque fichier de métadonnées, les sections à
maintenir et les commandes grep permettant de détecter les désynchronisations.

---

## 1. `GEMINI.md`

**Structure attendue :**
- `## 🎯 Rôle et Identité` — description de l'agent superviseur
- `## 🧠 Workflow et Context Compaction` — règles d'activation des skills
- `## 🧰 Skills Techniques & Maquettage` — **liste des skills avec chemin**
- `## 🗺️ Règles Métier & Architecture Technique Actuelle` — **20 règles numérotées**

**Détection de désync :**
```bash
# Skills dans .agents/ non référencés dans GEMINI.md
for skill in .agents/skills/*/; do
  name=$(basename "$skill")
  grep -q "$name" GEMINI.md || echo "⚠️ Skill non référencé dans GEMINI.md : $name"
done

# Comptage des règles actuelles
grep -cE "^\d+\. \*\*" GEMINI.md
```

**Sections à mettre à jour :**
- Ajouter un skill → `## 🧰 Skills Techniques` : `- 🔖 **Nom** : \`.agents/skills/<name>/SKILL.md\``
- Ajouter une règle → `## 🗺️ Règles Métier` : numéroter séquentiellement, conserver le style bold + description détaillée

---

## 2. `AGENTS.md`

**Structure attendue :**
- `## Project Overview` — description 1 ligne
- `## Key Commands` — bloc bash avec toutes les commandes `uv run`
- `## Architecture Highlights` — bullets des piliers techniques
- `## Testing Constraints (Critical)` — règles de test (LLM mocks, Qt headless)
- `## Code Conventions (Enforced)` — ruff, mypy, pre-commit
- `## Key Files / Entry Points` — fichiers clés `src/ankiforge/`
- `## CI/CD Pipeline` — jobs GitHub Actions
- `## Environment Variables` — `.env`, flags CLI
- `## Agent Skills Catalog (.agents/skills/)` — catalogue des 15 compétences spécialisées
- `## Documentation References` — liens vers GEMINI.md, AGENTS.md, copilot-instructions, skills, DESIGN.md, docs/

**Détection de désync :**
```bash
# Comptage réel des tests vs AGENTS.md
ACTUAL=$(uv run pytest --collect-only -q 2>/dev/null | tail -1 | grep -oE "[0-9]+" | head -1)
DOCUMENTED=$(grep -oE "all [0-9]+" AGENTS.md | grep -oE "[0-9]+")
[ "$ACTUAL" != "$DOCUMENTED" ] && echo "⚠️ Tests : réel=$ACTUAL, documenté=$DOCUMENTED"

# Nouvelles commandes dans pyproject.toml non dans AGENTS.md
grep -A1 "\[project.scripts\]" pyproject.toml | grep "=" | awk -F= '{print $1}' | while read cmd; do
  grep -q "$cmd" AGENTS.md || echo "⚠️ Commande '$cmd' absente de AGENTS.md"
done

# Fichiers clés récents non documentés
find src/ankiforge -name "*.py" -newer AGENTS.md -not -path "*/__pycache__/*" | head -10
```

**Sections à mettre à jour :**
- Compteur tests : `all 146+ tests` → mettre à jour le chiffre
- Nouveau fichier clé : ajouter dans `## Key Files / Entry Points`
- Nouvelle commande : ajouter dans `## Key Commands`

---

## 3. `DESIGN.md`

**Structure attendue (138 lignes) :**
- `# PARTIE 1 : Référentiel des Tokens & Standards par Composant`
  - `## 1.1 Matrice de Correspondance` — **tableau des widgets avec tokens**
  - autres sections tokens (1.2, 1.3...)
- `# PARTIE 2 : Inventaire des Thèmes & Layouts`
  - 12 familles de thèmes bivalentes (24 thèmes total)
  - 4 layouts
- `# PARTIE 3 : ...` (si applicable)

**Détection de désync :**
```bash
# Classes QWidget custom non documentées dans DESIGN.md
grep -rInE "^class \w+\(Q(Widget|Dialog|Frame|MainWindow)\)" src/ankiforge/ui/ --include="*.py" \
  | grep -oE "class \w+" | awk '{print $2}' | while read cls; do
    grep -q "$cls" DESIGN.md || echo "⚠️ Widget '$cls' non documenté dans DESIGN.md"
  done

# Thèmes dans theme.py non listés dans DESIGN.md
grep -oE '"[a-z_]+"' src/ankiforge/ui/theme.py | sort -u | while read theme; do
  grep -q "$theme" DESIGN.md || echo "⚠️ Thème $theme absent de DESIGN.md"
done
```

**Format d'entrée pour un nouveau widget dans §1.1 :**
```
| **NomWidget** | `NomWidget`, `QBaseClass[role="..."]` | Propriété | `token_semantique` | Description & règle métier |
```

---

## 4. `docs/Dossier_architecture/07_inventaire_composants_ui.md`

**Structure attendue :**
- `## 1. Composants Fondamentaux (src/ankiforge/ui/components/)` — fondations, structure, sélecteurs
- `## 2. Smart Widgets Métier (src/ankiforge/ui/widgets/)` — widgets spécialisés par catégorie
- `## 3. Boîtes de Dialogue Métier (src/ankiforge/ui/dialogs/)` — dialogues

**Détection de désync :**
```bash
# Fichiers dans ui/widgets/ non mentionnés dans l'inventaire
for f in src/ankiforge/ui/widgets/*.py; do
  base=$(basename "$f")
  grep -q "$base" docs/Dossier_architecture/07_inventaire_composants_ui.md \
    || echo "⚠️ $base absent de 07_inventaire_composants_ui.md"
done

# Idem pour ui/components/
for f in src/ankiforge/ui/components/*.py 2>/dev/null; do
  base=$(basename "$f")
  grep -q "$base" docs/Dossier_architecture/07_inventaire_composants_ui.md \
    || echo "⚠️ $base absent de 07_inventaire_composants_ui.md"
done
```

**Format d'entrée pour un nouveau widget :**
```markdown
  * `nouveau_widget.py` : Description courte du rôle et de la fonctionnalité.
```

---

## 5. `docs/Dossier_architecture/08_plan_implementation_global.md`

**Structure attendue :**
- Sections numérotées `## N. Nom de la Vue / Module` — une par vue/module
- Chaque section commence par `* **État Actuel :** ✅/🔄/❌`
- Sous-bullets détaillant les capacités implémentées

**Statuts autorisés :**
- `✅ **Opérationnel & Validé**` — testé et fonctionnel
- `🔄 **En cours**` — développement en cours
- `❌ **Non implémenté**` — planifié mais pas encore fait

**Mise à jour typique :**
Quand une feature passe à ✅, ajouter le détail des capacités sous forme de bullets indentés
avec le même niveau de détail que les sections existantes.

---

## 6. `docs/Dossier_architecture/03_modele_donnees_synchro.md`

**Détection de désync :**
```bash
# Nouveaux modèles Peewee non documentés
grep -rInE "^class \w+Model\(BaseModel\)" src/ankiforge/database/ --include="*.py" \
  | grep -oE "class \w+Model" | awk '{print $2}' | while read model; do
    grep -q "$model" docs/Dossier_architecture/03_modele_donnees_synchro.md \
      || echo "⚠️ Modèle '$model' non documenté dans 03_"
  done
```

---

## 7. `.agents/skills/*.md`

**Règles de cohérence :**
- Tout nouveau fichier `SKILL.md` dans `.agents/skills/` doit être référencé dans `GEMINI.md` ET dans `AGENTS.md`.
- Le `name` dans le frontmatter YAML doit correspondre au nom du dossier (kebab-case).
- La `description` doit comporter des déclencheurs explicites (`Use when the user asks to...`).
- Chaque skill doit avoir une section `## ⛔ Ne PAS utiliser ce skill si...`.
- `.github/copilot-instructions.md` doit référencer `.agents/skills/` et `AGENTS.md`.

**Détection de désync :**
```bash
# Vérification globale automatisée de l'ensemble du parc de skills et des fichiers de référence
uv run python .agents/skills/mise-a-jour-metadonnees/scripts/auditer_coherence_skills.py
```

**Scoring de maturité & rédaction :** `grille_evaluation.md` (5 axes /20, rangs A-D) et
`guide_redaction_skills.md` (modèle canonique de SKILL.md) dans `references/` de ce skill.

# Vérification frontmatter YAML de chaque skill
for skill in .agents/skills/*/SKILL.md; do
  python3 -c "
import yaml, pathlib, sys
content = pathlib.Path('$skill').read_text()
parts = content.split('---')
if len(parts) < 3:
    print(f'❌ Frontmatter manquant : $skill')
    sys.exit(0)
try:
    data = yaml.safe_load(parts[1])
    if 'name' not in data or 'description' not in data:
        print(f'⚠️ Frontmatter incomplet : $skill (name ou description manquant)')
except Exception as e:
    print(f'❌ YAML invalide : $skill : {e}')
" 2>/dev/null
done
```

---

## 8. `README.md` & `PRODUCT.md`

**README.md** : documentation publique orientée utilisateur final. Mettre à jour uniquement
pour les features visibles par l'utilisateur (nouvelles vues, nouvelles commandes, changements
de comportement notable).

**PRODUCT.md** : description produit haut niveau (3 piliers, cas d'usage, personas).
Mettre à jour uniquement pour les évolutions de vision produit ou l'ajout d'un pilier majeur.

**Détection de désync :**
Ces fichiers ne sont pas automatisables — baser la mise à jour sur le contexte fourni par
l'utilisateur ou `git diff HEAD` pour identifier les features significatives.

---

## 9. `pyproject.toml` → cohérence avec `AGENTS.md`

**Sections à surveiller dans pyproject.toml :**
- `[project.scripts]` → commandes `uv run <cmd>` → `AGENTS.md ## Key Commands`
- `[project.dependencies]` → dépendances runtime → `AGENTS.md ## Architecture Highlights`
- `[dependency-groups]` → groupes dev/docs/build → `GEMINI.md règle 10`

```bash
# Voir les scripts exposés
grep -A5 "\[project.scripts\]" pyproject.toml

# Voir les groupes de dépendances
grep -E "^\[dependency-groups" pyproject.toml
```

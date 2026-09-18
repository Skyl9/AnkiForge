# Grille d'Évaluation de la Qualité des Skills — AnkiForge 📐

Cette grille formalise les standards de qualité, de prompt engineering et d'architecture attendus pour chaque skill du dossier `.agents/skills/`.

---

## 🎯 Les 5 Dimensions d'Évaluation (Score /20)

### 1. Clarté & Efficacité du Déclencheur (*Triggering*) — 4 points
*Le modèle agentique sait-il exactement quand charger ce skill et quand s'en abstenir ?*

| Note | Critères |
| :---: | :--- |
| **4/4 (Optimal)** | Frontmatter YAML valide. Nom exact kebab-case correspondant au dossier. Description rédigée à la 3ème personne, débutant par un résumé du rôle et se poursuivant par `Use when the user asks to...` avec une liste riche de déclencheurs explicites (verbes d'action, expressions idiomatiques réelles, commandes courantes). Zéro collision avec d'autres skills. |
| **3/4 (Bon)** | Frontmatter valide, déclencheurs explicites présents, mais manque de variantes ou d'expressions synonymes. |
| **2/4 (Moyen)** | Description générique sans syntaxe `Use when...`, risque d'activation manquée ou involontaire. |
| **0/4 (Insuffisant)** | Frontmatter manquant, YAML corrompu, ou description vide. |

---

### 2. Divulgation Progressive (*Progressive Disclosure*) — 4 points
*Le skill évite-t-il la saturation de contexte (*Context Compaction*) de l'agent superviseur ?*

| Note | Critères |
| :---: | :--- |
| **4/4 (Optimal)** | `SKILL.md` compact (< 150 lignes), structuré en workflow clair. Les détails techniques exhaustifs, schémas, listes de tables ou règles secondaires sont déportés dans `references/` ou automatisés sous `scripts/`. L'agent ne charge que ce dont il a besoin. |
| **3/4 (Bon)** | `SKILL.md` un peu dense (150-250 lignes) mais bien structuré avec tables et sections nettes. |
| **2/4 (Moyen)** | Fichier monolithique (> 300 lignes) contenant du code brut ou des listes interminables saturant le contexte. |
| **1/4 (Insuffisant)** | Fichier éclaté sans logique ou absence de progressive disclosure. |

---

### 3. Rigueur Procédurale & Commandes CLI — 4 points
*Les consignes sont-elles directement actionnables, déterministes et vérifiables ?*

| Note | Critères |
| :---: | :--- |
| **4/4 (Optimal)** | Étapes numérotées précises. Commandes exactes prêtes à copier avec `uv run` (`uv run pytest -k ...`, `uv run ruff check ...`, `uv run mypy ...`). Critères de succès explicites à chaque étape. Sortie attendue clairement définie. |
| **3/4 (Bon)** | Procédure claire, commandes exactes mais critères de validation implicites. |
| **2/4 (Moyen)** | Consignes vagues ("vérifiez que tout fonctionne", "lancez les tests"), commandes sans options ou obsolètes. |
| **0/4 (Insuffisant)** | Commandes erronées, non adaptées à `uv` ou cassées. |

---

### 4. Conformité aux Standards & Écosystème AnkiForge — 4 points
*Le skill respecte-t-il l'architecture et les 20 règles de `GEMINI.md` ?*

| Note | Critères |
| :---: | :--- |
| **4/4 (Optimal)** | Respect absolu des règles : interdiction de `print()` (T20), typage strict mypy, isolation des tests (LLM 100% mockés, base SQLite mémoire partagée, Qt offscreen), transactions atomiques Peewee (`db.atomic()`), absence de couleurs hardcodées (`DESIGN.md`). |
| **3/4 (Bon)** | Parfait alignement sur les règles principales, mentionne les conventions du projet. |
| **2/4 (Moyen)** | Omet de rappeler les contraintes critiques d'isolation ou de logging. |
| **0/4 (Insuffisant)** | Contredit les règles de base du projet (ex: suggère d'utiliser `print()` ou d'appeler de vraies API en test). |

---

### 5. Garde-fous & Anti-patterns (*Negative Triggers*) — 4 points
*Le skill empêche-t-il l'agent d'agir de façon imprudente ou hors périmètre ?*

| Note | Critères |
| :---: | :--- |
| **4/4 (Optimal)** | Présence obligatoire d'une section `## ⛔ Ne PAS utiliser ce skill si...` identifiant les confusions possibles avec d'autres skills, les cas où l'opération est triviale ou destructive, et les prérequis nécessaires. |
| **3/4 (Bon)** | Section d'exclusion présente avec au moins 2 cas limites bien identifiés. |
| **2/4 (Moyen)** | Mises en garde dispersées dans le corps du texte sans section dédiée. |
| **0/4 (Insuffisant)** | Aucun garde-fou, risque élevé d'action destructive ou hors périmètre. |

---

## 🏆 Niveaux de Maturité

- **Rang A (18-20/20) — Expert / Production Ready** : Skill d'excellence, déclencheurs chirurgicaux, progressive disclosure exemplaire, scripts dédiés.
- **Rang B (14-17/20) — Opérationnel** : Skill solide et efficace, améliorations mineures possibles sur les triggers ou l'externalisation de références.
- **Rang C (10-13/20) — Perfectible** : Skill utile mais perfectible (triggers ambigus, commandes incomplètes, manque de garde-fous).
- **Rang D (< 10/20) — À refondre** : Manque de structure, YAML invalide ou risque de saturation / hallucination.

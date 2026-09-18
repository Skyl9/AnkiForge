# Gap Analysis — Analyse Réelle & Proposition de Nouveaux Skills

Ce référence transforme « proposer de nouveaux skills » (vague) en une méthode reproductible
fondée sur des **preuves** issues du code, des docs, des tests et de l'historique git.
Un skill ne se crée jamais sur une hypothèse : il se crée sur une récurrence démontrée.

---

## 1. Analyser réellement les skills existants (préalable obligatoire)

Avant de proposer quoi que ce soit, dépasser l'audit statique du script :

1. **Lire les vrais contenus** : chaque `SKILL.md` audité + ses `references/` + ses `scripts/`
   (pas seulement le frontmatter).
2. **Confronter au code réel** — un skill peut noter bien en statique et être obsolète :
   - chaque commande `uv run ...` doit exister dans `pyproject.toml` ;
   - chaque path fichier/dossier référencé doit exister ;
   - chaque inventaire cité (`DESIGN.md` §1.1, `03_modele_donnees_synchro.md`, `07_inventaire_composants_ui.md`)
     doit contenir les classes/modèles réels (`rg -n "^class" src/ankiforge/`);
   - les seuils (compteur de tests `AGENTS.md`) doivent matcher `uv run pytest --collect-only -q`.
3. **Cartographier les zones blanches** : pour chaque skill, noter les sujets adjacents évoqués
   dans la doc (`docs/Dossier_architecture/`, `PRODUCT.md`) mais **hors périmètre** du skill.

Commandes de croisement utiles :
```bash
uv run python .agents/skills/mise-a-jour-metadonnees/scripts/auditer_coherence_skills.py --json
grep -A5 '\[project.scripts\]' pyproject.toml
rg -n "^class (?!.*Test)" src/ankiforge/ --glob "*.py"
rg -ln "~/.ankiforge|profiles|apkg|colpkg|pdf|pptx|docx|youtube|ocr" src/ tests/ docs/ | sort
```

---

## 2. Sources de signaux pour de nouveaux skills

| # | Source | Détection |
|---|---|---|
| 1 | **Historique git thématique** | `git log --oneline -80 \| awk '{for(i=2;i<=NF;i++) printf "%s ", $i; print ""}' \| sort \| uniq -c \| sort -rn` → sujets récurrents |
| 2 | **Demandes utilisateur répétées** | Un même besoin exprimé ≥ 2-3 fois (sessions, messages, issues) |
| 3 | **Procédures manuelles multi-étapes** | Workflows décrits en prose dans les docs (ingestion, export, migration) = candidats à scripter |
| 4 | **Commandes `[project.scripts]` sans guide** | Script CLI exposé mais sans skill d'accompagnement |
| 5 | **Modules `08_plan_implementation_global.md` marqués ❌/🔄** | Périmètres prévus = besoins futurs de l'agent |
| 6 | **Tests/fixtures répétitifs** | `rg -l "profiles|migrate|import|export" tests/` → friction récurrente |

---

## 3. Critères d'admission (note d'éligibilité /7)

**Filtres obligatoires** (tous → sinon REJETÉ) :
- **A. Preuve de récurrence** : ≥ 3 occurrences réelles référencées (commits, fichiers, demandes).
- **B. Complexité réelle** : ≥ 3 étapes OU ≥ 2 fichiers distincts OU risque d'erreur destructif.
- **C. Non-couverture** : vérifier les descriptions des 13 skills → aucun ne couvre le domaine.

**Priorisation** (sans filtres, ça ne fait que classer) :
- **D. Gain agentique** (+2) : tâche que l'agent exécute fréquemment et mal à la main.
- **E. Périmètre stable** (+1) : sinon une simple doc suffit.
- **F. Alignement architecture** (+1) : touche un pilier (MCP, DAG, RAG, profils, export Anki...).

**Verdict** :
- **RECOMMANDÉ** : filtres A+B+C passés ET score ≥ 4/7.
- **EN ATTENTE** : 2 filtres sur 3 passés — re-prouver l'élément manquant avant réexamen.
- **REJETÉ** : un filtre manque ou tâche one-shot → documenter pourquoi (trace utile).

---

## 4. Fiche Candidat (obligatoire avant création)

```markdown
## Candidat : <nom-kebab-case>
- **Problème récurrent (preuves)** : commits/fichiers/demandes → critère A
- **Périmètre** : fichiers/processus concernés → critère B
- **Pourquoi un skill (vs script/doc)** : A/B/C détaillés
- **Triggers proposés** : description frontmatter prête (3e personne, `Use when the user asks to...`)
- **Références/scripts prévus** : comment rester sous 150 lignes
- **Collisions à surveiller** : skills aux triggers proches
- **Contre-arguments** (pourquoi ne PAS créer) : ...
- **Verdict** : RECOMMANDÉ / EN ATTENTE / REJETÉ (score /7)
```

---

## 5. Anti-génération (garde-fous)

- Jamais de nouveau skill sans section `## ⛔ Ne PAS utiliser ce skill si...` ni triggers explicites
  → l'audit statique le rejetterait.
- Ne pas créer pour une tâche **one-shot** ou un **script isolé** (une commande suffit).
- Ne pas dupliquer : `documentation-zensical` (doc), les 8 auditeurs spécialisés (code), `peewee-expert`,
  `mise-a-jour-metadonnees` (méta).
- Toute proposition validée par l'utilisateur est créée selon `guide_redaction_skills.md`,
  synchronisée (`GEMINI.md` + `AGENTS.md`) puis soumise au script d'audit → 0 erreur requis.
- La création se fait en §4.4 du skill et le candidat présenté d'abord à l'utilisateur.

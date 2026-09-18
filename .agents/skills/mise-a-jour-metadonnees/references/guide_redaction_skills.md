# Guide de Rédaction et de Conception des Skills — AnkiForge ✍️

Ce guide fournit le modèle canonique et les conventions d'écriture pour tout nouveau skill agentique créé dans `.agents/skills/`.

---

## 📁 Architecture Standard d'un Dossier Skill

```
.agents/skills/<nom-du-skill>/
├── SKILL.md                          # [Obligatoire] Instructions principales pour l'agent
├── references/                       # [Optionnel] Connaissances détaillées (Progressive Disclosure)
│   └── documentation_avancee.md
└── scripts/                          # [Optionnel] Scripts d'assistance exécutables
    └── verificateur_rapide.py
```

---

## 📄 Modèle Canonique de `SKILL.md`

```markdown
---
name: mon-nouveau-skill
description: >
  Rôle et description du skill rédigés à la 3ème personne.
  Use when the user asks to "verbe action 1", "expression 2", "commande 3",
  or needs to [cas d'usage précis].
---

# 🚀 Nom du Skill — AnkiForge

En tant qu'[Expert / Spécialiste du Domaine], ton rôle est de [mission claire].

## 1. Contexte & Périmètre
- **Périmètre couvert** : [Fichiers, modèles, vues ou processus concernés]
- **Principes directeurs** : [Règles clés de GEMINI.md applicables]

## 2. Procédure Pas-à-Pas
1. **Étape 1 : Diagnostic initial**
   \`\`\`bash
   uv run ...
   \`\`\`
2. **Étape 2 : Traitement / Correction**
   - Règle A...
   - Règle B...
3. **Étape 3 : Validation & Tests**
   \`\`\`bash
   uv run pytest tests/...
   \`\`\`

## 3. Restitution des Résultats
Structure attendue du rapport présenté à l'utilisateur :
- Résumé synthétique
- Tableau des constats
- Recommandations et prochaines étapes

## ⛔ Ne PAS utiliser ce skill si...
- L'utilisateur souhaite [autre tâche] → Utiliser le skill \`autre-skill\`
- La modification est triviale et ne requiert pas de procédure spécialisée.
```

---

## 💡 Règles d'Or de Rédaction

1. **Frontmatter YAML Strict** :
   - `name` doit correspondre exactement au nom du dossier en kebab-case (`a-z0-9-`).
   - `description` DOIT contenir des déclencheurs explicites réels précédés de `Use when the user asks to...`.
2. **Concision et Divulgation Progressive** :
   - Le fichier `SKILL.md` doit rester inférieur à 150 lignes (seuil de la grille de maturité — rang optimal).
   - Dès qu'un tableau ou une liste dépasse 30 lignes, déportez-le dans `references/<nom>.md` et indiquez à l'agent : *"Consulter `references/<nom>.md` pour le détail exhaustif."*
3. **Commandes Reproductibles** :
   - Toujours préfixer par `uv run` (`uv run pytest`, `uv run ruff`, `uv run mypy`).
   - Ne jamais supposer un environnement actif sans `uv`.
4. **Zéro `print()` dans les Scripts d'Assistance** :
   - Les scripts Python sous `scripts/` doivent utiliser `sys.stdout.write()` pour respecter la règle T20 de Ruff.
5. **Synchronisation avec l'Écosystème** :
   - Tout nouveau skill doit être immédiatement enregistré dans :
     - `GEMINI.md` (section *🧰 Skills Techniques*)
     - `AGENTS.md` (section *Agent Skills Catalog*)
     - `.github/copilot-instructions.md`

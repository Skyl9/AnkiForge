# 🔄 Protocole de Concaténation et Redirection des ADRs

Ce protocole définit la démarche pas à pas pour fusionner un ensemble d'ADRs fragmentés ou successifs en un ADR unique consolidé, tout en garantissant **zéro lien mort** dans le reste du dépôt.

---

## Les 6 Étapes Canoniques de Concaténation

### Étape 1 : Cartographie du Cluster et Choix de l'Hôte
1. Identifier les ADRs appartenant au même domaine thématique (ex: Thèmes, Raccourcis, MCP).
2. Choisir l'ADR cible :
   - Soit l'ADR le plus complet / récent de la série (ex: ADR 0034 pour le MCP),
   - Soit un nouvel ADR unifié portant un numéro suivant si la refonte forme un nouveau tout cohérent.
3. Soumettre la proposition à l'utilisateur via `ask_question`.

---

### Étape 2 : Rédaction de la Synthèse Consolidée
Dans l'ADR cible :
1. Rédiger une section claire intégrant les arbitrages absorbés (ex: `## 4. Historique et Fusion des Décisions Antérieures`).
2. Consigner de façon concise le contexte d'origine, le choix qui avait été fait et pourquoi il est aujourd'hui fusionné ou acté ainsi.
3. Conserver les choix architecturaux structurants (ne pas perdre la mémoire du « pourquoi »).

---

### Étape 3 : Scan Global des Références Existantes
Avant toute suppression, identifier chaque fichier du dépôt qui pointe vers le ou les ADRs à absorber.

Lancer la recherche :
```bash
# Via le script dédié du skill
uv run python .agents/skills/revue-adr/scripts/analyser_adrs.py --find-refs 0014

# Ou via git grep
git grep -i "0014"
git grep -i "ADR 0014"
git grep -i "ADR-0014"
```

Les fichiers typiquement concernés incluent :
- D'autres ADRs (`docs/adr/`)
- Les adaptateurs d'instructions (`AGENTS.md`, `GEMINI.md`, `CLAUDE.md`, `.github/copilot-instructions.md`)
- Les compétences agentiques (`.agents/skills/*/SKILL.md`)
- La documentation Zensical (`docs/Dossier_architecture/`, `docs/adr/`)
- Le glossaire (`CONTEXT.md`)
- Le code source Python sous `src/ankiforge/` (commentaires, docstrings)

---

### Étape 4 : Remplacement Chirurgical des Redirections
Mettre à jour chaque occurrence détectée :
1. Remplacer le numéro de l'ancien ADR par le numéro de l'ADR cible consolidé.
2. Si la référence ciblait un point précis, pointer vers l'ancre ou la sous-section dédiée (ex: `docs/adr/0034-...md#historique`).
3. Mettre à jour les textes explicatifs si la terminologie a changé.

---

### Étape 5 : Suppression Physique de l'ADR Absorbé
Une fois toutes les redirections effectuées et vérifiées :
```bash
rm docs/adr/XXXX-slug-absorbe.md
```

> [!IMPORTANT]
> Ne jamais supprimer un ADR sans avoir préalablement réécrit 100 % des liens et mentions le ciblant dans l'ensemble du dépôt.

---

### Étape 6 : Contrôles de Non-Régression
Valider l'intégrité globale du dépôt après la concaténation :
```bash
# 1. Vérifier la cohérence interne des compétences et liens ADR
uv run python .agents/skills/gouvernance-skills/scripts/auditer_coherence_skills.py

# 2. Vérifier la santé du registre ADRs
uv run python .agents/skills/revue-adr/scripts/analyser_adrs.py

# 3. Exécuter la porte de vérification canonique
uv run python script/verify.py
```

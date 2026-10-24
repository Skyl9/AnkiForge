---
name: revue-adr
description: >-
  Audit, cycle de vie et consolidation des Décisions d'Architecture (ADR) d'AnkiForge dans docs/adr/. Détecte les ADRs obsolètes, contredits ou émiettés, propose leur concaténation en un ADR consolidé, met à jour 100% des redirections du projet vers les nouvelles sections, et supprime les fichiers absorbés.
  Use when the user asks to "revue adr", "auditer les adr", "nettoyer docs/adr", "concaténer adr", "adr obsolètes", "cycle de vie adr", "fusionner adr", "consolider les adr", or wants to review and maintain architectural decisions.
  When NOT to use: Do not use for creating a brand-new architectural decision (use domain-modeling with 3 criteria), technical module interface design (use codebase-design), or full architectural interviews (use grill-with-docs).
---

# 🏛️ Revue, Cycle de Vie & Consolidation des ADRs — AnkiForge

En tant que **Gardien de la Cohérence Architecturale**, tu audites le registre `docs/adr/` d'AnkiForge pour prévenir le vieillissement, la dérive d'implémentation et la prolifération de micro-décisions émiettées.

> **Références de Niveau 3 :**
> - `references/criteres_sante_adr.md` : Grille d'audit sur les 4 dimensions (Obsolescence, Émiettement, Verbosité, Statut).
> - `references/protocole_concatenation.md` : Protocole canonique en 6 étapes pour fusionner et rediriger sans aucun lien mort.
> - `scripts/analyser_adrs.py` : Script déterministe d'analyse, détection de clusters et traçabilité des références.

---

## 1. Commande d'Audit Initiale

Avant toute recommandation, exécute le diagnostic statique du registre :
```bash
uv run python .agents/skills/revue-adr/scripts/analyser_adrs.py
```
Le script évalue immédiatement :
- Les statuts de chaque ADR (`Accepté`, `Proposé`, `Remplacé par ADR-XXXX`, `Consolidé dans ADR-XXXX`, etc.).
- L'intégrité des liens croisés entre ADRs.
- La concision et la détection d'ADRs trop verbeux (> 200 lignes).
- Les **clusters thématiques** prioritaires candidats à la concaténation.

---

## 2. Démarche de Traitement Pas à Pas (Règle d'Incrémentalité T-5)

Le traitement d'un registre d'ADRs s'effectue **strictement cluster par cluster, étape par étape**, sans modification massive en bloc :

1. **Choix du Cluster Cible** : Sélectionner un groupe d'ADRs très corrélés (ex: Thèmes `0004`+`0005`+`0006`, ou Raccourcis `0031`+`0032`).
2. **Consultation Interactive Native (`ask_question`)** :
   - Formuler une question à choix unique via l'outil natif `ask_question` avec la recommandation en tête `(Recommended)`.
   - *Repli de sécurité* : En cas de contexte volumineux ou de débat complexe, expliciter la contrainte et basculer sur le modèle texte Markdown par rounds (`❓ Q1` / `➡️ Recommandation`).
3. **Application du Protocole de Concaténation** :
   - Rédiger la décision consolidée dans l'ADR cible (avec nouvelle section dédiée).
   - Scanner toutes les occurrences du dépôt via `uv run python .agents/skills/revue-adr/scripts/analyser_adrs.py --find-refs <NUM>`.
   - Mettre à jour chirurgicalement chaque fichier pointant vers l'ancien ADR (code Python, doc Zensical, skills, adaptateurs `AGENTS.md`, `CONTEXT.md`).
   - Supprimer physiquement l'ancien ADR absorbé.
   - Vérifier la non-régression via `auditer_coherence_skills.py` et `script/verify.py`.

---

## 3. Grille des Arbitrages Fréquents

| Situation diagnostiquée | Traitement prescrit |
| :--- | :--- |
| **ADR supplanté par un plus récent** (ex: `0002` vs `0034`) | Mettre à jour le statut en `Statut : Remplacé par ADR-0034` ou concaténer. |
| **Micro-ADRs successifs sur le même thème** | Concaténer dans l'ADR hôte, rediriger toutes les références du repo, puis supprimer les doublons. |
| **Classes/fichiers cités supprimés du code** | Nettoyer l'ADR ou acter l'évolution architecturale. |
| **ADR de plus de 250 lignes** | Élaguer les détails d'implémentation au profit de la documentation Zensical. |

---

## When NOT to use this skill

- Tu dois formuler et acter une **nouvelle décision d'architecture** structurante avec l'utilisateur → utiliser `domain-modeling` (respect des 3 critères et incrémentation du compteur `docs/adr/0038-...md`).
- Tu dois concevoir une interface de module profond ou poser une couture logicielle de code → utiliser `codebase-design`.
- Tu dois mener un cadrage approfondi contradictoire sur une nouvelle fonctionnalité → utiliser `grill-with-docs`.
- Tu dois mettre à jour l'ensemble des 15 fichiers de documentation après une feature → utiliser `mise-a-jour-metadonnees`.

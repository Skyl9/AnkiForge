---
name: doubt-driven-development
description: >-
  Soumet chaque proposition technique ou décision de l'utilisateur à une critique active et systématique ("penser contre") avant validation. Identifie les hypothèses implicites, les effets de bord cachés, les défaillances silencieuses et les incohérences avec le codebase. Use when the user asks to "penser contre moi", "critiquer ma proposition", "revue contradictoire", "adversarial review", "doubt-driven-development", or when making high-stakes architectural or security-critical choices. When NOT to use: Do not use for mechanical refactorings (renaming, formatting), one-line changes, or when the user explicitly requests speed over verification.
---

# Doubt-Driven Development — Critique Active ("Penser Contre")

Une réponse affirmée avec assurance n'est pas nécessairement exacte. Dans les sessions longues, l'accumulation de contexte transforme insensiblement de simples hypothèses en prétendus « faits ». Le développement guidé par le doute matérialise une contre-revue dans un contexte vierge — biaisée pour **réfuter** plutôt que valider — avant qu'une décision structurante ne soit figée.

Ce skill a pour fonction explicite de **penser contre l'utilisateur** : critiquer activement ses propositions, chercher ce qui claque, et proposer des améliorations concrètes. Ce n'est pas une validation bienveillante, c'est un stress-test.

> **Références** :
> - `references/orchestration-patterns.md` : Règles d'orchestration (les sous-agents n'invoquent pas d'autres sous-agents).
> - `references/adversarial-review-guide.md` : Guide d'escalade cross-modèle et grille de classification.

## Périmètre d'Application

Une proposition est **non-triviale** dès lors qu'elle :

- Introduit ou altère des embranchements logiques.
- Traverse une frontière entre modules ou services.
- Repose sur des garanties non vérifiables par le compilateur (concurrence, idempotence, ordre).
- Possède un rayon d'impact irréversible (déploiement, migration BDD, changement d'API publique).

## Quand NE PAS utiliser ce skill

⛔ **Interdits bloquants** :

- Opérations mécaniques (renommage, formatage, déplacement de fichiers).
- Modifications triviales d'une ligne dont la correction est évidente.
- L'utilisateur a expressément demandé la vitesse d'exécution plutôt que la vérification approfondie.
- Relecture globale post-implémentation d'une branche entière → utiliser `/code-review`.
- Propositions déjà validées par l'utilisateur après une première passe de ce skill (éviter la boucle infinie de relecture).

## Processus en 5 Étapes

### Étape 1 — CLAIM : Nommer l'affirmation

Formuler l'affirmation de l'utilisateur en 2 ou 3 lignes, avec son enjeu.

```
CLAIM: "Le pipeline DAG délégué à l'agent externe MCP retourne le prompt de persona à chaque étape pour éviter le drift."
WHY THIS MATTERS: Cela change le modèle d'exécution de l'orchestrateur et introduit une dépendance réseau à chaque étape.
```

### Étape 2 — EXTRACT : Isoler l'unité minimale

Transmettre uniquement l'**artefact** (proposition, diff, spécification) et le **contrat** (invariants ou spec). Ne jamais transmettre le raisonnement ou la CLAIM : donner sa conclusion biaise le relecteur.

### Étape 3 — DOUBT : Prompt contradictoire

Transmettre au relecteur un mandat contradictoire explicite. Exemple :

> "Revue contradictoire. Identifie les défaillances, incohérences et hypothèses implicites dans cet artefact. Pars du principe que l'auteur est trop confiant. Cherche les cas limites non gérés, les violations du contrat existant, et les effets de bord sur les composants voisins. Liste chaque point sous forme : [Risque / Conséquence / Correction suggérée]."

### Étape 4 — RECONCILE : Arbitrer les retours

Classer chaque remarque selon la préséance :

1. **Contrat ambigu** → reformuler le contrat.
2. **Défaut actionnable** → corriger l'artefact.
3. **Compromis assumé** → documenter explicitement (avantages / inconvénients / verdict).
4. **Bruit / Faux positif** → contexte manquant, rejeter avec justification.

### Étape 5 — STOP : Fin de boucle

S'arrêter dès que :
- Les remarques deviennent mineures ;
- 3 cycles maximum sont atteints (escalader vers l'humain au-delà) ;
- L'utilisateur valide explicitement la version corrigée.

## Garde-fous Procéduraux

Avant de livrer une critique, vérifier systématiquement :

- [ ] L'artefact a été lu sur le disque (pas de présomption sur son contenu).
- [ ] Les fichiers cibles mentionnés existent et leur contenu a été inspecté.
- [ ] Les ADR et `CONTEXT.md` applicables ont été consultés.
- [ ] La critique identifie au moins un risque concret (sinon, elle est inutile).
- [ ] Chaque risque s'accompagne d'une correction ou d'un compromis documenté.

## Format de Restitution

La critique doit être rendue sous forme de tableau :

| # | Point critiqué | Risque / Inconvénient | Correction suggérée | Statut (accepte / refuse / compromis) |

Puis un **verdict final** clair : accepter, accepter avec réserves, ou refuser et proposer une alternative.

## Exemple d'application

L'utilisateur propose : « Refondre l'outil MCP `trigger_pipeline_run` pour qu'il retourne le prompt de la persona à chaque étape. »

Critique active :
1. **Latence** : chaque étape ajoute un aller-retour MCP → acceptable pour 6-7 étapes, mais non négligeable à l'échelle.
2. **Perte d'autonomie du DAG** : l'orchestrateur devient passif → trade-off assumé si l'agent externe maîtrise la génération.
3. **Pas d'écriture BDD directe** → le résultat doit aller dans le Garde-Fou MCP (staging), pas en base directe.
4. **Interface instable** → contrat texte à formaliser (prompt retourné, contenu attendu, statut).

Verdict : **Accepter avec réserves**, sous réserve de formaliser le contrat d'API et le timeout par étape.

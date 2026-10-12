---
name: doubt-driven-development
description: >-
  Soumet chaque décision technique ou diff non-trivial à une contre-revue contradictoire dans un contexte neutre avant validation. Dépiste les hypothèses implicites, les effets de bord cachés et les défaillances silencieuses.
  Use when the user asks to "douter de cette décision", "stress-tester l'implémentation", "revue contradictoire", "adversarial review", "doubt-driven-development", or when making high-stakes architectural or security-critical choices.
  When NOT to use: Do not use for mechanical refactorings (renaming, formatting), one-line changes, or when the user explicitly requests speed over verification.
---

# Doubt-Driven Development

Une réponse affirmée avec assurance n'est pas nécessairement exacte. Dans les sessions longues, l'accumulation de contexte transforme insensiblement de simples hypothèses en prétendus « faits ». Le développement guidé par le doute matérialise une contre-revue dans un contexte vierge — biaisée pour **réfuter** plutôt que valider — avant qu'une décision structurante ne soit figée.

> **Références de référence** :
> - `references/orchestration-patterns.md` : Règles d'orchestration (les sous-agents n'invoquent pas d'autres sous-agents).
> - `references/adversarial-review-guide.md` : Guide d'escalade cross-modèle et grille de classification.

## Périmètre d'Application

Une décision est **non-triviale** dès lors qu'elle :
- Introduit ou altère des embranchements logiques.
- Traverse une frontière entre modules ou services.
- Repose sur des garanties non vérifiables par le compilateur (concurrence, idempotence, ordre).
- Possède un rayon d'impact irréversible (déploiement, migration BDD, changement d'API publique).

## Processus en 5 Étapes

```
Cycle du doute :
- [ ] Étape 1 : CLAIM — Formuler explicitement la décision et son enjeu
- [ ] Étape 2 : EXTRACT — Isoler l'artefact et son contrat (sans explications)
- [ ] Étape 3 : DOUBT — Invoquer la contre-revue avec un prompt contradictoire
- [ ] Étape 4 : RECONCILE — Classer chaque observation face au texte de l'artefact
- [ ] Étape 5 : STOP — Vérifier les conditions d'arrêt (3 cycles max ou résolu)
```

### 1. CLAIM — Nommer l'affirmation
Formuler l'affirmation en 2 ou 3 lignes :
`CLAIM: "La couche de cache est thread-safe sous la charge spécifiée."`
`WHY THIS MATTERS: Une concurrence corrompt les données utilisateur.`

### 2. EXTRACT — Isoler l'unité minimale
Transmettre uniquement l'**artefact** (diff ou proposition) et le **contrat** (invariants ou spec). Ne jamais transmettre le raisonnement ou la claim : donner sa conclusion biaise le relecteur.

### 3. DOUBT — Prompt contradictoire
Transmettre au relecteur un mandat contradictoire :
*"Revue contradictoire. Identifie les défaillances et incohérences dans cet artefact. Pars du principe que l'auteur est trop confiant. Cherche les hypothèses implicites, les cas limites non gérés et les violations du contrat."*

### 4. RECONCILE — Arbitrer les retours
Classer chaque remarque selon la préséance :
1. *Contrat ambigu* (reformuler le contrat).
2. *Défaut actionnable* (corriger l'artefact).
3. *Compromis assumé* (documenter explicitement).
4. *Bruit / Faux positif* (contexte manquant).

### 5. STOP — Fin de boucle
S'arrêter dès que les remarques deviennent mineures, après 3 cycles maximum (escalader vers l'humain), ou sur validation explicite de l'utilisateur.

## When NOT to use this skill

- Opérations mécaniques (renommage, formatage, déplacement de fichiers).
- Modifications triviales d'une ligne dont la correction est évidente.
- L'utilisateur a expressément demandé la vitesse d'exécution plutôt que la vérification approfondie.
- Relecture globale post-implémentation d'une branche entière → utiliser `/code-review`.

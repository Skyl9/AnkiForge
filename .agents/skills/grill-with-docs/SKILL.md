---
name: grill-with-docs
description: >-
  Interview contradictoire rigoureuse pour cadrer une idée, explorer l'arbre de décision et affûter une fonctionnalité dans AnkiForge, avec mise à jour du glossaire CONTEXT.md et enregistrement d'ADRs.
  Use when the user asks to "grill-with-docs", "grilling", "grill-me", "grille-moi", "cadrer l'idée", "cadrer la fonctionnalité", "affûter le besoin", "relentless interview", or wants an architectural interview with paper trail.
  When NOT to use: Do not use when the idea is already fully decided and ready for specification (use to-spec) or coding (use implement).
disable-model-invocation: true
---

# 🎯 Grill With Docs — Cadrage & Affûtage d'Architecture

Mène une interview méthodique, contradictoire et rigoureuse pour affûter une idée ou une évolution d'AnkiForge, modéliser l'espace des choix et maintenir en continu une trace écrite vérifiable dans le dépôt.

---

## 1. Modélisation de l'Arbre de Décision

1. **Décomposition** : modéliser la réflexion sous la forme d'un **arbre de décision** où chaque choix conditionne les arbitrages aval.
2. **Identification de la frontière** : la **frontière** regroupe toutes les questions dont les prérequis sont déjà établis et qui peuvent être tranchées *immédiatement*, sans présumer des décisions futures.
3. **Faits vs Décisions** :
   - Les **faits** relèvent de la responsabilité de l'agent : chercher préalablement dans le code source (`src/ankiforge/`), les tests et les ADRs existants. Ne jamais interroger l'utilisateur sur un fait vérifiable par l'agent.
   - Les **décisions** relèvent de l'utilisateur.

---

## 2. Interaction Native & Modes de Questionnement

### Mode Nominal : Commande Native Interactive (`ask_question`)
Par défaut dans l'environnement Antigravity, poser l'ensemble des questions de la frontière active en un seul appel via l'outil natif interactif **`ask_question`** :
- Fournir pour chaque question des options mutuellement exclusives (ou multi-sélection si pertinent).
- Placer systématiquement en tête la recommandation argumentée de l'agent préfixée par `(Recommended)`.

### Mode de Repli : Contexte Volumineux ou Réponse Ouverte
Si la fenêtre de contexte de la conversation est déjà très volumineuse (risque d'amnésie ou de troncature), ou si une question requiert une analyse libre approfondie non réductible à un QCM :
1. **Notifier explicitement l'utilisateur** :
   > ⚠️ *Le contexte de session étant volumineux (ou les arbitrages nécessitant une réflexion ouverte), les questions sont formulées au format texte structuré pour préserver l'espace de travail.*
2. **Formuler les questions au format Markdown structuré par rounds** :
   ```markdown
   ❓ **Q1** - **<titre de la décision>** : <contexte, enjeu et options envisagées>

   ➡️ **Recommandation** : <choix préconisé par l'agent et justification technique>

   ---

   ❓ **Q2** - **<titre de la décision>** : <contexte, enjeu et options envisagées>

   ➡️ **Recommandation** : <choix préconisé par l'agent et justification technique>
   ```

3. **Itération** : à chaque round résolu, recalculer la frontière et itérer jusqu'à épuisement complet de l'arbre.

---

## 3. Persistance & Trace Écrite Continue

Dès qu'un palier de décision est validé par l'utilisateur :
- **Glossaire métier** : enrichir ou rectifier immédiatement `CONTEXT.md` à la racine pour figer les termes canoniques stabilisés (et bannir les faux synonymes sous `_Avoid_`).
- **Décisions d'architecture (ADR)** : consigner les choix structurants dans un nouveau document `docs/adr/0038-titre-de-l-adr.md` (incrémenter le numéro séquentiel à 4 chiffres suivant le dernier ADR existant).

---

## When NOT to use this skill

- **Ne JAMAIS utiliser d'emblée lorsqu'un ticket ou une demande affiche « rechercher »** (investigation documentaire, état de l'art, veille technique) : interdiction formelle de lancer un `/grill-with-docs` tout de suite. Demander d'abord le sujet précis de la recherche et apporter la documentation existante adaptée (via `/research` et recherche web) avant tout cadrage ultérieur.
- Ne pas utiliser lorsque l'idée est déjà totalement arrêtée et prête pour spécification technique structurée → utiliser `/to-spec`.
- Ne pas utiliser pour découper une spécification validée en tickets traçables → utiliser `/to-tickets`.
- Ne pas utiliser pour implémenter directement du code en TDD → utiliser `/implement`.
- Ne pas utiliser pour auditer la qualité du code statique → utiliser `audit-qualite-code`.

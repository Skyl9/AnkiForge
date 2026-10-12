---
name: handoff
description: >-
  Compresse la conversation courante en un document de transfert (handoff) portable pour permettre à un nouvel agent ou une nouvelle session de reprendre le travail.
  Use when the user asks to "handoff", "passer la main", "résumé pour prochaine session", "préparer le transfert", or wants to compact the conversation into a handoff document.
  When NOT to use: Do not use if you are continuing work in the same session without context boundary (just continue).
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

# Handoff — Transfert de Contexte Inter-Sessions

Rédige un document de synthèse structuré permettant à un agent dans une session vierge de reprendre immédiatement le travail sans perte d'information.

## Consignes

1. **Emplacement** : enregistrer dans le répertoire temporaire du système (`/tmp` ou équivalent), jamais à la racine du projet.
2. **Contenu ciblé** :
   - Objectif poursuivi et état actuel d'avancement.
   - Décisions déjà arbitrées et références vers les fichiers réels (`CONTEXT.md`, tickets Obsidian, ADRs).
   - Section **« Compétences recommandées »** indiquant explicitement les skills à activer pour la suite.
3. **Sécurité & Hygiène** : masquer tout secret ou clé d'API (`<REDACTED>`).
4. Ne pas dupliquer le contenu déjà committé ou formalisé dans les tickets ; utiliser des chemins relatifs ou liens.

## When NOT to use this skill

- Ne pas utiliser si le travail se poursuit directement dans la session courante sans dépassement de contexte.
- Ne pas utiliser pour rédiger un ticket de travail permanent → utiliser `/to-tickets`.
- Ne pas utiliser pour consigner une décision d'architecture → utiliser `/domain-modeling` (ADR).

---
name: to-questionnaire
description: >-
  Transforme une question ou décision non résolue en un questionnaire Markdown structuré destiné à être rempli par un tiers ou un expert du domaine.
  Use when the user asks to "to-questionnaire", "rédiger un questionnaire", "préparer un questionnaire", "interviewer un expert", or wants to turn an unresolved question into a questionnaire for someone else.
  When NOT to use: Do not use when the user can resolve the question themselves through code exploration or interview (use grill-with-docs).
disable-model-invocation: true
---

# To Questionnaire — Questionnaire Asynchrone pour Tiers

Transforme une question dont la réponse échappe à l'utilisateur et à l'agent en un **questionnaire ciblé** prêt à être transmis à un expert, un collègue ou un décideur tiers.

## Processus

1. **Identifier le destinataire** : rôle, expertise et niveau de contexte requis.
2. **Identifier les informations indispensables** : les faits ou décisions bloquantes précises dont l'utilisateur a besoin.
3. **Rédiger le questionnaire** sous forme d'un fichier Markdown structuré (`to-questionnaire-<slug>.md`).
   - Contexte court d'orientation.
   - Questions thématiques prioritaires (une seule idée par question, avec mention de *pourquoi cela compte*).
   - Zone de réponse prête à l'emploi (`> `).

## When NOT to use this skill

- L'information peut être déduite de la base de code ou de la documentation existante → utiliser `/research` ou chercher directement.
- L'utilisateur possède les éléments mais a besoin d'arbitrer → utiliser `/grill-with-docs`.
- La décision est déjà prise et nécessite d'être formellement spécifiée → utiliser `/to-spec`.

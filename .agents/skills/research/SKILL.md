---
name: research
description: >-
  Délègue l'investigation documentaire et l'analyse de sources primaires fiables à un sous-agent d'arrière-plan avec restitution sous forme de synthèse Markdown.
  Use when the user asks to "rechercher", "investiguer", "documenter les options", "research", or wants to delegate investigation of primary sources to a background agent.
  When NOT to use: Do not use for quick targeted lookups you can do yourself in one turn or for coding directly.
---

# Research — Investigation Documentaire Autonome

Délègue un travail de lecture et d'analyse approfondie à un **sous-agent de recherche**, permettant à la session principale de poursuivre d'autres tâches en parallèle.

## Mission du Sous-Agent

1. **Sources primaires exclusivement** : consulter la documentation officielle, le code source amont, les spécifications normatives ou les APIs de premier niveau.
2. **Rapport sourcé unique** : rédiger la synthèse dans un fichier Markdown structuré citant explicitement chaque source.
3. **Restitution** : enregistrer le document sous `docs/` ou dans le répertoire de notes convenu.

## When NOT to use this skill

- Pour une vérification rapide d'une signature d'API réalisable immédiatement en un tour → consulter directement.
- Pour affûter une décision en direct avec l'utilisateur → utiliser `/grill-with-docs`.
- Pour implémenter du code de production → utiliser `/implement`.

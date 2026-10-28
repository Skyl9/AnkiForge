# ADR 0052 : Méthodologie DAG — Étape de Synthèse Markdown Amont

## Statut
Accepté

## Contexte
La qualité des flashcards générées par les pipelines DAG dépend fortement de la propreté du contenu source injecté dans les étapes `LLM_PROMPT`. Les documents importés (PDF via Marker OCR, pages web, transcriptions audio) contiennent souvent des artefacts : césures OCR résiduelles, formules LaTeX non normalisées, tableaux Markdown mal alignés, hiérarchie de titres incohérente.

Une étape de **synthèse Markdown amont** placée en tout début de pipeline (via le type d'étape `PYTHON_TOOL` appelant `format_markdown_document`) normalise le contenu avant toute génération, ce qui :
- Améliore la pertinence du RAG (découpage sémantique plus propre)
- Réduit les hallucinations structurelles dans les prompts LLM
- Garantit une provenance déterministe (fil d'Ariane stable)
- Décuple la qualité des cartes dès la première passe

## Décision
1. **Documenter la méthodologie** dans `docs/Dossier_architecture/06_moteur_orchestration_ia.md` avec une section dédiée « Bonnes pratiques : Synthèse Markdown amont ».
2. **Fournir un exemple concret** de pipeline YAML/JSON incluant une étape `PYTHON_TOOL` d'ordre 1 appelant `format_markdown_document`.
3. **Référencer l'implémentation** : `src/ankiforge/services/markdown/formatter.py` (`MarkdownFormatter.format`) et l'outil MCP `format_markdown_document` (accessible via `ToolService`).
4. **Créer cet ADR** pour tracer la décision d'architecture.

## Alternatives considérées
- **Ne rien documenter** : laisse la découverte à l'utilisateur, qualité inégale des pipelines.
- **Imposer l'étape par défaut** : trop contraignant, tous les pipelines n'en ont pas besoin (ex: pipelines sur contenu déjà propre).
- **Nouveau type d'étape dédié `MARKDOWN_FORMAT`** : complexifie le moteur pour un cas d'usage couvert par `PYTHON_TOOL` existant.

## Conséquences
- Les auteurs de pipelines sont guidés vers une pratique éprouvée.
- La documentation reste alignée avec l'implémentation existante (`PYTHON_TOOL` + `ToolService`).
- Aucun changement de code requis : l'outillage existe déjà.

## Références
- `docs/Dossier_architecture/06_moteur_orchestration_ia.md` (section à ajouter)
- `src/ankiforge/services/ai/orchestrator.py` : `_execute_python_tool`
- `src/ankiforge/services/ai/mcp_tool_registry.py` : `format_markdown_document`
- `src/ankiforge/services/markdown/formatter.py` : `MarkdownFormatter`
- `src/ankiforge/services/tools/tool_service.py` : `ToolService.execute_tool`
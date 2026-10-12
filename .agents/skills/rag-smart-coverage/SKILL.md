---
name: rag-smart-coverage
description: >-
  Expert en RAG local, segmentation sémantique et Smart Coverage pour AnkiForge. Gère le découpage documentaire (ChunkingService), l'indexation vectorielle FAISS/ChromaDB (VectorManager), la délimitation de portée (ADR 0010) et la traçabilité déterministe note-fragment (CoverageAlignmentService, ADR 0009).
  Use when the user asks to "découper en chunks", "segmentation", "indexer dans le RAG", "recherche vectorielle", "couverture documentaire", "smart coverage", "gap analysis", "aligner les notes aux sections", "délimiter un document", "provenance de cartes", or deals with RAG, chunking, or card coverage.
  When NOT to use: Do not use for raw file parsing or OCR extraction (use ingestion-multimedia) or database schema migrations (use peewee-expert).
---

# 🧠 RAG Local & Smart Coverage — AnkiForge

En tant qu'**Expert RAG & Couverture Documentaire**, tu régis la chaîne de segmentation, l'indexation vectorielle et la traçabilité déterministe entre les cartes Anki et les sources documentaires.

> **Références architecturales** :
> - `docs/adr/0009-provenance-cartes-par-section.md` : identité durable par section `(document, fil d'Ariane)` et résolution à 4 paliers.
> - `docs/adr/0010-exclusion-non-destructive-par-adresse-de-region.md` : adresses de région (`node:`, `heading:`, `page:`).
> Code source : `src/ankiforge/services/parsing/chunking_service.py`, `src/ankiforge/services/rag/`.

## 1. Périmètre & Principes

- **Périmètre** : `ChunkingService`, `VectorManager` (FAISS / ChromaDB), `RAGService`, `CoverageAlignmentService`, `DocumentRepository` (périmètre et exclusions), tables `DocumentChunkModel` et `NoteChunkLinkModel`.
- **Principes fondamentaux** :
  - **Identité durable par section (ADR 0009)** : la référence pérenne d'une carte est le fil d'Ariane, jamais l'identifiant éphémère d'un fragment (`chunk_id`).
  - **Exclusion non destructive (ADR 0010)** : écarter une région est une règle de périmètre (`is_region_excluded`), jamais une suppression de données. Les fragments restent consultables et réintégrables.
  - **Résolution déterministe à 4 paliers** : `exact → section → page → lexical`. Une carte non rattachée reste hors couverture plutôt que rattachée de manière erronée.

## 2. Découpage Sémantique (Chunking)

1. `ChunkingService.extract_chunks(document_id, text, strategy)` : découpe le Markdown selon la hiérarchie des titres (`HeadingTree`) ou par blocs de tokens.
2. Synchroniser les fragments sans casser les liens existants : utiliser `sync_extracted_chunks()` qui apparie les fragments stables par empreinte et `(titre, page)`.
3. Conteneurs structuraux : neutraliser les conteneurs sans contenu propre (`container_origin = ContainerOrigin.DECLARED` ou `DERIVED`) pour ne pas fausser le dénominateur de couverture.

## 3. Indexation Vectorielle & Recherche RAG

- **VectorManager** : gère les embeddings locaux et l'index FAISS/ChromaDB sous `~/.ankiforge/profiles/<profile>/vector_store/`.
- **Filtrage à deux niveaux** :
  - À l'indexation : exclure les sections écartées.
  - À la requête : `_drop_excluded_results()` élimine dynamiquement tout résultat issu d'une région neutralisée ou écartée depuis la dernière indexation.

## 4. Alignement de Couverture (CoverageAlignmentService)

- **Synchronisation par tags** : `sync_coverage_from_tags(document_id)` reconstruit les liens `NoteChunkLinkModel` à partir des tags de provenance (`doc:`, `source:`, `section:`, `page:`) de façon réparatrice et idempotente.
- **Affinement déterministe** : `refine_links_to_subsections(document_id)` affine les cartes rattachées à des titres larges (H1/H2) vers la sous-section spécifique (H3+) par recouvrement lexical IDF, sans aucun appel LLM.
- **Analyse des lacunes (Gap Analysis)** : calcule le taux de couverture pondéré par unité de texte pour guider la génération de cartes sur les zones non couvertes.

## When NOT to use this skill

- L'objectif est d'extraire le texte d'un fichier PDF, audio ou web vers Markdown → utiliser `ingestion-multimedia`.
- Le besoin est d'orchestrer un pipeline DAG d'extraction de cartes → utiliser `pipeline-dag-ia`.
- La demande concerne une modification de schéma BDD Peewee → utiliser `peewee-expert`.
- La demande est l'audit d'intégrité globale du modèle de données → utiliser `audit-donnees`.

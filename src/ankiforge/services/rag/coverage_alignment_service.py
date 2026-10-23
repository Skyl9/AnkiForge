"""Réexport de CoverageAlignmentService pour le domaine RAG et Smart Coverage.

Permet l'accès unifié à CoverageAlignmentService depuis le package rag ou audit
conformément à l'architecture modulaire AnkiForge et l'ADR 0009.
"""

from __future__ import annotations

from ankiforge.services.audit.coverage_alignment_service import (
    RESOLUTION_EXACT,
    RESOLUTION_LEXICAL,
    RESOLUTION_PAGE,
    RESOLUTION_SECTION,
    RESOLUTION_TIERS,
    CoverageAlignmentService,
)

__all__ = [
    "CoverageAlignmentService",
    "RESOLUTION_EXACT",
    "RESOLUTION_LEXICAL",
    "RESOLUTION_PAGE",
    "RESOLUTION_SECTION",
    "RESOLUTION_TIERS",
]

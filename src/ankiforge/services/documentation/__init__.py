"""Module de gestion de la base de connaissances interne et de la documentation Zensical."""

from ankiforge.services.documentation.doc_service import (
    AppDocumentationService,
    DocSearchResult,
    DocSection,
    DocTopic,
    get_feature_quick_help,
    list_app_doc_topics,
    read_app_doc_page,
    search_app_documentation,
)

__all__ = [
    "AppDocumentationService",
    "DocSearchResult",
    "DocSection",
    "DocTopic",
    "get_feature_quick_help",
    "list_app_doc_topics",
    "read_app_doc_page",
    "search_app_documentation",
]

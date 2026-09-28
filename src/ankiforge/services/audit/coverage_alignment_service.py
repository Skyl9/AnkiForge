"""
Service de réconciliation déterministe et de traçabilité entre documents sources et fiches Anki.

Établit les correspondances NoteModel <-> DocumentChunkModel (NoteChunkLinkModel)
exclusivement à partir des tags de traçabilité (doc:<id>, source:<slug>, page:<num>, section:<slug>).
Conforme aux Règles 2, 8, 19 et 20 de GEMINI.md.
"""

from __future__ import annotations

import json
import logging
import math
import re
import shutil
import unicodedata
from typing import Any, cast

from peewee import fn

from ankiforge.database.models import (
    DocumentChunkModel,
    DocumentModel,
    MediaModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteVersionModel,
    db,
)
from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.services.markdown.table_of_contents import TableOfContentsDetector
from ankiforge.services.reindex_service import mark_document_version
from ankiforge.utils.paths import get_profile_dir
from ankiforge.utils.tags import clean_source_slug, extract_tag_metadata, replace_provenance_tags

logger = logging.getLogger(__name__)

#: Séparateur de fil d'Ariane porté par `DocumentChunkModel.heading_path`.
_HEADING_SEPARATOR = " > "

#: Mots vides écartés du scoring lexical et de la détection de titre cité (FR + EN).
_LEXICAL_STOPWORDS = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "et",
        "ou",
        "mais",
        "donc",
        "or",
        "ni",
        "car",
        "est",
        "sont",
        "qui",
        "que",
        "dans",
        "pour",
        "sur",
        "avec",
        "ce",
        "cette",
        "ces",
        "au",
        "aux",
        "à",
        "l",
        "d",
        "n",
        "en",
        "se",
        "sa",
        "son",
        "ses",
        "par",
        "plus",
        "pas",
        "ne",
        "the",
        "a",
        "an",
        "of",
        "to",
        "in",
        "on",
        "with",
        "for",
        "and",
        "is",
        "are",
    }
)

_TOKEN_RE = re.compile(r"\b\w{3,}\b")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_NUMBERING_RE = re.compile(r"^\d+(?:[.\-]\d+)*$")


def _fold_accents(text: str) -> str:
    """Supprime les diacritiques (NFKD) pour comparer des titres accentués à un texte simple."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _flatten_note_content(raw_content: str | None) -> str:
    """Aplatit le JSON de contenu d'une version de note en texte exploitable (recto + verso)."""
    try:
        content = json.loads(raw_content or "{}")
    except (TypeError, ValueError):
        return str(raw_content or "")
    if isinstance(content, dict):
        return " ".join(str(value) for value in content.values() if value)
    return str(content)


class CoverageAlignmentService:
    """Moteur de réconciliation déterministe de couverture documentaire par tags."""

    #: Longueur minimale du corps d'un fragment parent pour qu'il soit considéré comme une
    #: unité de cours à part entière (et non comme un simple conteneur de sous-sections).
    MIN_PARENT_CONTENT_WORDS: int = 25

    #: Score lexical minimal qu'une sous-section doit atteindre pour qu'une carte lui soit
    #: rattachée par la seule route lexicale (une citation littérale du titre s'en passe) : le
    #: score est une somme de poids idf, il faut au moins un terme réellement distinctif, pas
    #: un mot vide partagé par tout le document.
    MIN_SUBSECTION_SCORE: float = 1.0

    @classmethod
    def sync_coverage_from_tags(cls, doc_id: int | None = None) -> dict[str, Any]:
        """
        Synchronise déterministement les liaisons NoteModel <-> DocumentChunkModel à partir des tags des notes.

        Recherche et exploite les tags :
        - doc:<id> ou source:<slug>
        - page:<num>
        - section:<slug>

        En mode ciblé (doc_id), les liens résiduels dont la note ne porte plus de tags
        concordants vers ce document sont retirés (déliaison des liens "stale").

        Args:
            doc_id: Optionnel. Si spécifié, restreint la réconciliation à ce document.

        Returns:
            dict[str, Any]: Rapport statistique de réconciliation.
        """
        doc_repo = DocumentRepository()

        if doc_id is not None:
            target_doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
            if not target_doc:
                return {"matched_notes": 0, "newly_linked": 0, "covered_chunks": 0, "total_chunks": 0, "coverage_pct": 0.0}
            from ankiforge.services.parsing.chunking_service import ChunkingService

            if target_doc.chunk_strategy_version != ChunkingService.CHUNKING_VERSION:
                logger.debug(
                    "sync_coverage_from_tags : document %d est stale (v%s), synchronisation différée après re-indexation.",
                    doc_id,
                    target_doc.chunk_strategy_version,
                )
                return {"matched_notes": 0, "newly_linked": 0, "covered_chunks": 0, "total_chunks": 0, "coverage_pct": 0.0}
            docs_by_id = {target_doc.id: target_doc}
            docs_by_slug = {clean_source_slug(target_doc.title): target_doc}
        else:
            all_docs = list(DocumentModel.select())
            if not all_docs:
                return {"matched_notes": 0, "newly_linked": 0, "covered_chunks": 0, "total_chunks": 0, "coverage_pct": 0.0}
            docs_by_id = {d.id: d for d in all_docs}
            docs_by_slug = {clean_source_slug(d.title): d for d in all_docs}

        # Porte de sécurité : les documents stale (ancienne stratégie de structuration)
        # sont exclus de la synchronisation pour éviter des appariements incorrects.
        stale_doc_ids: set[int] = set()
        from ankiforge.services.parsing.chunking_service import ChunkingService

        for d in docs_by_id.values():
            if d.chunk_strategy_version != ChunkingService.CHUNKING_VERSION:
                stale_doc_ids.add(d.id)
        if stale_doc_ids:
            logger.debug("sync_coverage_from_tags : %d document(s) stale ignoré(s) (re-indexation requise).", len(stale_doc_ids))

        # Seules les notes portant des tags de traçabilité sont concernées : évite le scan O(N*M)
        all_notes = list(NoteModel.select().where((NoteModel.tags.contains("doc:")) | (NoteModel.tags.contains("source:"))))
        newly_linked = 0
        matched_notes = 0

        with db.atomic():
            for note in all_notes:
                if not note.tags:
                    continue
                meta = extract_tag_metadata(note.tags)
                matched_doc: DocumentModel | None = None
                if meta["doc_id"] is not None and meta["doc_id"] in docs_by_id:
                    matched_doc = docs_by_id[meta["doc_id"]]
                elif meta["source_slug"] is not None and meta["source_slug"] in docs_by_slug:
                    matched_doc = docs_by_slug[meta["source_slug"]]

                if not matched_doc:
                    continue

                if matched_doc.id in stale_doc_ids:
                    continue

                target_chunk: DocumentChunkModel | None = None
                page_num = meta["page_number"]
                section_slug = meta["section_slug"]
                chunk_id = meta["chunk_id"]

                if chunk_id is not None and chunk_id > 0:
                    target_chunk = (
                        DocumentChunkModel.select()
                        .where(
                            DocumentChunkModel.id == chunk_id,
                            DocumentChunkModel.document == matched_doc,
                        )
                        .first()
                    )
                elif page_num is not None and page_num > 0:
                    target_chunk = DocumentChunkModel.select().where(DocumentChunkModel.document == matched_doc, DocumentChunkModel.page_number == page_num).first()
                elif section_slug:
                    target_chunk = cls._find_chunk_by_section_suffix(matched_doc.id, section_slug)

                if target_chunk:
                    matched_notes += 1
                    _, created = NoteChunkLinkModel.get_or_create(
                        note=note,
                        chunk=target_chunk,
                        defaults={"is_hallucinating": False},
                    )
                    if created:
                        newly_linked += 1

        stale_removed = 0
        if doc_id is not None and target_doc is not None:
            with db.atomic():
                stale_removed = cls._remove_stale_links(target_doc, docs_by_id, docs_by_slug)

        if doc_id is not None:
            stats = doc_repo.get_coverage_stats(doc_id)
            cls._notify_coverage_synced(doc_id=doc_id, scope="document")
            return {
                "matched_notes": matched_notes,
                "newly_linked": newly_linked,
                "stale_removed": stale_removed,
                "covered_chunks": stats.get("covered_chunks", 0),
                "total_chunks": stats.get("total_chunks", 0),
                "coverage_pct": stats.get("coverage_pct", 0.0),
                "unit_type": stats.get("unit_type", "pages"),
                "total_units": stats.get("total_units", 0),
                "covered_units": stats.get("covered_units", 0),
            }

        cls._notify_coverage_synced(doc_id=None, scope="all")
        return {
            "matched_notes": matched_notes,
            "newly_linked": newly_linked,
            "total_documents": len(docs_by_id),
        }

    @staticmethod
    def _notify_coverage_synced(doc_id: int | None, scope: str) -> None:
        """Notifie l'UI (via l'event bus) que la couverture documentaire a été modifiée."""
        try:
            from ankiforge.utils.event_bus import CoverageSyncedEvent, event_bus

            event_bus.publish(CoverageSyncedEvent(doc_id=doc_id, scope=scope))
        except Exception as e:
            logger.debug("Émission de l'événement CoverageSyncedEvent ignorée : %s", e)

    @staticmethod
    def _remove_stale_links(
        target_doc: DocumentModel,
        docs_by_id: dict[int, DocumentModel],
        docs_by_slug: dict[str, DocumentModel],
    ) -> int:
        """Retire les liens vers un document dont la note garde des tags ne pointant plus vers ce document."""
        removed = 0
        doc_links = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == target_doc)
        for link in doc_links:
            note = link.note
            if not note.tags:
                continue
            meta = extract_tag_metadata(note.tags)
            resolved_doc: DocumentModel | None = None
            if meta["doc_id"] is not None and meta["doc_id"] in docs_by_id:
                resolved_doc = docs_by_id[meta["doc_id"]]
            elif meta["source_slug"] is not None and meta["source_slug"] in docs_by_slug:
                resolved_doc = docs_by_slug[meta["source_slug"]]
            if resolved_doc is None or resolved_doc.id != target_doc.id:
                link.delete_instance()
                removed += 1
        return removed

    @classmethod
    def align_document(
        cls,
        doc_id: int,
        deck_id: int | None = None,
        min_overlap: int = 2,
        clear_existing: bool = False,
    ) -> dict[str, Any]:
        """
        Réconcilie les fiches existantes de la base de données avec les fragments d'un document.

        Effectue une synchronisation déterministe par tags (doc:<id>, source:<slug>, page:<num>, section:<slug>).
        Les paramètres deck_id et min_overlap sont conservés pour la compatibilité des appelants mais sans effet :
        aucun matching sémantique/lexical n'est réalisé.

        Args:
            doc_id: ID du document cible.
            deck_id: Ignoré (compatibilité). Réservé à une réconciliation par paquet.
            min_overlap: Ignoré (compatibilité).
            clear_existing: Si True, supprime tous les liens existants du document avant réconciliation.

        Returns:
            dict[str, Any]: Rapport statistique de réconciliation et de couverture.
        """
        doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
        if not doc:
            logger.warning("CoverageAlignmentService : Document ID=%d introuvable.", doc_id)
            return {
                "error": f"Document {doc_id} introuvable",
                "matched_notes": 0,
                "total_notes": 0,
                "covered_chunks": 0,
                "total_chunks": 0,
                "coverage_pct": 0.0,
            }

        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index))
        total_chunks = len(chunks)
        if total_chunks == 0 and not doc.total_pages:
            logger.info("CoverageAlignmentService : Aucun fragment pour le document '%s'.", doc.title)
            return {
                "matched_notes": 0,
                "total_notes": 0,
                "covered_chunks": 0,
                "total_chunks": 0,
                "coverage_pct": 0.0,
            }

        if clear_existing:
            with db.atomic():
                chunk_ids = [c.id for c in chunks]
                NoteChunkLinkModel.delete().where(NoteChunkLinkModel.chunk.in_(chunk_ids)).execute()

        tag_res = cls.sync_coverage_from_tags(doc_id=doc_id)
        matched = tag_res.get("matched_notes", 0)

        doc_repo = DocumentRepository()
        stats = doc_repo.get_coverage_stats(doc_id)
        total_notes = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc).count()

        logger.info(
            "CoverageAlignmentService : Réconciliation terminée pour '%s' : %d cartes liées via tags (Couverture : %.1f%%)",
            doc.title,
            matched,
            stats.get("coverage_pct", 0.0),
        )

        return {
            "matched_notes": matched,
            "total_notes": total_notes,
            "total_cards": stats.get("total_cards", 0),
            "covered_chunks": stats.get("covered_chunks", 0),
            "total_chunks": stats.get("total_chunks", 0),
            "coverage_pct": stats.get("coverage_pct", 0.0),
            "unit_type": stats.get("unit_type", "pages"),
            "total_units": stats.get("total_units", 0),
            "covered_units": stats.get("covered_units", 0),
        }

    @classmethod
    def align_all_documents(cls, min_overlap: int = 2) -> dict[str, Any]:
        """Exécute la réconciliation déterministe sur tous les documents de la bibliothèque du profil courant."""
        all_docs = list(DocumentModel.select())
        summary: dict[str, Any] = {
            "total_documents": len(all_docs),
            "total_matched_links": 0,
            "details": [],
        }

        for doc in all_docs:
            res = cls.align_document(doc.id, min_overlap=min_overlap)
            summary["total_matched_links"] += res.get("matched_notes", 0)
            summary["details"].append({"doc_id": doc.id, "title": doc.title, "result": res})

        return summary

    @staticmethod
    def _find_chunk_by_section_suffix(doc_id: int, section_slug: str) -> DocumentChunkModel | None:
        """Retrouve le chunk dont le fil d'Ariane se termine par le slug de section fourni.

        Le matching est tolérant : le slug peut correspondre au breadcrumb entier
        ("chapitre_1_la_cellule_noyau") ou seulement à un titre feuille situé en fin
        de fil ("noyau"). Si plusieurs chunks matchent (titre répété), on privilégie :

        1. les fragments de cours — les entrées d'un sommaire (documents indexés avant
           le découpage v5) sont ignorées, faute de contenu substantiel ;
        2. le plus profond (granularité la plus fine) ;
        3. à granularité égale, le plus riche en mots (le corps réel, pas l'annonce).
        """
        if not section_slug:
            return None
        best: DocumentChunkModel | None = None
        best_depth = 0
        best_words = -1
        for c in DocumentChunkModel.select().where(DocumentChunkModel.document == doc_id).order_by(DocumentChunkModel.chunk_index):
            if not c.heading_path:
                continue
            if TableOfContentsDetector.looks_like_index_block(c.content or ""):
                continue
            slug = clean_source_slug(c.heading_path)
            parts = [p for p in c.heading_path.split(" > ") if p.strip()]
            if not (slug == section_slug or slug.endswith(f"_{section_slug}") or any(clean_source_slug(p) == section_slug for p in parts)):
                continue
            words = len((c.content or "").split())
            if len(parts) > best_depth or (len(parts) == best_depth and words > best_words):
                best = c
                best_depth = len(parts)
                best_words = words
        return best

    @classmethod
    def resolve_finest_chunk_for_card(
        cls,
        card_text: str,
        doc_id: int,
        llm_section: str | None = None,
        source_chunk_id: int | None = None,
        page_number: int | None = None,
    ) -> DocumentChunkModel | None:
        """Résout le fragment le plus fin d'un document correspondant à une carte générée.

        L'utilisateur fournit généralement une grande partie du document à l'IA
        (chapitre, scope entier) ; cette méthode retrouve, pour chaque carte, la
        sous-section précise (jusqu'au niveau H5/H6) dont le contenu provient.

        Priorité de résolution :
        1. source_chunk_id : fragment source connu (le scope fourni == un seul chunk) ;
        2. llm_section : fil d'Ariane déclaré par l'IA (suffix-match tolérant) ;
        3. page_number : fragment de la page correspondante ;
        4. overlap lexical : meilleur fragment par mots communs pondérés (profondeur = tie-break).

        Args:
            card_text: Texte de la carte (recto + verso) à localiser.
            doc_id: ID du document source.
            llm_section: Section/fil d'Ariane éventuellement déclaré par l'IA.
            source_chunk_id: ID du fragment source connu (le cas échéant).
            page_number: Numéro de page déclaré (le cas échéant).

        Returns:
            DocumentChunkModel | None : le fragment le plus pertinent, ou None si aucun match.
        """
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc_id))
        if not chunks:
            return None

        if source_chunk_id is not None and source_chunk_id > 0:
            exact = next((c for c in chunks if c.id == source_chunk_id), None)
            if exact:
                return exact

        if llm_section and str(llm_section).strip():
            by_section = cls._find_chunk_by_section_suffix(doc_id, clean_source_slug(str(llm_section)))
            if by_section:
                return by_section

        if page_number is not None and page_number > 0:
            by_page = next((c for c in chunks if c.page_number is not None and c.page_number == page_number), None)
            if by_page:
                return by_page

        if not card_text or not card_text.strip():
            return None

        return cls._best_chunk_by_lexical_overlap(card_text, chunks)

    @staticmethod
    def _lexical_overlap_scores(card_text: str, chunks: list[DocumentChunkModel]) -> list[float]:
        """Score de recouvrement lexical de chaque fragment avec le texte d'une carte.

        Score d'un fragment = somme, sur les tokens significatifs du texte de la carte, du poids
        idf du token lorsqu'il apparaît dans le fragment. Les tokens courts (< 3 caractères) et
        les mots vides du texte de la carte sont ignorés ; l'idf est calculé sur le corpus
        fourni, ce qui rend les scores comparables d'un ensemble de fragments à l'autre. Les
        accents sont repliés comme partout ailleurs, afin qu'un titre accentué et une carte
        reformulée sans accent se rencontrent.
        """
        if not chunks:
            return []

        tokens = [t.lower() for t in _TOKEN_RE.findall(_fold_accents(card_text)) if t.lower() not in _LEXICAL_STOPWORDS]
        if not tokens:
            return [0.0] * len(chunks)

        doc_freq: dict[str, int] = {}
        chunk_token_sets: list[set[str]] = []
        for c in chunks:
            c_tokens = {t.lower() for t in _TOKEN_RE.findall(_fold_accents(c.content or ""))}
            chunk_token_sets.append(c_tokens)
            for t in c_tokens:
                doc_freq[t] = doc_freq.get(t, 0) + 1

        n_docs = max(1, len(chunks))
        idf = {t: math.log(1.0 + n_docs / (1.0 + df)) for t, df in doc_freq.items()}

        scores: list[float] = []
        for chunk_tokens in chunk_token_sets:
            scores.append(sum(idf.get(t, 1.0) for t in tokens if t in chunk_tokens))
        return scores

    @classmethod
    def _best_chunk_by_lexical_overlap(cls, card_text: str, chunks: list[DocumentChunkModel]) -> DocumentChunkModel | None:
        """Sélectionne le fragment le plus proche lexicalement d'un texte de carte.

        En cas d'égalité, on privilégie le fragment le plus profond (granularité la plus fine).
        """
        scores = cls._lexical_overlap_scores(card_text, chunks)
        return cls._best_by_score_then_depth(list(zip(chunks, scores, strict=True)))

    @staticmethod
    def _best_by_score_then_depth(scored: list[tuple[DocumentChunkModel, float]]) -> DocumentChunkModel | None:
        """Élit le fragment le mieux noté, le plus profond départageant les égalités.

        Le départage par profondeur encode la granularité : à recouvrement égal, c'est la
        sous-section la plus fine qui est la meilleure explication, et non son conteneur.
        Les scores nuls ou négatifs ne sont jamais retenus.
        """
        best: DocumentChunkModel | None = None
        best_score = 0.0
        best_depth = -1
        for chunk, score in scored:
            if score <= 0:
                continue
            depth = len(CoverageAlignmentService._heading_parts(chunk))
            if best is None or score > best_score or (score == best_score and depth > best_depth):
                best = chunk
                best_score = score
                best_depth = depth
        return best

    @staticmethod
    def _heading_parts(chunk: DocumentChunkModel) -> list[str]:
        """Découpe le fil d'Ariane d'un fragment en ses niveaux de titres."""
        return [part.strip() for part in (chunk.heading_path or "").split(_HEADING_SEPARATOR) if part.strip()]

    @classmethod
    def _significant_tokens(cls, text: str) -> set[str]:
        """Tokens significatifs d'un texte : hors numérotation et mots vides, sans accents ni casse.

        La suppression des accents permet de reconnaître un titre accentué dans un texte de
        carte reformulé sans accent, et l'élimination de la numérotation (« 2.1 », « 3-2 »)
        comme des articles courts rend les titres numérotés comparables à leurs sous-sections.
        """
        folded = _fold_accents(text).lower()
        return {token for token in _TOKEN_RE.findall(folded) if token not in _LEXICAL_STOPWORDS and not _NUMBERING_RE.match(token)}

    @classmethod
    def _quotes_subsection_title(cls, card_tokens: set[str], chunk: DocumentChunkModel) -> bool:
        """Indique si le texte de la carte cite mot pour mot le titre de la sous-section.

        Tous les tokens significatifs du titre feuille doivent figurer dans la carte : c'est le
        signal fort du rapprochement, celui qui rattache une carte « Quelle est la fonction de
        la membrane ? » au H3 « 2.1 La Membrane » sans appel à un modèle.
        """
        parts = cls._heading_parts(chunk)
        if not parts:
            return False
        title_tokens = cls._significant_tokens(parts[-1])
        return bool(title_tokens) and title_tokens.issubset(card_tokens)

    @classmethod
    def _is_admissible(cls, score: float, parent_score: float, literal: bool) -> bool:
        """Indique si une sous-section peut recevoir une carte que son conteneur explique aussi.

        Deux régimes, parce que deux régimes de preuve :

        - *citation littérale* : la carte cite mot pour mot le titre de la sous-section, ce
          qui est une citation volontaire du sous-sujet. Les mots d'usage commun que la
          carte partage avec le conteneur ne peuvent pas annuler cette preuve, sans quoi un
          simple « échanges » laudatif suffit à figer la carte sur son chapitre ;
        - *inférence lexicale* : le recouvrement de vocabulaire est une présomption, qui doit
          donc franchir le seuil de pertinence **et** expliquer la carte mieux que le
          conteneur qu'elle quitte.
        """
        if literal:
            return True
        return score >= cls.MIN_SUBSECTION_SCORE and score > parent_score

    @classmethod
    def _narrow_to_subsection(
        cls,
        card_text: str,
        parent: DocumentChunkModel,
        descendants: list[DocumentChunkModel],
    ) -> tuple[DocumentChunkModel | None, str]:
        """Choisit la sous-section la plus spécifique qu'une carte rattachée à `parent` traite.

        Deux niveaux de détection lexicale, tous deux déterministes et purement locaux :

        1. présence littérale du titre d'une sous-section dans le texte de la carte ;
        2. à défaut, meilleur recouvrement lexical pondéré par l'idf, calculé sur le seul
           corpus « conteneur + descendants » pour que les scores soient comparables.

        Le signal littéral est prioritaire, mais une carte qui cite *plusieurs* sous-sections
        est par définition une carte de chapitre : elle reste sur son conteneur. Le critère
        d'admissibilité de la sous-section retenue est celui de ``_is_admissible``.

        Returns:
            tuple[DocumentChunkModel | None, str] : le fragment cible et le signal qui l'a
            désigné (``"titre"`` ou ``"lexique"``), ou ``(None, "")`` si aucun raffinement.
        """
        card_tokens = cls._significant_tokens(card_text)
        if not card_tokens:
            return None, ""

        # Les fragments d'une même sous-section (titre répété, page de PDF scindée) ne
        # comptent qu'une fois : une carte qui cite un seul titre n'est pas pour autant une
        # carte de chapitre, et deux fragments du même titre n'en sont pas deux sous-sections.
        quoted: list[DocumentChunkModel] = []
        cited_headings: set[str] = set()
        for candidate in descendants:
            if not cls._quotes_subsection_title(card_tokens, candidate):
                continue
            heading = candidate.heading_path or ""
            if heading in cited_headings:
                continue
            cited_headings.add(heading)
            quoted.append(candidate)

        if len(quoted) > 1:
            return None, ""
        candidates = quoted or descendants
        signal = "titre" if quoted else "lexique"

        # Le conteneur parent est inclus dans le corpus : sa colonne de score sert de
        # référence pour exiger un gain de pertinence réel.
        scores = cls._lexical_overlap_scores(card_text, [parent, *candidates])
        parent_score = scores[0]
        eligible = [pair for pair in zip(candidates, scores[1:], strict=True) if cls._is_admissible(pair[1], parent_score, bool(quoted))]
        best = cls._best_by_score_then_depth(eligible)
        return best, signal if best is not None else ""

    @staticmethod
    def _descendants_by_prefix(chunks: list[DocumentChunkModel]) -> dict[tuple[str, ...], list[DocumentChunkModel]]:
        """Indexe, pour chaque préfixe de fil d'Ariane, les fragments qui lui sont strictement descendants.

        Les entrées de sommaire sont écartées : elles annoncent un titre sans porter le cours
        correspondant, et constitueraient des cibles d'affinement aberrantes.
        """
        descendants: dict[tuple[str, ...], list[DocumentChunkModel]] = {}
        for chunk in chunks:
            if TableOfContentsDetector.looks_like_index_block(chunk.content or ""):
                continue
            parts = tuple(CoverageAlignmentService._heading_parts(chunk))
            for depth in range(1, len(parts)):
                descendants.setdefault(parts[:depth], []).append(chunk)
        return descendants

    @staticmethod
    def _links_per_heading(doc_id: int) -> dict[str, int]:
        """Nombre de liens de couverture par fil d'Ariane, en une seule requête agrégée."""
        rows = cast(
            "list[tuple[Any, ...]]",
            NoteChunkLinkModel.select(DocumentChunkModel.heading_path, fn.COUNT(NoteChunkLinkModel.id).alias("link_count"))
            .join(DocumentChunkModel)
            .where(DocumentChunkModel.document == doc_id)
            .group_by(DocumentChunkModel.heading_path)
            .tuples(),
        )
        return {str(heading or ""): int(count or 0) for heading, count in rows}

    @staticmethod
    def _active_version_texts(note_ids: list[int]) -> dict[int, str]:
        """Texte (recto + verso, HTML retiré) de la version active de chaque note, en une requête."""
        if not note_ids:
            return {}
        rows = cast(
            "list[tuple[Any, ...]]",
            NoteVersionModel.select(NoteVersionModel.note, NoteVersionModel.content).where(NoteVersionModel.note.in_(note_ids), NoteVersionModel.is_active == True).tuples(),  # noqa: E712
        )
        return {int(note_id): _HTML_TAG_RE.sub(" ", _flatten_note_content(content)) for note_id, content in rows}

    @classmethod
    def _empty_refinement_report(cls, doc_id: int) -> dict[str, Any]:
        """Rapport neutre d'un affinement sans effet (document inconnu, sans lien ou sans descendant)."""
        return {
            "doc_id": doc_id,
            "reassigned": 0,
            "false_gaps_resolved": 0,
            "new_gaps": 0,
            "kept_on_parent": 0,
            "details": [],
            "coverage_before": 0.0,
            "coverage_after": 0.0,
        }

    @classmethod
    def refine_links_to_subsections(cls, doc_id: int) -> dict[str, Any]:
        """Rattache les cartes d'un conteneur de cours aux sous-sections qu'elles traitent réellement.

        Affinement *top-down narrowing* purement algorithmique, sans appel réseau ni LLM : pour
        chaque lien de couverture pointant sur un fragment qui possède des sous-sections, le
        texte de la carte est confronté aux descendants du fil d'Ariane (présence littérale
        du titre, puis recouvrement lexical pondéré par l'idf). La liaison et les tags de
        traçabilité `section:` / `chunk:` sont réécrits atomiquement vers la sous-section
        retenue, ce qui résorbe les fausses lacunes d'un audit de couverture granularity.

        Une carte n'est jamais retirée d'un fragment parent porteur de contenu substantiel si
        elle en est la dernière : déplacer la seule carte d'une unité réellement enseignée
        déplacerait la lacune au lieu de la résoudre.

        Args:
            doc_id: ID du document dont les liens de couverture doivent être affinés.

        Returns:
            dict[str, Any]: rapport ``reassigned`` / ``false_gaps_resolved`` / ``new_gaps`` /
            ``kept_on_parent`` / ``details`` et couverture avant-après.
        """
        doc = DocumentModel.get_or_none(DocumentModel.id == doc_id)
        if not doc:
            logger.warning("CoverageAlignmentService : affinement impossible, document ID=%d introuvable.", doc_id)
            return cls._empty_refinement_report(doc_id)

        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index))
        if not chunks:
            return cls._empty_refinement_report(doc_id)

        descendants = cls._descendants_by_prefix(chunks)
        links = list(NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc).order_by(NoteChunkLinkModel.note_id, NoteChunkLinkModel.chunk_id))
        if not links:
            return cls._empty_refinement_report(doc_id)

        note_ids = sorted({link.note_id for link in links})
        notes = {note.id: note for note in NoteModel.select().where(NoteModel.id.in_(note_ids))}
        repo = DocumentRepository()
        before = repo.get_coverage_stats(doc_id)
        links_per_heading = cls._links_per_heading(doc_id)
        card_texts = cls._active_version_texts(note_ids)

        details: list[dict[str, Any]] = []
        kept_on_parent = 0

        with db.atomic():
            for link in links:
                parent = link.chunk
                parent_parts = cls._heading_parts(parent)
                candidates = descendants.get(tuple(parent_parts)) if parent_parts else None
                if not candidates:
                    continue
                card_text = card_texts.get(link.note_id, "")
                if not card_text.strip():
                    continue

                target, signal = cls._narrow_to_subsection(card_text, parent, candidates)
                if target is None:
                    continue
                note = notes.get(link.note_id)
                if note is None:
                    continue

                parent_key = parent.heading_path or ""
                remaining = links_per_heading.get(parent_key, 0) - 1
                if remaining <= 0 and len((parent.content or "").split()) >= cls.MIN_PARENT_CONTENT_WORDS:
                    logger.debug("Affinement : %s conservé sur le conteneur « %s », dernière carte d'une unité de cours.", link.note_id, parent_key)
                    kept_on_parent += 1
                    continue

                was_hallucinating = link.is_hallucinating
                link.delete_instance()
                NoteChunkLinkModel.get_or_create(note=note, chunk=target, defaults={"is_hallucinating": was_hallucinating})
                note.tags = replace_provenance_tags(note.tags, {"section": clean_source_slug(target.heading_path or ""), "chunk": target.id})
                note.save(only=[NoteModel.tags])

                links_per_heading[parent_key] = max(0, remaining)
                target_key = target.heading_path or ""
                links_per_heading[target_key] = links_per_heading.get(target_key, 0) + 1
                details.append(
                    {
                        "note_id": link.note_id,
                        "from_chunk_id": parent.id,
                        "from_heading": parent.heading_path,
                        "to_chunk_id": target.id,
                        "to_heading": target.heading_path,
                        "signal": signal,
                    }
                )

        after = repo.get_coverage_stats(doc_id)
        orphans_before = {str(unit) for unit in before.get("orphan_units", [])}
        orphans_after = {str(unit) for unit in after.get("orphan_units", [])}

        report = {
            "doc_id": doc_id,
            "reassigned": len(details),
            "false_gaps_resolved": len(orphans_before - orphans_after),
            "new_gaps": len(orphans_after - orphans_before),
            "kept_on_parent": kept_on_parent,
            "details": details,
            "coverage_before": before.get("coverage_pct", 0.0),
            "coverage_after": after.get("coverage_pct", 0.0),
        }

        if details:
            logger.info(
                "CoverageAlignmentService : affinement de « %s » : %d carte(s) rattachée(s) à une sous-section (%d fausse(s) lacune(s) résolue(s), %d nouvelle(s)).",
                doc.title,
                report["reassigned"],
                report["false_gaps_resolved"],
                report["new_gaps"],
            )
            cls._notify_coverage_synced(doc_id=doc_id, scope="document")
        return report

    @classmethod
    def find_matching_chunk_for_note(cls, note_id: int, min_overlap: int = 2) -> DocumentChunkModel | None:
        """Trouve le fragment de document le plus pertinent pour une note donnée via sa traçabilité par tags."""
        note = NoteModel.get_or_none(NoteModel.id == note_id)
        if not note:
            return None

        existing_link = NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == note).first()
        if existing_link:
            return existing_link.chunk

        # Recherche déterministe via les tags de la note
        if note.tags:
            meta = extract_tag_metadata(note.tags)
            doc_target: DocumentModel | None = None
            if meta["doc_id"] is not None:
                doc_target = DocumentModel.get_or_none(DocumentModel.id == meta["doc_id"])
            elif meta["source_slug"]:
                for d in DocumentModel.select():
                    if clean_source_slug(d.title) == meta["source_slug"]:
                        doc_target = d
                        break

            if doc_target:
                if meta["chunk_id"] is not None:
                    chunk = (
                        DocumentChunkModel.select()
                        .where(
                            DocumentChunkModel.id == meta["chunk_id"],
                            DocumentChunkModel.document == doc_target,
                        )
                        .first()
                    )
                    if chunk:
                        return chunk
                if meta["page_number"] is not None:
                    chunk = (
                        DocumentChunkModel.select()
                        .where(
                            DocumentChunkModel.document == doc_target,
                            DocumentChunkModel.page_number == meta["page_number"],
                        )
                        .first()
                    )
                    if chunk:
                        return chunk
                if meta["section_slug"]:
                    chunk = cls._find_chunk_by_section_suffix(doc_target.id, meta["section_slug"])
                    if chunk:
                        return chunk

        return None

    @classmethod
    def copy_document_from_profile(
        cls,
        source_profile: str,
        target_profile: str,
        doc_id: int,
    ) -> DocumentModel | None:
        """
        Copie un DocumentModel et ses chunks d'un profil source vers le profil cible.
        Copie également les fichiers physiques associés (original_media).
        """
        import sqlite3

        src_dir = get_profile_dir(source_profile)
        src_db_path = src_dir / "ankiforge.db"
        if not src_db_path.exists():
            logger.warning("Base source introuvable pour profil '%s' : %s", source_profile, src_db_path)
            return None

        src_con = sqlite3.connect(src_db_path)
        src_con.row_factory = sqlite3.Row
        src_cur = src_con.cursor()

        doc_row = src_cur.execute("SELECT * FROM documentmodel WHERE id = ?", (doc_id,)).fetchone()
        if not doc_row:
            src_con.close()
            return None

        media_filename = None
        orig_name = None
        mime = None
        chksum = None
        if doc_row["original_media_id"]:
            m_row = src_cur.execute("SELECT * FROM mediamodel WHERE id = ?", (doc_row["original_media_id"],)).fetchone()
            if m_row:
                media_filename = m_row["filename"]
                orig_name = m_row["original_name"]
                mime = m_row["mime_type"]
                chksum = m_row["checksum"]

        chunks_rows = src_cur.execute(
            "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()
        src_con.close()

        target_media_id = None
        target_media_dir = get_profile_dir(target_profile) / "media"
        target_media_dir.mkdir(parents=True, exist_ok=True)

        if media_filename:
            src_media_file = src_dir / "media" / media_filename
            if src_media_file.exists():
                dst_media_file = target_media_dir / media_filename
                if not dst_media_file.exists():
                    shutil.copy2(src_media_file, dst_media_file)

            target_media, _ = MediaModel.get_or_create(
                checksum=chksum or media_filename,
                defaults={
                    "filename": media_filename,
                    "original_name": orig_name or media_filename,
                    "mime_type": mime or "application/octet-stream",
                },
            )
            target_media_id = target_media.id

        doc_dict = dict(doc_row)
        new_doc, _ = DocumentModel.get_or_create(
            title=doc_dict["title"],
            defaults={
                "content": doc_dict["content"],
                "file_type": doc_dict["file_type"],
                "source_url": doc_dict["source_url"],
                "total_pages": doc_dict.get("total_pages", 1),
                "original_media_id": target_media_id,
            },
        )

        with db.atomic():
            DocumentChunkModel.delete().where(DocumentChunkModel.document == new_doc).execute()
            for r in chunks_rows:
                r_dict = dict(r)
                DocumentChunkModel.create(
                    document=new_doc,
                    chunk_index=r_dict["chunk_index"],
                    content=r_dict["content"],
                    content_hash=r_dict["content_hash"],
                    page_number=r_dict.get("page_number"),
                    heading_path=r_dict.get("heading_path"),
                    start_time=r_dict.get("start_time"),
                    end_time=r_dict.get("end_time"),
                )

        mark_document_version(new_doc)

        logger.info(
            "Document '%s' et %d chunks copiés avec succès de '%s' vers '%s'.",
            new_doc.title,
            len(chunks_rows),
            source_profile,
            target_profile,
        )
        return new_doc

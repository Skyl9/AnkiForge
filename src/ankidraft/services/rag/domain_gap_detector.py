"""Service de détection neuro-symbolique des lacunes de connaissances et décloisonnement de collection.

Approche F : Diagnostic en 3 passes combinant un référentiel conceptuel (Blueprint),
une aspiration globale dédoublonnée de la collection SQLite (Deck Virtuel) et une
analyse tripartite des écarts cognitifs (Type 1 Absences, Type 2 Atomicité, Type 3 Liant).
"""

from __future__ import annotations

import datetime
import html
import json
import logging
import os
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from peewee import JOIN, SqliteDatabase

from ankidraft.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedPatchModel,
    db,
)
from ankidraft.repositories.document_repository import DocumentRepository
from ankidraft.services.ai.staged_patch_registry import StagedPatchRegistry
from ankidraft.services.profile_manager import ProfileManager
from ankidraft.utils.i18n import tr
from ankidraft.utils.paths import get_active_profile

logger = logging.getLogger(__name__)


# ============================================================================
# Fonctions Utilitaires & Nettoyage Textuel
# ============================================================================


def strip_accents(text: str) -> str:
    """Normalise le texte en minuscules sans diacritiques (NFKD) pour le matching robuste."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c)).lower()


def slugify_anki_tag(tag_part: str) -> str:
    """Normalise une chaîne pour en faire un tag Anki valide sans espaces ni caractères réservés."""
    normalized = strip_accents(tag_part.strip())
    slug = re.sub(r"[^\w\-]", "-", normalized)
    return re.sub(r"-+", "-", slug).strip("-")


def sanitize_html_for_search(raw_html: str) -> str:
    """Nettoie le HTML en supprimant les blocs <style> et <script>.

    Décode également les entités HTML et retire les balises restantes.
    """
    no_scripts = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
    unescaped = html.unescape(no_scripts)
    no_tags = re.sub(r"<[^>]+>", " ", unescaped)
    return " ".join(no_tags.split())


def build_flexible_word_regex(expr: str) -> str:
    """Construit un motif regex gérant les tirets et espaces de manière interchangeable.

    Exemple : 'sans-etat' ou 'sans etat' -> r'\\bsans[-\\s]+etat\\b'.
    """
    escaped = re.escape(strip_accents(expr.strip()))
    flexible = re.sub(r"\\\s+|\\-", r"[-\\s]+", escaped)
    return r"\b" + flexible + r"\b"


def clean_cloze_text(raw_text: str) -> str:
    """Épure la syntaxe Cloze Anki en préservant le texte masqué et en retirant les indices.

    Exemple : '{{c1::401 Unauthorized::Code statut}}' -> '401 Unauthorized'.
    """
    return re.sub(r"\{\{c\d+::(.*?)(?:::.*?)?\}\}", r"\1", raw_text)


def compile_combined_sieve_regex(keywords: set[str]) -> re.Pattern[str]:
    """Compile un unique automate disjonctif pour tamiser 100% de la collection en une seule passe O(N).

    Évite l'explosion combinatoire O(N x K) sur les collections massives.
    """
    valid_kws = [kw.strip() for kw in keywords if kw.strip()]
    if not valid_kws:
        return re.compile(r"$^")
    patterns = [build_flexible_word_regex(kw) for kw in valid_kws]
    return re.compile("|".join(patterns), flags=re.IGNORECASE)


def clean_tech_and_math_blocks(raw_html: str) -> str:
    """Neutralise les blocs de code et délimiteurs mathématiques Anki / LaTeX / MathJax."""
    pattern = re.compile(
        r"(?:<pre[^>]*>[\s\S]*?<\/pre>|<code[^>]*>[\s\S]*?<\/code>|"
        r"\[\$\][\s\S]*?\[\/\$\]|\[\$\$\][\s\S]*?\[\/\$\$\]|"
        r"\\\[[\s\S]*?\\\]|\\\(.*?\\\)|\$\$[\s\S]*?\$\$)",
        flags=re.IGNORECASE,
    )
    return pattern.sub(" [BLOC_TECHNIQUE] ", raw_html)


def escape_markdown_table_cell(text: str) -> str:
    """Échappe les pipes et retours à la ligne pour garantir l'intégrité des tableaux Markdown."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def sanitize_subject_slug(subject: str) -> str:
    """Génère un slug de fichier sécurisé, sans traversée de chemin ni caractères réservés OS."""
    normalized = strip_accents(subject.strip())
    slug = re.sub(r"[^\w\-]", "_", normalized)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:64] or "domaine_inconnu"


def generate_ascii_progress_bar(percentage: float, length: int = 10) -> str:
    """Génère une jauge textuelle Unicode proportionnelle (ex: [████████░░] 80.0%)."""
    filled = int(round((percentage / 100.0) * length))
    filled = max(0, min(length, filled))
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {percentage:.1f}%"


# ============================================================================
# Modèles de Données & Structures Internes
# ============================================================================


@dataclass(frozen=True)
class RescuedCardEntry:
    """Fiche explicative d'une carte transversale repêchée hors du paquet cible."""

    note_id: int
    card_id: int
    source_deck: str
    prompt_preview: str
    matched_concepts: list[str]


@dataclass(frozen=True)
class DomainGapTelemetry:
    """Télémétrie d'exécution chronométrée en millisecondes pour chaque phase de l'audit."""

    passe_1_blueprint_ms: int
    passe_2_virtual_deck_ms: int
    passe_3_audit_ms: int
    total_duration_ms: int
    total_scanned_notes: int
    virtual_deck_filtered_cards: int


@dataclass(frozen=True)
class DomainConcept:
    """Représente une notion pivot du domaine cible."""

    id: str
    label: str
    keywords: list[str]
    description: str = ""
    criticality: str = "HIGH"
    is_acronym: bool = False
    source_chunk_ids: list[int] = field(default_factory=list)
    source_excerpt: str = ""


@dataclass(frozen=True)
class DomainRelation:
    """Relation conceptuelle, différentielle, causale ou conditionnelle entre deux notions."""

    source_id: str
    target_id: str
    relation_type: str  # contrast | causality | conditionality | synergy | prerequisite
    probe_question: str = ""

    def get_canonical_pair(self) -> frozenset[str] | tuple[str, str]:
        """Retourne une clé de dédoublonnage canonique (non ordonnée pour contrast/synergy)."""
        if self.relation_type in ("contrast", "synergy"):
            return frozenset({self.source_id, self.target_id})
        return (self.source_id, self.target_id)


@dataclass
class DomainBlueprint:
    """Référentiel conceptuel servant de gabarit d'évaluation."""

    subject: str
    concepts: list[DomainConcept]
    relations: list[DomainRelation] = field(default_factory=list)
    document_id: int | None = None
    document_slug: str = ""

    def get_all_keywords(self) -> set[str]:
        """Agrège l'ensemble des expressions dé-accentuées pour le tamis du deck virtuel."""
        kws: set[str] = set()
        for c in self.concepts:
            for kw in c.keywords:
                cleaned = strip_accents(kw.strip())
                if cleaned:
                    kws.add(cleaned)
            # Ajouter le label et les acronymes si pertinents
            c_label = strip_accents(c.label.strip())
            if c_label:
                kws.add(c_label)
        return kws

    def get_deduplicated_relations(self) -> list[DomainRelation]:
        """Retourne la liste des relations sans doublons miroirs (ex: A-B et B-A en contrast)."""
        seen: set[Any] = set()
        deduped: list[DomainRelation] = []
        for r in self.relations:
            pair = r.get_canonical_pair()
            if pair not in seen:
                seen.add(pair)
                deduped.append(r)
        return deduped


@dataclass
class VirtualCard:
    """Représentation dénormalisée d'une carte candidate extraite de toute la collection."""

    note_id: int
    primary_card_id: int
    card_ids: list[int]
    deck_name: str
    all_deck_names: list[str]
    target_deck_id: int | None
    note_type_name: str
    fields_dict: dict[str, str]
    primary_prompt: str
    primary_response: str
    secondary_context: str
    is_cloze: bool
    is_suspended: bool
    clean_text: str
    raw_response_html: str
    raw_text: str = ""
    is_staged: bool = False


@dataclass
class DomainMetrics:
    """Métrologie chiffrée consolidée pour l'affichage synthétique dans l'IDE et les jauges."""

    concept_coverage_pct: float
    atomicity_health_pct: float
    synthesis_coverage_pct: float
    global_health_score: float


@dataclass
class MissingConceptGap:
    """Type 1 : Concept indispensable absent de toute la collection active."""

    concept_id: str
    label: str
    criticality: str
    recommendation: str
    target_deck_id: int | None = None
    suggested_model_type: str = "basic"
    document_id: int | None = None
    document_slug: str = ""
    provenance_section: str = ""
    target_tags: list[str] = field(default_factory=list)
    source_excerpt: str = ""


@dataclass
class AtomicityGap:
    """Type 2 : Carte dont le bloc principal présente une surcharge cognitive."""

    note_id: int
    card_id: int
    deck_name: str
    prompt_preview: str
    reasons: list[str]
    suggested_split_count: int
    target_deck_id: int | None = None
    suggested_model_type: str = "basic"


@dataclass
class SynthesisGap:
    """Type 3 : Manque de liant, de nuance ou de confrontation causale/différentielle."""

    concept_a: str
    concept_b: str
    relation_type: str
    diagnosis: str
    suggested_card_prompt: str
    target_deck_id: int | None = None
    suggested_model_type: str = "basic"


@dataclass
class DomainGapReport:
    """Rapport consolidé d'audit différentiel."""

    subject: str
    domain_status: str  # UNSTARTED | IN_PROGRESS | MATURE
    metrics: DomainMetrics
    total_profile_cards: int
    virtual_deck_count: int
    transversal_cards_count: int
    transversal_cards_rescued: list[RescuedCardEntry]
    missing_concepts: list[MissingConceptGap]
    non_atomic_cards: list[AtomicityGap]
    missing_synthesis: list[SynthesisGap]
    staged_cards_included: int = 0
    full_report_path: str | None = None
    full_markdown_report_path: str | None = None
    telemetry: DomainGapTelemetry | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convertit le rapport en dictionnaire sérialisable en JSON."""
        return {
            "subject": self.subject,
            "domain_status": self.domain_status,
            "metrics": asdict(self.metrics),
            "total_profile_cards": self.total_profile_cards,
            "virtual_deck_count": self.virtual_deck_count,
            "transversal_cards_count": self.transversal_cards_count,
            "transversal_cards_rescued": [asdict(r) for r in self.transversal_cards_rescued],
            "missing_concepts": [asdict(m) for m in self.missing_concepts],
            "non_atomic_cards": [asdict(a) for a in self.non_atomic_cards],
            "missing_synthesis": [asdict(s) for s in self.missing_synthesis],
            "staged_cards_included": self.staged_cards_included,
            "full_report_path": self.full_report_path,
            "full_markdown_report_path": self.full_markdown_report_path,
            "telemetry": asdict(self.telemetry) if self.telemetry else None,
        }


# ============================================================================
# Constantes Regex Sémantiques Bilingues (FR/EN)
# ============================================================================

SYNTHESIS_MARKERS: dict[str, re.Pattern[str]] = {
    "contrast": re.compile(
        r"\b(difference|distinction|contrairement a|unlike|whereas|compared to|versus|vs|"
        r"a ne pas confondre avec|nuance|specificite|tandis que|alors que|oppose a|opposed to|"
        r"n'est pas|ne sont pas|ne garantit pas|ne supporte pas|ne permet pas|is not|are not|"
        r"does not guarantee|does not support|cannot be|contraire de|opposite of)\b",
        flags=re.IGNORECASE,
    ),
    "conditionality": re.compile(
        r"\b(sauf si|a l'exception de|except when|unless|conditioned by|only if|provided that|"
        r"conditionne par|uniquement si|limite|cas particulier|derogation|a condition que)\b",
        flags=re.IGNORECASE,
    ),
    "causality": re.compile(
        r"\b(entraine|cause|decoule de|leads to|results in|triggers|induces|stimulates|inhibits|"
        r"consequence|mecanisme|aboutit a|provoque|induit|stimule|inhibe|declenche)\b",
        flags=re.IGNORECASE,
    ),
    "synergy": re.compile(
        r"\b(complementaire|en synergie|synergy with|combined with|coupled with|alongside|"
        r"articule avec|conjointement|cooperation|par opposition|en regard de)\b",
        flags=re.IGNORECASE,
    ),
}


# ============================================================================
# Moteur de Détection DomainGapDetector
# ============================================================================


class DomainGapDetector:
    """Service d'audit et diagnostic des lacunes de connaissances pour l'ensemble d'un domaine."""

    def __init__(self, database: SqliteDatabase | None = None, reports_dir: Path | None = None) -> None:
        self.db = database or db
        self.reports_dir = reports_dir

    def _resolve_reports_dir(self) -> Path:
        """Détermine le dossier de stockage des rapports selon le profil actif."""
        if self.reports_dir is not None:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            return self.reports_dir
        pm = ProfileManager()
        active_prof = get_active_profile() or "default"
        rep_dir = pm.profiles_dir / active_prof / "reports"
        rep_dir.mkdir(parents=True, exist_ok=True)
        return rep_dir

    # ------------------------------------------------------------------------
    # Passe 1 : Établissement du Référentiel Conceptuel (Blueprint)
    # ------------------------------------------------------------------------

    def build_blueprint(
        self,
        subject: str,
        reference_document_id: int | None = None,
        blueprint_json: str = "",
    ) -> DomainBlueprint:
        """Construit le référentiel conceptuel à partir du document source ou du JSON externe."""
        # Cas B : JSON fourni par l'agent externe
        if blueprint_json and blueprint_json.strip():
            return self._parse_external_blueprint(subject, blueprint_json.strip())

        # Cas A : Document de référence
        if reference_document_id is not None:
            return self._build_blueprint_from_document(subject, reference_document_id)

        # Fallback par défaut si ni doc ni blueprint fourni
        return self._build_fallback_blueprint(subject)

    def _parse_external_blueprint(self, subject: str, raw_json: str) -> DomainBlueprint:
        """Désérialise et borne de façon défensive le blueprint injecté (anti-DoS)."""
        data = json.loads(raw_json)
        if not isinstance(data, dict):
            raise ValueError("Le blueprint doit être un objet JSON.")

        raw_concepts = data.get("concepts", [])[:50]  # Borne 50 concepts max
        raw_relations = data.get("relations", [])[:100]  # Borne 100 relations max

        concepts: list[DomainConcept] = []
        for rc in raw_concepts:
            if not isinstance(rc, dict):
                continue
            c_id = str(rc.get("id", "")).strip()
            c_label = str(rc.get("label", c_id)).strip()
            c_keywords = [str(kw).strip()[:80] for kw in rc.get("keywords", [])[:10] if str(kw).strip()]
            c_desc = str(rc.get("description", ""))
            c_crit = str(rc.get("criticality", "HIGH"))
            c_acronym = bool(rc.get("is_acronym", False))
            if c_id:
                concepts.append(
                    DomainConcept(
                        id=c_id,
                        label=c_label,
                        keywords=c_keywords,
                        description=c_desc,
                        criticality=c_crit,
                        is_acronym=c_acronym,
                    )
                )

        relations: list[DomainRelation] = []
        for rr in raw_relations:
            if not isinstance(rr, dict):
                continue
            s_id = str(rr.get("source_id", "")).strip()
            t_id = str(rr.get("target_id", "")).strip()
            r_type = str(rr.get("relation_type", "contrast")).strip().lower()
            probe = str(rr.get("probe_question", "")).strip()
            if s_id and t_id:
                relations.append(
                    DomainRelation(
                        source_id=s_id,
                        target_id=t_id,
                        relation_type=r_type,
                        probe_question=probe,
                    )
                )

        return DomainBlueprint(
            subject=subject.strip(),
            concepts=concepts,
            relations=relations,
        )

    def _build_blueprint_from_document(self, subject: str, document_id: int) -> DomainBlueprint:
        """Extrait les concepts et relations à partir des sections et chunks du document."""
        doc = DocumentModel.get_or_none(DocumentModel.id == document_id)
        if not doc:
            raise FileNotFoundError(f"Document introuvable pour l'id {document_id}")

        doc_slug = slugify_anki_tag(doc.title or subject)
        doc_repo = DocumentRepository()
        raw_chunks = doc_repo.get_chunks_for_document(document_id)

        # Filtrage ADR 0010 : écarter sections neutralisées ou exclues
        valid_chunks: list[DocumentChunkModel] = []
        for ch in raw_chunks:
            if DocumentRepository.is_region_excluded(doc, heading_path=ch.heading_path, page_number=ch.page_number):
                continue
            if DocumentRepository.is_region_neutralized(doc, heading_path=ch.heading_path, page_number=ch.page_number):
                continue
            valid_chunks.append(ch)

        # Regroupement au niveau h1 ou h2 du fil d'Ariane
        section_map: dict[str, dict[str, Any]] = {}
        for ch in valid_chunks:
            hp = ch.heading_path or ""
            parts = [p.strip() for p in hp.split(">") if p.strip()]
            if not parts:
                sec_key = "Introduction"
                h_level = 1
                parent_h1 = "Introduction"
            elif len(parts) == 1:
                sec_key = parts[0]
                h_level = 1
                parent_h1 = parts[0]
            else:
                # Niveau 2 (h2) comme pivot
                sec_key = parts[1]
                h_level = 2
                parent_h1 = parts[0]

            if sec_key not in section_map:
                section_map[sec_key] = {
                    "label": sec_key,
                    "h_level": h_level,
                    "parent_h1": parent_h1,
                    "texts": [],
                    "chunk_ids": [],
                    "subsections": set(),
                }
            section_map[sec_key]["texts"].append(ch.content)
            section_map[sec_key]["chunk_ids"].append(ch.id)
            if len(parts) > 2:
                section_map[sec_key]["subsections"].update(parts[2:])

        # Repli déterministe pour documents sans titres Markdown (heading_path vide ou <= 2 sections)
        if len(section_map) < 3 and doc.content and len(doc.content.split()) > 100:
            return self._build_blueprint_from_unstructured_text(subject, doc, doc_slug)

        concepts: list[DomainConcept] = []
        relations: list[DomainRelation] = []
        sec_items = list(section_map.items())[:30]  # Plafond 30 concepts

        for sec_name, data in sec_items:
            combined_text = " ".join(data["texts"])
            excerpt = combined_text[:400].strip()
            # Mots-clés : nom de la section + sous-sections + termes fréquents
            kws: list[str] = [sec_name]
            kws.extend(list(data["subsections"]))
            words = [w for w in re.findall(r"\b\w{4,}\b", combined_text) if len(w) > 3]
            most_freq = [w for w, _ in Counter(words).most_common(5) if w.lower() not in strip_accents(sec_name)]
            kws.extend(most_freq)

            c_id = slugify_anki_tag(sec_name)
            concepts.append(
                DomainConcept(
                    id=c_id,
                    label=sec_name,
                    keywords=list(dict.fromkeys(kws))[:10],
                    source_chunk_ids=data["chunk_ids"],
                    source_excerpt=excerpt,
                    criticality="HIGH" if data["h_level"] == 1 else "MEDIUM",
                )
            )

        # Extraction déterministe des relations entre sections sœurs
        for i in range(len(sec_items)):
            name_a, data_a = sec_items[i]
            id_a = slugify_anki_tag(name_a)
            for j in range(i + 1, len(sec_items)):
                name_b, data_b = sec_items[j]
                id_b = slugify_anki_tag(name_b)
                # Sections sœurs sous le même h1 -> contrast
                if data_a["parent_h1"] == data_b["parent_h1"]:
                    relations.append(
                        DomainRelation(
                            source_id=id_a,
                            target_id=id_b,
                            relation_type="contrast",
                            probe_question=f"Différence entre {name_a} et {name_b}",
                        )
                    )
                # Sections consécutives de niveau 2 -> causality ou prerequisite
                elif j == i + 1:
                    relations.append(
                        DomainRelation(
                            source_id=id_a,
                            target_id=id_b,
                            relation_type="causality",
                            probe_question=f"Articulation entre {name_a} et {name_b}",
                        )
                    )

        return DomainBlueprint(
            subject=subject.strip(),
            concepts=concepts,
            relations=relations,
            document_id=document_id,
            document_slug=doc_slug,
        )

    def _build_blueprint_from_unstructured_text(
        self,
        subject: str,
        doc: DocumentModel,
        doc_slug: str,
    ) -> DomainBlueprint:
        """Découpe un document sans titres en tranches textuelles de 800 à 1500 caractères."""
        text = doc.content or ""
        chunk_size = 1200
        slices = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size) if len(text[i : i + chunk_size]) > 100]
        if not slices:
            slices = [text]

        concepts: list[DomainConcept] = []
        for idx, sl in enumerate(slices[:20], start=1):
            lbl = f"Section {idx}"
            words = [w for w in re.findall(r"\b\w{4,}\b", sl) if len(w) > 3]
            top_words = [w for w, _ in Counter(words).most_common(4)]
            concepts.append(
                DomainConcept(
                    id=f"sec_{idx}",
                    label=lbl,
                    keywords=[lbl] + top_words,
                    source_excerpt=sl[:400].strip(),
                )
            )

        relations: list[DomainRelation] = []
        for i in range(len(concepts) - 1):
            relations.append(
                DomainRelation(
                    source_id=concepts[i].id,
                    target_id=concepts[i + 1].id,
                    relation_type="causality",
                )
            )

        return DomainBlueprint(
            subject=subject,
            concepts=concepts,
            relations=relations,
            document_id=doc.id,
            document_slug=doc_slug,
        )

    def _build_fallback_blueprint(self, subject: str) -> DomainBlueprint:
        """Génère un blueprint de secours minimal à partir du libellé du sujet."""
        slug = sanitize_subject_slug(subject)
        sub_concept = DomainConcept(
            id=slug,
            label=subject,
            keywords=[subject] + [w for w in subject.split() if len(w) > 3],
        )
        return DomainBlueprint(subject=subject, concepts=[sub_concept], relations=[])

    # ------------------------------------------------------------------------
    # Passe 2 : Extraction Exhaustive Optimisée & Tamis
    # ------------------------------------------------------------------------

    def extract_virtual_deck(
        self,
        blueprint: DomainBlueprint,
        target_deck: str = "",
        include_suspended: bool = False,
    ) -> tuple[list[VirtualCard], list[RescuedCardEntry], int]:
        """Extrait l'ensemble des notes pertinentes de la collection en une requête unique O(N)."""
        # 1. Clôture des transactions SQLite pendantes
        if not self.db.is_closed() and self.db.in_transaction():
            self.db.commit()

        # 2. Requête SQL Peewee unique
        query = (
            NoteModel.select(
                NoteModel.id.alias("note_id"),
                NoteModel.tags.alias("tags"),
                NoteTypeModel.name.alias("note_type_name"),
                NoteVersionModel.content.alias("content"),
                CardModel.id.alias("card_id"),
                CardModel.is_suspended.alias("is_suspended"),
                DeckModel.id.alias("deck_id"),
                DeckModel.name.alias("deck_name"),
            )
            .join(NoteVersionModel, on=(NoteVersionModel.note == NoteModel.id))
            .where(NoteVersionModel.is_active == True)  # noqa: E712
            .switch(NoteModel)
            .join(NoteTypeModel, JOIN.LEFT_OUTER, on=(NoteModel.note_type == NoteTypeModel.id))
            .switch(NoteModel)
            .join(CardModel, JOIN.LEFT_OUTER, on=(CardModel.note == NoteModel.id))
            .switch(CardModel)
            .join(DeckModel, JOIN.LEFT_OUTER, on=(CardModel.deck == DeckModel.id))
            .dicts()
        )
        raw_rows: list[dict[str, Any]] = list(cast(Iterable[dict[str, Any]], query))
        total_profile_cards = len(raw_rows)

        # 3. Regroupement par note_id
        grouped_notes: dict[int, list[dict[str, Any]]] = {}
        for row in raw_rows:
            nid = int(row["note_id"])
            grouped_notes.setdefault(nid, []).append(row)

        target_clean = target_deck.strip().lower()

        # Compiler le tamis combiné
        all_keywords = blueprint.get_all_keywords()
        sieve_regex = compile_combined_sieve_regex(all_keywords)

        virtual_cards: list[VirtualCard] = []
        rescued_cards: list[RescuedCardEntry] = []

        for nid, note_rows in grouped_notes.items():
            first_row = note_rows[0]
            # Résolution de l'activité de la note
            has_active_card = any(not r.get("is_suspended", False) for r in note_rows)
            if not include_suspended and not has_active_card:
                continue

            # Cartes physiques
            card_ids = [int(r["card_id"]) for r in note_rows if r.get("card_id") is not None]
            primary_card_id = min(card_ids) if card_ids else nid

            all_decks = [str(r.get("deck_name") or "Sans paquet") for r in note_rows]
            dominant_deck = Counter(all_decks).most_common(1)[0][0] if all_decks else "Sans paquet"
            target_deck_id = first_row.get("deck_id")

            # Décodage du contenu
            content_raw = first_row.get("content") or "{}"
            try:
                fields_dict = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
            except Exception:
                fields_dict = {}

            # Extraction des champs
            vals = list(fields_dict.values())
            primary_prompt = vals[0] if len(vals) > 0 else ""
            primary_response = vals[1] if len(vals) > 1 else ""
            secondary_context = " ".join(vals[2:]) if len(vals) > 2 else ""

            # Concaténation et nettoyage
            raw_full = " ".join(str(v) for v in vals)
            is_cloze = "{{c" in raw_full
            cloze_cleaned = clean_cloze_text(raw_full)
            sanitized_text = sanitize_html_for_search(cloze_cleaned)
            clean_text = strip_accents(sanitized_text)

            # Vérification par acronymes stricts ou tamis général
            matched = False
            matched_concept_ids: list[str] = []

            for concept in blueprint.concepts:
                if concept.is_acronym:
                    # Règle des acronymes <= 2 lettres : exiger l'expression développée
                    if len(concept.id) <= 2:
                        for kw in concept.keywords:
                            if strip_accents(kw) in clean_text:
                                matched = True
                                matched_concept_ids.append(concept.id)
                                break
                    else:
                        # Règle 3-4 lettres : \bREST\b exact en majuscule OU expression développée
                        if re.search(r"\b" + re.escape(concept.id.upper()) + r"\b", raw_full):
                            matched = True
                            matched_concept_ids.append(concept.id)
                        else:
                            for kw in concept.keywords:
                                if strip_accents(kw) in clean_text:
                                    matched = True
                                    matched_concept_ids.append(concept.id)
                                    break
                else:
                    for kw in concept.keywords:
                        if re.search(build_flexible_word_regex(kw), clean_text):
                            matched = True
                            matched_concept_ids.append(concept.id)
                            break
                    if strip_accents(concept.label) in clean_text:
                        matched = True
                        if concept.id not in matched_concept_ids:
                            matched_concept_ids.append(concept.id)

            if not matched and sieve_regex.search(clean_text):
                matched = True

            if not matched:
                continue

            # Qualification dans le VirtualCard
            vc = VirtualCard(
                note_id=nid,
                primary_card_id=primary_card_id,
                card_ids=card_ids,
                deck_name=dominant_deck,
                all_deck_names=all_decks,
                target_deck_id=target_deck_id,
                note_type_name=str(first_row.get("note_type_name") or "Basique"),
                fields_dict=fields_dict,
                primary_prompt=primary_prompt,
                primary_response=primary_response,
                secondary_context=secondary_context,
                is_cloze=is_cloze,
                is_suspended=not has_active_card,
                clean_text=clean_text,
                raw_response_html=primary_response,
                raw_text=raw_full,
            )
            virtual_cards.append(vc)

            # Vérification du rattachement au paquet cible
            is_in_target = False
            if target_clean:
                for dk in all_decks:
                    dk_low = dk.strip().lower()
                    if dk_low == target_clean or dk_low.startswith(f"{target_clean}::"):
                        is_in_target = True
                        break

                if not is_in_target:
                    preview = (sanitize_html_for_search(primary_prompt) or clean_text)[:60]
                    rescued_cards.append(
                        RescuedCardEntry(
                            note_id=nid,
                            card_id=primary_card_id,
                            source_deck=dominant_deck,
                            prompt_preview=preview,
                            matched_concepts=matched_concept_ids,
                        )
                    )

        # 4. Intégration de l'Overlay Virtuel des Staged Bundles (ADR 0043)
        staged_cards = self._extract_staged_overlay_cards(blueprint, target_deck)
        virtual_cards.extend(staged_cards)

        return virtual_cards, rescued_cards, total_profile_cards

    def _extract_staged_overlay_cards(
        self,
        blueprint: DomainBlueprint,
        target_deck: str = "",
    ) -> list[VirtualCard]:
        """Extrait les cartes en attente dans un Staged Bundle actif pour le deck virtuel."""
        if not StagedPatchRegistry._active_bundles:
            return []

        staged_cards: list[VirtualCard] = []
        pending_patches = list(
            StagedPatchModel.select().where(
                StagedPatchModel.status == "pending",
                StagedPatchModel.patch_type.in_(["note_create", "batch_note_create"]),
            )
        )

        for p in pending_patches:
            try:
                payload = json.loads(p.diff_payload) if isinstance(p.diff_payload, str) else p.diff_payload
            except Exception as err:
                logger.warning("Payload de patch staged invalide pour %s : %s", p.patch_id, err)
                continue
            if not isinstance(payload, dict):
                continue

            notes_to_add: list[dict[str, Any]] = []
            if p.patch_type == "note_create":
                notes_to_add.append(payload)
            elif p.patch_type == "batch_note_create":
                batch = payload.get("notes") or []
                def_dk = payload.get("default_deck")
                for n in batch:
                    if isinstance(n, dict):
                        if "deck" not in n and def_dk:
                            n["deck"] = def_dk
                        notes_to_add.append(n)

            for idx, note_dict in enumerate(notes_to_add, start=1000):
                dk = str(note_dict.get("deck") or note_dict.get("deck_name") or target_deck or "Staged")
                fields = note_dict.get("fields") or {}
                vals = list(fields.values()) if isinstance(fields, dict) else []
                raw_full = " ".join(str(v) for v in vals)
                cloze_cleaned = clean_cloze_text(raw_full)
                clean_text = strip_accents(sanitize_html_for_search(cloze_cleaned))

                # Vérifier si la carte staged correspond au blueprint
                matched = False
                for c in blueprint.concepts:
                    if any(re.search(build_flexible_word_regex(kw), clean_text) for kw in c.keywords):
                        matched = True
                        break
                    if strip_accents(c.label) in clean_text:
                        matched = True
                        break

                if matched:
                    staged_cards.append(
                        VirtualCard(
                            note_id=-idx,
                            primary_card_id=-idx,
                            card_ids=[-idx],
                            deck_name=dk,
                            all_deck_names=[dk],
                            target_deck_id=None,
                            note_type_name="Staged",
                            fields_dict=fields if isinstance(fields, dict) else {},
                            primary_prompt=vals[0] if vals else "",
                            primary_response=vals[1] if len(vals) > 1 else "",
                            secondary_context="",
                            is_cloze="{{c" in raw_full,
                            is_suspended=False,
                            clean_text=clean_text,
                            raw_response_html=vals[1] if len(vals) > 1 else "",
                            raw_text=raw_full,
                            is_staged=True,
                        )
                    )

        return staged_cards

    # ------------------------------------------------------------------------
    # Passe 3 : Diagnostic Tripartite des Lacunes & Métrologie
    # ------------------------------------------------------------------------

    def analyze_gaps(
        self,
        blueprint: DomainBlueprint,
        virtual_cards: list[VirtualCard],
        rescued_cards: list[RescuedCardEntry],
        total_profile_cards: int,
        target_deck: str = "",
    ) -> DomainGapReport:
        """Exécute l'analyse d'écarts cognitifs et consolide le rapport avec ses métriques."""
        # Résolution du paquet dominant par défaut
        dominant_deck_id: int | None = None
        dominant_deck_name = target_deck
        if virtual_cards:
            deck_counts = Counter(c.deck_name for c in virtual_cards if not c.is_staged)
            if deck_counts:
                dominant_deck_name = deck_counts.most_common(1)[0][0]
                matching_card = next((c for c in virtual_cards if c.deck_name == dominant_deck_name and c.target_deck_id), None)
                if matching_card:
                    dominant_deck_id = matching_card.target_deck_id

        if dominant_deck_id is None:
            first_deck = DeckModel.select().first()
            if first_deck:
                dominant_deck_id = first_deck.id

        # Cas Limite : Deck Virtuel Vide (|Cs| == 0) -> Collection Vierge
        if not virtual_cards:
            missing_all = [
                MissingConceptGap(
                    concept_id=c.id,
                    label=c.label,
                    criticality=c.criticality,
                    recommendation=tr("Créer 1 à 2 carte(s) atomique(s) couvrant la notion '%1' à partir de la source.", c.label),
                    target_deck_id=dominant_deck_id,
                    document_id=blueprint.document_id,
                    document_slug=blueprint.document_slug,
                    source_excerpt=c.source_excerpt,
                    target_tags=[
                        f"source:{slugify_anki_tag(blueprint.document_slug or blueprint.subject)}",
                        f"section:{slugify_anki_tag(c.label)}",
                    ],
                )
                for c in blueprint.concepts
            ]
            metrics_empty = DomainMetrics(
                concept_coverage_pct=0.0,
                atomicity_health_pct=100.0,
                synthesis_coverage_pct=100.0,
                global_health_score=0.0,
            )
            return DomainGapReport(
                subject=blueprint.subject,
                domain_status="UNSTARTED",
                metrics=metrics_empty,
                total_profile_cards=total_profile_cards,
                virtual_deck_count=0,
                transversal_cards_count=0,
                transversal_cards_rescued=[],
                missing_concepts=missing_all,
                non_atomic_cards=[],
                missing_synthesis=[],
            )

        # 1. Type 1 — Détection des Concepts Absents
        missing_concepts: list[MissingConceptGap] = []
        covered_concept_ids: set[str] = set()

        for concept in blueprint.concepts:
            is_covered = False
            for vc in virtual_cards:
                if concept.is_acronym:
                    if len(concept.id) <= 2:
                        for kw in concept.keywords:
                            if strip_accents(kw) in vc.clean_text:
                                is_covered = True
                                break
                    else:
                        if re.search(r"\b" + re.escape(concept.id.upper()) + r"\b", vc.raw_text):
                            is_covered = True
                        else:
                            for kw in concept.keywords:
                                if strip_accents(kw) in vc.clean_text:
                                    is_covered = True
                                    break
                else:
                    for kw in concept.keywords:
                        if re.search(build_flexible_word_regex(kw), vc.clean_text):
                            is_covered = True
                            break
                    if not is_covered and strip_accents(concept.label) in vc.clean_text:
                        is_covered = True

                if is_covered:
                    covered_concept_ids.add(concept.id)
                    break

            if not is_covered:
                tag_doc = slugify_anki_tag(blueprint.document_slug or blueprint.subject)
                tag_sec = slugify_anki_tag(concept.label)
                missing_concepts.append(
                    MissingConceptGap(
                        concept_id=concept.id,
                        label=concept.label,
                        criticality=concept.criticality,
                        recommendation=tr(
                            "Créer 1 à 2 carte(s) atomique(s) couvrant la notion '%1' à partir de la section source.",
                            concept.label,
                        ),
                        target_deck_id=dominant_deck_id,
                        document_id=blueprint.document_id,
                        document_slug=blueprint.document_slug,
                        provenance_section=concept.label,
                        target_tags=[f"source:{tag_doc}", f"section:{tag_sec}"],
                        source_excerpt=concept.source_excerpt,
                    )
                )

        # 2. Type 2 — Analyse Qualitative d'Atomicité
        non_atomic_cards: list[AtomicityGap] = []
        for vc in virtual_cards:
            reasons = self._evaluate_card_atomicity(vc)
            if reasons:
                preview = (sanitize_html_for_search(vc.primary_prompt) or vc.clean_text)[:60]
                non_atomic_cards.append(
                    AtomicityGap(
                        note_id=vc.note_id,
                        card_id=vc.primary_card_id,
                        deck_name=vc.deck_name,
                        prompt_preview=preview,
                        reasons=reasons,
                        suggested_split_count=max(2, len(reasons) + 1),
                        target_deck_id=vc.target_deck_id or dominant_deck_id,
                    )
                )

        # 3. Type 3 — Détection du Manque de Liant Bilingue
        missing_synthesis: list[SynthesisGap] = []
        deduped_relations = blueprint.get_deduplicated_relations()

        for rel in deduped_relations:
            # Vérifier si les deux concepts sont couverts individuellement
            if rel.source_id not in covered_concept_ids or rel.target_id not in covered_concept_ids:
                continue

            concept_a = next((c for c in blueprint.concepts if c.id == rel.source_id), None)
            concept_b = next((c for c in blueprint.concepts if c.id == rel.target_id), None)
            if not concept_a or not concept_b:
                continue

            synthesis_found = False
            marker_pattern = SYNTHESIS_MARKERS.get(rel.relation_type, SYNTHESIS_MARKERS["contrast"])

            for vc in virtual_cards:
                has_a = any(strip_accents(kw) in vc.clean_text for kw in concept_a.keywords) or strip_accents(concept_a.label) in vc.clean_text
                has_b = any(strip_accents(kw) in vc.clean_text for kw in concept_b.keywords) or strip_accents(concept_b.label) in vc.clean_text

                if has_a and has_b and marker_pattern.search(vc.clean_text):
                    synthesis_found = True
                    break

            if not synthesis_found:
                missing_synthesis.append(
                    SynthesisGap(
                        concept_a=concept_a.label,
                        concept_b=concept_b.label,
                        relation_type=rel.relation_type,
                        diagnosis=tr(
                            "Notions '%1' et '%2' acquises séparément mais absence de carte comparative explicitant leur distinction ou causalité.",
                            concept_a.label,
                            concept_b.label,
                        ),
                        suggested_card_prompt=tr("Quelle est la différence essentielle entre %1 et %2 ?", concept_a.label, concept_b.label),
                        target_deck_id=dominant_deck_id,
                    )
                )

        # 4. Calcul de la Métrologie Chiffrée Consolidée
        metrics = self.compute_metrics(
            total_concepts=len(blueprint.concepts),
            missing_concepts_count=len(missing_concepts),
            virtual_deck_count=len(virtual_cards),
            non_atomic_cards_count=len(non_atomic_cards),
            total_relations=len(deduped_relations),
            missing_synthesis_count=len(missing_synthesis),
        )

        # Détermination du statut global
        domain_status = "MATURE" if metrics.global_health_score >= 85.0 and len(missing_concepts) == 0 else "IN_PROGRESS"

        staged_count = sum(1 for vc in virtual_cards if vc.is_staged)

        return DomainGapReport(
            subject=blueprint.subject,
            domain_status=domain_status,
            metrics=metrics,
            total_profile_cards=total_profile_cards,
            virtual_deck_count=len(virtual_cards),
            transversal_cards_count=len(rescued_cards),
            transversal_cards_rescued=rescued_cards,
            missing_concepts=missing_concepts,
            non_atomic_cards=non_atomic_cards,
            missing_synthesis=missing_synthesis,
            staged_cards_included=staged_count,
        )

    def _evaluate_card_atomicity(self, card: VirtualCard) -> list[str]:
        """Évalue qualitativement le bloc principal d'une carte (Wozniak règles 4 et 8)."""
        reasons: list[str] = []

        # Inspection Cloze spécifique (Règle 8 de Wozniak : omission composite)
        if card.is_cloze:
            cloze_matches = re.findall(r"\{\{c\d+::(.*?)(?:::.*?)?\}\}", card.raw_text)
            for cm in cloze_matches:
                segments = re.split(r",|;|<br\s*/?>|\band\b|\bet\b", cm)
                valid_segs = [s.strip() for s in segments if s.strip()]
                if len(valid_segs) >= 3:
                    reasons.append(tr("Omission Cloze composite : teste un ensemble de faits simultanés au lieu d'une notion unitaire (Règle 8 de Wozniak)."))
                    break
            # Tolérance de longueur accrue sur la phrase hôte Cloze (<75 mots)
            word_count = len(sanitize_html_for_search(clean_cloze_text(card.raw_text)).split())
            if word_count > 75:
                reasons.append(tr("Phrase Cloze excessivement longue (%1 mots > 75 mots tolérés).", word_count))
            return reasons

        # Découpage Bloc Principal vs Bloc Annexe
        raw_resp = card.raw_response_html or ""
        # Découpe sur séparateurs visuels
        split_pattern = re.compile(
            r"<hr[^>]*>|<blockquote>|<details>|<small>|<h[2-6][^>]*>(?:Remarque|Détails|Contexte|Notes?)</h[2-6]>",
            flags=re.IGNORECASE,
        )
        parts = split_pattern.split(raw_resp, maxsplit=1)
        primary_block_html = parts[0] if parts else raw_resp

        # Neutralisation préalable des blocs techniques et formules scientifiques
        clean_primary = clean_tech_and_math_blocks(primary_block_html)
        text_primary = sanitize_html_for_search(clean_primary)
        words = text_primary.split()
        word_count = len(words)

        # 1. Énumérations à puces dans le bloc principal
        li_matches = re.findall(r"<li[^>]*>(.*?)</li>", primary_block_html, flags=re.DOTALL | re.IGNORECASE)
        if li_matches:
            li_texts = [sanitize_html_for_search(li) for li in li_matches]
            # Si >= 5 puces -> Rejet immédiat
            if len(li_texts) >= 5:
                reasons.append(tr("Énumération excessive dans le bloc principal (%1 puces > 4 tolérées).", len(li_texts)))
            elif len(li_texts) in (3, 4):
                # Tolérance : si chaque puce est concise (<8 mots simples), validé sans pénalité !
                avg_words = sum(len(t.split()) for t in li_texts) / len(li_texts)
                has_complex_sub = any(":" in t or ";" in t for t in li_texts)
                if avg_words > 8 or has_complex_sub:
                    reasons.append(tr("Énumération dense de %1 puces complexes (moyenne de %2 mots par puce).", len(li_texts), round(avg_words, 1)))

        # 2. Bloc compact non structuré > 45 mots sans paragraphe
        elif word_count > 45:
            reasons.append(tr("Bloc principal compact non atomique de %1 mots (> 45 mots sans séparation visuelle).", word_count))

        # 3. Empilement de définitions primaires concurrentes ou de faits multiples avec séparateurs
        colon_count = text_primary.count(":")
        def_markers = len(re.findall(r"\b(?:c'est-a-dire|signifie|definit|constitue|represente)\b", strip_accents(text_primary)))
        if (def_markers >= 3 and word_count > 35) or (colon_count >= 3 and word_count > 30):
            reasons.append(tr("Empilement de faits ou définitions concurrentes dans le bloc principal (%1 repères détectés).", max(def_markers, colon_count)))

        return reasons

    @staticmethod
    def compute_metrics(
        total_concepts: int,
        missing_concepts_count: int,
        virtual_deck_count: int,
        non_atomic_cards_count: int,
        total_relations: int,
        missing_synthesis_count: int,
    ) -> DomainMetrics:
        """Calcule de manière déterministe les métriques chiffrées DomainMetrics."""
        covered_concepts = total_concepts - missing_concepts_count
        concept_coverage_pct = round((max(0, covered_concepts) / max(1, total_concepts)) * 100, 1)

        healthy_cards = virtual_deck_count - non_atomic_cards_count
        atomicity_health_pct = round((max(0, healthy_cards) / max(1, virtual_deck_count)) * 100, 1)

        if total_relations == 0:
            synthesis_coverage_pct = 100.0
            global_health_score = round((0.65 * concept_coverage_pct) + (0.35 * atomicity_health_pct), 1)
        else:
            covered_relations = total_relations - missing_synthesis_count
            synthesis_coverage_pct = round((max(0, covered_relations) / total_relations) * 100, 1)
            global_health_score = round(
                (0.50 * concept_coverage_pct) + (0.25 * atomicity_health_pct) + (0.25 * synthesis_coverage_pct),
                1,
            )

        return DomainMetrics(
            concept_coverage_pct=concept_coverage_pct,
            atomicity_health_pct=atomicity_health_pct,
            synthesis_coverage_pct=synthesis_coverage_pct,
            global_health_score=global_health_score,
        )

    # ------------------------------------------------------------------------
    # Pipeline Complet & Export sur Disque
    # ------------------------------------------------------------------------

    def diagnose(
        self,
        subject: str,
        target_deck: str = "",
        reference_document_id: int | None = None,
        blueprint_json: str = "",
        include_suspended: bool = False,
    ) -> DomainGapReport:
        """Point d'entrée principal orchestrant les 3 passes et la génération des rapports."""
        t_start = time.perf_counter()

        # Passe 1
        t_p1_start = time.perf_counter()
        blueprint = self.build_blueprint(
            subject=subject,
            reference_document_id=reference_document_id,
            blueprint_json=blueprint_json,
        )
        t_p1_end = time.perf_counter()

        # Passe 2
        t_p2_start = time.perf_counter()
        virtual_cards, rescued_cards, total_profile_cards = self.extract_virtual_deck(
            blueprint=blueprint,
            target_deck=target_deck,
            include_suspended=include_suspended,
        )
        t_p2_end = time.perf_counter()

        # Passe 3
        t_p3_start = time.perf_counter()
        report = self.analyze_gaps(
            blueprint=blueprint,
            virtual_cards=virtual_cards,
            rescued_cards=rescued_cards,
            total_profile_cards=total_profile_cards,
            target_deck=target_deck,
        )
        t_p3_end = time.perf_counter()
        t_total_end = time.perf_counter()

        # Télémétrie
        telemetry = DomainGapTelemetry(
            passe_1_blueprint_ms=int((t_p1_end - t_p1_start) * 1000),
            passe_2_virtual_deck_ms=int((t_p2_end - t_p2_start) * 1000),
            passe_3_audit_ms=int((t_p3_end - t_p3_start) * 1000),
            total_duration_ms=int((t_total_end - t_start) * 1000),
            total_scanned_notes=total_profile_cards,
            virtual_deck_filtered_cards=len(virtual_cards),
        )
        report.telemetry = telemetry

        # Export sur disque (ADR 0048)
        json_path, md_path = self.export_reports(report)
        report.full_report_path = str(json_path)
        report.full_markdown_report_path = str(md_path)

        return report

    def export_reports(self, report: DomainGapReport) -> tuple[Path, Path]:
        """Génère les deux fichiers de rapport persistant (JSON et Markdown exécutif)."""
        reports_dir = self._resolve_reports_dir()
        slug = sanitize_subject_slug(report.subject)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        latest_json_path = reports_dir / f"domain_gaps_{slug}_latest.json"
        archive_json_path = reports_dir / f"domain_gaps_{slug}_{timestamp}.json"
        latest_md_path = reports_dir / f"domain_gaps_{slug}_latest.md"

        # 1. Écriture atomique JSON
        json_content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        self._atomic_write(latest_json_path, json_content)
        self._atomic_write(archive_json_path, json_content)

        # 2. Écriture atomique Markdown
        md_content = self._render_markdown_report(report)
        self._atomic_write(latest_md_path, md_content)

        # 3. Rotation automatique (max 10 archives)
        self._rotate_archives(reports_dir, slug)

        return latest_json_path, latest_md_path

    def _atomic_write(self, target_path: Path, content: str) -> None:
        """Écrit le fichier sous forme temporaire puis le déplace atomiquement (os.replace)."""
        tmp_path = target_path.with_suffix(".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, target_path)

    def _rotate_archives(self, reports_dir: Path, slug: str) -> None:
        """Ne conserve au maximum que les 10 archives horodatées les plus récentes."""
        pattern = re.compile(rf"^domain_gaps_{re.escape(slug)}_\d{{8}}_\d{{6}}\.json$")
        archives = [p for p in reports_dir.iterdir() if pattern.match(p.name)]
        archives.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in archives[10:]:
            try:
                old.unlink()
            except OSError as exc:
                logger.debug("Échec de suppression de l'archive obsolète %s : %s", old, exc)

    def _render_markdown_report(self, report: DomainGapReport) -> str:
        """Génère le rapport exécutif Markdown avec jauges textuelles Unicode et callouts."""
        badge_status = {
            "MATURE": "🟢 MATURE",
            "IN_PROGRESS": "🟡 EN COURS",
            "UNSTARTED": "🔴 VIERGE",
        }.get(report.domain_status, "⚪ INCONNU")

        lines = [
            f"# Rapport d'Audit de Domaine — {escape_markdown_table_cell(report.subject)}",
            "",
            f"**Statut Global :** {badge_status} · **Score de Maîtrise :** `{report.metrics.global_health_score:.1f}%`",
            f"**Cartes inspectées :** `{report.total_profile_cards}` · **Deck Virtuel :** `{report.virtual_deck_count}` · **Transversales sauvées :** `{report.transversal_cards_count}`",
            "",
            "## 📊 Métrologie Chiffrée Consolidée",
            "",
            "| Métrique | Jauge de Progression | Score |",
            "| :--- | :--- | :---: |",
            f"| Couverture des Concepts (Type 1) | `{generate_ascii_progress_bar(report.metrics.concept_coverage_pct)}` | {report.metrics.concept_coverage_pct:.1f}% |",
            f"| Santé d'Atomicité (Type 2) | `{generate_ascii_progress_bar(report.metrics.atomicity_health_pct)}` | {report.metrics.atomicity_health_pct:.1f}% |",
            f"| Couverture du Liant (Type 3) | `{generate_ascii_progress_bar(report.metrics.synthesis_coverage_pct)}` | {report.metrics.synthesis_coverage_pct:.1f}% |",
            f"| **Score Global Pondéré** | `{generate_ascii_progress_bar(report.metrics.global_health_score)}` | **{report.metrics.global_health_score:.1f}%** |",
            "",
        ]

        if report.staged_cards_included > 0:
            lines.extend(
                [
                    "> [!TIP]",
                    f"> **Intégration Staged Bundle (ADR 0043)** : {report.staged_cards_included} carte(s) en attente de commit ont été intégrées dans l'évaluation virtuelle.",
                    "",
                ]
            )

        # Type 1
        lines.extend(
            [
                "## 🔴 1. Concepts Absents (Type 1)",
                "",
            ]
        )
        if not report.missing_concepts:
            lines.append("✅ *Aucun concept manquant identifié. Tous les concepts pivots sont couverts.*")
        else:
            lines.extend(
                [
                    "| Concept | Criticité | Recommandation | Extrait Source Probant |",
                    "| :--- | :---: | :--- | :--- |",
                ]
            )
            for m in report.missing_concepts[:15]:
                lbl = escape_markdown_table_cell(m.label)
                rec = escape_markdown_table_cell(m.recommendation)
                exc = escape_markdown_table_cell(m.source_excerpt[:100] + "..." if len(m.source_excerpt) > 100 else m.source_excerpt)
                lines.append(f"| **{lbl}** | `{m.criticality}` | {rec} | *{exc}* |")

        # Type 2
        lines.extend(
            [
                "",
                "## 🟡 2. Déficits d'Atomicité & Surcharges Cognitives (Type 2)",
                "",
            ]
        )
        if not report.non_atomic_cards:
            lines.append("✅ *Toutes les cartes du deck virtuel respectent les règles de concision et d'atomicité.*")
        else:
            lines.extend(
                [
                    "| Carte | Paquet | Motifs de non-atomicité | Scission recommandée |",
                    "| :--- | :--- | :--- | :---: |",
                ]
            )
            for a in report.non_atomic_cards[:15]:
                p = escape_markdown_table_cell(a.prompt_preview)
                dk = escape_markdown_table_cell(a.deck_name)
                rs = escape_markdown_table_cell(" ; ".join(a.reasons))
                lines.append(f"| {p} | `{dk}` | {rs} | `{a.suggested_split_count} cartes` |")

        # Type 3
        lines.extend(
            [
                "",
                "## 🔵 3. Manque de Liant & Distinctions Manquantes (Type 3)",
                "",
            ]
        )
        if not report.missing_synthesis:
            lines.append("✅ *Aucune dette de synthèse détectée. Les nuances et distinctions fines sont acquises.*")
        else:
            lines.extend(
                [
                    "| Notion A | Notion B | Type de Relation | Question de Confrontation Suggérée |",
                    "| :--- | :--- | :---: | :--- |",
                ]
            )
            for s in report.missing_synthesis[:15]:
                ca = escape_markdown_table_cell(s.concept_a)
                cb = escape_markdown_table_cell(s.concept_b)
                pr = escape_markdown_table_cell(s.suggested_card_prompt)
                lines.append(f"| **{ca}** | **{cb}** | `{s.relation_type}` | {pr} |")

        # Transversales repêchées
        if report.transversal_cards_rescued:
            lines.extend(
                [
                    "",
                    "## 🌐 Cartes Transversales Repêchées Hors Paquet Cible",
                    "",
                    "| Paquet Source | Aperçu Question | Concepts Sauvegardés |",
                    "| :--- | :--- | :--- |",
                ]
            )
            for r in report.transversal_cards_rescued[:10]:
                dk = escape_markdown_table_cell(r.source_deck)
                pr = escape_markdown_table_cell(r.prompt_preview)
                cps = escape_markdown_table_cell(", ".join(r.matched_concepts))
                lines.append(f"| `{dk}` | {pr} | {cps} |")

        lines.append("")
        return "\n".join(lines)


# ============================================================================
# Fonction d'Outil FastMCP Canonique
# ============================================================================


def diagnose_domain_knowledge_gaps(
    subject: str,
    target_deck: str = "",
    reference_document_id: int | None = None,
    blueprint_json: str = "",
    include_suspended: bool = False,
) -> str:
    """Diagnostique les lacunes de connaissances sur un domaine à l'échelle de toute la collection."""
    # 1. Validation Fail-Safe du sujet
    if not subject or not subject.strip():
        return json.dumps(
            {
                "status": "error",
                "error_code": "EMPTY_SUBJECT",
                "message": tr("Le sujet d'audit ne peut pas être vide."),
            },
            ensure_ascii=False,
        )

    # 2. Validation Fail-Safe du document
    if reference_document_id is not None:
        doc = DocumentModel.get_or_none(DocumentModel.id == reference_document_id)
        if not doc:
            return json.dumps(
                {
                    "status": "error",
                    "error_code": "DOCUMENT_NOT_FOUND",
                    "message": tr("Document introuvable pour l'id spécifié."),
                },
                ensure_ascii=False,
            )

    # 3. Validation Fail-Safe du JSON externe
    if blueprint_json and blueprint_json.strip():
        try:
            parsed = json.loads(blueprint_json)
            if not isinstance(parsed, dict):
                raise ValueError("JSON non dictionnaire")
        except Exception:
            return json.dumps(
                {
                    "status": "error",
                    "error_code": "INVALID_BLUEPRINT_JSON",
                    "message": tr("Le blueprint_json fourni n'est pas un JSON valide."),
                },
                ensure_ascii=False,
            )

    try:
        detector = DomainGapDetector()
        report = detector.diagnose(
            subject=subject,
            target_deck=target_deck,
            reference_document_id=reference_document_id,
            blueprint_json=blueprint_json,
            include_suspended=include_suspended,
        )

        res_dict = report.to_dict()
        res_dict["status"] = "success"

        # Garde-fou ADR 0048 sur la taille du payload MCP
        if len(report.non_atomic_cards) > 15:
            res_dict["non_atomic_cards"] = res_dict["non_atomic_cards"][:10]
            res_dict["truncated_atomicity"] = True
        if len(report.missing_synthesis) > 20:
            res_dict["missing_synthesis"] = res_dict["missing_synthesis"][:10]
            res_dict["truncated_synthesis"] = True

        return json.dumps(res_dict, indent=2, ensure_ascii=False)

    except Exception as exc:
        logger.exception("Erreur lors de l'exécution de diagnose_domain_knowledge_gaps: %s", exc)
        return json.dumps(
            {
                "status": "error",
                "error_code": "INTERNAL_ERROR",
                "message": str(exc),
            },
            ensure_ascii=False,
        )

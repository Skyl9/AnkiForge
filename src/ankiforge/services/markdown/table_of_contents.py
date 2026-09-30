"""Détection et isolation du bloc « Table des Matières » d'un document Markdown.

Les documents issus de Marker (PDF paginés) comportent très souvent un sommaire en
tête de document. Ses entrées sont balisées comme des titres Markdown (`## Titre...`)
ou comme des lignes d'index (`Titre ......... 15`), et le corps du chapitre
correspondant réapparaît plus loin sous le **même titre**. Ce doublon est
destructeur pour trois consommateurs :

- la navigation par titre s'arrête sur la ligne du sommaire (premier `break`) ;
- le découpage sémantique génère des fragments orphelins quasi-vides ;
- l'appariment des cartes (Smart Coverage) vise le fragment du sommaire.

Ce module isole la notion de « ligne d'index » en un point d'entrée unique
(`TableOfContentsDetector.detect`) afin que l'outline, le découpage, la navigation
et l'alignement de couverture partagent exactement la même définition.

**Conservatisme.** Un sommaire n'est retenu que sur *preuve* d'index (filets de
points, liens d'ancres, ou titres dupliqués plus bas dans le document — cf.
`_confirm_as_index_block`). Un chapitre réellement intitulé « Sommaire », qui
n'énumère que des sous-titres sans prose, ne présente aucune de ces preuves et
reste donc du contenu de cours : mieux vaut un doublon résiduel que la disparition
de sections réelles.

**Dépendances.** Ce module est une feuille : il n'utilise que des primitives de
`text_utils`, jamais `structurer` ni `services.parsing`. Les mapping ligne → page
sont donc fournis par l'appelant (voir `MarkdownStructurer.resolve_heading_line_number`).
"""

import logging
import re
from dataclasses import dataclass

from ankiforge.services.markdown.text_utils import clean_heading_title, code_fence_lines, slugify

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TableOfContentsSpan:
    """Bloc de table des matières localisé dans un document Markdown (lignes 1-indexées)."""

    start_line: int
    end_line: int
    title: str
    anchor_line: int | None
    entry_titles: tuple[str, ...]

    def contains_line(self, line_number: int) -> bool:
        """Indique si une ligne (1-indexée) appartient au bloc de sommaire."""
        return self.start_line <= line_number <= self.end_line


class TableOfContentsDetector:
    """Repère le bloc Table des Matières / Sommaire d'un document Markdown."""

    #: Un titre ancre n'est cherché que dans les premières lignes du document.
    MAX_ANCHOR_LINE = 60
    #: Garde-fou d'analyse : au-delà, le bloc est considéré comme du contenu de cours.
    MAX_SCAN_LINES = 2000
    #: Nombre minimal d'entrées d'index confirmant un sommaire (anti faux positif).
    MIN_ENTRIES = 2
    #: Volume de mots au-delà duquel un titre possède un « corps de cours » réel.
    SUBSTANTIVE_WORD_COUNT = 50
    #: Garde-fou secondaire : un index n'a pas de prose. La vraie barrière est
    #: `_has_explicit_index_marker` ; cette borne permet les sommaires à 20+ entrées.
    MAX_INDEX_BLOCK_WORDS = 250

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
    _PAGE_MARKER_RE = re.compile(r"^(?:\{(\d+)\}-{5,}|<!--\s*PAGE:\s*(\d+)\s*-->)$", re.IGNORECASE)
    _TOC_COMMENT_RE = re.compile(r"^<!--\s*(/?)\s*toc\s*-->$", re.IGNORECASE)
    _COMMENT_RE = re.compile(r"^<!--.*-->$", re.DOTALL)
    _HORIZONTAL_RULE_RE = re.compile(r"^(?:[-*_]\s*){3,}$")
    # Filets de points (ou équivalent Unicode) suivis d'un numéro de page.
    _DOT_LEADER_RE = re.compile(r"(?:[.…·]\s*){3,}\s*(?:[ivxlcdm]{1,6}|\d{1,4})?\s*$", re.IGNORECASE)
    # Lien d'ancres Markdown : [Titre](#titre)
    _ANCHOR_LINK_RE = re.compile(r"\[[^\]\n]+\]\(\s*#")
    _BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
    _PAGE_TAIL_RE = re.compile(r"(?:\.{2,}\s*|\s)\d{1,4}\s*$")
    _TOC_TITLE_RE = re.compile(
        r"^(?:"
        r"sommaire(?:\s+général)?"
        r"|table\s+des\s+mati[èe]res"
        r"|table\s+of\s+contents?"
        r"|contents"
        r"|inhaltsverzeichnis"
        r"|[íi]ndice(?:\s+g[ée]n[ée]ral)?"
        r"|plan\s+du\s+(?:cours|document|chapitre|module)"
        r"|toc"
        r"|index"
        r")$",
        re.IGNORECASE,
    )

    @classmethod
    def detect(cls, markdown: str) -> TableOfContentsSpan | None:
        """Localise le bloc de sommaire en tête de document, s'il existe.

        Returns:
            TableOfContentsSpan | None : le bloc détecté, ou None si le document n'a pas
            de sommaire exploitable (titre « Sommaire » suivi d'un vrai contenu, bloc
            situé au-delà de la zone d'ouverture, moins de deux entrées d'index, ou
            aucune preuve d'index — cf. `_confirm_as_index_block`).
        """
        if not markdown or not markdown.strip():
            return None

        lines = markdown.split("\n")
        anchor = cls._find_anchor_heading(lines)
        span = cls._build_span_from_anchor(lines, anchor) if anchor is not None else cls._detect_headless_span(lines)
        if span is None:
            return None
        if not cls._confirm_as_index_block(lines, span):
            logger.debug("Bloc « %s » (lignes %d-%d) sans marqueur d'index : traité comme du contenu de cours.", span.title or "(sans titre)", span.start_line, span.end_line)
            return None
        return span

    @classmethod
    def strip_span(cls, markdown: str, span: TableOfContentsSpan) -> str:
        """Retire le bloc de sommaire du texte et renvoie le corps restant.

        Point d'entrée unique du retranchement : le sommaire est un index, jamais du
        contenu de cours, et ses lignes ne doivent pas être héritées par la section
        qui le précède. Un document fait uniquement d'un sommaire rend une chaîne vide.
        """
        lines = markdown.split("\n")
        return "\n".join([*lines[: span.start_line - 1], *lines[span.end_line :]])

    @classmethod
    def is_toc_title(cls, title: str) -> bool:
        """Indique si un titre (déjà nettoyé) nomme une table des matières."""
        if not title:
            return False
        return bool(cls._TOC_TITLE_RE.match(clean_heading_title(title).strip()))

    @classmethod
    def is_index_entry_line(cls, line: str) -> bool:
        """Indique si une ligne brute ressemble à une entrée d'index (titre ou lien de sommaire)."""
        stripped = line.strip()
        if not stripped:
            return False
        if cls._HEADING_RE.match(stripped):
            return True
        if cls._DOT_LEADER_RE.search(stripped) or cls._ANCHOR_LINK_RE.search(stripped):
            return True
        bullet = cls._BULLET_RE.match(stripped)
        return bool(bullet and (cls._DOT_LEADER_RE.search(stripped) or cls._PAGE_TAIL_RE.search(bullet.group(1))))

    @classmethod
    def looks_like_index_block(cls, text: str) -> bool:
        """Indique si un fragment de texte n'est qu'un bloc d'index (sommaire) sans corps de cours.

        Filet de sécurité pour les documents indexés avec une ancienne version de
        découpage : leurs fragments de sommaire survivent en base et ne doivent ni
        alimenter l'arbre de portée, ni se substituer au fragment de cours. Le bump de
        `CHUNKING_VERSION` reste le vrai mécanisme de purge ; ce filet ne couvre que les
        fragments bearing des marqueurs d'index **sans ambiguïté** (filets de points,
        numéro de page final, lien d'ancre, délimiteur ``<!-- toc -->``).

        Exigence assumée : un titre « Sommaire » seul ne suffit pas. Un chapitre de cours
        réellement intitulé « Sommaire », « Index » ou « Plan du cours », composé de
        sous-titres sans prose, est indiscernable d'une annonce de sommaire à partir du
        seul fragment. Le doute est tranché contre la suppression : mieux vaut une entrée
        fantôme résiduelle (filtrée à la réindexation) que la disparition de sections réelles.
        """
        if not text or not text.strip():
            return False
        if len(text.split()) > cls.MAX_INDEX_BLOCK_WORDS:
            return False

        lines = [raw.strip() for raw in text.split("\n") if raw.strip()]
        if len(lines) < 2:
            return False

        entries = 0
        for line in lines:
            if cls._COMMENT_RE.match(line):
                if cls._TOC_COMMENT_RE.match(line):
                    entries += 1
                continue
            heading = cls._HEADING_RE.match(line)
            if heading:
                entries += 1
                continue
            # Réutilise `is_index_entry_line` : un numéro final ne vaut preuve que
            # sur une ligne de puce d'index, pas sur n'importe quelle phrase.
            if cls.is_index_entry_line(line):
                entries += 1
                continue
            return False
        # Un titre nu ne constitue pas une preuve : il faut au moins un marqueur explicite.
        return entries >= cls.MIN_ENTRIES and cls._has_explicit_index_marker(lines)

    @classmethod
    def _has_explicit_index_marker(cls, lines: list[str]) -> bool:
        """Indique si le fragment porte un marqueur d'index sans ambiguïté.

        Un titre nu en est volontairement exclu : « Sommaire », « Index » ou « Plan du
        cours » sont aussi des noms de chapitres légitimes (cf. `looks_like_index_block`).
        """
        return any(cls._TOC_COMMENT_RE.match(line) or cls._ANCHOR_LINK_RE.search(line) or cls._DOT_LEADER_RE.search(line) for line in lines)

    @classmethod
    def _confirm_as_index_block(cls, lines: list[str], span: TableOfContentsSpan) -> bool:
        """Exige une preuve d'index avant de traiter un bloc candidat comme une table des matières.

        Un chapitre réellement intitulé « Sommaire » (liste de modules, de leçons ou de
        parties, sans prose) ne présente aucun marqueur d'index. Trois preuves sont
        acceptées, chacune corroborée par au moins `MIN_ENTRIES` éléments :

        1. les filets de points ou numéros de page d'une table imprimée ;
        2. les liens d'ancres ou les délimiteurs ``<!-- toc -->`` d'une table générée ;
        3. les entrées dont le titre réapparaît comme titre plus bas dans le document —
           signature Marker : l'annonce du sommaire et le corps réel du chapitre.
        """
        start = span.start_line - 1
        end = span.end_line  # borne exclusive
        leaders = 0
        anchors = 0
        for raw in lines[start:end]:
            stripped = raw.strip()
            if cls._ANCHOR_LINK_RE.search(stripped) or cls._TOC_COMMENT_RE.match(stripped):
                anchors += 1
            elif cls._DOT_LEADER_RE.search(stripped):
                leaders += 1
            elif not cls._HEADING_RE.match(stripped) and cls._PAGE_TAIL_RE.search(stripped):
                # Numéro de page final sur une ligne d'index non titrée (« Introduction 15 »).
                # Exclu pour les titres, dont « ## Module 2 » se terminerait aussi par un nombre.
                leaders += 1
        if leaders >= cls.MIN_ENTRIES or anchors >= cls.MIN_ENTRIES:
            return True
        return cls._count_duplicated_entries(lines, end, span.entry_titles) >= cls.MIN_ENTRIES

    @classmethod
    def _count_duplicated_entries(cls, lines: list[str], from_idx: int, entry_titles: tuple[str, ...]) -> int:
        """Compte les entrées d'index dont le titre réapparaît comme titre dans la suite du document."""
        targets = {slugify(title) for title in entry_titles if title.strip()}
        targets.discard("section")
        if not targets:
            return 0

        found = 0
        fence_lines = code_fence_lines(lines)
        for idx in range(from_idx, len(lines)):
            if idx in fence_lines:
                continue
            match = cls._HEADING_RE.match(lines[idx].strip())
            if match and slugify(clean_heading_title(match.group(2))) in targets:
                found += 1
                if found >= cls.MIN_ENTRIES:
                    return found
        return found

    @classmethod
    def _find_anchor_heading(cls, lines: list[str]) -> tuple[int, str] | None:
        """Cherche le premier titre ancre « Sommaire » / « Table des matières » du document."""
        limit = min(len(lines), cls.MAX_ANCHOR_LINE)
        fence_lines = code_fence_lines(lines)
        for idx in range(limit):
            if idx in fence_lines:
                continue
            match = cls._HEADING_RE.match(lines[idx].strip())
            if not match:
                continue
            title = clean_heading_title(match.group(2))
            if cls._TOC_TITLE_RE.match(title.strip()):
                return idx, title.strip()
        return None

    @classmethod
    def _build_span_from_anchor(cls, lines: list[str], anchor: tuple[int, str]) -> TableOfContentsSpan | None:
        """Étend le bloc d'index à partir du titre ancre, entrée par entrée."""
        anchor_idx, title = anchor
        total = len(lines)
        entries: list[str] = []
        end_idx = anchor_idx

        idx = anchor_idx + 1
        while idx < total and idx - anchor_idx < cls.MAX_SCAN_LINES:
            stripped = lines[idx].strip()

            if not stripped:
                idx += 1
                continue

            comment = cls._TOC_COMMENT_RE.match(stripped)
            if comment:
                if comment.group(1):
                    # Fermeture <!-- /toc --> : frontière dure du bloc généré.
                    end_idx = idx
                    break
                idx += 1
                continue

            if cls._is_ignorable(stripped):
                idx += 1
                continue

            heading = cls._HEADING_RE.match(stripped)
            if heading:
                if not cls._body_is_empty(lines, idx):
                    break
                entries.append(cls._entry_title(heading.group(2), from_heading=True))
                end_idx = idx
                idx += 1
                continue

            if cls.is_index_entry_line(stripped):
                entries.append(cls._entry_title(stripped))
                end_idx = idx
                idx += 1
                continue

            break

        if len(entries) < cls.MIN_ENTRIES:
            logger.debug("Titre ancre « %s » sans entrées d'index : aucun sommaire détecté.", title)
            return None

        logger.debug("Bloc Table des Matières détecté : lignes %d-%d (%d entrées).", anchor_idx + 1, end_idx + 1, len(entries))
        return TableOfContentsSpan(
            start_line=anchor_idx + 1,
            end_line=end_idx + 1,
            title=title,
            anchor_line=anchor_idx + 1,
            entry_titles=tuple(entries),
        )

    @classmethod
    def _detect_headless_span(cls, lines: list[str]) -> TableOfContentsSpan | None:
        """Détecte un bloc d'ancres initial sans titre ancre (Markdown généré, liste de liens)."""
        limit = min(len(lines), cls.MAX_ANCHOR_LINE)
        idx = 0
        while idx < limit and (not lines[idx].strip() or cls._is_ignorable(lines[idx].strip())):
            idx += 1

        entries: list[str] = []
        start_idx = idx
        end_idx = idx - 1
        while idx < limit:
            stripped = lines[idx].strip()
            if not stripped or cls._is_ignorable(stripped):
                idx += 1
                continue
            # Un titre marque la fin d'un bloc d'ancres initial : il appartient au cours.
            if cls._HEADING_RE.match(stripped) or not cls.is_index_entry_line(stripped):
                break
            entries.append(cls._entry_title(stripped))
            end_idx = idx
            idx += 1

        if len(entries) < cls.MIN_ENTRIES:
            return None

        return TableOfContentsSpan(
            start_line=start_idx + 1,
            end_line=end_idx + 1,
            title="",
            anchor_line=None,
            entry_titles=tuple(entries),
        )

    @classmethod
    def _is_ignorable(cls, stripped: str) -> bool:
        """Indique si une ligne est neutre pour la délimitation du sommaire."""
        return bool(cls._PAGE_MARKER_RE.match(stripped) or cls._COMMENT_RE.match(stripped) or cls._HORIZONTAL_RULE_RE.match(stripped))

    @classmethod
    def _body_is_empty(cls, lines: list[str], heading_idx: int) -> bool:
        """Indique si le titre `heading_idx` est suivi d'un corps textuel propre (hors index)."""
        for raw in lines[heading_idx + 1 :]:
            stripped = raw.strip()
            if not stripped or cls._is_ignorable(stripped):
                continue
            if cls._HEADING_RE.match(stripped):
                return True
            if cls.is_index_entry_line(stripped):
                continue
            return False
        return True

    @classmethod
    def _entry_title(cls, raw_title: str, *, from_heading: bool = False) -> str:
        """Extrait le titre lisible d'une entrée d'index (hors puces, ancres et filets de points).

        `from_heading` préserve la numérotation d'un titre (`## 1. La cellule` → « 1. La cellule ») :
        pour un titre, le nombre fait partie du nom du chapitre ; seul un index en ligne
        (« 1. La cellule .... 12 ») le sépare de son libellé. Sans cette distinction, le titre
        du sommaire et celui du corps ne produisent plus le même slug et la détection échoue.
        """
        title = clean_heading_title(raw_title).strip()
        if not from_heading:
            title = cls._BULLET_RE.sub(r"\1", title).strip()
        title = cls._ANCHOR_LINK_RE.sub(lambda m: m.group(0).split("](")[0].lstrip("["), title)
        title = cls._DOT_LEADER_RE.sub("", title).strip()
        return title

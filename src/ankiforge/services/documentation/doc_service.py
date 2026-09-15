"""Service de base de connaissances interne basé sur la documentation Zensical et SQLite FTS5."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ankiforge.utils.paths import get_docs_path, get_zensical_config_path

logger = logging.getLogger(__name__)


@dataclass
class DocSection:
    """Représente une section découpée d'une page de documentation Markdown."""

    page_path: str
    page_title: str
    category: str
    section_title: str
    anchor: str
    content: str


@dataclass
class DocSearchResult:
    """Résultat enrichi d'une recherche dans la base de connaissances."""

    page_path: str
    page_title: str
    category: str
    section_title: str
    anchor: str
    snippet: str
    score: float
    ref: str


@dataclass
class DocTopic:
    """Représente un sujet de documentation avec son chemin et sa catégorie."""

    title: str
    path: str
    category: str
    sections: list[str] = field(default_factory=list)


def _slugify(text: str) -> str:
    """Génère un slug compatible avec les ancres Markdown standards."""
    # Nettoie les emojis ou caractères spéciaux décoratifs
    clean = re.sub(r"[^\w\s-]", "", text.lower())
    clean = re.sub(r"[-\s]+", "-", clean).strip("-")
    return clean or "section"


def _clean_header_text(header_line: str) -> str:
    """Extrait le texte propre d'un en-tête Markdown en retirant les dièses et les emojis."""
    raw = re.sub(r"^#+\s*", "", header_line).strip()
    return raw


class AppDocumentationService:
    """
    Gestionnaire centralisé de la base de connaissances interne de l'application.

    Parse l'arborescence Zensical (`zensical.toml`) et les pages Markdown (`docs/`),
    puis indexe les sections dans une table SQLite FTS5 en mémoire pour une recherche
    ultra-rapide (< 10 ms) avec pertinence BM25 et génération d'extraits contextualisés.
    """

    _instance: AppDocumentationService | None = None
    _lock = threading.Lock()

    def __init__(self, docs_dir: Path | None = None, config_path: Path | None = None) -> None:
        self.docs_dir = docs_dir or get_docs_path()
        self.config_path = config_path or get_zensical_config_path()
        self._db_lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        self._topics_cache: list[DocTopic] = []
        self._page_meta_cache: dict[str, tuple[str, str]] = {}
        self._indexed = False

    @classmethod
    def get_instance(cls) -> AppDocumentationService:
        """Retourne l'instance singleton thread-safe du service."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _init_db(self) -> sqlite3.Connection:
        """Initialise la table FTS5 en mémoire avec le tokenizer unicode61."""
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS app_docs_fts USING fts5(
                page_path UNINDEXED,
                page_title,
                category,
                section_title,
                anchor UNINDEXED,
                content,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
        return conn

    def _parse_zensical_nav(self) -> dict[str, tuple[str, str]]:
        """
        Extrait l'arborescence de navigation définie dans `zensical.toml`.
        Retourne un dictionnaire { 'rel_path.md': ('Titre de la Page', 'Catégorie') }.
        """
        meta: dict[str, tuple[str, str]] = {}
        if not self.config_path.is_file():
            logger.debug("Configuration Zensical non trouvée : %s", self.config_path)
            return meta

        try:
            with open(self.config_path, "rb") as f:
                data = tomllib.load(f)

            nav = data.get("project", {}).get("nav", [])
            for item in nav:
                if isinstance(item, dict):
                    for cat_or_title, target in item.items():
                        if isinstance(target, str):
                            meta[target.strip()] = (cat_or_title.strip(), "Général")
                        elif isinstance(target, list):
                            category_name = cat_or_title.strip()
                            for sub_item in target:
                                if isinstance(sub_item, dict):
                                    for sub_title, sub_path in sub_item.items():
                                        if isinstance(sub_path, str):
                                            meta[sub_path.strip()] = (sub_title.strip(), category_name)
        except Exception as e:
            logger.warning("Erreur lors de la lecture de %s : %s", self.config_path, e)

        return meta

    def _infer_category_and_title(self, rel_path: str, raw_content: str) -> tuple[str, str]:
        """Déduit le titre et la catégorie d'un fichier Markdown s'il n'est pas déclaré dans zensical.toml."""
        if rel_path in self._page_meta_cache:
            return self._page_meta_cache[rel_path]

        # Catégorie basée sur le dossier parent
        parts = Path(rel_path).parts
        if len(parts) > 1:
            parent = parts[0]
            cat_map = {
                "features": "Fonctionnalités",
                "Dossier_architecture": "Architecture",
                "guides": "Guides & Prompts",
                "dev": "Développement",
            }
            category = cat_map.get(parent, parent.capitalize())
        else:
            category = "Démarrage" if "guide" in rel_path or "install" in rel_path else "Accueil"

        # Titre basé sur le premier header H1 (# ...)
        title = Path(rel_path).stem.replace("_", " ").title()
        for line in raw_content.splitlines():
            sline = line.strip()
            if sline.startswith("# "):
                title = _clean_header_text(sline)
                break

        return title, category

    def _chunk_markdown_file(self, rel_path: str, raw_content: str, default_title: str, category: str) -> list[DocSection]:
        """Découpe un fichier Markdown en sections hiérarchiques (H1, H2, H3)."""
        sections: list[DocSection] = []
        lines = raw_content.splitlines()

        current_header = default_title
        current_anchor = ""
        current_lines: list[str] = []

        for line in lines:
            # Détection d'un titre H1, H2 ou H3
            header_match = re.match(r"^(#{1,3})\s+(.*)$", line)
            if header_match:
                # Sauvegarde de la section précédente si elle a du contenu
                if current_lines:
                    text_content = "\n".join(current_lines).strip()
                    if text_content:
                        sections.append(
                            DocSection(
                                page_path=rel_path,
                                page_title=default_title,
                                category=category,
                                section_title=current_header,
                                anchor=current_anchor,
                                content=text_content,
                            )
                        )
                    current_lines = []

                raw_header_text = header_match.group(2).strip()
                current_header = _clean_header_text(raw_header_text)
                current_anchor = f"#{_slugify(raw_header_text)}"
            else:
                current_lines.append(line)

        # Dernière section
        if current_lines:
            text_content = "\n".join(current_lines).strip()
            if text_content:
                sections.append(
                    DocSection(
                        page_path=rel_path,
                        page_title=default_title,
                        category=category,
                        section_title=current_header,
                        anchor=current_anchor,
                        content=text_content,
                    )
                )

        # Si le fichier était complètement vide de headers
        if not sections and raw_content.strip():
            sections.append(
                DocSection(
                    page_path=rel_path,
                    page_title=default_title,
                    category=category,
                    section_title=default_title,
                    anchor="",
                    content=raw_content.strip(),
                )
            )

        return sections

    def ensure_indexed(self) -> None:
        """Garantit que la base de documentation est indexée en mémoire."""
        if self._indexed and self._db is not None:
            return

        with self._db_lock:
            if self._indexed and self._db is not None:
                return

            self._page_meta_cache = self._parse_zensical_nav()
            self._db = self._init_db()
            self._topics_cache = []

            if not self.docs_dir.is_dir():
                logger.warning("Répertoire de documentation introuvable : %s", self.docs_dir)
                self._indexed = True
                return

            md_files = sorted(self.docs_dir.rglob("*.md"))
            sections_count = 0

            for fpath in md_files:
                try:
                    rel_path = str(fpath.relative_to(self.docs_dir))
                    raw_text = fpath.read_text(encoding="utf-8", errors="replace")
                    page_title, category = self._infer_category_and_title(rel_path, raw_text)

                    file_sections = self._chunk_markdown_file(rel_path, raw_text, page_title, category)
                    section_titles = [s.section_title for s in file_sections if s.section_title != page_title]

                    self._topics_cache.append(
                        DocTopic(
                            title=page_title,
                            path=rel_path,
                            category=category,
                            sections=section_titles,
                        )
                    )

                    for sec in file_sections:
                        self._db.execute(
                            """
                            INSERT INTO app_docs_fts (page_path, page_title, category, section_title, anchor, content)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                sec.page_path,
                                sec.page_title,
                                sec.category,
                                sec.section_title,
                                sec.anchor,
                                sec.content,
                            ),
                        )
                        sections_count += 1

                except Exception as e:
                    logger.error("Erreur lors de l'indexation de %s : %s", fpath, e)

            self._db.commit()
            self._indexed = True
            logger.info(
                "Base de connaissances Zensical indexée : %d fichiers Markdown, %d sections.",
                len(md_files),
                sections_count,
            )

    def _sanitize_fts_query(self, raw_query: str) -> str:
        """Nettoie et formate la requête pour SQLite FTS5 avec préfixe wildcard."""
        tokens = re.findall(r"[\w]+", raw_query, flags=re.UNICODE)
        if not tokens:
            return ""
        return " ".join(f'"{tok}"*' for tok in tokens)

    def search(self, query: str, category: str = "", limit: int = 5) -> list[DocSearchResult]:
        """
        Recherche des passages pertinents dans la documentation Zensical via FTS5 BM25.

        Args:
            query: Termes recherchés.
            category: Filtre optionnel par catégorie (ex: 'Fonctionnalités', 'Architecture').
            limit: Nombre maximum de résultats.

        Returns:
            Liste de DocSearchResult classés par score BM25 croissant (plus négatif = plus pertinent).
        """
        self.ensure_indexed()
        if self._db is None or not query.strip():
            return []

        fts_query = self._sanitize_fts_query(query)
        if not fts_query:
            return []

        with self._db_lock:
            try:
                if category.strip():
                    sql = """
                        SELECT page_path, page_title, category, section_title, anchor,
                               snippet(app_docs_fts, 5, '**', '**', '...', 25),
                               bm25(app_docs_fts)
                        FROM app_docs_fts
                        WHERE app_docs_fts MATCH ? AND category LIKE ?
                        ORDER BY bm25(app_docs_fts)
                        LIMIT ?
                    """
                    params: tuple[Any, ...] = (fts_query, f"%{category.strip()}%", limit)
                else:
                    sql = """
                        SELECT page_path, page_title, category, section_title, anchor,
                               snippet(app_docs_fts, 5, '**', '**', '...', 25),
                               bm25(app_docs_fts)
                        FROM app_docs_fts
                        WHERE app_docs_fts MATCH ?
                        ORDER BY bm25(app_docs_fts)
                        LIMIT ?
                    """
                    params = (fts_query, limit)

                cursor = self._db.execute(sql, params)
                results: list[DocSearchResult] = []
                for row in cursor.fetchall():
                    p_path, p_title, cat, sec_title, anchor, snip, score = row
                    ref = f"{p_path}{anchor}" if anchor else p_path
                    results.append(
                        DocSearchResult(
                            page_path=p_path,
                            page_title=p_title,
                            category=cat,
                            section_title=sec_title,
                            anchor=anchor,
                            snippet=snip,
                            score=float(score),
                            ref=ref,
                        )
                    )
                return results

            except Exception as e:
                logger.error("Erreur lors de la recherche FTS doc : %s", e)
                return []

    def get_page_content(self, doc_path: str, section_anchor: str = "") -> str | None:
        """
        Récupère le contenu Markdown complet d'une page ou d'une section spécifique.

        Args:
            doc_path: Chemin relatif ou partiel de la page (ex: 'features/consultant_mcp.md').
            section_anchor: Ancre optionnelle de la section (ex: '#2-boite-a-outils-mcp-in-process').

        Returns:
            Contenu Markdown ou None si non trouvé.
        """
        self.ensure_indexed()
        target_path = doc_path.strip().lstrip("/")
        if not target_path.endswith(".md"):
            target_path += ".md"

        matched_file: Path | None = None
        cand_direct = self.docs_dir / target_path
        if cand_direct.is_file():
            matched_file = cand_direct
        else:
            for f in self.docs_dir.rglob("*.md"):
                if str(f.relative_to(self.docs_dir)) == target_path or f.name == Path(target_path).name:
                    matched_file = f
                    break

        if not matched_file or not matched_file.is_file():
            return None

        raw_text = matched_file.read_text(encoding="utf-8", errors="replace")
        if not section_anchor.strip():
            return raw_text

        # Recherche de la section ciblée
        norm_anchor = section_anchor.strip().lower()
        if not norm_anchor.startswith("#"):
            norm_anchor = f"#{norm_anchor}"

        sections = self._chunk_markdown_file(str(matched_file.relative_to(self.docs_dir)), raw_text, matched_file.stem, "Doc")
        for sec in sections:
            if sec.anchor.lower() == norm_anchor:
                return f"## {sec.section_title}\n\n{sec.content}"

        return raw_text

    def get_topics(self, category: str = "") -> list[DocTopic]:
        """Retourne la liste des sujets documentés avec filtrage optionnel."""
        self.ensure_indexed()
        if not category.strip():
            return list(self._topics_cache)

        norm_cat = category.strip().lower()
        return [t for t in self._topics_cache if norm_cat in t.category.lower()]

    def get_feature_quick_help(self, feature_name: str) -> str:
        """
        Génère une fiche synthétique pour une fonctionnalité clé ou via recherche sémantique.
        """
        self.ensure_indexed()
        norm_feat = feature_name.strip().lower()

        # Fiches de raccourcis rapides pour les fonctionnalités fondamentales
        quick_guides: dict[str, tuple[str, str, str]] = {
            "wozniak": (
                "Linter Wozniak & Hôpital d'Audit",
                "features/linter_wozniak.md",
                "Le Linter vérifie les 20 règles de formulation de Piotr Wozniak (atomicité, minimum information, clarté, suppression des interférences). "
                "Il propose la scission automatique des cartes surchargées en 1-clic.",
            ),
            "mcp": (
                "Consultant IA & Protocole MCP",
                "features/consultant_mcp.md",
                "Le serveur MCP in-process expose des outils d'audit, de requêtage Peewee, de tuning CSS et de gestion d'outils Python au Consultant ReAct avec garde-fous (staging diffs).",
            ),
            "dag": (
                "Moteur d'Orchestration DAG",
                "features/dag_et_rag.md",
                "Orchestre les pipelines de génération via 5 types d'étapes : LLM_PROMPT, RAG_RETRIEVAL, MAP_REDUCE, HUMAN_VALIDATION, PYTHON_TOOL avec sauts conditionnels.",
            ),
            "rag": (
                "RAG Hybride & Smart Coverage",
                "features/dag_et_rag.md",
                "Recherche vectorielle locale (FAISS/ChromaDB), découpage sémantique des documents sources et traçabilité NoteChunkLinkModel pour le calcul de couverture (Smart Coverage).",
            ),
            "katex": (
                "Éditeur de Notes KaTeX Live",
                "features/editeur_notes_katex.md",
                "Éditeur 100% natif Qt avec rendu mathématique KaTeX en direct, autocomplétion des symboles LaTeX, gestionnaire d'occlusions (Cloze) et historique Time Machine.",
            ),
            "nuitka": (
                "Compilation Binaire Autonome",
                "dev/compilation_nuitka.md",
                "AnkiForge se compile en binaire natif autonome C via Nuitka sans dépendance Python préalable sur le poste client.",
            ),
            "smart merge": (
                "Synchronisation & Smart Merge",
                "features/synchro_smart_merge.md",
                "Import/export .apkg et .colpkg avec boîte de fusion 3 panneaux (Local, Base, Distant). Seules les modifications du contenu brut déclenchent un arbitrage.",
            ),
            "ollama": (
                "Fournisseurs LLM Locaux (Ollama)",
                "guides/ia_fournisseurs.md",
                "AnkiForge délègue l'exécution des modèles locaux à Ollama via l'API REST http://localhost:11434 sans dépendance PyTorch lourde embarquée.",
            ),
        }

        for key, (title, path, summary) in quick_guides.items():
            if key in norm_feat:
                return f"📖 **Fiche d'Aide Rapide — {title}**\n\n{summary}\n\n🔗 *Référence complète :* `{path}` (utilisez `read_app_doc_page('{path}')` pour consulter la documentation exhaustive)."

        # Repli : Recherche FTS5 du meilleur passage
        results = self.search(feature_name, limit=2)
        if not results:
            return f"Aucune information trouvée dans la documentation officielle pour '{feature_name}'."

        best = results[0]
        return (
            f"📖 **Documentation — {best.page_title} ({best.section_title})**\n"
            f"*Catégorie :* {best.category} | *Référence :* `{best.ref}`\n\n"
            f"{best.snippet}\n\n"
            f"💡 *Pour lire la section entière, utilisez l'outil `read_app_doc_page(doc_path='{best.page_path}', section_anchor='{best.anchor}')`.*"
        )


# =====================================================================
# FONCTIONS UTILITAIRES EXPORTÉES POUR LE SERVEUR MCP ET LE CONSULTANT
# =====================================================================


def search_app_documentation(query: str, category: str = "", limit: int = 5) -> str:
    """Recherche des extraits pertinents dans la documentation officielle d'AnkiForge."""
    service = AppDocumentationService.get_instance()
    results = service.search(query=query, category=category, limit=limit)
    if not results:
        return f"Aucun résultat trouvé dans la documentation pour la recherche : '{query}'" + (f" (catégorie: {category})" if category else "") + "."

    lines: list[str] = [f"📚 **Résultats de recherche dans la documentation AnkiForge ({len(results)}) :**"]
    for i, r in enumerate(results, start=1):
        lines.append(f"{i}. **{r.page_title}** ➔ *{r.section_title}* `[{r.category}]`\n   - 🔗 Référence : `{r.ref}`\n   - 📝 Extrait : {r.snippet}")
    lines.append("\n💡 *Astuce : utilisez `read_app_doc_page(doc_path, section_anchor)` pour lire le contenu complet d'une section.*")
    return "\n\n".join(lines)


def read_app_doc_page(doc_path: str, section_anchor: str = "") -> str:
    """Lit le contenu complet d'une page ou d'une section de la documentation officielle."""
    service = AppDocumentationService.get_instance()
    content = service.get_page_content(doc_path=doc_path, section_anchor=section_anchor)
    if not content:
        return f"Erreur : La page de documentation '{doc_path}' n'a pas été trouvée."

    header = f"📄 **Documentation : `{doc_path}`" + (f" ({section_anchor})" if section_anchor else "") + "**\n\n"
    return header + content


def list_app_doc_topics(category: str = "") -> str:
    """Liste la table des matières et les chapitres disponibles dans la documentation Zensical."""
    service = AppDocumentationService.get_instance()
    topics = service.get_topics(category=category)
    if not topics:
        return "Aucun chapitre trouvé dans la documentation" + (f" pour la catégorie '{category}'" if category else "") + "."

    by_cat: dict[str, list[DocTopic]] = {}
    for t in topics:
        by_cat.setdefault(t.category, []).append(t)

    lines: list[str] = ["📚 **Sommaire de la Documentation Officielle d'AnkiForge :**\n"]
    for cat, items in by_cat.items():
        lines.append(f"### 📁 {cat}")
        for item in items:
            sec_preview = f" *(sections: {', '.join(item.sections[:3])}...)*" if item.sections else ""
            lines.append(f"- **{item.title}** (`{item.path}`){sec_preview}")
        lines.append("")

    return "\n".join(lines)


def get_feature_quick_help(feature_name: str) -> str:
    """Retourne une fiche synthétique d'aide sur une fonctionnalité d'AnkiForge."""
    service = AppDocumentationService.get_instance()
    return service.get_feature_quick_help(feature_name)

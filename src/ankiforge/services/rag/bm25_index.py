"""
Indexation lexicale locale BM25 (Okapi BM25) pour le RAG Hybride d'AnkiForge.
Implémentation pure Python déterministe, ultra-légère et sans dépendance C lourde,
optimisée pour Nuitka et compatible multi-plateformes.
"""

from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Stop words par défaut (Français & Anglais)
DEFAULT_STOP_WORDS: set[str] = {
    # Français
    "a",
    "au",
    "aux",
    "avec",
    "ce",
    "ces",
    "dans",
    "de",
    "des",
    "du",
    "elle",
    "en",
    "et",
    "eux",
    "il",
    "ils",
    "je",
    "la",
    "le",
    "les",
    "leur",
    "lui",
    "ma",
    "mais",
    "me",
    "même",
    "mes",
    "moi",
    "mon",
    "ne",
    "nos",
    "notre",
    "nous",
    "on",
    "ou",
    "par",
    "pas",
    "pour",
    "qu",
    "que",
    "qui",
    "sa",
    "se",
    "ses",
    "son",
    "sur",
    "ta",
    "te",
    "tes",
    "toi",
    "ton",
    "tu",
    "un",
    "une",
    "vos",
    "votre",
    "vous",
    "c",
    "d",
    "j",
    "l",
    "m",
    "n",
    "s",
    "t",
    "y",
    "est",
    "sont",
    "été",
    "être",
    "avoir",
    "fait",
    "comme",
    "si",
    # Anglais
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "did",
    "do",
    "does",
    "doing",
    "don",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}

# Regex de tokenisation préservant les termes alphanumériques, acronymes et mots composés
_TOKEN_PATTERN = re.compile(r"(?u)[a-zA-Z0-9][a-zA-Z0-9_\-\+\#\.]*")


def normalize_text(text: str) -> str:
    """
    Normalise le texte en supprimant les accents (NFKD) et en passant en minuscules.
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    # Supprime les marques diacritiques combinées
    no_diacritics = "".join(c for c in normalized if not unicodedata.combining(c))
    return no_diacritics.lower()


def tokenize(text: str, stop_words: set[str] | None = None) -> list[str]:
    """
    Tokenise un texte en conservant les termes techniques et en filtrant les stop-words.
    """
    if not text:
        return []

    norm_text = normalize_text(text)
    raw_tokens = _TOKEN_PATTERN.findall(norm_text)
    stops = stop_words if stop_words is not None else DEFAULT_STOP_WORDS

    tokens: list[str] = []
    for tok in raw_tokens:
        cleaned = tok.strip(".-_")
        if len(cleaned) >= 2 and cleaned not in stops:
            tokens.append(cleaned)

    return tokens


class BM25OkapiIndex:
    """
    Index lexical BM25 Okapi optimisé.

    Formule de score standard Okapi BM25 :
    score(D, Q) = sum_{q in Q} IDF(q) * (f(q, D) * (k1 + 1)) / (f(q, D) + k1 * (1 - b + b * (|D| / avgdl)))

    avec :
    IDF(q) = ln((N - n(q) + 0.5) / (n(q) + 0.5) + 1.0)
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        stop_words: set[str] | None = None,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.stop_words = stop_words if stop_words is not None else DEFAULT_STOP_WORDS

        # Métriques de l'index
        self.doc_ids: list[int] = []
        self.doc_lengths: dict[int, int] = {}
        self.avg_doc_len: float = 0.0
        self.total_docs: int = 0

        # Term Frequencies: {doc_id: Counter({token: freq})}
        self.doc_term_freqs: dict[int, dict[str, int]] = {}

        # Document Frequencies: {token: count_of_docs_containing_token}
        self.doc_freqs: dict[str, int] = {}

        # Precomputed IDF values: {token: idf_score}
        self.idf_cache: dict[str, float] = {}

    def fit(self, corpus: dict[int, str]) -> BM25OkapiIndex:
        """
        Construit l'index BM25 à partir d'un dictionnaire {doc_id: text}.
        """
        self.doc_ids = []
        self.doc_lengths = {}
        self.doc_term_freqs = {}
        self.doc_freqs = {}
        self.idf_cache = {}

        total_length = 0

        for doc_id, text in corpus.items():
            tokens = tokenize(text, self.stop_words)
            doc_len = len(tokens)
            self.doc_ids.append(doc_id)
            self.doc_lengths[doc_id] = doc_len
            total_length += doc_len

            term_counts = Counter(tokens)
            self.doc_term_freqs[doc_id] = dict(term_counts)

            # Mise à jour des document frequencies
            for token in term_counts:
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        self.total_docs = len(self.doc_ids)
        self.avg_doc_len = (total_length / self.total_docs) if self.total_docs > 0 else 0.0

        # Précalcul des scores IDF
        for token, df in self.doc_freqs.items():
            # Formule Okapi BM25 avec lissage standard (+1.0 pour éviter les scores négatifs)
            idf = math.log(((self.total_docs - df + 0.5) / (df + 0.5)) + 1.0)
            self.idf_cache[token] = max(0.0, idf)

        logger.debug(
            "Index BM25 construit : %d documents, vocabulaire de %d termes, longueur moyenne %.1f",
            self.total_docs,
            len(self.doc_freqs),
            self.avg_doc_len,
        )
        return self

    def score_document(self, query_tokens: list[str], doc_id: int) -> float:
        """
        Calcule le score BM25 pour un document spécifique donné une liste de tokens de requête.
        """
        if doc_id not in self.doc_term_freqs or self.avg_doc_len == 0.0:
            return 0.0

        doc_len = self.doc_lengths.get(doc_id, 0)
        term_freqs = self.doc_term_freqs[doc_id]
        score = 0.0

        len_norm = 1.0 - self.b + (self.b * (doc_len / self.avg_doc_len))

        for q_token in query_tokens:
            if q_token not in term_freqs:
                continue

            tf = term_freqs[q_token]
            idf = self.idf_cache.get(q_token, 0.0)

            # Formule BM25 par terme
            numerator = tf * (self.k1 + 1.0)
            denominator = tf + self.k1 * len_norm
            score += idf * (numerator / denominator)

        return score

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Recherche les `top_k` documents les plus pertinents pour la requête.
        Retourne une liste triée de tuples (doc_id, bm25_score).
        """
        if not query or self.total_docs == 0:
            return []

        query_tokens = tokenize(query, self.stop_words)
        if not query_tokens:
            return []

        # Identifier les documents candidats contenant au moins un terme de la requête
        candidate_doc_ids: set[int] = set()
        for q_token in query_tokens:
            if q_token in self.doc_freqs:
                for doc_id, tf_map in self.doc_term_freqs.items():
                    if q_token in tf_map:
                        candidate_doc_ids.add(doc_id)

        if not candidate_doc_ids:
            return []

        scores: list[tuple[int, float]] = []
        for doc_id in candidate_doc_ids:
            s = self.score_document(query_tokens, doc_id)
            if s > 0.0:
                scores.append((doc_id, s))

        # Tri décroissant par score BM25
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def to_dict(self) -> dict[str, Any]:
        """Sérialise l'index BM25 sous forme de dictionnaire JSON-compatible."""
        return {
            "version": "1.0",
            "k1": self.k1,
            "b": self.b,
            "total_docs": self.total_docs,
            "avg_doc_len": self.avg_doc_len,
            "doc_ids": self.doc_ids,
            "doc_lengths": {str(k): v for k, v in self.doc_lengths.items()},
            "doc_term_freqs": {str(k): v for k, v in self.doc_term_freqs.items()},
            "doc_freqs": self.doc_freqs,
            "idf_cache": self.idf_cache,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BM25OkapiIndex:
        """Désérialise un index BM25 depuis un dictionnaire."""
        idx = cls(k1=float(data.get("k1", 1.5)), b=float(data.get("b", 0.75)))
        idx.total_docs = int(data.get("total_docs", 0))
        idx.avg_doc_len = float(data.get("avg_doc_len", 0.0))
        idx.doc_ids = [int(i) for i in data.get("doc_ids", [])]
        idx.doc_lengths = {int(k): int(v) for k, v in data.get("doc_lengths", {}).items()}
        idx.doc_term_freqs = {int(k): {tok: int(freq) for tok, freq in v.items()} for k, v in data.get("doc_term_freqs", {}).items()}
        idx.doc_freqs = {tok: int(df) for tok, df in data.get("doc_freqs", {}).items()}
        idx.idf_cache = {tok: float(idf) for tok, idf in data.get("idf_cache", {}).items()}
        return idx

    def save(self, file_path: Path | str) -> None:
        """Sauvegarde l'index sur le disque au format JSON."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, file_path: Path | str) -> BM25OkapiIndex:
        """Charge l'index depuis un fichier JSON."""
        path = Path(file_path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

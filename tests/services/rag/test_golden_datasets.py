import json
from pathlib import Path

import pytest

from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.rag.vector_manager import BM25OkapiIndex
from ankiforge.utils.anki_renderer import render_anki_card


@pytest.fixture
def golden_data_dir() -> Path:
    return Path(__file__).parent.parent.parent / "fixtures" / "golden_data"


@pytest.mark.unit
def test_golden_wikipedia_chunking_preserves_latex(golden_data_dir: Path) -> None:
    """Vérifie que le découpage en chunks d'un article mathématique préserve les formules LaTeX."""
    wiki_file = golden_data_dir / "wikipedia_article_latex.md"
    assert wiki_file.exists()

    content = wiki_file.read_text(encoding="utf-8")
    chunks = ChunkingService.extract_chunks(content, file_type="markdown")

    assert len(chunks) >= 2
    # Vérifie que la formule principale $$P(A \mid B)...$$ est préservée
    all_chunks_text = " ".join(c["content"] for c in chunks)
    assert r"\frac{P(B \mid A)" in all_chunks_text
    assert "$$P(A \\mid B)" in all_chunks_text


@pytest.mark.unit
def test_golden_course_bm25_search(golden_data_dir: Path) -> None:
    """Vérifie que l'index BM25 Sparse retrouve avec précision les concepts d'un chapitre de cours."""
    course_file = golden_data_dir / "course_chapter_rag.md"
    assert course_file.exists()

    content = course_file.read_text(encoding="utf-8")
    chunks = ChunkingService.extract_chunks(content, file_type="markdown")

    corpus = {f"chunk_{i}": c["content"] for i, c in enumerate(chunks)}
    bm25 = BM25OkapiIndex()
    bm25.fit(corpus)

    # Recherche pour "Théorème CAP Brewer"
    results_cap = bm25.search("Théorème CAP Brewer", top_k=2)
    assert len(results_cap) > 0
    top_cap_id = results_cap[0][0]
    assert "CAP" in corpus[top_cap_id] or "Brewer" in corpus[top_cap_id]

    # Recherche pour "Paxos Raft leader"
    results_raft = bm25.search("Raft Leader Follower", top_k=2)
    assert len(results_raft) > 0
    top_raft_id = results_raft[0][0]
    assert "Raft" in corpus[top_raft_id] or "Paxos" in corpus[top_raft_id]


@pytest.mark.unit
def test_golden_wozniak_card_rendering(golden_data_dir: Path) -> None:
    """Vérifie le rendu HTML/KaTeX des cartes du Golden Dataset."""
    cards_file = golden_data_dir / "wozniak_test_cards.json"
    assert cards_file.exists()

    cards = json.loads(cards_file.read_text(encoding="utf-8"))
    assert len(cards) == 4

    # Carte KaTeX conforme
    katex_card = next(c for c in cards if c["id"] == "card_04_compliant_katex")
    rendered_recto = render_anki_card(
        raw_html="{{Recto}}",
        css="",
        fields_dict={"Recto": katex_card["recto"], "Verso": katex_card["verso"]},
        is_recto=True,
    )
    assert "operatorname{Var}" in rendered_recto

    rendered_verso = render_anki_card(
        raw_html="{{FrontSide}}<hr>{{Verso}}",
        css="",
        fields_dict={"Recto": katex_card["recto"], "Verso": katex_card["verso"]},
        front_html=rendered_recto,
        is_recto=False,
    )
    assert "mathbb{E}" in rendered_verso

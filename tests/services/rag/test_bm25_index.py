"""
Tests unitaires pour l'index lexical BM25 Okapi pur Python (src/ankiforge/services/rag/bm25_index.py).
Valide la tokenisation multi-langue, la préservation des acronymes, le calcul IDF,
la formule de score Okapi BM25 et la persistance JSON.
"""

from pathlib import Path

from ankiforge.services.rag.bm25_index import BM25OkapiIndex, normalize_text, tokenize


def test_normalize_text():
    assert normalize_text("Électron & Protéine") == "electron & proteine"
    assert normalize_text("À l'Hôpital Général") == "a l'hopital general"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""  # type: ignore


def test_tokenize_and_stop_words():
    # Test avec stop-words français et anglais
    text = "Le patient présente des symptômes de COVID-19 avec une altération du gène p53 et du niveau d'HbA1c."
    tokens = tokenize(text)

    # Vérification des stop-words filtrés
    assert "le" not in tokens
    assert "des" not in tokens
    assert "du" not in tokens
    assert "de" not in tokens
    assert "une" not in tokens

    # Vérification de la préservation des termes médicaux et acronymes
    assert "covid-19" in tokens
    assert "p53" in tokens
    assert "hba1c" in tokens
    assert "patient" in tokens
    assert "symptomes" in tokens
    assert "gene" in tokens


def test_tokenize_empty_and_punctuation():
    assert tokenize("") == []
    assert tokenize("... --- ,,,") == []
    assert tokenize("C++ et C#") == ["c++", "c#"]


def test_bm25_fit_and_scoring():
    corpus = {
        1: "Le myocarde est le tissu musculaire épais du cœur responsable de la contraction cardiaque.",
        2: "Le péricarde est la membrane protectrice qui enveloppe le myocarde et l'ensemble du cœur.",
        3: "Le système nerveux central comprend l'encéphale et la moelle épinière.",
        4: "L'ATP (adénosine triphosphate) fournit l'énergie nécessaire à la contraction du myocarde.",
    }

    bm25 = BM25OkapiIndex(k1=1.5, b=0.75)
    bm25.fit(corpus)

    assert bm25.total_docs == 4
    assert bm25.avg_doc_len > 0
    assert "myocarde" in bm25.doc_freqs
    assert bm25.doc_freqs["myocarde"] == 3  # Dans docs 1, 2, 4
    assert bm25.doc_freqs["pericarde"] == 1  # Uniquement doc 2

    # Terme rare (péricarde) doit avoir un IDF plus élevé que myocarde
    assert bm25.idf_cache["pericarde"] > bm25.idf_cache["myocarde"]

    # Recherche sur terme spécifique "péricarde"
    res_pericarde = bm25.search("péricarde", top_k=2)
    assert len(res_pericarde) > 0
    assert res_pericarde[0][0] == 2  # Doc 2 en top 1

    # Recherche multi-termes "ATP contraction"
    res_atp = bm25.search("ATP énergie contraction", top_k=2)
    assert len(res_atp) > 0
    assert res_atp[0][0] == 4  # Doc 4 en top 1


def test_bm25_empty_query_and_empty_corpus():
    bm25 = BM25OkapiIndex()
    assert bm25.search("test") == []

    bm25.fit({1: "Texte simple"})
    assert bm25.search("") == []
    assert bm25.search("   ") == []
    assert bm25.search("mot_totalement_absent_xyz") == []


def test_bm25_serialization_and_loading(tmp_path: Path):
    corpus = {
        10: "Architecture logicielle et microservices en Python.",
        20: "Bases de données SQL, Peewee ORM et indexation binaire.",
        30: "Intelligence artificielle, réseaux de neurones et LLM.",
    }

    bm25_orig = BM25OkapiIndex()
    bm25_orig.fit(corpus)

    save_file = tmp_path / "test_bm25.json"
    bm25_orig.save(save_file)
    assert save_file.exists()

    bm25_loaded = BM25OkapiIndex.load(save_file)
    assert bm25_loaded.total_docs == 3
    assert bm25_loaded.doc_ids == [10, 20, 30]

    # Les résultats de recherche doivent être strictement identiques
    res_orig = bm25_orig.search("Peewee ORM", top_k=2)
    res_loaded = bm25_loaded.search("Peewee ORM", top_k=2)
    assert res_orig == res_loaded
    assert res_loaded[0][0] == 20

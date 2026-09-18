"""
Tests unitaires pour SegmentInspectorWidget.

Couverture :
- Instanciation sans document
- set_document() avec Markdown → stratégies H1/H2/H3/tokens
- set_document() avec PDF → stratégies page/range/toc/tokens
- get_active_segments() retourne les items cochés
- _set_all_checked(False) → 0 actif; _set_all_checked(True) → tous actifs
- get_total_active_tokens() cohérent avec get_active_segments()
- Signal segments_updated émis lors de recompute_segments()
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from ankiforge.database.models import DocumentModel
from ankiforge.ui.widgets.segment_inspector_widget import SegmentInspectorWidget

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def parent_widget(qtbot) -> QWidget:
    w = QWidget()
    w.resize(900, 600)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def inspector(qtbot, parent_widget) -> SegmentInspectorWidget:
    widget = SegmentInspectorWidget(parent=parent_widget)
    qtbot.addWidget(widget)
    return widget


def _make_doc(file_type: str = "md", content: str = "") -> DocumentModel:
    """Crée un vrai DocumentModel en base mémoire (fixture autouse mock_db)."""
    total_pages = content.count("--- PAGE") or 1
    return DocumentModel.create(
        title=f"Document de test ({file_type})",
        content=content,
        file_type=file_type,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Contenu de test réutilisable
# ---------------------------------------------------------------------------

MD_CONTENT = """\
# Chapitre 1 — Introduction
Contenu de l'introduction. La formation Python est essentielle pour les développeurs modernes.

## 1.1 Présentation
Ce cours couvre les bases du langage Python depuis la version 3.10 jusqu'à 3.12.

## 1.2 Prérequis
Il faut connaître les bases de la programmation avant de commencer ce module.

# Chapitre 2 — Variables
Les variables en Python sont dynamiquement typées et gèrent automatiquement la mémoire.

## 2.1 Types de base
int, float, str, bool, list, dict, set, tuple — chacun a ses usages spécifiques.
"""

PDF_CONTENT = """\
--- PAGE 1 ---
Première page du document de cours. Introduction au programme et aux objectifs pédagogiques.

--- PAGE 2 ---
Deuxième page : concepts fondamentaux de la matière. Approfondissement des notions théoriques.

--- PAGE 3 ---
Troisième page : exercices pratiques. Application directe des concepts vus en cours.
"""


# ---------------------------------------------------------------------------
# Tests d'instanciation
# ---------------------------------------------------------------------------


def test_inspector_instantiation_empty(inspector: SegmentInspectorWidget) -> None:
    """Le widget s'instancie sans document et la liste est vide."""
    assert inspector.segments_list.count() == 0
    assert inspector.get_active_segments() == []
    assert inspector.get_total_active_tokens() == 0


def test_inspector_has_required_attributes(inspector: SegmentInspectorWidget) -> None:
    """Les attributs d'UI fondamentaux existent."""
    assert hasattr(inspector, "combo_strategy")
    assert hasattr(inspector, "segments_list")
    assert hasattr(inspector, "btn_check_all")
    assert hasattr(inspector, "btn_uncheck_all")
    assert hasattr(inspector, "lbl_summary")
    assert hasattr(inspector, "input_page_range")
    assert hasattr(inspector, "token_slider")


# ---------------------------------------------------------------------------
# Tests set_document — Markdown
# ---------------------------------------------------------------------------


def test_set_document_markdown_populates_strategies(inspector: SegmentInspectorWidget) -> None:
    """Un document Markdown expose les stratégies H1/H2/H3/tokens."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    with (
        patch("ankiforge.ui.widgets.segment_inspector_widget.ChunkingService") as mock_cs,
        patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc,
        patch("ankiforge.ui.widgets.segment_inspector_widget.smart_chunk_text") as mock_sct,
    ):
        mock_cc.estimate_tokens.return_value = 120
        mock_cs.extract_chunks.return_value = []
        mock_sct.return_value = []

        inspector.set_document(doc, fallback_text="")

    strategies = [inspector.combo_strategy.itemData(i) for i in range(inspector.combo_strategy.count())]
    assert "h2" in strategies
    assert "h1" in strategies
    assert "h3" in strategies
    assert "tokens" in strategies
    assert "page" not in strategies


def test_set_document_markdown_recompute_produces_segments(inspector: SegmentInspectorWidget) -> None:
    """set_document sur du Markdown H2 génère au moins 2 segments."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    inspector._doc = doc
    inspector._fallback_text = ""
    inspector._populate_strategies()

    for i in range(inspector.combo_strategy.count()):
        if inspector.combo_strategy.itemData(i) == "h2":
            inspector.combo_strategy.setCurrentIndex(i)
            break

    with patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc:
        mock_cc.estimate_tokens.return_value = 150
        inspector.recompute_segments()

    count = inspector.segments_list.count()
    assert count >= 2, f"Au moins 2 segments H2 attendus pour MD_CONTENT, got {count}"


# ---------------------------------------------------------------------------
# Tests set_document — PDF
# ---------------------------------------------------------------------------


def test_set_document_pdf_populates_strategies(inspector: SegmentInspectorWidget) -> None:
    """Un document PDF expose les stratégies page/range/toc/tokens."""
    doc = _make_doc(file_type="pdf", content=PDF_CONTENT)

    with (
        patch("ankiforge.ui.widgets.segment_inspector_widget.ChunkingService") as mock_cs,
        patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc,
        patch("ankiforge.ui.widgets.segment_inspector_widget.smart_chunk_text") as mock_sct,
    ):
        mock_cc.estimate_tokens.return_value = 80
        mock_cs.extract_chunks.return_value = [
            {"index": 0, "content": "Page 1 content", "page_number": 1, "heading_path": None},
        ]
        mock_sct.return_value = []

        inspector.set_document(doc, fallback_text="")

    strategies = [inspector.combo_strategy.itemData(i) for i in range(inspector.combo_strategy.count())]
    assert "page" in strategies
    assert "range" in strategies
    assert "tokens" in strategies
    assert "h2" not in strategies


def test_set_document_pdf_page_strategy_creates_segments(inspector: SegmentInspectorWidget) -> None:
    """La stratégie 'page' crée autant de segments que de pages retournées."""
    doc = _make_doc(file_type="pdf", content=PDF_CONTENT)

    fake_chunks = [
        {"index": 0, "content": "Page 1 content here.", "page_number": 1, "heading_path": None},
        {"index": 1, "content": "Page 2 content here.", "page_number": 2, "heading_path": None},
        {"index": 2, "content": "Page 3 content here.", "page_number": 3, "heading_path": None},
    ]

    with (
        patch("ankiforge.ui.widgets.segment_inspector_widget.ChunkingService") as mock_cs,
        patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc,
        patch("ankiforge.ui.widgets.segment_inspector_widget.smart_chunk_text") as mock_sct,
    ):
        mock_cc.estimate_tokens.return_value = 50
        mock_cs.extract_chunks.return_value = fake_chunks
        mock_sct.return_value = []

        inspector.set_document(doc, fallback_text="")

    assert inspector.segments_list.count() == 3
    item0 = inspector.segments_list.item(0)
    data0 = item0.data(Qt.ItemDataRole.UserRole)
    assert data0 is not None
    assert "1" in data0["title"]


# ---------------------------------------------------------------------------
# Tests get_active_segments et décocher
# ---------------------------------------------------------------------------


def test_uncheck_all_makes_active_segments_empty(inspector: SegmentInspectorWidget) -> None:
    """_set_all_checked(False) vide get_active_segments()."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    inspector._doc = doc
    inspector._populate_strategies()

    with patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc:
        mock_cc.estimate_tokens.return_value = 100
        inspector.recompute_segments()

    assert inspector.segments_list.count() >= 1

    inspector._set_all_checked(False)
    assert inspector.get_active_segments() == []
    assert inspector.get_total_active_tokens() == 0


def test_check_all_restores_all_segments(inspector: SegmentInspectorWidget) -> None:
    """_set_all_checked(True) après un décocher total restitue tous les segments."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    inspector._doc = doc
    inspector._populate_strategies()

    with patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc:
        mock_cc.estimate_tokens.return_value = 100
        inspector.recompute_segments()

    total = inspector.segments_list.count()
    inspector._set_all_checked(False)
    inspector._set_all_checked(True)

    active = inspector.get_active_segments()
    assert len(active) == total


def test_individual_uncheck_reduces_active_count(inspector: SegmentInspectorWidget) -> None:
    """Décocher un item individuellement réduit get_active_segments() de 1."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    inspector._doc = doc
    inspector._populate_strategies()

    with patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc:
        mock_cc.estimate_tokens.return_value = 100
        inspector.recompute_segments()

    total = inspector.segments_list.count()
    if total < 2:
        pytest.skip("Pas assez de segments pour tester la décocher individuelle")

    item0 = inspector.segments_list.item(0)
    item0.setCheckState(Qt.CheckState.Unchecked)

    active = inspector.get_active_segments()
    assert len(active) == total - 1


# ---------------------------------------------------------------------------
# Tests get_total_active_tokens
# ---------------------------------------------------------------------------


def test_get_total_active_tokens_consistent_with_segments(inspector: SegmentInspectorWidget) -> None:
    """get_total_active_tokens() = somme des 'tokens' dans get_active_segments()."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    inspector._doc = doc
    inspector._populate_strategies()

    with patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc:
        mock_cc.estimate_tokens.return_value = 250
        inspector.recompute_segments()

    total_tokens = inspector.get_total_active_tokens()
    expected = sum(c.get("tokens", 0) for c in inspector.get_active_segments())
    assert total_tokens == expected


# ---------------------------------------------------------------------------
# Tests signaux
# ---------------------------------------------------------------------------


def test_segments_updated_signal_emitted_on_recompute(qtbot, inspector: SegmentInspectorWidget) -> None:
    """Le signal segments_updated est émis lors de recompute_segments()."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    inspector._doc = doc
    inspector._populate_strategies()

    with qtbot.waitSignal(inspector.segments_updated, timeout=3000), patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc:
        mock_cc.estimate_tokens.return_value = 100
        inspector.recompute_segments()


def test_open_delimitation_requested_signal(qtbot, inspector: SegmentInspectorWidget) -> None:
    """Cliquer sur btn_delimit émet open_delimitation_requested."""
    with qtbot.waitSignal(inspector.open_delimitation_requested, timeout=2000):
        inspector.btn_delimit.click()


# ---------------------------------------------------------------------------
# Tests visibilité des contrôles contextuels
# ---------------------------------------------------------------------------


def test_token_slider_frame_hidden_by_default_for_markdown(inspector: SegmentInspectorWidget) -> None:
    """Le curseur de tokens est caché (isHidden) quand la stratégie est h2."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    with (
        patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc,
        patch("ankiforge.ui.widgets.segment_inspector_widget.ChunkingService"),
        patch("ankiforge.ui.widgets.segment_inspector_widget.smart_chunk_text") as mock_sct,
    ):
        mock_cc.estimate_tokens.return_value = 100
        mock_sct.return_value = []
        inspector.set_document(doc)

    # Par défaut (h2) → curseur masqué : isHidden() est fiable en headless
    assert inspector.token_slider_frame.isHidden()

    # Passer en stratégie tokens → ne doit plus être hidden
    for i in range(inspector.combo_strategy.count()):
        if inspector.combo_strategy.itemData(i) == "tokens":
            inspector.combo_strategy.setCurrentIndex(i)
            break

    assert not inspector.token_slider_frame.isHidden()


def test_fused_scope_and_strategy_differentiation_for_pdf(inspector: SegmentInspectorWidget) -> None:
    """Vérifie que la portée est intégrée et que 'page' (N segments) et 'range' (1 bloc) ne font pas la même chose."""
    doc = _make_doc(file_type="pdf", content=PDF_CONTENT)

    fake_chunks = [
        {"index": 0, "content": "Page 1 text.", "page_number": 1, "heading_path": None},
        {"index": 1, "content": "Page 2 text.", "page_number": 2, "heading_path": None},
        {"index": 2, "content": "Page 3 text.", "page_number": 3, "heading_path": None},
    ]

    with (
        patch("ankiforge.ui.widgets.segment_inspector_widget.ChunkingService") as mock_cs,
        patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc,
        patch("ankiforge.ui.widgets.segment_inspector_widget.smart_chunk_text") as mock_sct,
    ):
        mock_cc.estimate_tokens.return_value = 80
        mock_cs.extract_chunks.return_value = fake_chunks
        mock_sct.return_value = []
        inspector.set_document(doc)

        # 1. Par défaut : stratégie 'page' -> 3 segments individuels
        assert inspector.segments_list.count() == 3
        assert not inspector.scope_container.isHidden()
        assert inspector.input_page_scope.text() == "1-3"

        # 2. Preset 'Page 1' restreint la portée et les segments
        inspector.btn_preset_page.click()
        assert inspector.input_page_scope.text() == "1"
        assert inspector.segments_list.count() == 1
        assert "Page 1" in inspector.segments_list.item(0).data(Qt.ItemDataRole.UserRole)["title"]

        # 3. Rétablir 'Tout le doc'
        inspector.btn_preset_all.click()
        assert inspector.segments_list.count() == 3

        # 4. Stratégie 'range' (Plage complète en 1 bloc) -> 1 seul segment groupé (différent de 'page')
        for i in range(inspector.combo_strategy.count()):
            if inspector.combo_strategy.itemData(i) == "range":
                inspector.combo_strategy.setCurrentIndex(i)
                break

        assert inspector.segments_list.count() == 1
        chunk_data = inspector.segments_list.item(0).data(Qt.ItemDataRole.UserRole)
        assert "1-3" in chunk_data["title"]
        assert "Page 1 text." in chunk_data["content"]
        assert "Page 3 text." in chunk_data["content"]


def test_segment_item_widget_checkbox_interaction(inspector: SegmentInspectorWidget) -> None:
    """Vérifie que la case à cocher sur chaque fragment permet de l'inclure ou l'exclure."""
    doc = _make_doc(file_type="md", content=MD_CONTENT)

    with patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor") as mock_cc:
        mock_cc.estimate_tokens.return_value = 100
        inspector.set_document(doc)

    assert inspector.segments_list.count() >= 2
    item0 = inspector.segments_list.item(0)
    w0 = inspector.segments_list.itemWidget(item0)
    assert w0 is not None
    assert hasattr(w0, "checkbox")
    assert w0.is_checked()

    # Décocher via la case à cocher
    w0.checkbox.setChecked(False)
    assert not w0.is_checked()
    assert item0.checkState() == Qt.CheckState.Unchecked

    active = inspector.get_active_segments()
    assert len(active) == inspector.segments_list.count() - 1

    # Recocher
    w0.checkbox.setChecked(True)
    assert w0.is_checked()
    assert len(inspector.get_active_segments()) == inspector.segments_list.count()


# ---------------------------------------------------------------------------
# Test fallback si contenu vide
# ---------------------------------------------------------------------------


def test_set_document_empty_content_shows_no_segments(inspector: SegmentInspectorWidget) -> None:
    """Un document sans contenu ne génère aucun segment."""
    doc = _make_doc(file_type="md", content="")

    with (
        patch("ankiforge.ui.widgets.segment_inspector_widget.ContextCompactor"),
        patch("ankiforge.ui.widgets.segment_inspector_widget.ChunkingService"),
        patch("ankiforge.ui.widgets.segment_inspector_widget.smart_chunk_text") as mock_sct,
    ):
        mock_sct.return_value = []
        inspector.set_document(doc)

    assert inspector.segments_list.count() == 0
    assert inspector.get_active_segments() == []

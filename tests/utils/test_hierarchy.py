"""
Tests unitaires des utilitaires de hiérarchie séparée par ``::``.
"""

from __future__ import annotations

import pytest

from ankiforge.utils.hierarchy import (
    ANKI_UNIT_SEPARATOR,
    SEPARATOR,
    descendants_prefix,
    descends_from,
    from_anki_unit_separator,
    join_hierarchy,
    leaf_name,
    parent_path,
    split_hierarchy,
    to_anki_unit_separator,
    to_filename_safe,
)

pytestmark = pytest.mark.unit


class TestSplitHierarchy:
    def test_split_basic(self) -> None:
        assert split_hierarchy("Science::Physique::Thermo") == ["Science", "Physique", "Thermo"]

    def test_split_cleans_whitespace(self) -> None:
        assert split_hierarchy("Science :: Physique :: ") == ["Science", "Physique"]

    def test_split_filters_empty_levels(self) -> None:
        assert split_hierarchy("a::::b") == ["a", "b"]

    def test_split_no_strip(self) -> None:
        assert split_hierarchy("A:: B ", strip=False) == ["A", " B "]

    def test_split_empty(self) -> None:
        assert split_hierarchy("") == []
        assert split_hierarchy("::") == []


class TestJoinHierarchy:
    def test_join_basic(self) -> None:
        assert join_hierarchy(["Science", "Physique"]) == "Science::Physique"

    def test_join_cleans_parts(self) -> None:
        assert join_hierarchy(["Science ", " Physique"]) == "Science::Physique"

    def test_join_ignores_empty_parts(self) -> None:
        assert join_hierarchy(["a", "", "  ", "b"]) == "a::b"

    def test_roundtrip(self) -> None:
        assert split_hierarchy(join_hierarchy(["a", "b", "c"])) == ["a", "b", "c"]


class TestLeafAndParent:
    def test_leaf_name(self) -> None:
        assert leaf_name("Science::Physique::Thermo") == "Thermo"
        assert leaf_name("Racine") == "Racine"

    def test_parent_path(self) -> None:
        assert parent_path("Science::Physique::Thermo") == "Science::Physique"
        assert parent_path("Science") is None


class TestDescendants:
    def test_descendants_prefix(self) -> None:
        assert descendants_prefix("Science") == "Science::"

    def test_descends_from_self(self) -> None:
        assert descends_from("Science", "Science") is True

    def test_descends_from_child(self) -> None:
        assert descends_from("Science::Physique", "Science") is True

    def test_descends_from_no_false_positive_prefix(self) -> None:
        assert descends_from("Mathématiques", "Math") is False
        assert descends_from("Mathau", "Math") is False

    def test_descends_from_unrelated(self) -> None:
        assert descends_from("Chimie", "Physique") is False


class TestFilenameSafe:
    def test_replaces_separator(self) -> None:
        assert to_filename_safe("Science::Physique") == "Science_Physique"

    def test_replaces_spaces(self) -> None:
        assert to_filename_safe("Bonjour tout le monde") == "Bonjour_tout_le_monde"

    def test_custom_replacement(self) -> None:
        assert to_filename_safe("a::b", replacement="-") == "a-b"


class TestAnkiUnitSeparator:
    def test_from_anki(self) -> None:
        assert from_anki_unit_separator("Science\x1fPhysique") == "Science::Physique"

    def test_from_anki_noop(self) -> None:
        assert from_anki_unit_separator("Science::Physique") == "Science::Physique"

    def test_to_anki(self) -> None:
        assert to_anki_unit_separator("Science::Physique") == "Science\x1fPhysique"

    def test_roundtrip(self) -> None:
        name = "Science::Physique::Thermo"
        assert from_anki_unit_separator(to_anki_unit_separator(name)) == name

    def test_separator_constants(self) -> None:
        assert SEPARATOR == "::"
        assert ANKI_UNIT_SEPARATOR == "\x1f"
        assert to_anki_unit_separator(join_hierarchy(["a", "b"])) == f"a{ANKI_UNIT_SEPARATOR}b"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("", []),
        ("Racine", ["Racine"]),
        ("A::B", ["A", "B"]),
        ("  A  ::  B  ", ["A", "B"]),
        ("::A::", ["A"]),
    ],
)
def test_split_hierarchy_parametrized(name: str, expected: list[str]) -> None:
    assert split_hierarchy(name) == expected

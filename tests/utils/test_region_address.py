"""Tests du prédicat unifié d'adresses de région (ADR 0010).

L'identité durable d'une région est son *adresse* — ``node:``, ``heading:`` ou ``page:`` — et
jamais l'identifiant d'un fragment, réattribué à chaque réingestion. Ce module est le point de
passage unique du test d'appartenance : le dépôt, les dialogues, les vues et la couverture
l'interrogent tous, ce qui supprime la divergence « correspondance exacte » (dialogue) contre
« correspondance par sous-chaîne » (dépôt) qui faisait renaître une exclusion à la réouverture.
"""

from __future__ import annotations

import pytest

from ankiforge.utils.region_address import (
    RegionAddress,
    RegionScope,
    covers_region,
    parse_region_address,
    parse_region_addresses,
    render_region_addresses,
)


class TestRegionScopeParsing:
    def test_explicit_scopes_are_parsed(self) -> None:
        assert parse_region_address("node:Cours > Ch1") == RegionAddress(RegionScope.NODE, "Cours > Ch1")
        assert parse_region_address("heading:Cours") == RegionAddress(RegionScope.HEADING, "Cours")
        assert parse_region_address("page:3") == RegionAddress(RegionScope.PAGE, "3")

    def test_legacy_entry_without_prefix_is_read_as_heading(self) -> None:
        """Rétrocompatibilité sans migration : une entrée nue reste une exclusion de lignée."""
        assert parse_region_address("Cours > Ch1") == RegionAddress(RegionScope.HEADING, "Cours > Ch1")

    def test_bare_number_is_a_heading_not_a_page_hole(self) -> None:
        """Régression du.dialogue : un titre « 4 » ne doit plus être lu comme un trou de page."""
        assert parse_region_address("4") == RegionAddress(RegionScope.HEADING, "4")

    def test_prefix_is_only_recognised_on_a_non_empty_value(self) -> None:
        assert parse_region_address("heading:") is None
        assert parse_region_address("node:   ") is None
        assert parse_region_address("page:abc") is None

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_blank_input_yields_nothing(self, raw: str | None) -> None:
        assert parse_region_address(raw) is None

    def test_case_of_the_scope_prefix_is_insensitive(self) -> None:
        assert parse_region_address("PAGE:12") == RegionAddress(RegionScope.PAGE, "12")

    def test_render_round_trip_is_canonical(self) -> None:
        for raw in ("node:Cours > Ch1", "heading:Cours", "page:3"):
            assert parse_region_address(raw).render() == raw

    def test_legacy_entry_is_rendered_with_its_canonical_prefix(self) -> None:
        assert parse_region_address("Cours").render() == "heading:Cours"

    def test_render_normalises_whitespace_of_the_value(self) -> None:
        assert parse_region_address("  heading:   Cours   ").render() == "heading:Cours"

    def test_render_reorders_a_non_canonical_page_number(self) -> None:
        assert parse_region_address("page:007").render() == "page:7"


class TestRegionAddressCollection:
    def test_parses_a_json_list_and_keeps_order(self) -> None:
        assert parse_region_addresses('["node:A", "page:2", "B"]') == [
            RegionAddress(RegionScope.NODE, "A"),
            RegionAddress(RegionScope.PAGE, "2"),
            RegionAddress(RegionScope.HEADING, "B"),
        ]

    def test_parses_a_plain_string_and_a_legacy_json_list(self) -> None:
        expected = [RegionAddress(RegionScope.HEADING, "A")]
        assert parse_region_addresses("A") == expected
        assert parse_region_addresses('["A"]') == expected

    def test_ignores_unparsable_entries_without_losing_the_others(self) -> None:
        assert parse_region_addresses('["", "  ", "page:1"]') == [RegionAddress(RegionScope.PAGE, "1")]

    def test_deduplicates_equivalent_entries(self) -> None:
        assert parse_region_addresses('["heading:Cours", "Cours", "heading:  Cours  "]') == [RegionAddress(RegionScope.HEADING, "Cours")]

    def test_render_is_canonical_and_deduplicated(self) -> None:
        assert render_region_addresses('["Cours", "heading:Cours", "page:02", "page:2"]') == '["heading:Cours", "page:2"]'

    def test_render_of_an_empty_collection_is_an_empty_json_array(self) -> None:
        assert render_region_addresses([]) == "[]"
        assert render_region_addresses(None) == "[]"


class TestRegionCoverage:
    def test_node_scope_matches_only_the_node_own_breadcrumb(self) -> None:
        address = RegionAddress(RegionScope.NODE, "Cours > Ch1")
        assert address.covers(heading_path="Cours > Ch1", page_number=3) is True
        assert address.covers(heading_path="Cours > Ch1 > 1.1", page_number=3) is False
        assert address.covers(heading_path="Cours", page_number=1) is False

    def test_heading_scope_covers_the_node_and_its_descendants(self) -> None:
        address = RegionAddress(RegionScope.HEADING, "Cours")
        assert address.covers(heading_path="Cours", page_number=1) is True
        assert address.covers(heading_path="Cours > Ch1 > 1.1", page_number=9) is True

    def test_heading_scope_respects_the_breadcrumb_boundary(self) -> None:
        """« Cours » ne doit pas englober « Coursan » : le test par sous-chaîne était le bug."""
        address = RegionAddress(RegionScope.HEADING, "Cours")
        assert address.covers(heading_path="Coursan", page_number=1) is False
        assert address.covers(heading_path="Cours avancés", page_number=1) is False

    def test_heading_scope_of_a_full_breadcrumb_covers_a_descendant_only(self) -> None:
        address = RegionAddress(RegionScope.HEADING, "Cours > Ch1")
        assert address.covers(heading_path="Cours > Ch1", page_number=1) is True
        assert address.covers(heading_path="Cours > Ch1 > 1.1", page_number=1) is True
        assert address.covers(heading_path="Cours > Ch2", page_number=1) is False
        assert address.covers(heading_path="Cours", page_number=1) is False

    def test_page_scope_matches_the_exact_page_number(self) -> None:
        address = RegionAddress(RegionScope.PAGE, "3")
        assert address.covers(heading_path=None, page_number=3) is True
        assert address.covers(heading_path="Cours", page_number=4) is False
        assert address.covers(heading_path="Cours", page_number=None) is False

    def test_heading_scopes_ignore_the_page_number(self) -> None:
        address = RegionAddress(RegionScope.HEADING, "Cours")
        assert address.covers(heading_path="Cours", page_number=None) is True

    def test_matching_is_case_and_whitespace_insensitive(self) -> None:
        address = RegionAddress(RegionScope.HEADING, "Cours")
        assert address.covers(heading_path="  cours  >  ch1 ", page_number=1) is True

    def test_addresses_are_hashable_and_comparable(self) -> None:
        assert RegionAddress(RegionScope.HEADING, "A") == RegionAddress(RegionScope.HEADING, " a ")
        assert len({RegionAddress(RegionScope.HEADING, "A"), RegionAddress(RegionScope.HEADING, "A")}) == 1


class TestCoversRegion:
    def test_no_address_never_covers_anything(self) -> None:
        assert covers_region([], heading_path="Cours", page_number=1) is False

    def test_any_matching_scope_covers(self) -> None:
        addresses = [RegionAddress(RegionScope.PAGE, "9"), RegionAddress(RegionScope.HEADING, "Cours")]
        assert covers_region(addresses, heading_path="Cours > Ch1", page_number=1) is True

    def test_accepts_a_raw_json_collection(self) -> None:
        assert covers_region('["page:2"]', heading_path=None, page_number=2) is True
        assert covers_region('["page:2"]', heading_path=None, page_number=3) is False

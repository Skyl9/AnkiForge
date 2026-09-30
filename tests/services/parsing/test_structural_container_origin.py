"""Tests de l'axe *Origine* du conteneur structurel (ADR 0010).

Le drapeau `is_structural_container` ne dit pas **pourquoi** une région sort du dénominateur
de couverture. `container_origin` rend cette cause explicite :

- ``derived`` — déduit de la structure (titre parent maigre au-dessus de sous-sections
  substantielles) ;
- ``declared`` — déclaré par l'utilisateur, qui **neutralise** la région.

Une origine déclarée prime sur les heuristiques : ni le seuil de 25 mots, ni l'existence de
descendants ne peuvent disqualifier une déclaration. Le seuil reste une **aide à la
déclaration** — une suggestion faite à l'utilisateur — jamais un critère de calcul.
"""

from __future__ import annotations

from typing import Any

from ankiforge.services.parsing.chunking_service import ChunkingService, ContainerOrigin


def _chunk(heading_path: str, content: str) -> dict[str, Any]:
    return {"heading_path": heading_path, "content": content}


class TestContainerOriginEnum:
    def test_declared_and_derived_are_distinct_axes_of_one_flag(self) -> None:
        assert ContainerOrigin.DERIVED == "derived"
        assert ContainerOrigin.DECLARED == "declared"
        assert ContainerOrigin.DECLARED != ContainerOrigin.DERIVED


class TestIsStructuralContainer:
    def test_derived_rule_is_unchanged(self) -> None:
        assert ChunkingService.is_structural_container("A > B", "# B\n\nSix mots ici.", has_descendants=True) is True
        assert ChunkingService.is_structural_container("A > B", "# B\n\n" + " ".join(["mot"] * 50), has_descendants=True) is False
        assert ChunkingService.is_structural_container("A > B", "# B\n\nSix mots ici.", has_descendants=False) is False

    def test_declared_origin_overrides_the_word_threshold(self) -> None:
        """Un contenu riche déclaré neutre le reste : le seuil est une aide, pas un filtre."""
        content = "# B\n\n" + " ".join(["mot"] * 500)
        assert ChunkingService.is_structural_container("A > B", content, has_descendants=True, origin=ContainerOrigin.DECLARED) is True
        assert ChunkingService.is_structural_container("A > B", content, has_descendants=True) is False

    def test_declared_origin_overrides_the_absence_of_descendants(self) -> None:
        assert ChunkingService.is_structural_container("A > B", "Un contenu de cours tout à fait substantiel.", has_descendants=False, origin=ContainerOrigin.DECLARED) is True
        assert ChunkingService.is_structural_container("A > B", "Un contenu de cours tout à fait substantiel.", has_descendants=False) is False

    def test_declared_origin_still_requires_a_heading_path(self) -> None:
        assert ChunkingService.is_structural_container(None, "Un contenu.", has_descendants=True, origin=ContainerOrigin.DECLARED) is False
        assert ChunkingService.is_structural_container("", "Un contenu.", has_descendants=True, origin=ContainerOrigin.DECLARED) is False


class TestFlagStructuralContainers:
    def test_declared_addresses_are_materialized_on_every_covered_chunk(self) -> None:
        chunks = [
            _chunk("Cours > Ch1", "# Ch1\n\n" + " ".join(["mot"] * 100)),
            _chunk("Cours > Ch1 > 1.1", "# 1.1\n\n" + " ".join(["mot"] * 100)),
            _chunk("Cours > Ch2", "# Ch2\n\n" + " ".join(["mot"] * 100)),
        ]
        ChunkingService.flag_structural_containers(chunks, declared_addresses=["heading:Cours > Ch1"])
        assert chunks[0]["is_structural_container"] is True
        assert chunks[0]["container_origin"] == "declared"
        assert chunks[1]["is_structural_container"] is True
        assert chunks[1]["container_origin"] == "declared"
        assert chunks[2]["is_structural_container"] is False
        assert chunks[2]["container_origin"] is None

    def test_derived_containers_are_marked_derived_and_leaves_have_no_origin(self) -> None:
        chunks = [
            _chunk("Cours > Ch1", "# Ch1\n\nSix mots ici."),
            _chunk("Cours > Ch1 > 1.1", "# 1.1\n\n" + " ".join(["mot"] * 60)),
        ]
        ChunkingService.flag_structural_containers(chunks)
        assert chunks[0]["is_structural_container"] is True
        assert chunks[0]["container_origin"] == "derived"
        assert chunks[1]["is_structural_container"] is False
        assert chunks[1]["container_origin"] is None

    def test_a_declared_region_stops_being_derived(self) -> None:
        """Une région déclarée n'est pas « en plus » dérivée : l'axe porte une cause, pas un or."""
        chunks = [_chunk("A > B", "# B\n\nSix mots ici."), _chunk("A > B > 1", "# 1\n\n" + " ".join(["mot"] * 60))]
        ChunkingService.flag_structural_containers(chunks, declared_addresses=["node:A > B"])
        assert chunks[0]["container_origin"] == "declared"

    def test_reingestion_reevaluates_the_declaration(self) -> None:
        """Le drapeau n'est jamais figé : un appel sans déclaration rend le conteneur dérivé."""
        chunks = [_chunk("A > B", "# B\n\nSix mots ici."), _chunk("A > B > 1", "# 1\n\n" + " ".join(["mot"] * 60))]
        ChunkingService.flag_structural_containers(chunks, declared_addresses=["node:A > B"])
        assert chunks[0]["container_origin"] == "declared"
        ChunkingService.flag_structural_containers(chunks)
        assert chunks[0]["container_origin"] == "derived"

    def test_ignores_a_node_address_that_matches_nothing(self) -> None:
        chunks = [_chunk("A > B", "# B\n\n" + " ".join(["mot"] * 60))]
        ChunkingService.flag_structural_containers(chunks, declared_addresses=["node:Absent > X"])
        assert chunks[0]["is_structural_container"] is False


class TestContainerCandidates:
    def test_suggests_every_title_that_only_serves_as_a_parent(self) -> None:
        chunks = [
            _chunk("Cours > Ch1", "# Ch1\n\n" + " ".join(["mot"] * 100)),
            _chunk("Cours > Ch1 > 1.1", "# 1.1\n\n" + " ".join(["mot"] * 100)),
        ]
        assert ChunkingService.container_candidates(chunks) == ["Cours", "Cours > Ch1"]

    def test_suggests_a_maigre_parent_too(self) -> None:
        """Le seuil de 25 mots aide à proposer ; il ne doit pas rendre la suggestion muette."""
        chunks = [
            _chunk("Cours > Ch1", "# Ch1\n\nSix mots ici."),
            _chunk("Cours > Ch1 > 1.1", "# 1.1\n\n" + " ".join(["mot"] * 100)),
        ]
        assert ChunkingService.container_candidates(chunks) == ["Cours", "Cours > Ch1"]

    def test_does_not_suggest_a_leaf(self) -> None:
        chunks = [_chunk("Cours", "# Cours\n\n" + " ".join(["mot"] * 100))]
        assert ChunkingService.container_candidates(chunks) == []

    def test_excludes_a_region_already_declared(self) -> None:
        chunks = [
            _chunk("Cours > Ch1", "# Ch1\n\n" + " ".join(["mot"] * 100)),
            _chunk("Cours > Ch1 > 1.1", "# 1.1\n\n" + " ".join(["mot"] * 100)),
        ]
        assert ChunkingService.container_candidates(chunks, declared_addresses=["heading:Cours > Ch1"]) == ["Cours"]

    def test_own_content_words_excludes_the_heading_lines(self) -> None:
        """Un titre long ne doit pas faire passer un fragment maigre au-dessus du seuil."""
        assert ChunkingService.own_content_words("# Titre" + chr(10) + chr(10) + "Six mots ici.") == 3
        assert ChunkingService.own_content_words("# Titre") == 0
        assert ChunkingService.own_content_words(None) == 0

    def test_the_threshold_is_judged_on_own_words_only(self) -> None:
        maigre = "# Titre" + chr(10) + chr(10) + " ".join(["mot"] * 24)
        riche = "# Titre" + chr(10) + chr(10) + " ".join(["mot"] * 25)
        assert ChunkingService.is_structural_container("Cours", maigre, has_descendants=True) is True
        assert ChunkingService.is_structural_container("Cours", riche, has_descendants=True) is False

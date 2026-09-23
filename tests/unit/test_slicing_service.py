"""Tests unitaires purs pour le SlicingService de la Batch Factory."""

import pytest

from ankiforge.services.batch.slicing_service import (
    SliceUnit,
    SlicingMode,
    SlicingService,
)

pytestmark = pytest.mark.unit


def test_slice_by_headings_basic() -> None:
    content = """# Chapitre 1 : Introduction

Ceci est le premier paragraphe du chapitre introductif qui explique les principes fondamentaux de la cellule vivante
et son fonctionnement général. Nous abordons les concepts de base nécessaires pour la suite du cours de biologie moléculaire.

# Chapitre 2 : La Membrane Cellulaire

La membrane plasmique sépare le milieu intracellulaire du milieu extracellulaire.
Elle est composée d'une bicouche lipidique de phospholipides amphiphiles et de protéines transmembranaires
diverses qui assurent le transport actif et passif des ions et molécules.
"""
    slices = SlicingService.slice_by_headings(content, min_words=20)
    assert len(slices) == 2
    assert slices[0].title == "Chapitre 1 : Introduction"
    assert "Chapitre 1 : Introduction" in slices[0].heading_path
    assert slices[0].words_estimate > 20
    assert slices[0].tokens_estimate > slices[0].words_estimate

    assert slices[1].title == "Chapitre 2 : La Membrane Cellulaire"
    assert "Chapitre 2 : La Membrane Cellulaire" in slices[1].heading_path
    assert "bicouche lipidique" in slices[1].content


def test_slice_by_headings_merges_small_sections() -> None:
    content = """# Grand Titre

Texte principal du grand titre avec suffisamment de matière pour faire une belle tranche pédagogique d'étude.

## Sous-titre microscopique

Deux mots seulement.

## Autre sous-titre minuscule

Encore trois mots.
"""
    # Avec min_words=30, les sous-sections minuscules doivent être fusionnées
    slices = SlicingService.slice_by_headings(content, min_words=30)
    assert len(slices) == 1
    assert "Deux mots seulement" in slices[0].content
    assert "Encore trois mots" in slices[0].content


def test_slice_by_tokens_soft_boundaries_and_overlap() -> None:
    # Créer un texte de plusieurs paragraphes
    para = (
        "Le système cardiovasculaire transporte le sang, les nutriments, les gaz respiratoires, "
        "les hormones et les déchets métaboliques à travers tout l'organisme humain. "
        "Le cœur agit comme une pompe musculaire centrale constituée de quatre cavités distinctes. "
    )
    long_content = "\n\n".join([f"Paragraphe {i}. {para}" for i in range(1, 25)])

    slices = SlicingService.slice_by_tokens(long_content, target_tokens=300, overlap_tokens=30)
    assert len(slices) >= 2
    for s in slices:
        assert isinstance(s, SliceUnit)
        assert s.words_estimate > 0
        assert s.tokens_estimate > 0
        # Vérification qu'on ne coupe pas sur un mot tronqué
        assert not s.content.endswith("-")


def test_slice_by_pages_markers() -> None:
    content = """{1}-----
Contenu de la première page du polycopié d'exercices.

{2}-----
Contenu de la deuxième page sur les équations différentielles.

{3}-----
Contenu de la troisième page avec les corrigés détaillés.

{4}-----
Contenu de la quatrième page sur les séries de Fourier.

{5}-----
Contenu de la cinquième page finale.
"""
    slices = SlicingService.slice_by_pages(content, pages_per_slice=2)
    assert len(slices) == 3
    assert slices[0].title == "Pages 1 à 2"
    assert slices[0].start_page == 1
    assert slices[0].end_page == 2
    assert "première page" in slices[0].content

    assert slices[1].title == "Pages 3 à 4"
    assert slices[1].start_page == 3
    assert slices[1].end_page == 4

    assert slices[2].title == "Page 5"
    assert slices[2].start_page == 5
    assert slices[2].end_page == 5


def test_get_outline_tree() -> None:
    content = """# Introduction
Contenu intro
## Historique
Contenu historique
# Chapitre 1
Contenu chap 1
"""
    outline = SlicingService.get_outline_tree(content)
    assert len(outline) == 3
    assert outline[0]["title"] == "Introduction"
    assert outline[0]["level"] == 1
    assert outline[1]["title"] == "Historique"
    assert outline[1]["level"] == 2
    assert outline[2]["title"] == "Chapitre 1"
    assert outline[2]["level"] == 1


def test_slice_document_dispatcher() -> None:
    content = """# Section 1
Contenu première section avec un peu de texte descriptif pour les tests.

# Section 2
Contenu deuxième section également bien fournie pour tester les différents modes.
"""
    h_slices = SlicingService.slice_document(content, mode=SlicingMode.HEADINGS, min_words=10)
    assert len(h_slices) == 2

    t_slices = SlicingService.slice_document(content, mode=SlicingMode.TOKENS, target_tokens=100)
    assert len(t_slices) >= 1

    p_slices = SlicingService.slice_document(content, mode=SlicingMode.PAGES)
    assert len(p_slices) >= 1


def test_slice_by_headings_hierarchical_max_depth() -> None:
    doc = """# Chapitre 1 : Les Fondations
Introduction du premier chapitre détaillant l'ensemble des concepts fondamentaux nécessaires à la compréhension de l'ouvrage.

## Section 1.1 : Premier Pilier
Développement approfondi du premier pilier contenant de nombreux détails techniques essentiels pour la pratique.

### Sous-section 1.1.1 : Détail Atomique
Précisions complémentaires sur les cas limites et les applications réelles du pilier étudié dans cette partie.

## Section 1.2 : Deuxième Pilier
Analyse complète du deuxième pilier avec des exemples concrets et des cas cliniques représentatifs.

# Chapitre 2 : Les Applications Pratiques
Deuxième grand chapitre traitant de la mise en oeuvre opérationnelle de tous les concepts étudiés précédemment.

## Section 2.1 : Mise en Pratique
Exemples pratiques commentés étape par étape pour guider l'étudiant dans sa démarche d'apprentissage.
"""
    # 1. max_depth=1 (COARSE / Large) : Seulement les 2 H1, englobant tous leurs sous-titres H2 et H3
    coarse_slices = SlicingService.slice_by_headings(doc, max_depth=1, min_words=10)
    assert len(coarse_slices) == 2
    assert coarse_slices[0].title == "Chapitre 1 : Les Fondations"
    assert "Section 1.1 : Premier Pilier" in coarse_slices[0].content
    assert "Sous-section 1.1.1 : Détail Atomique" in coarse_slices[0].content
    assert "Section 1.2 : Deuxième Pilier" in coarse_slices[0].content
    assert coarse_slices[1].title == "Chapitre 2 : Les Applications Pratiques"
    assert "Section 2.1 : Mise en Pratique" in coarse_slices[1].content

    # 2. max_depth=2 (BALANCED / Équilibré) : H1 et H2 découpés, H3 englobé dans Section 1.1
    balanced_slices = SlicingService.slice_by_headings(doc, max_depth=2, min_words=10)
    # Chapitre 1 (intro), Section 1.1 (incluant Sous-section 1.1.1), Section 1.2, Chapitre 2, Section 2.1
    assert len(balanced_slices) == 5
    sec_1_1 = next(s for s in balanced_slices if "Section 1.1" in s.title)
    assert "Sous-section 1.1.1 : Détail Atomique" in sec_1_1.content

    # 3. max_depth=3 (FINE / Fin) : Sous-section 1.1.1 devient sa propre tranche
    fine_slices = SlicingService.slice_by_headings(doc, max_depth=3, min_words=10)
    assert len(fine_slices) == 6
    sub_1_1_1 = next(s for s in fine_slices if "Sous-section 1.1.1" in s.title)
    assert "Précisions complémentaires sur les cas limites" in sub_1_1_1.content


def test_granularity_presets() -> None:
    from ankiforge.services.batch.slicing_service import GranularityLevel

    # Headings presets
    depth, min_w = SlicingService.get_headings_preset(GranularityLevel.COARSE)
    assert depth == 1 and min_w == 100
    depth, min_w = SlicingService.get_headings_preset(GranularityLevel.BALANCED)
    assert depth == 2 and min_w == 50
    depth, min_w = SlicingService.get_headings_preset(GranularityLevel.FINE)
    assert depth == 3 and min_w == 30

    # Tokens presets
    t_tokens, overlap = SlicingService.get_tokens_preset(GranularityLevel.COARSE)
    assert t_tokens == 3500 and overlap == 200
    t_tokens, overlap = SlicingService.get_tokens_preset(GranularityLevel.FINE)
    assert t_tokens == 1000 and overlap == 100

    # Pages presets
    assert SlicingService.get_pages_preset(GranularityLevel.COARSE) == 10
    assert SlicingService.get_pages_preset(GranularityLevel.BALANCED) == 5
    assert SlicingService.get_pages_preset(GranularityLevel.FINE) == 1

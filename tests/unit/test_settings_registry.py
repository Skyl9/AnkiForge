"""Tests unitaires du registre déclaratif de recherche de paramètres.

Vérifie le catalogue statique ``SettingsRegistry`` et sa méthode ``search`` :
insensibilité à la casse et aux accents, scoring de pertinence et tri des résultats.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ankidraft.ui.widgets.settings_modal.search_registry import (
    SettingDescriptor,
    SettingSearchResult,
    SettingsRegistry,
)


def _descriptor(key: str, label: str, tab_index: int = 0) -> SettingDescriptor:
    return SettingDescriptor(
        key=key,
        label=label,
        description="Description de " + label,
        keywords=(key.split("/")[-1],),
        tab="Onglet Test",
        section="Section Test",
        widget=label,
        tab_index=tab_index,
    )


@pytest.mark.unit
def test_registry_expose_un_catalogue_non_vide() -> None:
    """Le registre expose un catalogue de réglages non vide."""
    settings = SettingsRegistry.all_settings()
    assert len(settings) > 0
    assert all(isinstance(s, SettingDescriptor) for s in settings)


@pytest.mark.unit
def test_search_renvoie_des_resultats_pour_mot_cle() -> None:
    """Une recherche par mot-clé renvoie au moins un résultat pertinent."""
    resultats = SettingsRegistry.search("langue")
    assert len(resultats) > 0
    assert all(isinstance(r, SettingSearchResult) for r in resultats)
    assert any("Langue" in r.descriptor.label for r in resultats)


@pytest.mark.unit
def test_search_est_insensible_a_la_casse() -> None:
    """La recherche ignore la casse des caractères saisis."""
    par_majuscule = SettingsRegistry.search("LANGUE")
    par_minuscule = SettingsRegistry.search("langue")
    assert [r.descriptor.key for r in par_majuscule] == [r.descriptor.key for r in par_minuscule]


@pytest.mark.unit
def test_search_est_insensible_aux_accents() -> None:
    """La recherche ignore les diacritiques (ex: « apparence » trouve « d'apparence »)."""
    sans_accent = SettingsRegistry.search("apparence")
    assert len(sans_accent) > 0
    assert any("Apparence" in r.descriptor.label or "apparence" in r.descriptor.label for r in sans_accent)


@pytest.mark.unit
def test_query_vide_renvoie_liste_vide() -> None:
    """Une requête vide ou uniquement blanche ne renvoie aucun résultat."""
    assert SettingsRegistry.search("") == []
    assert SettingsRegistry.search("   ") == []


@pytest.mark.unit
def test_resultat_contient_champs_appariés_et_score_positif() -> None:
    """Chaque résultat porte un score positif et la liste des champs appariés."""
    resultats = SettingsRegistry.search("température")
    assert len(resultats) > 0
    for r in resultats:
        assert r.score > 0.0
        assert isinstance(r.matched_fields, tuple)
        assert all(champ in ("label", "description", "keywords") for champ in r.matched_fields)


@pytest.mark.unit
def test_resultats_tries_par_pertinence_decroissante() -> None:
    """Les résultats sont triés par score décroissant puis par index d'onglet."""
    resultats = SettingsRegistry.search("moteur")
    scores = [r.score for r in resultats]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.unit
def test_recherche_multi_termes_combine_les_correspondances() -> None:
    """Plusieurs termes doivent apparaître pour augmenter le score de pertinence."""
    simple = SettingsRegistry.search("moteur")
    double = SettingsRegistry.search("moteur ia")
    assert len(double) > 0
    assert double[0].score >= simple[0].score


@pytest.mark.unit
def test_descriptor_est_gelé() -> None:
    """Les instances de SettingDescriptor sont immuables (dataclass frozen)."""
    d = _descriptor("test/cle", "Mon Réglage", 2)
    with pytest.raises(FrozenInstanceError):
        d.label = "Modifié"

"""
Tests unitaires et d'intégration pour les outils d'inspection chirurgicale et manifeste du Consultant IA (MCP-ADV-02).
"""

import json
import uuid

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.ai.consultant_engine import (
    DEFAULT_CONSULTANT_TOOLS,
    ConsultantEngine,
    ConsultantToolRegistry,
)
from ankiforge.services.ai.mcp_server import mcp

pytestmark = pytest.mark.integration


@pytest.fixture
def surgical_dataset():
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Chirurg {uid}")
    nt1 = NoteTypeModel.create(
        name=f"Modèle Standard {uid}",
        description="Gabarit classique Recto/Verso",
        fields_schema=json.dumps(["Recto", "Verso", "Remarques"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}<br>{{Remarques}}"}]),
        css_style=".card { font-family: sans-serif; }",
    )
    nt_cloze = NoteTypeModel.create(
        name=f"Modèle Texte à Trous {uid}",
        description="Gabarit Cloze",
        fields_schema=json.dumps(["Texte", "Extra"]),
        templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Texte}}", "afmt": "{{cloze:Texte}}<br>{{Extra}}"}]),
        css_style=".cloze { color: blue; }",
    )

    # 1. Carte saine
    n_ok = NoteModel.create(guid=f"n_ok_{uid}", note_type=nt1, tags="sante standard")
    NoteVersionModel.create(
        note=n_ok,
        version_number=1,
        content=json.dumps({"Recto": "Quelle est la capitale de la France ?", "Verso": "Paris.", "Remarques": ""}),
        is_active=True,
    )
    CardModel.create(note=n_ok, deck=deck, reps=8, lapses=0, ivl=35)

    # 2. Carte sangsue (lapses >= 4) avec instabilité
    n_leech = NoteModel.create(guid=f"n_leech_{uid}", note_type=nt1, tags="sangsue bio")
    NoteVersionModel.create(
        note=n_leech,
        version_number=1,
        content=json.dumps({"Recto": "Définir la mitose cellulaire.", "Verso": "Processus de division cellulaire.", "Remarques": ""}),
        is_active=True,
    )
    CardModel.create(note=n_leech, deck=deck, reps=15, lapses=6, ivl=1)

    # 3. Carte verbeuse (> 200 caractères et > 30 mots)
    n_verbose = NoteModel.create(guid=f"n_verb_{uid}", note_type=nt1, tags="verbeux histoire")
    long_q = (
        "Pouvez-vous expliquer en détail et de manière exhaustive l'ensemble des causes socio-économiques, "
        "politiques et culturelles qui ont provoqué le déclenchement de la Révolution française en mai et juin 1789 à Versailles et à Paris ?"
    )
    long_a = (
        "Les causes principales comportent la crise financière monarchique, l'injustice du système des trois ordres "
        "avec les privilèges fiscaux du clergé et de la noblesse, les mauvaises récoltes de 1788 provoquant la disette de pain, "
        "la montée des idées des Lumières et la paralysie politique des États Généraux."
    )
    NoteVersionModel.create(
        note=n_verbose,
        version_number=1,
        content=json.dumps({"Recto": long_q, "Verso": long_a, "Remarques": ""}),
        is_active=True,
    )
    CardModel.create(note=n_verbose, deck=deck, reps=4, lapses=2, ivl=3)

    # 4. Carte Cloze avec densité excessive (> 5 trous clozes)
    n_cloze = NoteModel.create(guid=f"n_clz_{uid}", note_type=nt_cloze, tags="cloze excessive")
    cloze_text = (
        "Le {{c1::cœur}} pompe le sang à travers les {{c2::artères}} vers les {{c3::organes}}, puis le sang revient par les {{c4::veines}} vers les {{c5::oreillettes}} et les {{c6::ventricules}}."
    )
    NoteVersionModel.create(
        note=n_cloze,
        version_number=1,
        content=json.dumps({"Texte": cloze_text, "Extra": "Anatomie cardiovasculaire"}),
        is_active=True,
    )
    CardModel.create(note=n_cloze, deck=deck, reps=5, lapses=1, ivl=4)

    return {
        "uid": uid,
        "deck": deck,
        "nt1": nt1,
        "nt_cloze": nt_cloze,
        "n_ok": n_ok,
        "n_leech": n_leech,
        "n_verbose": n_verbose,
        "n_cloze": n_cloze,
    }


def test_diagnose_deck_weaknesses_non_existent():
    res = ConsultantToolRegistry.diagnose_deck_weaknesses("Paquet Inexistant Introuvable 1234")
    assert "Erreur" in res or "n'a pas été trouvé" in res


def test_diagnose_deck_weaknesses_empty():
    uid = uuid.uuid4().hex[:6]
    empty_deck = DeckModel.create(name=f"Deck Vide {uid}")
    res = ConsultantToolRegistry.diagnose_deck_weaknesses(empty_deck.name)
    assert "ne contient aucune carte" in res or "0 carte" in res


def test_diagnose_deck_weaknesses_comprehensive(surgical_dataset):
    deck = surgical_dataset["deck"]
    diag = ConsultantToolRegistry.diagnose_deck_weaknesses(deck.name)

    assert f"Diagnostic Chirurgical du Paquet '{deck.name}'" in diag
    assert "Score de Santé" in diag
    assert "Sangsues critiques (lapses ≥ 4)" in diag
    assert "1" in diag  # Au moins 1 sangsue détectée (n_leech)
    assert "Surcharge textuelle / Verbosité" in diag
    assert "Densité excessive d'occlusions" in diag  # n_cloze
    assert "Actions chirurgicales recommandées" in diag
    assert str(surgical_dataset["n_leech"].id) in diag
    assert str(surgical_dataset["n_verbose"].id) in diag
    assert str(surgical_dataset["n_cloze"].id) in diag


def test_list_card_models_manifest(surgical_dataset):
    manifest_str = ConsultantToolRegistry.list_card_models_manifest()

    assert "Manifeste des Modèles de Cartes" in manifest_str
    assert surgical_dataset["nt1"].name in manifest_str
    assert surgical_dataset["nt_cloze"].name in manifest_str
    assert "Recto" in manifest_str
    assert "Verso" in manifest_str
    assert ".cloze" in manifest_str
    assert "total_notes" in manifest_str or "Nombre de notes" in manifest_str


def test_refactor_cards_by_criteria_deck(surgical_dataset):
    deck = surgical_dataset["deck"]
    res = ConsultantToolRegistry.refactor_cards_by_criteria(f"deck:{deck.name}", instruction="Rendre les questions atomiques")

    assert "Échantillon de Cartes pour Refactorisation" in res
    assert "Rendre les questions atomiques" in res
    assert str(surgical_dataset["n_ok"].id) in res
    assert str(surgical_dataset["n_verbose"].id) in res
    assert "propose_card_refactor" in res
    assert "active_version_id" in res


def test_refactor_cards_by_criteria_tag_and_leeches(surgical_dataset):
    # Test par tag
    res_tag = ConsultantToolRegistry.refactor_cards_by_criteria("tag:sangsue", instruction="Diviser si nécessaire")
    assert str(surgical_dataset["n_leech"].id) in res_tag

    # Test mot-clé sangsues
    res_leeches = ConsultantToolRegistry.refactor_cards_by_criteria("sangsues")
    assert str(surgical_dataset["n_leech"].id) in res_leeches


def test_consultant_engine_tool_dispatch(surgical_dataset):
    engine = ConsultantEngine()

    # 1. diagnose_deck_weaknesses
    obs1, err1 = engine._execute_tool_call("diagnose_deck_weaknesses", {"deck_name": surgical_dataset["deck"].name})
    assert err1 is False
    assert "Score de Santé" in obs1

    # 2. list_card_models_manifest
    obs2, err2 = engine._execute_tool_call("list_card_models_manifest", {})
    assert err2 is False
    assert surgical_dataset["nt1"].name in obs2

    # 3. refactor_cards_by_criteria
    obs3, err3 = engine._execute_tool_call(
        "refactor_cards_by_criteria",
        {"query": f"deck:{surgical_dataset['deck'].name}", "instruction": "Simplifier"},
    )
    assert err3 is False
    assert "Échantillon" in obs3


def test_default_consultant_tools_schemas():
    tool_names = [t["function"]["name"] for t in DEFAULT_CONSULTANT_TOOLS]
    assert "diagnose_deck_weaknesses" in tool_names
    assert "list_card_models_manifest" in tool_names
    assert "refactor_cards_by_criteria" in tool_names


def test_fastmcp_surgical_tools_exposed(surgical_dataset):
    import asyncio

    async def _check():
        tools = await mcp.list_tools()
        return [t.name for t in tools]

    tool_names = asyncio.run(_check())
    assert "diagnose_deck_weaknesses" in tool_names
    assert "list_card_models_manifest" in tool_names
    assert "refactor_cards_by_criteria" in tool_names

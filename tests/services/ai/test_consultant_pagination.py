"""
Tests unitaires pour la pagination des outils du Consultant IA et MCP.
Vérifie le respect des arguments `limit` et `offset` sur query_peewee, find_cards_by_content,
et get_cards_by_deck_or_tag, ainsi que la conformité des schémas DEFAULT_CONSULTANT_TOOLS.
"""

import json
import re
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
    ConsultantToolRegistry,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def sample_paginated_deck():
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck_Paging_{uid}")
    nt = NoteTypeModel.create(
        name=f"NT_Paging_{uid}",
        fields_schema='["Front", "Back"]',
        templates="[]",
        css_style="",
    )

    notes = []
    cards = []
    for i in range(25):
        n = NoteModel.create(guid=f"g_{uid}_{i:02d}", note_type=nt, tags=f"tag_page_{uid} index_{i}")
        NoteVersionModel.create(
            note=n,
            version_number=1,
            content=json.dumps({"Front": f"Question cardiologie {i}", "Back": f"Réponse détail {i}"}),
            is_active=True,
        )
        c = CardModel.create(note=n, deck=deck, template_index=0)
        notes.append(n)
        cards.append(c)

    return {"uid": uid, "deck": deck, "nt": nt, "notes": notes, "cards": cards}


def test_query_peewee_pagination(sample_paginated_deck):
    table_name = NoteModel._meta.table_name
    sql = f"SELECT id FROM {table_name} WHERE note_type_id = {sample_paginated_deck['nt'].id} ORDER BY id ASC"

    # Page 1 : limit=10, offset=0
    res1 = ConsultantToolRegistry.query_peewee(sql, limit=10, offset=0)
    assert "1 à 10 sur 25 total" in res1
    assert "limit=10, offset=0" in res1
    assert "offset=10 pour la page suivante" in res1

    # Page 2 : limit=10, offset=10
    res2 = ConsultantToolRegistry.query_peewee(sql, limit=10, offset=10)
    assert "11 à 20 sur 25 total" in res2
    assert "limit=10, offset=10" in res2
    assert "offset=20 pour la page suivante" in res2

    # Page 3 : limit=10, offset=20
    res3 = ConsultantToolRegistry.query_peewee(sql, limit=10, offset=20)
    assert "21 à 25 sur 25 total" in res3
    assert "page suivante" not in res3


def test_find_cards_by_content_pagination(sample_paginated_deck):
    deck_name = sample_paginated_deck["deck"].name

    def _extract_cards(text: str) -> list[dict]:
        m = re.search(r"(\[[\s\S]+\])", text)
        return json.loads(m.group(1)) if m else []

    # Page 1 : limit=8, offset=0
    res1 = ConsultantToolRegistry.find_cards_by_content(query="cardiologie", deck_name=deck_name, limit=8, offset=0)
    cards1 = _extract_cards(res1)
    assert len(cards1) == 8

    # Page 2 : limit=8, offset=8
    res2 = ConsultantToolRegistry.find_cards_by_content(query="cardiologie", deck_name=deck_name, limit=8, offset=8)
    cards2 = _extract_cards(res2)
    assert len(cards2) == 8

    # Page 3 : limit=8, offset=16
    res3 = ConsultantToolRegistry.find_cards_by_content(query="cardiologie", deck_name=deck_name, limit=8, offset=16)
    cards3 = _extract_cards(res3)
    assert len(cards3) == 8

    # Page 4 : limit=8, offset=24
    res4 = ConsultantToolRegistry.find_cards_by_content(query="cardiologie", deck_name=deck_name, limit=8, offset=24)
    cards4 = _extract_cards(res4)
    assert len(cards4) == 1

    ids1 = {c["note_id"] for c in cards1}
    ids2 = {c["note_id"] for c in cards2}
    ids3 = {c["note_id"] for c in cards3}
    ids4 = {c["note_id"] for c in cards4}
    assert ids1.isdisjoint(ids2)
    assert ids2.isdisjoint(ids3)
    assert ids3.isdisjoint(ids4)


def test_get_cards_by_deck_or_tag_pagination(sample_paginated_deck):
    uid = sample_paginated_deck["uid"]
    tag = f"tag_page_{uid}"

    def _extract_cards(text: str) -> list[dict]:
        m = re.search(r"(\[[\s\S]+\])", text)
        return json.loads(m.group(1)) if m else []

    # Page 1
    res1 = ConsultantToolRegistry.get_cards_by_deck_or_tag(tag=tag, limit=12, offset=0)
    cards1 = _extract_cards(res1)
    assert len(cards1) == 12

    # Page 2
    res2 = ConsultantToolRegistry.get_cards_by_deck_or_tag(tag=tag, limit=12, offset=12)
    cards2 = _extract_cards(res2)
    assert len(cards2) == 12

    # Page 3
    res3 = ConsultantToolRegistry.get_cards_by_deck_or_tag(tag=tag, limit=12, offset=24)
    cards3 = _extract_cards(res3)
    assert len(cards3) == 1

    ids1 = {c["note_id"] for c in cards1}
    ids2 = {c["note_id"] for c in cards2}
    assert ids1.isdisjoint(ids2)


def test_tool_schemas_pagination_and_apply_patch():
    """Vérifie la conformité des schémas DEFAULT_CONSULTANT_TOOLS pour l'orchestrateur IA."""
    tools_by_name = {t["function"]["name"]: t["function"] for t in DEFAULT_CONSULTANT_TOOLS}

    # 1. query_peewee
    qp = tools_by_name["query_peewee"]
    props = qp["parameters"]["properties"]
    assert "limit" in props
    assert "offset" in props
    assert props["limit"]["type"] == "integer"
    assert props["offset"]["type"] == "integer"

    # 2. find_cards_by_content
    fc = tools_by_name["find_cards_by_content"]
    assert "limit" in fc["parameters"]["properties"]
    assert "offset" in fc["parameters"]["properties"]

    # 3. get_cards_by_deck_or_tag
    gc = tools_by_name["get_cards_by_deck_or_tag"]
    assert "limit" in gc["parameters"]["properties"]
    assert "offset" in gc["parameters"]["properties"]

    # 4. apply_patch
    assert "apply_patch" in tools_by_name
    ap = tools_by_name["apply_patch"]
    ap_props = ap["parameters"]["properties"]
    assert "patch_json" in ap_props
    assert "patch_type" in ap_props
    assert "target_id" in ap_props

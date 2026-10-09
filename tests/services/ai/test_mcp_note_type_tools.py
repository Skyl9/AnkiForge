"""Tests d'intégration pour les outils MCP de gestion des types de note via la surface mcp.call_tool().

Couvre :
- create_note_type (proposer, collision, validation, application two-phase)
- change_note_type (proposer, remap, préservation SRS, atomicité, two-phase)
- get_notes_by_model (filtre type de note, descente sous-paquets '::', pagination)
- audit_note_type_conformity (règles fermées, déterminisme, pagination)
- preview_card_render (recto/verso, {{FrontSide}}, CSS, surcharges)
"""

import asyncio
import json

import pytest

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.services.ai.mcp_server import mcp

pytestmark = pytest.mark.integration


@pytest.fixture
def test_setup():
    with db.atomic():
        deck_parent = DeckModel.create(name="Sciences")
        deck_sub = DeckModel.create(name="Sciences::Biologie", parent_deck=deck_parent)
        deck_other = DeckModel.create(name="Histoire")

        nt_med = NoteTypeModel.create(
            name="Medical Model MCP",
            fields_schema=json.dumps(["Symptome", "Diagnostic", "Traitement", "Audio"]),
            templates=json.dumps(
                [
                    {"name": "Reconnaissance", "qfmt": "{{Symptome}}", "afmt": "{{FrontSide}}<hr>{{Diagnostic}}"},
                    {"name": "Traitement", "qfmt": "{{Diagnostic}}", "afmt": "{{FrontSide}}<hr>{{Traitement}}"},
                ]
            ),
            css_style=".card { color: #1e293b; font-size: 16px; }",
            description="Modèle pour tests médicaux",
        )

        nt_simple = NoteTypeModel.create(
            name="Simple Target MCP",
            fields_schema=json.dumps(["Front", "Back"]),
            templates=json.dumps(
                [
                    {"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr>{{Back}}"},
                ]
            ),
            css_style=".card { background: white; }",
        )

        # Note 1 dans sous-paquet avec SRS complet sur sa carte
        n1 = NoteModel.create(note_type=nt_med, tags="p1::cardio")
        n1.add_version(
            {
                "Symptome": "Douleur thoracique irradiant dans le bras gauche",
                "Diagnostic": "Infarctus du myocarde",
                "Traitement": "Coronarographie en urgence",
                "Audio": "[sound:ecg_bip.mp3]",
            },
            source="init",
        )
        c1 = CardModel.create(
            note=n1,
            deck=deck_sub,
            template_index=0,
            flags=2,
            is_suspended=False,
            ivl=90,
            reps=15,
            lapses=1,
            stability=45.2,
            difficulty=3.1,
            retrievability=0.95,
        )

        # Note 2 dans paquet parent avec violations pour audit
        n2 = NoteModel.create(note_type=nt_med, tags="p2::pneumo")
        n2.add_version(
            {
                "Symptome": "<span style='font-size:12px;'>Dyspnée aiguë</span>",
                "Diagnostic": "Embolie pulmonaire",
                "Traitement": "Embolie pulmonaire",  # doublon avec Diagnostic
                "Audio": "",  # champ vide
            },
            source="init",
        )
        c2 = CardModel.create(
            note=n2,
            deck=deck_parent,
            template_index=0,
            ivl=10,
            reps=3,
        )

        # Note 3 dans paquet Histoire avec un autre type de note
        n3 = NoteModel.create(note_type=nt_simple, tags="hist")
        n3.add_version({"Front": "1789", "Back": "Révolution"}, source="init")
        CardModel.create(note=n3, deck=deck_other, template_index=0)

    return {
        "deck_parent": deck_parent,
        "deck_sub": deck_sub,
        "deck_other": deck_other,
        "nt_med": nt_med,
        "nt_simple": nt_simple,
        "notes": [n1, n2, n3],
        "cards": [c1, c2],
    }


def _extract_text(tool_result) -> str:
    if hasattr(tool_result, "content") and tool_result.content:
        return tool_result.content[0].text
    return str(tool_result)


def test_mcp_create_note_type_flow():
    """Vérifie le cycle complet create_note_type -> patch pending -> preview_and_apply_patch -> BDD."""

    async def _run():
        model_name = "Vocabulaire Japonais MCP"
        fields = ["Kanji", "Kana", "Sens", "Exemple"]
        templates = [
            {"name": "Reconnaissance", "qfmt": "{{Kanji}}", "afmt": "{{FrontSide}}<hr>{{Kana}}<br>{{Sens}}"},
            {"name": "Production", "qfmt": "{{Sens}}", "afmt": "{{FrontSide}}<hr>{{Kanji}} ({{Kana}})"},
        ]
        css = ".card { font-family: 'Noto Sans JP'; }"
        desc = "Cartes de kanji et vocabulaire"

        # 1. Échec si champs invalides ou template référence champ inexistant
        bad_templates = [{"name": "C1", "qfmt": "{{Inexistant}}", "afmt": "{{Sens}}"}]
        res_bad = await mcp.call_tool(
            "create_note_type",
            {
                "name": model_name,
                "fields_json": json.dumps(fields),
                "templates_json": json.dumps(bad_templates),
            },
        )
        bad_data = json.loads(_extract_text(res_bad))
        assert bad_data["status"] == "error"
        assert "inexistant" in bad_data["message"].lower()

        # 2. Proposition valide
        res_prop = await mcp.call_tool(
            "create_note_type",
            {
                "name": model_name,
                "fields_json": json.dumps(fields),
                "templates_json": json.dumps(templates),
                "css": css,
                "description": desc,
                "on_conflict": "error",
            },
        )
        prop_data = json.loads(_extract_text(res_prop))
        assert prop_data["status"] == "staged_diff"
        assert "patch_id" in prop_data
        patch_id = prop_data["patch_id"]

        # Vérification qu'il n'existe PAS encore en base
        assert NoteTypeModel.get_or_none(NoteTypeModel.name == model_name) is None

        # 3. Application du patch via preview_and_apply_patch
        res_apply = await mcp.call_tool("preview_and_apply_patch", {"patch_id": patch_id})
        apply_data = json.loads(_extract_text(res_apply))
        assert apply_data["status"] == "applied"

        # Vérification en base SQLite
        created_nt = NoteTypeModel.get_or_none(NoteTypeModel.name == model_name)
        assert created_nt is not None
        assert created_nt.description == desc
        assert "Noto Sans JP" in created_nt.css_style
        loaded_flds = json.loads(created_nt.fields_schema)
        assert loaded_flds == fields

        # 4. Collision : tentative avec le même nom et on_conflict="error"
        res_conflict = await mcp.call_tool(
            "create_note_type",
            {
                "name": model_name,
                "fields_json": json.dumps(fields),
                "templates_json": json.dumps(templates),
                "on_conflict": "error",
            },
        )
        conflict_data = json.loads(_extract_text(res_conflict))
        assert conflict_data["status"] == "error"
        assert "existe déjà" in conflict_data["message"].lower()

    asyncio.run(_run())


def test_mcp_change_note_type_flow(test_setup):
    """Vérifie change_note_type -> patch pending -> preview_and_apply_patch -> préservation SRS."""

    async def _run():
        n1 = test_setup["notes"][0]
        c1 = test_setup["cards"][0]
        nt_target = test_setup["nt_simple"]

        c1_id = c1.id
        c1_ivl = c1.ivl
        c1_stability = c1.stability
        c1_reps = c1.reps

        # 1. Proposer la migration
        mapping = {"Symptome": "Front", "Diagnostic": "Back"}
        res_prop = await mcp.call_tool(
            "change_note_type",
            {
                "note_ids_json": json.dumps([n1.id]),
                "target_model": nt_target.name,
                "mapping_champs_json": json.dumps(mapping),
            },
        )
        prop_data = json.loads(_extract_text(res_prop))
        assert prop_data["status"] == "staged_diff"
        assert prop_data["count"] == 1
        patch_id = prop_data["patch_id"]

        # Note toujours sur l'ancien modèle avant validation
        assert NoteModel.get_by_id(n1.id).note_type.id == test_setup["nt_med"].id

        # 2. Validation et application
        res_apply = await mcp.call_tool("preview_and_apply_patch", {"patch_id": patch_id})
        apply_data = json.loads(_extract_text(res_apply))
        assert apply_data["status"] == "applied"
        assert apply_data["count"] == 1

        # Vérification SRS et cartes préservées
        reloaded_c1 = CardModel.get_by_id(c1_id)
        assert reloaded_c1.ivl == c1_ivl
        assert reloaded_c1.stability == c1_stability
        assert reloaded_c1.reps == c1_reps
        assert reloaded_c1.note.id == n1.id

        # Vérification du type de note et du contenu remappé
        reloaded_n1 = NoteModel.get_by_id(n1.id)
        assert reloaded_n1.note_type.id == nt_target.id
        active_v = reloaded_n1.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
        assert active_v is not None
        v_data = json.loads(active_v.content)
        assert "Douleur thoracique" in v_data["Front"]
        assert "Infarctus" in v_data["Back"]

    asyncio.run(_run())


def test_mcp_get_notes_by_model(test_setup):
    """Vérifie get_notes_by_model avec filtre de type de note, sous-paquets et pagination."""

    async def _run():
        nt_med = test_setup["nt_med"]

        # 1. Lister les notes de Medical Model MCP
        res = await mcp.call_tool(
            "get_notes_by_model",
            {
                "note_type_name": nt_med.name,
                "include_subdecks": True,
                "limit": 10,
                "offset": 0,
            },
        )
        text = _extract_text(res)
        assert "2 notes au total" in text
        assert "Douleur thoracique" in text
        assert "Dyspnée" in text
        # La note 3 (histoire) ne doit pas y figurer
        assert "Révolution" not in text

        # 2. Descente dans sous-paquet 'Sciences' (doit trouver Note 1 et Note 2)
        res_sub = await mcp.call_tool(
            "get_notes_by_model",
            {
                "note_type_name": nt_med.name,
                "deck_name": "Sciences",
                "include_subdecks": True,
            },
        )
        text_sub = _extract_text(res_sub)
        assert "2 notes au total" in text_sub

        # 3. Sans sous-paquets pour 'Sciences' (doit trouver uniquement Note 2)
        res_nosub = await mcp.call_tool(
            "get_notes_by_model",
            {
                "note_type_name": nt_med.name,
                "deck_name": "Sciences",
                "include_subdecks": False,
            },
        )
        text_nosub = _extract_text(res_nosub)
        assert "1 notes au total" in text_nosub
        assert "Dyspnée" in text_nosub
        assert "Douleur thoracique" not in text_nosub

        # 4. Pagination (limit=1, offset=1)
        res_pag = await mcp.call_tool(
            "get_notes_by_model",
            {
                "note_type_name": nt_med.name,
                "limit": 1,
                "offset": 1,
            },
        )
        text_pag = _extract_text(res_pag)
        assert "Affichage 2-2" in text_pag

    asyncio.run(_run())


def test_mcp_audit_note_type_conformity(test_setup):
    """Vérifie audit_note_type_conformity avec détection déterministe des violations."""

    async def _run():
        nt_med = test_setup["nt_med"]

        # 1. Audit complet
        res_raw = await mcp.call_tool(
            "audit_note_type_conformity",
            {
                "note_type_name": nt_med.name,
                "limit": 50,
                "offset": 0,
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["note_type_name"] == nt_med.name
        summary = data["summary"]
        assert summary["total_violations"] > 0
        assert summary["by_rule"]["inline_html"] >= 1
        assert summary["by_rule"]["field_duplicates"] >= 1
        assert summary["by_rule"]["empty_fields"] >= 1

        # 2. Audit filtré sur inline_html uniquement
        res_filtered = await mcp.call_tool(
            "audit_note_type_conformity",
            {
                "note_type_name": nt_med.name,
                "regles": "inline_html",
            },
        )
        data_f = json.loads(_extract_text(res_filtered))
        assert data_f["rules_evaluated"] == ["inline_html"]
        assert "inline_html" in data_f["summary"]["by_rule"]
        assert "empty_fields" not in data_f["summary"]["by_rule"]

    asyncio.run(_run())


def test_mcp_preview_card_render(test_setup):
    """Vérifie preview_card_render avec rendu de carte existante et surcharges."""

    async def _run():
        n1 = test_setup["notes"][0]
        nt_med = test_setup["nt_med"]

        # 1. Rendu courant
        res_raw = await mcp.call_tool(
            "preview_card_render",
            {
                "note_id": n1.id,
                "template_index": 0,
            },
        )
        data = json.loads(_extract_text(res_raw))
        assert data["note_id"] == n1.id
        assert data["note_type"] == nt_med.name
        assert "Douleur thoracique" in data["front_html"]
        assert "Infarctus du myocarde" in data["back_html"]
        assert "font-size: 16px" in data["css"]

        # 2. Rendu avec surcharges proposées
        res_override = await mcp.call_tool(
            "preview_card_render",
            {
                "note_id": n1.id,
                "fields_json": json.dumps({"Symptome": "Céphalée brutale en coup de tonnerre", "Diagnostic": "Hémorragie sous-arachnoïdienne"}),
                "template_index": 0,
            },
        )
        data_o = json.loads(_extract_text(res_override))
        assert "coup de tonnerre" in data_o["front_html"]
        assert "Hémorragie" in data_o["back_html"]

    asyncio.run(_run())

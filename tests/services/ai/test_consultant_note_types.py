"""
Tests unitaires pour la consultation, la refactorisation et l'analyse
des modèles de cartes (Note Types, champs dynamiques, CSS, templates) par le Consultant IA.
"""

from __future__ import annotations

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
from ankiforge.services.ai.consultant_engine import ConsultantToolRegistry
from ankiforge.ui.views.consultant_view.widgets.workspace_inspector_widget import WorkspaceInspectorWidget


@pytest.fixture
def custom_model_data():
    uid = uuid.uuid4().hex[:6]
    deck = DeckModel.create(name=f"Deck Modele {uid}")
    nt = NoteTypeModel.create(
        name=f"Medical {uid}",
        description="Modèle pour termes médicaux et pathologies",
        fields_schema=json.dumps(["Organe", "Symptôme", "Diagnostic", "Traitement"]),
        templates=json.dumps(
            [
                {"name": "Reconnaissance", "qfmt": "{{Organe}} - {{Symptôme}}", "afmt": "{{FrontSide}}<hr>{{Diagnostic}}"},
                {"name": "Traitement", "qfmt": "{{Diagnostic}}", "afmt": "{{FrontSide}}<hr>{{Traitement}}"},
            ]
        ),
        css_style=".card { font-family: sans-serif; color: #1e293b; background: #f8fafc; }",
    )

    note = NoteModel.create(guid=f"g_med_{uid}", note_type=nt, tags="medecine urgence")
    NoteVersionModel.create(
        note=note,
        version_number=1,
        content=json.dumps(
            {
                "Organe": "Cœur",
                "Symptôme": "Douleur thoracique irradiant dans le bras gauche",
                "Diagnostic": "Infarctus du myocarde",
                "Traitement": "Aspirine + Désobstruction coronaire en urgence",
            }
        ),
        is_active=True,
    )
    card1 = CardModel.create(note=note, deck=deck, template_index=0, reps=5, lapses=1, ivl=12)
    card2 = CardModel.create(note=note, deck=deck, template_index=1, reps=3, lapses=0, ivl=6)

    return {"uid": uid, "deck": deck, "nt": nt, "note": note, "card1": card1, "card2": card2}


def test_list_note_types(custom_model_data):
    nt = custom_model_data["nt"]
    res = ConsultantToolRegistry.list_note_types()
    assert "Modèles de cartes (Note Types) enregistrés" in res
    assert nt.name in res
    assert "Organe" in res
    assert "Diagnostic" in res


def test_get_note_type_details(custom_model_data):
    nt = custom_model_data["nt"]
    res = ConsultantToolRegistry.get_note_type_details(nt.name)
    assert f"Détails complets du Modèle '{nt.name}'" in res
    assert "Reconnaissance" in res
    assert "Traitement" in res
    assert "font-family: sans-serif" in res
    assert "Infarctus du myocarde" in res


def test_get_note_full_profile_360_with_dynamic_model(custom_model_data):
    note = custom_model_data["note"]
    nt = custom_model_data["nt"]
    profile = ConsultantToolRegistry.get_note_full_profile_360(note.id)

    assert f"Profil 360° de la Note #{note.id}" in profile
    assert nt.name in profile
    assert "Organe" in profile
    assert "Traitement" in profile
    assert "Infarctus du myocarde" in profile
    assert "Reconnaissance" in profile
    assert "Cartes physiques générées par ce modèle (2)" in profile


def test_propose_note_type_refactor_garde_fou(custom_model_data):
    nt = custom_model_data["nt"]
    new_fields = ["Organe", "Symptôme", "Diagnostic", "Traitement", "Pronostic"]
    new_css = ".card { font-family: 'Inter', sans-serif; font-size: 16px; }"

    res = ConsultantToolRegistry.propose_note_type_refactor(
        note_type_name=nt.name,
        new_fields_schema_json=json.dumps(new_fields),
        new_css=new_css,
        explanation="Ajout du champ Pronostic et police moderne.",
    )

    parsed = json.loads(res)
    assert parsed.get("status") == "staged_diff"
    assert parsed.get("type") == "model"
    assert parsed.get("note_type_name") == nt.name
    assert "Pronostic" in parsed["modified"]["fields_schema"]
    assert "Pronostic" not in parsed["original"]["fields_schema"]

    # Garde-Fou : vérifier que la BDD n'a pas encore changé
    fresh_nt = NoteTypeModel.get_by_id(nt.id)
    assert "Pronostic" not in fresh_nt.fields_schema


def test_workspace_inspector_apply_model_patch(qtbot, custom_model_data):
    nt = custom_model_data["nt"]
    new_css = ".card { background-color: #0f172a; color: #f8fafc; }"
    new_fields = ["Organe", "Symptôme", "Diagnostic", "Traitement", "Contre-indications"]

    patch = {
        "title": f"Mise à jour Modèle {nt.name}",
        "type": "model",
        "note_type_name": nt.name,
        "note_type_id": nt.id,
        "original": {"css_style": nt.css_style},
        "modified": {"css_style": new_css, "fields_schema": new_fields},
        "metadata": {"note_type_name": nt.name, "note_type_id": nt.id},
    }

    inspector = WorkspaceInspectorWidget()
    qtbot.addWidget(inspector)
    inspector.add_patch_to_queue(patch)

    # Valider le garde-fou
    inspector._on_apply_clicked()

    # Vérifier la persistance en BDD
    fresh_nt = NoteTypeModel.get_by_id(nt.id)
    assert fresh_nt.css_style == new_css
    assert "Contre-indications" in fresh_nt.fields_schema

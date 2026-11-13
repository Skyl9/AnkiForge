"""Tests unitaires pour le service d'import/export de modèles de cartes (CardModelIO)."""

import json
from pathlib import Path

import pytest

from ankidraft.database.models import DEFAULT_LATEX_POST, DEFAULT_LATEX_PRE, NoteTypeModel
from ankidraft.services.cards.card_model_io import BUNDLE_EXTENSION, CardModelIO

pytestmark = pytest.mark.integration


def test_export_to_dict_and_json():
    model = NoteTypeModel.create(
        name="Test Model",
        fields_schema=json.dumps(["Recto", "Verso", "Remarques"]),
        templates=json.dumps([{"name": "Face 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}} <hr> {{Remarques}}"}]),
        css_style=".card { color: red; }",
    )

    data = CardModelIO.export_to_dict(
        model=model,
        author="Alice",
        version="1.2.0",
        description="Modèle de test",
        tags=["test", "sciences"],
        demo_cards=[{"Recto": "Q1", "Verso": "R1", "Remarques": "Rem1"}],
    )

    assert data["ankiforge_schema_version"] == "1.0"
    assert data["metadata"]["name"] == "Test Model"
    assert data["metadata"]["author"] == "Alice"
    assert data["metadata"]["version"] == "1.2.0"
    assert data["fields_schema"] == ["Recto", "Verso", "Remarques"]
    assert len(data["templates"]) == 1
    assert data["css_style"] == ".card { color: red; }"
    assert data["demo_cards"][0]["Recto"] == "Q1"

    json_str = CardModelIO.export_to_json(model, author="Alice")
    assert "Test Model" in json_str
    assert "Alice" in json_str


def test_export_and_read_bundle(tmp_path: Path):
    model = NoteTypeModel.create(
        name="Anatomy Card",
        fields_schema=json.dumps(["Organ", "Function"]),
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Organ}}", "afmt": "{{Function}}"}]),
        css_style=".anatomy { font-size: 16px; }",
    )

    out_file = tmp_path / "anatomy_model.afmodel"
    saved_path = CardModelIO.export_to_bundle(
        model=model,
        output_path=out_file,
        author="Dr. Bob",
        version="2.0.0",
        description="Medical deck card",
        tags=["anatomy", "medicine"],
        demo_cards=[{"Organ": "Heart", "Function": "Pumps blood"}],
    )

    assert saved_path.exists()
    assert saved_path.suffix == BUNDLE_EXTENSION

    # Lecture de l'archive
    is_valid, parsed_data, err_msg = CardModelIO.read_bundle_file(saved_path)
    assert is_valid is True
    assert err_msg == ""
    assert parsed_data is not None
    assert parsed_data["name"] == "Anatomy Card"
    assert parsed_data["metadata"]["author"] == "Dr. Bob"
    assert parsed_data["metadata"]["version"] == "2.0.0"
    assert parsed_data["fields_schema"] == ["Organ", "Function"]
    assert parsed_data["templates"][0]["qfmt"] == "{{Organ}}"
    assert parsed_data["css_style"] == ".anatomy { font-size: 16px; }"
    assert parsed_data["demo_cards"][0]["Organ"] == "Heart"


def test_read_model_file_auto_detection(tmp_path: Path):
    # 1. Test avec un fichier JSON standard
    json_path = tmp_path / "simple_model.json"
    json_content = {
        "name": "Simple Model",
        "fields_schema": ["Front", "Back"],
        "templates": [{"name": "Card", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
        "css_style": "body { margin: 0; }",
    }
    json_path.write_text(json.dumps(json_content), encoding="utf-8")

    ok, data, err = CardModelIO.read_model_file(json_path)
    assert ok is True
    assert data["name"] == "Simple Model"
    assert data["fields_schema"] == ["Front", "Back"]

    # 2. Test avec un paquet .afmodel
    model = NoteTypeModel.create(
        name="Bundle Model",
        fields_schema=json.dumps(["A", "B"]),
        templates=json.dumps([{"name": "Card", "qfmt": "{{A}}", "afmt": "{{B}}"}]),
        css_style="",
    )
    bundle_path = tmp_path / "bundle.afmodel"
    CardModelIO.export_to_bundle(model, bundle_path)

    ok_b, data_b, err_b = CardModelIO.read_model_file(bundle_path)
    assert ok_b is True
    assert data_b["name"] == "Bundle Model"


def test_save_model_to_db_collisions():
    model_data = {
        "name": "Chemistry Formula",
        "fields_schema": ["Reactants", "Products"],
        "templates": [{"name": "C1", "qfmt": "{{Reactants}}", "afmt": "{{Products}}"}],
        "css_style": ".chem { color: blue; }",
    }

    # Premier enregistrement
    inst1, created1 = CardModelIO.save_model_to_db(model_data)
    assert created1 is True
    assert inst1.name == "Chemistry Formula"

    # Deuxième enregistrement sans écrasement -> Copie incrémentée
    inst2, created2 = CardModelIO.save_model_to_db(model_data, overwrite_existing=False)
    assert created2 is True
    assert inst2.name == "Chemistry Formula (2)"

    # Troisième enregistrement avec écrasement
    model_data["css_style"] = ".chem { color: green; }"
    inst3, created3 = CardModelIO.save_model_to_db(model_data, overwrite_existing=True)
    assert created3 is False
    assert inst3.id == inst1.id
    assert inst3.css_style == ".chem { color: green; }"


def test_starter_pack_models():
    packs = CardModelIO.get_starter_pack_models()
    assert len(packs) == 5

    pack_ids = [p["id"] for p in packs]
    assert "medical_qcm" in pack_ids
    assert "dev_jetbrains" in pack_ids
    assert "math_katex" in pack_ids
    assert "vocab_languages" in pack_ids
    assert "cloze" in pack_ids

    # Installation du modèle médical
    med_model = CardModelIO.install_starter_pack("medical_qcm")
    assert med_model is not None
    assert "Médical" in med_model.name
    assert "Options" in med_model.fields_schema

    # Réinstallation sans écrasement
    med_copy = CardModelIO.install_starter_pack("medical_qcm", overwrite=False)
    assert med_copy is not None
    assert "(2)" in med_copy.name


def test_starter_pack_cloze_installable_on_demand():
    """Le modèle Cloze n'est plus semé d'office mais reste installable en un clic."""
    cloze_model = CardModelIO.install_starter_pack("cloze")

    assert cloze_model is not None
    assert cloze_model.name == "Texte à trous (Cloze)"
    assert json.loads(cloze_model.fields_schema) == ["Texte", "Remarques extra"]
    assert "{{cloze:" in cloze_model.templates


def test_export_to_dict_includes_latex_fields():
    """Vérifie que export_to_dict inclut les champs LaTeX avec valeurs par défaut et personnalisées."""
    # 1. Test avec valeurs par défaut
    model_default = NoteTypeModel.create(
        name="Default Latex Model",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
    )

    data = CardModelIO.export_to_dict(model=model_default)
    assert data["latex_pre"] == DEFAULT_LATEX_PRE
    assert data["latex_post"] == DEFAULT_LATEX_POST
    assert data["latex_svg"] is True

    # 2. Test avec valeurs personnalisées
    custom_pre = r"""\documentclass[11pt]{article}
\usepackage{amsmath}
\begin{document}
"""
    custom_post = r"\end{document}"

    model_custom = NoteTypeModel.create(
        name="Custom Latex Model",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
        latex_pre=custom_pre,
        latex_post=custom_post,
        latex_svg=False,
    )

    data = CardModelIO.export_to_dict(model=model_custom)
    assert data["latex_pre"] == custom_pre
    assert data["latex_post"] == custom_post
    assert data["latex_svg"] is False


def test_export_and_read_bundle_includes_latex(tmp_path: Path):
    """Vérifie que l'export/lecture de bundle .afmodel conserve les champs LaTeX."""
    custom_pre = r"""\documentclass[11pt]{article}
\usepackage{amsmath}
\begin{document}
"""
    custom_post = r"\end{document}"

    model = NoteTypeModel.create(
        name="Latex Bundle Model",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
        latex_pre=custom_pre,
        latex_post=custom_post,
        latex_svg=False,
    )

    out_file = tmp_path / "latex_model.afmodel"
    CardModelIO.export_to_bundle(model=model, output_path=out_file)

    # Lecture de l'archive
    is_valid, parsed_data, err_msg = CardModelIO.read_bundle_file(out_file)
    assert is_valid is True
    assert err_msg == ""
    assert parsed_data is not None
    assert parsed_data["latex_pre"] == custom_pre
    assert parsed_data["latex_post"] == custom_post
    assert parsed_data["latex_svg"] is False


def test_validate_and_parse_json_includes_latex():
    """Vérifie que validate_and_parse_json gère les champs LaTeX."""
    json_data = {
        "name": "JSON Latex Model",
        "fields_schema": ["Front", "Back"],
        "templates": [{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
        "css_style": "",
        "latex_pre": r"""\documentclass{article}\begin{document}""",
        "latex_post": r"\end{document}",
        "latex_svg": False,
    }

    is_valid, parsed_data, err_msg = CardModelIO.validate_and_parse_json(json.dumps(json_data))
    assert is_valid is True
    assert err_msg == ""
    assert parsed_data["latex_pre"] == r"""\documentclass{article}\begin{document}"""
    assert parsed_data["latex_post"] == r"\end{document}"
    assert parsed_data["latex_svg"] is False

    # Test avec valeurs par défaut (champs manquants)
    json_data_minimal = {
        "name": "Minimal Model",
        "fields_schema": ["Front", "Back"],
        "templates": [{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
        "css_style": "",
    }
    is_valid2, parsed_data2, err_msg2 = CardModelIO.validate_and_parse_json(json.dumps(json_data_minimal))
    assert is_valid2 is True
    assert parsed_data2["latex_pre"] == DEFAULT_LATEX_PRE
    assert parsed_data2["latex_post"] == DEFAULT_LATEX_POST
    assert parsed_data2["latex_svg"] is True


def test_save_model_to_db_includes_latex():
    """Vérifie que save_model_to_db persiste les champs LaTeX."""
    custom_pre = r"""\documentclass[11pt]{article}\begin{document}"""
    custom_post = r"\end{document}"

    model_data = {
        "name": "DB Latex Model",
        "fields_schema": ["Front", "Back"],
        "templates": [{"name": "C1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
        "css_style": "",
        "latex_pre": custom_pre,
        "latex_post": custom_post,
        "latex_svg": False,
    }

    # Enregistrement initial
    inst, created = CardModelIO.save_model_to_db(model_data)
    assert created is True
    assert inst.latex_pre == custom_pre
    assert inst.latex_post == custom_post
    assert inst.latex_svg is False

    # Mise à jour avec overwrite
    model_data["latex_pre"] = r"""\documentclass[12pt]{article}\begin{document}"""
    model_data["latex_svg"] = True
    inst2, created2 = CardModelIO.save_model_to_db(model_data, overwrite_existing=True)
    assert created2 is False
    assert inst2.id == inst.id
    assert inst2.latex_pre == r"""\documentclass[12pt]{article}\begin{document}"""
    assert inst2.latex_svg is True

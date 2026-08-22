"""
Tests unitaires pour la bibliothèque de snippets, le résolveur de conflits CSS et l'import/export de modèles.
"""

import json
import uuid
from ankiforge.database.models import NoteTypeModel
from ankiforge.services.cards.snippet_library import SnippetLibrary, CSSConflictResolver
from ankiforge.services.cards.card_model_io import CardModelIO


def test_snippet_library_catalog():
    """Vérifie la complétude du catalogue de snippets et de ses catégories."""
    snippets = SnippetLibrary.get_all_snippets()
    assert len(snippets) >= 5

    categories = SnippetLibrary.get_categories()
    assert "Callouts & Remarques" in categories
    assert "Badges & Étiquettes" in categories
    assert "QCM & Choix Multiples" in categories
    assert "KaTeX & Mathématiques" in categories
    assert "Code Développeur" in categories

    callouts = SnippetLibrary.get_by_category("Callouts & Remarques")
    assert len(callouts) >= 3

    info_snippet = SnippetLibrary.get_by_id("callout_info")
    assert info_snippet is not None
    assert "af-callout-info" in info_snippet.html_template
    assert "af-callout" in info_snippet.css_style


def test_css_conflict_resolver_detection():
    """Vérifie la détection précise des sélecteurs CSS en collision."""
    existing_css = """
    .card { font-family: arial; }
    .af-callout { padding: 10px; }
    .af-callout-info { border-left: 4px solid blue; }
    .custom-title { font-weight: bold; }
    """

    new_css = """
    .af-callout { margin: 12px; }
    .af-callout-warning { border-left: 4px solid orange; }
    .new-badge { font-size: 10px; }
    """

    conflicts = CSSConflictResolver.find_conflicts(existing_css, new_css)
    assert conflicts == ["af-callout"]


def test_css_conflict_resolver_renaming():
    """Vérifie le renommage cohérent des classes en collision dans le HTML et le CSS."""
    html = '<div class="af-callout af-callout-info"><p>Contenu</p></div>'
    css = ".af-callout { margin: 10px; }\n.af-callout-info { color: blue; }"

    mapping = {
        "af-callout": "af-callout-v2",
        "af-callout-info": "af-callout-info-v2",
    }

    renamed_html, renamed_css = CSSConflictResolver.rename_classes(html, css, mapping)
    assert "af-callout-v2" in renamed_html
    assert "af-callout-info-v2" in renamed_html
    assert ".af-callout-v2" in renamed_css
    assert ".af-callout-info-v2" in renamed_css


def test_css_conflict_resolver_merge():
    """Vérifie la fusion CSS selon les stratégies append et replace."""
    existing_css = ".card { color: black; }\n.af-callout { padding: 5px; }"
    new_css = ".af-callout { padding: 15px; }\n.af-badge { font-size: 12px; }"

    # Strategy Append
    appended = CSSConflictResolver.merge_css(existing_css, new_css, strategy="append")
    assert ".card" in appended
    assert ".af-badge" in appended
    assert "/* --- Snippet Ajouté --- */" in appended

    # Strategy Replace
    replaced = CSSConflictResolver.merge_css(existing_css, new_css, strategy="replace", replace_classes=["af-callout"])
    assert "padding: 15px;" in replaced


def test_card_model_io_export_and_import(mock_db):
    """Vérifie l'exportation JSON standardisée et la réimportation fidèle."""
    uid = uuid.uuid4().hex[:6]
    nt = NoteTypeModel.create(
        name=f"Modèle Test IO {uid}",
        fields_schema=json.dumps(["Recto", "Verso", "Remarque"]),
        templates=json.dumps(
            [
                {"name": "Carte 1", "qfmt": "{{Recto}}", "afmt": "{{Verso}}"},
                {"name": "Carte 2 (Inversée)", "qfmt": "{{Verso}}", "afmt": "{{Recto}}"},
            ]
        ),
        css_style=".card { font-size: 16px; }",
    )

    json_str = CardModelIO.export_to_json(nt, author="Tester", tags=["test", "io"])
    assert json_str is not None

    is_valid, parsed, err = CardModelIO.validate_and_parse_json(json_str)
    assert is_valid is True
    assert parsed is not None
    assert parsed["name"] == f"Modèle Test IO {uid}"
    assert parsed["fields_schema"] == ["Recto", "Verso", "Remarque"]
    assert len(parsed["templates"]) == 2

    # Test de sauvegarde sans écrasement (génère un nom incrémenté)
    created, is_new = CardModelIO.save_model_to_db(parsed, overwrite_existing=False)
    assert is_new is True
    assert f"Modèle Test IO {uid} (2)" == created.name

    # Test de sauvegarde avec écrasement
    overwritten, is_new2 = CardModelIO.save_model_to_db(parsed, overwrite_existing=True)
    assert is_new2 is False
    assert overwritten.id == nt.id


def test_snippet_library_custom_crud(tmp_path):
    """Vérifie la création, modification et suppression de snippets personnalisés."""
    uid = uuid.uuid4().hex[:6]
    created = SnippetLibrary.create_custom_snippet(
        name=f"Snippet Custom Test {uid}",
        category="Mes Snippets",
        description="Description de test",
        icon_name="ph.sparkle",
        html_template='<div class="custom-box">{{Test}}</div>',
        css_style=".custom-box { color: red; }",
        tags=["custom", "test"],
    )

    assert created.id.startswith("custom_")
    assert created.is_custom is True

    # Vérifier que le snippet est présent dans all_snippets
    all_snippets = SnippetLibrary.get_all_snippets()
    found = next((s for s in all_snippets if s.id == created.id), None)
    assert found is not None
    assert found.name == f"Snippet Custom Test {uid}"

    # Modifier le snippet
    created.name = f"Snippet Modifié {uid}"
    SnippetLibrary.save_snippet(created)

    updated = SnippetLibrary.get_by_id(created.id)
    assert updated is not None
    assert updated.name == f"Snippet Modifié {uid}"

    # Supprimer le snippet
    deleted = SnippetLibrary.delete_snippet(created.id)
    assert deleted is True
    assert SnippetLibrary.get_by_id(created.id) is None

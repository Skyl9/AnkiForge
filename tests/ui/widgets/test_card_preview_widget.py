import json
from unittest.mock import patch

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget


def test_preview_widget_empty_state(qtbot):
    """Vérifie que le composant affiche bien son message par défaut si aucune donnée n'est fournie."""
    widget = CardPreviewWidget()
    qtbot.addWidget(widget)

    # On mocke l'appel au WebEngine pour éviter de lancer un vrai navigateur Chromium en tâche de fond
    with patch.object(widget.web_view, "setHtmlSafe") as mock_set_html:
        widget.set_empty_state("Message de test")

        mock_set_html.assert_called_once()
        html_envoye = mock_set_html.call_args[0][0]
        assert "Message de test" in html_envoye


def test_preview_widget_update_preview(qtbot, mock_db):
    """Vérifie que le composant peuple ses listes déroulantes et génère le HTML d'aperçu."""
    widget = CardPreviewWidget()
    qtbot.addWidget(widget)

    # 1. Préparation d'un faux Modèle Anki (AVEC le css_style cette fois !)
    nt = NoteTypeModel.create(
        name="Test Model",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "<b>{{Front}}</b>", "afmt": "{{Front}}<hr>{{Back}}"}]),
        css_style=".card { color: black; }",  # <-- La correction est ici
    )
    fields_dict = {"Front": "Quelle est la capitale ?", "Back": "Paris"}

    # 2. Action : On met à jour l'aperçu
    with patch.object(widget.web_view, "setHtmlSafe") as mock_set_html:
        widget.update_preview(note_type=nt, fields_dict=fields_dict)

        # 3. Vérifications de l'UI
        assert widget.card_selector.count() == 1
        assert widget.card_selector.itemText(0) == "Carte 1"
        assert widget.is_recto is True
        assert widget.btn_toggle_side is not None

        # 4. Vérifications du Rendu (le Recto doit être affiché par défaut)
        mock_set_html.assert_called_once()
        html_envoye = mock_set_html.call_args[0][0]
        assert "<b>Quelle est la capitale ?</b>" in html_envoye
        assert "Paris" not in html_envoye  # Le verso ne doit pas fuiter sur le recto

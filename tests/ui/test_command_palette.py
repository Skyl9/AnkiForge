from ankiforge.ui.widgets.command_palette import CommandPalette


def test_command_palette_creation(qtbot):
    widget = CommandPalette()
    qtbot.addWidget(widget)
    assert widget is not None

    # Vérification que l'action tour est bien enregistrée
    tour_cmds = [cmd for cmd in widget.commands if cmd["id"] == "action.tour"]
    assert len(tour_cmds) == 1
    assert "visite guidée" in tour_cmds[0]["title"]


def test_command_palette_selection_tour(qtbot):
    widget = CommandPalette()
    qtbot.addWidget(widget)

    captured: dict[str, str] = {}

    widget.command_selected.connect(lambda cid: captured.update(cmd=cid))
    widget.view_requested.connect(lambda vid: captured.update(view=vid))

    # Filtrage par mot-clé 'tour' ou 'visite'
    widget.search_input.setText("visite")
    assert widget.result_list.count() >= 1

    first_item = widget.result_list.item(0)
    widget._on_item_clicked(first_item)

    assert captured.get("cmd") == "action.tour"
    assert captured.get("view") == "tour"

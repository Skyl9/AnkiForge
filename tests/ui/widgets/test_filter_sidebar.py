import pytest
from ankiforge.ui.widgets.filter_sidebar import FilterSidebar
from ankiforge.database.models import DeckModel, NoteModel, CardModel, NoteTypeModel, db
import json


@pytest.fixture
def filter_sidebar(qtbot):
    sidebar = FilterSidebar()
    qtbot.addWidget(sidebar)
    return sidebar


def test_filter_sidebar_refresh_decks(filter_sidebar, mock_db):
    with db.atomic():
        DeckModel.create(name="Science")
        DeckModel.create(name="Science::Physique")
        DeckModel.create(name="Maths")

    filter_sidebar.refresh_decks()

    # alphabetical: Maths, Science
    assert filter_sidebar.deck_tree.topLevelItemCount() == 2

    maths_item = filter_sidebar.deck_tree.topLevelItem(0)
    assert "Maths" in maths_item.text(0)

    science_item = filter_sidebar.deck_tree.topLevelItem(1)
    assert "Science" in science_item.text(0)
    assert science_item.childCount() == 1
    assert "Physique" in science_item.child(0).text(0)


def test_filter_sidebar_selection_signal(filter_sidebar, qtbot, mock_db):
    with db.atomic():
        deck = DeckModel.create(name="Test Deck")

    filter_sidebar.refresh_decks()
    item = filter_sidebar.deck_tree.topLevelItem(0)

    with qtbot.waitSignal(filter_sidebar.deck_selected) as blocker:
        filter_sidebar.deck_tree.itemClicked.emit(item, 0)

    assert blocker.args == [deck.id]


def test_filter_sidebar_refresh_tags(filter_sidebar, mock_db):
    with db.atomic():
        nt = NoteTypeModel.create(name="Basic", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
        deck = DeckModel.create(name="Test Deck")
        note = NoteModel.create(note_type=nt, tags=json.dumps(["tag1", "tag2"]), status="new", guid="abc")
        CardModel.create(note=note, deck=deck)

    filter_sidebar.refresh_tags(deck.id)

    assert filter_sidebar.tag_list.count() == 3
    assert "tag1" in filter_sidebar.tag_list.item(1).text()
    assert "tag2" in filter_sidebar.tag_list.item(2).text()

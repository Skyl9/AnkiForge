"""Tests pour l'optimisation mémoire et le recyclage des vues dans DuplicateMergeInspector."""

from pytestqt.qtbot import QtBot

from ankiforge.database.models import DeckModel, NoteModel, NoteTypeModel
from ankiforge.ui.components.duplicate_widgets import DuplicateMergeInspector
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView


def test_duplicate_merge_inspector_lazy_loading_and_recycling(qtbot: QtBot) -> None:
    inspector = DuplicateMergeInspector()
    qtbot.addWidget(inspector)

    # 1. Vérifier qu'au démarrage en mode source, AUCUNE vue WebEngine n'est instanciée (Lazy Loading)
    assert inspector.web_a is None
    assert inspector.web_b is None
    assert inspector.web_fusion is None
    assert inspector.stack_a.currentIndex() == 0
    assert inspector.stack_b.currentIndex() == 0
    assert inspector.stack_fusion.currentIndex() == 0

    deck = DeckModel.create(name="Deck Doublons Memory")
    nt = NoteTypeModel.create(name="Type Memory", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    note_a = NoteModel.create(guid="mem_a", deck=deck, note_type=nt)
    note_b = NoteModel.create(guid="mem_b", deck=deck, note_type=nt)

    conflict_data = {
        "note_a": note_a,
        "content_a": {"Front": "Question 1", "Back": "Réponse 1"},
        "note_b": note_b,
        "content_b": {"Front": "Question 1 bis", "Back": "Réponse 1 bis"},
        "sim": 0.95,
    }

    # 2. Chargement du conflit en mode Source
    inspector.load_conflict(conflict_data)

    # Toujours 0 vue WebEngine instanciée en mode Source
    assert inspector.web_a is None
    assert inspector.web_b is None
    assert inspector.web_fusion is None
    assert inspector.stack_a.currentIndex() == 0

    # 3. Basculement de la Colonne A en mode KaTeX
    inspector.view_modes["A"] = "katex"
    inspector._refresh_col("A")

    # Une seule vue WebEngine créée pour la colonne A
    assert inspector.web_a is not None
    assert isinstance(inspector.web_a, SafeWebEngineView)
    assert inspector.stack_a.currentIndex() == 1
    # Colonnes B et Fusion toujours sans vue WebEngine
    assert inspector.web_b is None
    assert inspector.web_fusion is None

    web_a_instance = inspector.web_a

    # 4. Chargement d'un nouveau conflit : la vue web_a DOIT être recyclée (même instance)
    conflict_data_2 = {
        "note_a": note_a,
        "content_a": {"Front": "Formule $E=mc^2$", "Back": "Énergie"},
        "note_b": note_b,
        "content_b": {"Front": "Formule $E=mc^2$", "Back": "Masse"},
        "sim": 0.88,
    }
    inspector.load_conflict(conflict_data_2)

    assert inspector.web_a is web_a_instance  # Recyclage garanti, 0 réallocation !
    assert inspector.stack_a.currentIndex() == 1

    # 5. Test d'injection de champ depuis le protocole applicatif ankiforge://inject/A/Back
    inspector._on_web_action("inject", {"source": "A", "field_name": "Back"})
    assert inspector.current_conflict["merged_content"]["Back"] == "Énergie"

    # 6. Test de réinitialisation et nettoyage
    inspector.reset_inspector()
    assert inspector.current_conflict is None
    assert inspector.stack_a.currentIndex() == 0
    assert inspector.stack_b.currentIndex() == 0
    assert inspector.stack_fusion.currentIndex() == 0

    # Test cleanup
    inspector.cleanup()

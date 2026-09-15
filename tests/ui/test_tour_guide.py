from PySide6.QtWidgets import QLabel, QWidget

from ankiforge.ui.widgets.tour_guide import TourBubble, TourStep, create_default_tour_steps


def test_tour_bubble_creation(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    bubble = TourBubble(parent)
    qtbot.addWidget(bubble)
    assert bubble is not None
    assert bubble.current_step == 0


def test_tour_bubble_navigation(qtbot):
    parent = QWidget()
    target_label = QLabel("Cible", parent)
    qtbot.addWidget(parent)

    action_executed = False

    def on_step_action():
        nonlocal action_executed
        action_executed = True

    steps = [
        TourStep(title="Étape 1", text="Bienvenue", target_widget=None),
        TourStep(title="Étape 2", text="Inspection", target_widget=target_label, action=on_step_action),
    ]

    bubble = TourBubble(parent)
    qtbot.addWidget(bubble)
    bubble.set_scenario(steps)

    bubble.start_tour()
    assert bubble.isVisible()
    assert bubble.lbl_title.text() == "Étape 1"
    assert bubble.lbl_counter.text() == "1/2"
    assert not bubble.btn_prev.isVisible()

    # Avance vers étape 2
    bubble.next_step()
    assert bubble.current_step == 1
    assert bubble.lbl_title.text() == "Étape 2"
    assert bubble.lbl_counter.text() == "2/2"
    assert bubble.btn_prev.isVisible()
    assert action_executed is True

    # Retour vers étape 1
    bubble.prev_step()
    assert bubble.current_step == 0
    assert bubble.lbl_title.text() == "Étape 1"

    # Terminer le tour
    bubble.next_step()
    bubble.next_step()  # déclenche end_tour
    assert bubble.isHidden()


def test_tour_dict_scenario_compatibility(qtbot):
    parent = QWidget()
    qtbot.addWidget(parent)

    dict_steps = [
        {"title": "Step Dict 1", "text": "Contenu 1"},
        {"title": "Step Dict 2", "text": "Contenu 2"},
    ]

    bubble = TourBubble(parent)
    qtbot.addWidget(bubble)
    bubble.set_scenario(dict_steps)
    bubble.start_tour()

    assert len(bubble.steps) == 2
    assert bubble.steps[0].title == "Step Dict 1"
    bubble.end_tour()
    assert bubble.isHidden()


def test_create_default_tour_steps():
    class DummyMainWindow:
        def __init__(self):
            self.sidebar = None

        def _on_view_selected(self, view_id):
            pass

    dummy_win = DummyMainWindow()
    steps = create_default_tour_steps(dummy_win)
    assert len(steps) >= 5
    assert "Bienvenue" in steps[0].title

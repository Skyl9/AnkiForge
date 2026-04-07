# tests/test_toast.py
import pytest
from PySide6.QtWidgets import QWidget, QLabel
from unittest.mock import patch

from ankiforge.ui.widgets.toast import Toast, show_toast

@pytest.fixture
def parent_widget(qtbot):
    """Fixture qui crée un widget parent factice."""
    widget = QWidget()
    widget.resize(800, 600)
    qtbot.addWidget(widget)
    return widget

def test_toast_initialization(parent_widget, qtbot):
    message = "Sauvegarde réussie"
    color = "#123456"

    toast = Toast(parent_widget, message=message, color=color)
    qtbot.addWidget(toast)

    labels = toast.findChildren(QLabel)
    texts = [label.text() for label in labels]
    assert message in texts, "Le message du toast n'a pas été trouvé."
    # On vérifie juste que la couleur dynamique a bien été injectée
    assert color in toast.bg_frame.styleSheet(), "La couleur personnalisée n'est pas appliquée."

def test_toast_show_behavior(parent_widget, qtbot):
    toast = Toast(parent_widget, message="Test")
    qtbot.addWidget(toast)

    with patch.object(toast.animation, 'start') as mock_anim_start, \
            patch.object(toast.timer, 'start') as mock_timer_start:
        toast.show_toast(duration=1500)
        assert toast.isVisible()
        mock_anim_start.assert_called_once()
        mock_timer_start.assert_called_once_with(1500)

def test_toast_hide_behavior(parent_widget, qtbot):
    toast = Toast(parent_widget, message="Test")
    qtbot.addWidget(toast)
    toast.show_toast()

    with patch.object(toast.animation, 'start') as mock_anim_start, \
            patch.object(toast.timer, 'stop') as mock_timer_stop:
        toast.hide_toast()
        mock_timer_stop.assert_called_once()
        mock_anim_start.assert_called_once()
        assert toast.animation.startValue() == 1.0
        assert toast.animation.endValue() == 0.0

@patch("ankiforge.ui.widgets.toast.Toast")
def test_helper_show_toast(mock_toast_class, parent_widget):
    mock_instance = mock_toast_class.return_value
    show_toast(parent_widget, "Tout va bien")
    mock_toast_class.assert_called_with(parent_widget, "Tout va bien", "#4CAF50", "fa5s.check")
    mock_instance.show_toast.assert_called_once()

    mock_toast_class.reset_mock()
    mock_instance.reset_mock()

    show_toast(parent_widget, "Grosse erreur", is_error=True)
    mock_toast_class.assert_called_with(parent_widget, "Grosse erreur", "#F44336", "fa5s.exclamation-triangle")
    mock_instance.show_toast.assert_called_once()
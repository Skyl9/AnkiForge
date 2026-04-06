import pytest
from PySide6.QtWidgets import QWidget, QLabel
from unittest.mock import patch

# Remplace 'ankiforge' par le vrai nom de ton module racine si besoin
from ankiforge.ui.widgets.toast import Toast, show_toast


@pytest.fixture
def parent_widget(qtbot):
    """
    Fixture qui crée un widget parent factice.
    Le Toast a besoin d'un parent pour calculer sa position (local_x, local_y).
    """
    widget = QWidget()
    widget.resize(800, 600)
    qtbot.addWidget(widget)  # qtbot se chargera de le détruire proprement à la fin du test
    return widget


def test_toast_initialization(parent_widget, qtbot):
    """Vérifie que le Toast est bien configuré à sa création."""
    message = "Sauvegarde réussie"
    color = "#123456"

    toast = Toast(parent_widget, message=message, color=color)
    qtbot.addWidget(toast)

    # 1. Vérification du texte
    # On cherche tous les QLabels à l'intérieur du Toast pour trouver notre message
    labels = toast.findChildren(QLabel)
    texts = [label.text() for label in labels]
    assert message in texts, "Le message du toast n'a pas été trouvé dans les labels."

    # 2. Vérification de la couleur dans le style
    assert color in toast.bg_frame.styleSheet(), "La couleur personnalisée n'est pas appliquée."


def test_toast_show_behavior(parent_widget, qtbot):
    """Vérifie que la méthode show_toast lance bien l'animation et le timer."""
    toast = Toast(parent_widget, message="Test")
    qtbot.addWidget(toast)

    # On mock l'animation pour éviter d'attendre pour rien dans les tests
    # et vérifier simplement qu'elle est bien déclenchée
    with patch.object(toast.animation, 'start') as mock_anim_start, \
            patch.object(toast.timer, 'start') as mock_timer_start:
        toast.show_toast(duration=1500)

        # Vérifications
        assert toast.isVisible()
        mock_anim_start.assert_called_once()
        mock_timer_start.assert_called_once_with(1500)


def test_toast_hide_behavior(parent_widget, qtbot):
    """Vérifie que la méthode hide_toast arrête le timer et lance la disparition."""
    toast = Toast(parent_widget, message="Test")
    qtbot.addWidget(toast)

    # On lance le toast pour le mettre dans l'état initial
    toast.show_toast()

    with patch.object(toast.animation, 'start') as mock_anim_start, \
            patch.object(toast.timer, 'stop') as mock_timer_stop:
        # On simule la fin du timer
        toast.hide_toast()

        mock_timer_stop.assert_called_once()
        mock_anim_start.assert_called_once()

        # On vérifie que les valeurs de l'animation sont bien inversées pour le fondu
        assert toast.animation.startValue() == 1.0
        assert toast.animation.endValue() == 0.0




@patch("ankiforge.ui.widgets.toast.Toast")
def test_helper_show_toast(mock_toast_class, parent_widget):
    """
    Vérifie la fonction utilitaire sans réellement créer l'UI.
    C'est très utile pour vérifier la logique métier (choix des couleurs).
    """
    mock_instance = mock_toast_class.return_value

    # 1. Test du succès (is_error = False par défaut)
    show_toast(parent_widget, "Tout va bien")
    mock_toast_class.assert_called_with(parent_widget, "Tout va bien", "#4CAF50", "fa5s.check")
    mock_instance.show_toast.assert_called_once()

    # On reset les compteurs du mock pour le test suivant
    mock_toast_class.reset_mock()
    mock_instance.reset_mock()

    # 2. Test de l'erreur (is_error = True)
    show_toast(parent_widget, "Grosse erreur", is_error=True)
    mock_toast_class.assert_called_with(parent_widget, "Grosse erreur", "#F44336", "fa5s.exclamation-triangle")
    mock_instance.show_toast.assert_called_once()
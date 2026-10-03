from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QResizeEvent
from PySide6.QtWidgets import QWidget

from ankiforge.ui.components.elided_label import ElidedLabel


def test_elided_label_initialization_and_text(qtbot: Any) -> None:
    """Vérifie l'initialisation d'ElidedLabel, sa politique de taille et ses accesseurs de texte."""
    full_text = "Titre très long pour un cours de médecine générale et pharmacologie clinique"
    label = ElidedLabel(full_text)
    qtbot.addWidget(label)

    assert label.text() == full_text
    assert label.full_text() == full_text
    assert label.minimumWidth() == 0
    assert label.minimumSizeHint().width() == 0
    assert label.sizeHint().width() == 0


def test_elided_label_dynamic_elision_on_resize(qtbot: Any) -> None:
    """Vérifie que le texte s'élide dynamiquement lors des redimensionnements."""
    container = QWidget()
    qtbot.addWidget(container)
    container.resize(400, 100)

    long_title = "Chapitre 1 : Introduction détaillée à la physiologie cellulaire et aux membranes"
    label = ElidedLabel(long_title, parent=container)
    label.setFont(QFont("Arial", 12))

    container.show()
    label.resize(100, 30)
    label.resizeEvent(QResizeEvent(QSize(100, 30), QSize(0, 0)))

    # Le texte complet reste accessible via .text() et .full_text()
    assert label.text() == long_title
    assert label.full_text() == long_title

    # Le texte affiché à l'écran (elided_text) contient l'ellipse
    elided = label.elided_text()
    assert len(elided) < len(long_title)
    assert elided.endswith("…") or "..." in elided

    # En agrandissant le label, le texte elidé contient plus de caractères
    label.resize(300, 30)
    label.resizeEvent(QResizeEvent(QSize(300, 30), QSize(100, 30)))
    elided_large = label.elided_text()
    assert len(elided_large) > len(elided)


def test_elided_label_set_text_empty(qtbot: Any) -> None:
    """Vérifie le comportement avec une chaîne vide."""
    label = ElidedLabel("Texte initial")
    qtbot.addWidget(label)
    assert label.text() == "Texte initial"

    label.setText("")
    assert label.text() == ""
    assert label.elided_text() == ""

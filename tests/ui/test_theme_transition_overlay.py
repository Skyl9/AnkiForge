from PySide6.QtWidgets import QWidget

from ankiforge.ui.widgets.theme_transition_overlay import (
    SpinningIconLabel,
    ThemeTransitionOverlay,
    show_theme_transition,
)


def test_spinning_icon_label(qtbot):
    spinner = SpinningIconLabel(icon_name="ph.palette", color="#6366f1", size=32)
    qtbot.addWidget(spinner)
    assert spinner.width() == 32
    assert spinner.height() == 32

    # Rotation tick (+12 deg)
    spinner._rotate()
    assert spinner._angle == 12
    spinner.stop()


def test_theme_transition_overlay_creation(qtbot):
    parent = QWidget()
    parent.resize(800, 600)
    parent.show()
    qtbot.addWidget(parent)

    called = False

    def on_applied():
        nonlocal called
        called = True

    overlay = ThemeTransitionOverlay(
        parent=parent,
        theme_title="JetBrains Dark",
        subtext="Application en cours...",
        duration_ms=100,
        on_applied=on_applied,
    )
    qtbot.addWidget(overlay)

    # Attend que l'animation d'entrée se termine et appelle le callback
    qtbot.waitUntil(lambda: called is True, timeout=1000)
    assert called is True


def test_show_theme_transition_helper(qtbot):
    parent = QWidget()
    parent.show()
    qtbot.addWidget(parent)

    callback_called = False

    def callback():
        nonlocal callback_called
        callback_called = True

    overlay = show_theme_transition(
        parent=parent,
        theme_title="Apple macOS Slate",
        duration_ms=100,
        on_applied=callback,
    )
    assert overlay is not None

    qtbot.waitUntil(lambda: callback_called is True, timeout=1000)
    assert callback_called is True

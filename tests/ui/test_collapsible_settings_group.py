from PySide6.QtWidgets import QLabel, QPushButton

from ankiforge.ui.widgets.settings_modal.components import CollapsibleSettingsGroup


def test_collapsible_settings_group_defaults_collapsed(qtbot):
    """Le groupe est replié par défaut : contenu masqué et pastille de décompte affichée."""
    group = CollapsibleSettingsGroup("Options avancées")
    qtbot.addWidget(group)
    group.add_widget(QLabel("contrôle A"))
    group.add_widget(QLabel("contrôle B"))

    assert group.is_expanded() is False
    assert group.content.isHidden()
    assert group.lbl_badge.text() == "2"
    assert not group.lbl_badge.isHidden()


def test_collapsible_settings_group_expand_via_set_expanded(qtbot):
    """set_expanded(True) déplie le contenu et émet toggled(True)."""
    group = CollapsibleSettingsGroup("Options avancées")
    qtbot.addWidget(group)
    group.add_widget(QLabel("contenu"))

    emitted = []
    group.toggled.connect(emitted.append)

    group.set_expanded(True)
    assert group.is_expanded() is True
    assert not group.content.isHidden()
    assert emitted == [True]

    # Appel idempotent : pas de réémission.
    group.set_expanded(True)
    assert emitted == [True]


def test_collapsible_settings_group_collapse_and_toggle(qtbot):
    """toggle() replie/déploie et émet toggled(bool) à chaque changement."""
    group = CollapsibleSettingsGroup("Options avancées")
    qtbot.addWidget(group)
    group.add_widget(QLabel("contenu"))

    emitted = []
    group.toggled.connect(emitted.append)

    group.toggle()
    assert group.is_expanded() is True
    assert emitted == [True]

    group.toggle()
    assert group.is_expanded() is False
    assert group.content.isHidden()
    assert emitted == [True, False]


def test_collapsible_settings_group_chevron_and_object_name(qtbot):
    """L'en-tête porte un caret et l'objet est identifiable pour le QSS."""
    group = CollapsibleSettingsGroup("Options avancées")
    qtbot.addWidget(group)

    assert group.objectName() == "CollapsibleSettingsGroup"
    assert group.lbl_caret.pixmap() is not None
    assert group.lbl_title.text() == "Options avancées"

    group.set_expanded(True)
    assert group.lbl_caret.pixmap() is not None


def test_collapsible_settings_group_add_layout_counts_badge(qtbot):
    """add_layout incrémente également la pastille de décompte."""
    from PySide6.QtWidgets import QHBoxLayout

    group = CollapsibleSettingsGroup("Options")
    qtbot.addWidget(group)

    layout = QHBoxLayout()
    layout.addWidget(QPushButton("action"))
    group.add_layout(layout)

    assert group.lbl_badge.text() == "1"


def test_collapsible_settings_group_refresh_theme_no_crash(qtbot):
    """refresh_theme ne lève pas d'exception au changement de thème."""
    from ankiforge.ui.style_engine import get_style_engine

    group = CollapsibleSettingsGroup("Options")
    qtbot.addWidget(group)
    group.add_widget(QLabel("contenu"))

    profile = get_style_engine().get_theme("ide")
    group.refresh_theme(profile)
    group.set_expanded(True)
    group.refresh_theme(profile)

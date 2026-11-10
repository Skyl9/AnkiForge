from PySide6.QtWidgets import QLabel

from ankiforge.ui.components.badges import Badge
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.collapsible_group import CollapsibleSettingsGroup
from ankiforge.ui.widgets.settings_modal.components.settings_card import apply_pill_badge_style
from ankiforge.ui.widgets.settings_modal.tabs.storage_tab import StorageMaintenanceTab


def test_apply_pill_badge_style_fluid_pill(qtbot):
    """Vérifie que apply_pill_badge_style applique une forme de capsule fluide 9999px."""
    label = QLabel("Test Pill")
    qtbot.addWidget(label)
    apply_pill_badge_style(label, DesignTokens.COLOR_GREEN)

    ss = label.styleSheet()
    assert "border-radius: 9999px" in ss
    assert "10px" not in ss
    assert DesignTokens.COLOR_GREEN in ss


def test_apply_pill_badge_style_custom_radius(qtbot):
    """Vérifie que apply_pill_badge_style accepte un rayon d'arrondi paramétrable."""
    label = QLabel("Custom Radius Pill")
    qtbot.addWidget(label)
    apply_pill_badge_style(label, DesignTokens.COLOR_YELLOW, radius_px=DesignTokens.RADIUS_SM)

    ss = label.styleSheet()
    assert f"border-radius: {DesignTokens.RADIUS_SM}px" in ss
    assert DesignTokens.COLOR_YELLOW in ss


def test_badge_variant_primary_alias_for_filled(qtbot):
    """Vérifie que la classe Badge accepte variant='primary' comme alias de 'filled'."""
    badge = Badge("v1.0.0", variant="primary")
    qtbot.addWidget(badge)

    ss = badge.styleSheet()
    assert "border-radius: 9999px" in ss
    assert f"background-color: {DesignTokens.ACCENT_PRIMARY}" in ss
    assert f"color: {DesignTokens.TEXT_ON_ACCENT}" in ss


def test_collapsible_group_badge_is_pill(qtbot):
    """Vérifie que la pastille de comptage de CollapsibleSettingsGroup utilise la capsule fluide."""
    group = CollapsibleSettingsGroup("Avancé")
    qtbot.addWidget(group)
    group.add_widget(QLabel("item 1"))

    ss = group.lbl_badge.styleSheet()
    assert "border-radius: 9999px" in ss
    assert "10px" not in ss


def test_storage_tab_checkbox_indicator_radius(qtbot, mock_db):
    """Vérifie que le QSS du checkbox indicator de StorageTab utilise RADIUS_SM."""
    tab = StorageMaintenanceTab()
    qtbot.addWidget(tab)

    ss = tab.chk_clean_media_on_exit.styleSheet()
    assert f"border-radius: {DesignTokens.RADIUS_SM}px" in ss
    assert "border-radius: 4px;" not in ss

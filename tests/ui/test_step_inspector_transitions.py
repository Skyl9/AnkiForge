from typing import Any

import pytest
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.pipelines_view.widgets.step_inspector import StepInspectorPanel

pytestmark = pytest.mark.ui


def _contains_emoji(text: str) -> bool:
    """Vérifie si une chaîne contient des émojis ou symboles graphiques interdits."""
    forbidden = ["✅", "⚠️", "🛑", "⏭️", "🔀", "➡️", "↳", "📄", "📑", "📦"]
    return any(ch in text for ch in forbidden) or any(ord(ch) > 10000 for ch in text)


def test_step_inspector_dag_tab_scroll_area(qtbot: Any) -> None:
    """Vérifie que l'onglet DAG est enveloppé dans une QScrollArea fluide sans cadre."""
    inspector = StepInspectorPanel()
    qtbot.addWidget(inspector)

    assert hasattr(inspector, "dag_scroll"), "StepInspectorPanel doit exposer dag_scroll"
    assert isinstance(inspector.dag_scroll, QScrollArea)
    assert inspector.dag_scroll.widgetResizable() is True
    assert inspector.dag_scroll.frameShape() == QFrame.Shape.NoFrame


def test_step_inspector_dag_cards_semantic_tokens(qtbot: Any) -> None:
    """Vérifie que card_succ et card_fail appliquent les teintes sémantiques de DESIGN.md (§1.0)."""
    inspector = StepInspectorPanel()
    qtbot.addWidget(inspector)

    assert hasattr(inspector, "card_succ")
    assert hasattr(inspector, "card_fail")

    style_succ = inspector.card_succ.styleSheet()
    assert DesignTokens.COLOR_GREEN_BG in style_succ
    assert DesignTokens.COLOR_GREEN_BORDER in style_succ

    style_fail = inspector.card_fail.styleSheet()
    assert DesignTokens.COLOR_YELLOW_BG in style_fail
    assert DesignTokens.COLOR_YELLOW_BORDER in style_fail


def test_step_inspector_dag_no_text_emojis_and_phosphor_icons(qtbot: Any) -> None:
    """Vérifie l'élimination stricte de 100% des émojis texte au profit d'icônes Phosphor."""
    inspector = StepInspectorPanel()
    qtbot.addWidget(inspector)

    step_data = {
        "type": "LLM_PROMPT",
        "custom_title": "Étape Initiale",
        "on_success_order": None,
        "failure_behavior": "stop",
        "on_failure_order": None,
    }
    all_steps = [
        step_data,
        {"type": "HUMAN_VALIDATION", "custom_title": "Validation Humaine"},
        {"type": "MAP_REDUCE", "custom_title": "Synthèse Finale"},
    ]
    inspector.inspect_step(
        step_data=step_data,
        step_order=1,
        total_steps=3,
        personas=[],
        llms=[],
        all_steps=all_steps,
    )

    # Vérification des titres et labels de l'onglet DAG
    labels = inspector.dag_scroll.findChildren(QLabel)
    for lbl in labels:
        txt = lbl.text()
        assert not _contains_emoji(txt), f"Label contient un emoji interdit : {txt}"

    # Vérification combo_succ
    assert inspector.combo_succ.count() >= 3
    for idx in range(inspector.combo_succ.count()):
        txt = inspector.combo_succ.itemText(idx)
        assert not _contains_emoji(txt), f"combo_succ[{idx}] contient un emoji : {txt}"
        icon = inspector.combo_succ.itemIcon(idx)
        assert not icon.isNull(), f"combo_succ[{idx}] doit posséder une icône vectorielle"

    # Vérification combo_fail_beh
    assert inspector.combo_fail_beh.count() == 3
    for idx in range(inspector.combo_fail_beh.count()):
        txt = inspector.combo_fail_beh.itemText(idx)
        assert not _contains_emoji(txt), f"combo_fail_beh[{idx}] contient un emoji : {txt}"
        icon = inspector.combo_fail_beh.itemIcon(idx)
        assert not icon.isNull(), f"combo_fail_beh[{idx}] doit posséder une icône vectorielle"

    # Vérification combo_fail_target
    assert inspector.combo_fail_target.count() >= 3
    for idx in range(inspector.combo_fail_target.count()):
        txt = inspector.combo_fail_target.itemText(idx)
        assert not _contains_emoji(txt), f"combo_fail_target[{idx}] contient un emoji : {txt}"
        icon = inspector.combo_fail_target.itemIcon(idx)
        assert not icon.isNull(), f"combo_fail_target[{idx}] doit posséder une icône vectorielle"


def test_step_inspector_dag_branching_interactions(qtbot: Any) -> None:
    """Vérifie le masquage/affichage dynamique de l'étape de secours et la mise à jour des données."""
    inspector = StepInspectorPanel()
    qtbot.addWidget(inspector)

    step_data = {
        "type": "LLM_PROMPT",
        "custom_title": "Étape 1",
        "on_success_order": None,
        "failure_behavior": "stop",
        "on_failure_order": None,
    }
    inspector.inspect_step(
        step_data=step_data,
        step_order=1,
        total_steps=2,
        personas=[],
        llms=[],
        all_steps=[step_data, {"type": "HUMAN_VALIDATION", "custom_title": "Étape 2"}],
    )

    # Par défaut (stop) -> cible cachée
    assert inspector.row_fail_target_widget.isHidden()

    # Passer à continue -> toujours cachée
    idx_continue = inspector.combo_fail_beh.findData("continue")
    inspector.combo_fail_beh.setCurrentIndex(idx_continue)
    assert step_data["failure_behavior"] == "continue"
    assert inspector.row_fail_target_widget.isHidden()

    # Passer à goto_failure_step -> affichée
    idx_goto = inspector.combo_fail_beh.findData("goto_failure_step")
    inspector.combo_fail_beh.setCurrentIndex(idx_goto)
    assert step_data["failure_behavior"] == "goto_failure_step"
    assert not inspector.row_fail_target_widget.isHidden()

    # Sélectionner une étape cible de secours
    idx_target = inspector.combo_fail_target.findData(2)
    assert idx_target >= 0
    inspector.combo_fail_target.setCurrentIndex(idx_target)
    assert step_data["on_failure_order"] == 2

    # Sélectionner une étape de succès
    idx_succ = inspector.combo_succ.findData(2)
    assert idx_succ >= 0
    inspector.combo_succ.setCurrentIndex(idx_succ)
    assert step_data["on_success_order"] == 2

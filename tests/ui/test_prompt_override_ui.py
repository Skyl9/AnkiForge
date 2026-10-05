"""Tests UI de la surcharge locale de persona : bouton, figeage, indicateur et retrait."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from PySide6.QtWidgets import QLabel

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.persona_override import (
    OVERRIDE_FROZEN_AT_KEY,
    PROMPT_OVERRIDE_KEY,
    apply_persona_override,
)
from ankiforge.ui.dialogs.persona_prompt_override_dialog import PersonaPromptOverrideDialog
from ankiforge.ui.views.pipelines_view.widgets.step_inspector import StepInspectorPanel

pytestmark = pytest.mark.ui


def _panel_with_step(qtbot: Any, persona: PersonaModel | None, config: dict[str, Any] | None = None) -> StepInspectorPanel:
    inspector = StepInspectorPanel()
    qtbot.addWidget(inspector)
    inspector.inspect_step(
        step_data={"type": "LLM_PROMPT", "persona": persona, "config": dict(config or {})},
        step_order=1,
        total_steps=1,
        personas=[],
        llms=[],
    )
    return inspector


def _patch_editor(monkeypatch: Any, text: str) -> None:
    """Fait valider l'éditeur par un texte imposé, sans boucle d'événements Qt.

    `exec` doit renvoyer `Accepted` : l'inspecteur teste ce code de retour pour savoir
    s'il doit figer, et un `accept()` seul renverrait `None`, donc « annulation ».
    """

    def _fake_exec(self: PersonaPromptOverrideDialog) -> Any:
        self.edit_prompt.setPlainText(text)
        self.accept()
        return PersonaPromptOverrideDialog.DialogCode.Accepted

    monkeypatch.setattr(PersonaPromptOverrideDialog, "exec", _fake_exec)


def _visible_now(widget: Any) -> bool:
    """Un panneau jamais montré masque ses enfants : on interroge la volonté, pas l'écran."""
    return not widget.isHidden()


def test_inspecteur_expose_un_bouton_d_edition_du_prompt(qtbot: Any) -> None:
    """Critère d'acceptation : un bouton d'édition du prompt, distinct de l'aperçu."""
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    panel = _panel_with_step(qtbot, persona)

    bouton = panel.persona_card.btn_edit_prompt
    assert bouton.text() == "Surcharger le prompt..."
    assert bouton.isEnabled() is True


def test_placeholder_nomme_la_source_reelle_du_prompt_resolu(qtbot: Any) -> None:
    """Un champ vide désigne l'agent, pas un « prompt par défaut » de persona inexistant."""
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    panel = _panel_with_step(qtbot, persona)

    assert panel.edit_prompt.placeholderText() == "PROMPT AGENT"


def test_placeholder_nomme_le_defaut_du_fournisseur_sans_agent(qtbot: Any) -> None:
    panel = _panel_with_step(qtbot, None)

    assert "fournisseur" in panel.edit_prompt.placeholderText()


def test_placeholder_nomme_le_defaut_si_agent_sans_prompt(qtbot: Any) -> None:
    persona = PersonaModel(name="Vide", system_prompt="")
    panel = _panel_with_step(qtbot, persona)

    assert "fournisseur" in panel.edit_prompt.placeholderText()


def test_editeur_ouvre_une_surface_qui_annonce_la_portee_locale(qtbot: Any, contains_forbidden_glyph: Callable[[str], bool]) -> None:
    """L'éditeur doit promettre la local avant que l'utilisateur n'écrive."""
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    dlg = PersonaPromptOverrideDialog(persona=persona, parent=None)
    qtbot.addWidget(dlg)

    texts = " ".join(label.text() for label in dlg.findChildren(QLabel))
    assert "ne sera pas modifié" in texts
    assert contains_forbidden_glyph(texts) is False


def test_editeur_preremplit_le_prompt_de_l_agent(qtbot: Any) -> None:
    """On édite ce qui partira réellement : le champ vide désignerait ce texte."""
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    dlg = PersonaPromptOverrideDialog(persona=persona, parent=None)
    qtbot.addWidget(dlg)

    assert dlg.edit_prompt.toPlainText() == "PROMPT AGENT"


def test_editeur_preremplit_la_surcharge_existante(qtbot: Any) -> None:
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    dlg = PersonaPromptOverrideDialog(
        persona=persona,
        current_text="PROMPT SURCHARGE",
        config={PROMPT_OVERRIDE_KEY: "PROMPT SURCHARGE"},
        parent=None,
    )
    qtbot.addWidget(dlg)

    assert dlg.edit_prompt.toPlainText() == "PROMPT SURCHARGE"


def test_editeur_propose_le_retrait_seulement_si_il_y_a_une_surcharge(qtbot: Any) -> None:
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")

    sans = PersonaPromptOverrideDialog(persona=persona, config={}, parent=None)
    qtbot.addWidget(sans)
    assert _visible_now(sans.btn_clear) is False

    avec = PersonaPromptOverrideDialog(
        persona=persona,
        config={PROMPT_OVERRIDE_KEY: "SURCHARGE", OVERRIDE_FROZEN_AT_KEY: "2026-03-12T14:32:00"},
        parent=None,
    )
    qtbot.addWidget(avec)
    assert _visible_now(avec.btn_clear) is True


def test_editeur_ne_promet_pas_une_derive_sur_une_surcharge_non_figee(qtbot: Any) -> None:
    """Une surcharge ancienne n'a pas d'estampille : on ne prétend pas savoir depuis quand elle est figée."""
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    dlg = PersonaPromptOverrideDialog(
        persona=persona,
        config={PROMPT_OVERRIDE_KEY: "SURCHARGE ANCIENNE"},
        parent=None,
    )
    qtbot.addWidget(dlg)

    texts = " ".join(label.text() for label in dlg.findChildren(QLabel))
    assert "a été modifié depuis" not in texts


def test_editer_le_prompt_fige_la_surcharge_dans_l_etape(qtbot: Any, monkeypatch: Any) -> None:
    """Le bouton écrit une surcharge locale : la config de l'étape, jamais la persona."""
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    panel = _panel_with_step(qtbot, persona)

    _patch_editor(monkeypatch, "PROMPT SURCHARGE")
    panel.persona_card.btn_edit_prompt.click()

    assert panel.step_data["config"][PROMPT_OVERRIDE_KEY] == "PROMPT SURCHARGE"
    assert persona.system_prompt == "PROMPT AGENT"


def test_editer_deux_etapes_du_meme_agent_les_isole(qtbot: Any, monkeypatch: Any) -> None:
    persona = PersonaModel(name="Partage", system_prompt="PROMPT AGENT PARTAGE")

    panneau_a = _panel_with_step(qtbot, persona)
    panneau_b = _panel_with_step(qtbot, persona)

    _patch_editor(monkeypatch, "PROMPT POUR A")
    panneau_a.persona_card.btn_edit_prompt.click()

    _patch_editor(monkeypatch, "PROMPT POUR B")
    panneau_b.persona_card.btn_edit_prompt.click()

    assert panneau_a.step_data["config"][PROMPT_OVERRIDE_KEY] == "PROMPT POUR A"
    assert panneau_b.step_data["config"][PROMPT_OVERRIDE_KEY] == "PROMPT POUR B"


def test_indicateur_absent_sans_surcharge(qtbot: Any) -> None:
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    panel = _panel_with_step(qtbot, persona)

    assert _visible_now(panel.prompt_override_indicator) is False


def test_indicateur_signale_le_figeage_depuis_une_date(qtbot: Any) -> None:
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    config: dict[str, Any] = {}
    apply_persona_override(config, "PROMPT SURCHARGE", persona, now=datetime(2026, 3, 12, 14, 32))

    panel = _panel_with_step(qtbot, persona, config)

    assert _visible_now(panel.prompt_override_indicator) is True
    assert "12/03/2026 à 14:32" in panel.prompt_override_indicator.lbl_summary.text()


def test_modifier_l_agent_global_ne_bouge_pas_la_surcharge_et_signale_la_derive(qtbot: Any, contains_forbidden_glyph: Callable[[str], bool]) -> None:
    """Critère d'acceptation final : la persona change, la surcharge ne bouge pas, l'indicateur le dit."""
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    config: dict[str, Any] = {}
    apply_persona_override(config, "PROMPT SURCHARGE FIGE", persona, now=datetime(2026, 3, 12, 14, 32))

    panel = _panel_with_step(qtbot, persona, config)

    # L'agent partagé est réécrit après coup, comme le ferait son auteur depuis une autre vue.
    persona.system_prompt = "PROMPT AGENT REECRIT"
    panel.inspect_step(
        step_data={"type": "LLM_PROMPT", "persona": persona, "config": config},
        step_order=1,
        total_steps=1,
        personas=[],
        llms=[],
    )

    assert panel.step_data["config"][PROMPT_OVERRIDE_KEY] == "PROMPT SURCHARGE FIGE"
    assert panel.edit_prompt.toPlainText() == "PROMPT SURCHARGE FIGE"

    summary = panel.prompt_override_indicator.lbl_summary.text()
    assert _visible_now(panel.prompt_override_indicator) is True
    assert "a été modifié depuis" in summary
    assert contains_forbidden_glyph(summary) is False


def test_retirer_la_surcharge_rend_a_l_agent_son_prompt(qtbot: Any) -> None:
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    config: dict[str, Any] = {}
    apply_persona_override(config, "PROMPT SURCHARGE", persona, now=datetime(2026, 3, 12, 14, 32))

    panel = _panel_with_step(qtbot, persona, config)
    panel.prompt_override_indicator.btn_remove.click()

    assert PROMPT_OVERRIDE_KEY not in panel.step_data["config"]
    assert OVERRIDE_FROZEN_AT_KEY not in panel.step_data["config"]
    assert panel.edit_prompt.toPlainText() == ""
    assert _visible_now(panel.prompt_override_indicator) is False
    assert panel.edit_prompt.placeholderText() == "PROMPT AGENT"


def test_vider_le_champ_a_la_main_retire_egalement_la_surcharge(qtbot: Any) -> None:
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    config: dict[str, Any] = {}
    apply_persona_override(config, "PROMPT SURCHARGE", persona, now=datetime(2026, 3, 12, 14, 32))

    panel = _panel_with_step(qtbot, persona, config)
    panel.edit_prompt.setPlainText("")

    assert PROMPT_OVERRIDE_KEY not in panel.step_data["config"]
    assert OVERRIDE_FROZEN_AT_KEY not in panel.step_data["config"]


def test_indicateur_reste_muet_si_l_agent_na_bouge_puis(qtbot: Any) -> None:
    persona = PersonaModel(name="Architecte", system_prompt="PROMPT AGENT")
    config: dict[str, Any] = {}
    apply_persona_override(config, "PROMPT SURCHARGE", persona, now=datetime(2026, 3, 12, 14, 32))

    panel = _panel_with_step(qtbot, persona, config)

    assert "a été modifié depuis" not in panel.prompt_override_indicator.lbl_summary.text()


def test_surcharge_ne_cree_aucune_version_de_persona(qtbot: Any) -> None:
    """Critère d'acceptation : une surcharge est un réglage du pipeline, pas une version d'agent."""
    from ankiforge.database.models import PersonaVersionModel

    persona = PersonaModel.create(name="Partage", system_prompt="PROMPT AGENT", output_format="text")
    versions_avant = PersonaVersionModel.select().count()

    panel = _panel_with_step(qtbot, persona)
    apply_persona_override(panel.step_data["config"], "PROMPT SURCHARGE", persona)

    assert PersonaVersionModel.select().count() == versions_avant

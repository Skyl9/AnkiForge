"""Tests de la surcharge locale de persona : texte figé, dérive de l'agent, retrait."""

from datetime import datetime
from typing import Any

import pytest

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.persona_override import (
    OVERRIDE_BASE_DIGEST_KEY,
    OVERRIDE_FROZEN_AT_KEY,
    PROMPT_OVERRIDE_KEY,
    apply_persona_override,
    clear_persona_override,
    persona_override_state,
    prompt_override_field_hint,
    resolve_prompt_source,
    resolve_system_prompt,
)

pytestmark = pytest.mark.unit

FREEZE_DATE = datetime(2026, 3, 12, 14, 32)


def _persona(name: str = "Architecte", system_prompt: str = "PROMPT AGENT") -> PersonaModel:
    return PersonaModel(name=name, system_prompt=system_prompt)


def test_champ_vide_resout_vers_le_prompt_de_l_agent() -> None:
    assert resolve_system_prompt({}, _persona()) == "PROMPT AGENT"


def test_agent_sans_prompt_resout_vers_le_defaut_fourni() -> None:
    assert resolve_system_prompt({}, _persona(system_prompt=""), fallback="DEFAUT FOURNISSEUR") == "DEFAUT FOURNISSEUR"


def test_surcharge_prime_sur_le_prompt_de_l_agent() -> None:
    cfg = {PROMPT_OVERRIDE_KEY: "SURCHARGE LOCALE"}
    assert resolve_system_prompt(cfg, _persona()) == "SURCHARGE LOCALE"


def test_surcharge_blanche_est_ignoree() -> None:
    """Un espace seul ne masque pas l'agent : seuls des caractères non vides comptent comme surcharge."""
    assert resolve_system_prompt({PROMPT_OVERRIDE_KEY: "   \n "}, _persona()) == "PROMPT AGENT"


def test_reecrire_le_prompt_de_l_agent_le_fige_deliberement() -> None:
    """Épingler la version courante de l'agent est un geste valide : cela fige, et le dit."""
    persona = _persona()
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "PROMPT AGENT", persona, now=FREEZE_DATE)

    assert cfg[PROMPT_OVERRIDE_KEY] == "PROMPT AGENT"
    assert cfg[OVERRIDE_FROZEN_AT_KEY] == FREEZE_DATE.isoformat(timespec="seconds")
    assert persona_override_state(cfg, persona).active is True


def test_reformater_l_agent_ne_compte_pas_comme_une_derive() -> None:
    """Une indentation ou un retour à la ligne n'ont pas de fond : l'indicateur doit se taire."""
    persona = _persona(system_prompt="PROMPT\n  AGENT")
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", persona, now=FREEZE_DATE)

    persona.system_prompt = "PROMPT     AGENT"
    state = persona_override_state(cfg, persona)

    assert state.persona_changed_since_freeze is False


def test_source_reelle_designe_le_tiers_effectif() -> None:
    assert resolve_prompt_source({}, _persona()).source == "persona"
    assert resolve_prompt_source({}, _persona(system_prompt="")).source == "default"
    assert resolve_prompt_source({PROMPT_OVERRIDE_KEY: "SURCHARGE"}, _persona()).source == "override"


def test_indice_du_champ_vide_nomme_l_agent_affiche() -> None:
    assert prompt_override_field_hint(_persona()) == "PROMPT AGENT"


def test_indice_du_champ_vide_nomme_le_defaut_sans_agent() -> None:
    assert prompt_override_field_hint(_persona(system_prompt="")) == "prompt système par défaut du fournisseur LLM"
    assert prompt_override_field_hint(None) == "prompt système par défaut du fournisseur LLM"


def test_surcharge_figee_a_la_creation() -> None:
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", _persona(), now=FREEZE_DATE)

    assert cfg[PROMPT_OVERRIDE_KEY] == "SURCHARGE"
    assert cfg[OVERRIDE_FROZEN_AT_KEY] == FREEZE_DATE.isoformat(timespec="seconds")
    assert cfg[OVERRIDE_BASE_DIGEST_KEY]


def test_reecrire_la_surcharge_ne_redate_pas_le_figeage() -> None:
    """La date dit depuis quand le texte est figé, pas depuis quand on a fini de taper.

    Si elle se redatait à chaque frappe, elle perdrait tout son sens : elle dirait l'heure
    de la dernière touche au lieu de l'ancienneté réelle du prompt.
    """
    persona = _persona()
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", persona, now=FREEZE_DATE)

    apply_persona_override(cfg, "SURCHARGE AFFINÉE", persona, now=datetime(2026, 4, 1, 8, 0))

    assert cfg[PROMPT_OVERRIDE_KEY] == "SURCHARGE AFFINÉE"
    assert cfg[OVERRIDE_FROZEN_AT_KEY] == FREEZE_DATE.isoformat(timespec="seconds")


def test_modifier_l_agent_ne_bouge_pas_la_surcharge() -> None:
    """Critère central : la surcharge est figée, l'agent peut bouger sans l'entraîner."""
    persona = _persona()
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", _persona(), now=FREEZE_DATE)

    persona.system_prompt = "PROMPT AGENT RÉÉCRIT"

    assert resolve_system_prompt(cfg, persona) == "SURCHARGE"
    assert cfg[PROMPT_OVERRIDE_KEY] == "SURCHARGE"


def test_indicateur_signale_que_l_agent_a_bouge_depuis_le_figeage() -> None:
    persona = _persona()
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", persona, now=FREEZE_DATE)

    assert persona_override_state(cfg, persona).persona_changed_since_freeze is False

    persona.system_prompt = "PROMPT AGENT RÉÉCRIT"
    state = persona_override_state(cfg, persona)

    assert state.active is True
    assert state.persona_changed_since_freeze is True
    assert state.frozen_at == FREEZE_DATE


def test_indicateur_ne_signale_rien_si_l_agent_na_bouge() -> None:
    persona = _persona()
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", persona, now=FREEZE_DATE)

    state = persona_override_state(cfg, persona)

    assert state.persona_changed_since_freeze is False
    assert "a été modifié depuis" not in state.summary


def test_changement_d_agent_compte_comme_une_derive() -> None:
    """On fige l'agent, pas seulement son texte : remplacer l'agent invalide le repère."""
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", PersonaModel(id=1, name="A", system_prompt="PROMPT AGENT"), now=FREEZE_DATE)

    other = PersonaModel(id=2, name="A", system_prompt="PROMPT AGENT")
    assert persona_override_state(cfg, other).persona_changed_since_freeze is True


def test_vider_la_surcharge_rend_a_l_agent_son_prompt() -> None:
    persona = _persona()
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", persona, now=FREEZE_DATE)

    clear_persona_override(cfg, persona)

    assert cfg == {}
    assert resolve_system_prompt(cfg, persona) == "PROMPT AGENT"


def test_vider_le_champ_dans_lediteur_equivaut_a_un_retrait() -> None:
    persona = _persona()
    cfg: dict[str, Any] = {}
    apply_persona_override(cfg, "SURCHARGE", persona, now=FREEZE_DATE)

    apply_persona_override(cfg, "   ", persona, now=FREEZE_DATE)

    assert cfg == {}
    assert persona_override_state(cfg, persona).active is False


def test_surcharge_sans_empreinte_ancienne_reste_lisible() -> None:
    """Les profils existants ont un `prompt_override` nu : il doit rester honoré, sans faux signal."""
    persona = _persona()
    cfg = {PROMPT_OVERRIDE_KEY: "ANCIENNE SURCHARGE"}

    state = persona_override_state(cfg, persona)

    assert state.active is True
    assert state.persona_changed_since_freeze is False
    assert state.frozen_at is None
    assert "date inconnue" in state.summary
    assert resolve_system_prompt(cfg, persona) == "ANCIENNE SURCHARGE"


def test_deux_pipelines_surchargeant_le_meme_agent_ne_se_voient_pas() -> None:
    """La surcharge est un réglage d'étape : aucun état partagé entre deux définitions."""
    persona = _persona()
    pipeline_a: dict[str, Any] = {"prompt_override": "PROMPT POUR A"}
    pipeline_b: dict[str, Any] = {"prompt_override": "PROMPT POUR B"}

    apply_persona_override(pipeline_a, "PROMPT POUR A", persona, now=FREEZE_DATE)

    assert pipeline_b[PROMPT_OVERRIDE_KEY] == "PROMPT POUR B"
    assert resolve_system_prompt(pipeline_a, persona) == "PROMPT POUR A"
    assert resolve_system_prompt(pipeline_b, persona) == "PROMPT POUR B"

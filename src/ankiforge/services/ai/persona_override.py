"""
Surcharge locale de persona : un prompt propre à une étape de pipeline.

Une surcharge est un **réglage du pipeline**, pas une version d'agent. Elle vit dans
la `config_data` de l'étape, n'est jamais journalisée dans `PersonaVersionModel`, et
deux étapes qui surchargent le même agent ne se voient jamais.

Elle est **figée** : elle conserve le texte qu'elle portait à sa création et ne suit
pas les réécritures ultérieures de l'agent. Pour que l'auteur ne croie pas disposer du
prompt courant, on estampille au figeage l'empreinte de l'agent et la date, et on signale
toute dérive.

Ce module est la **couture unique** de cette notion : l'orchestrateur, l'interpréteur de
prompts et l'inspecteur d'étape consomment tous cette résolution, afin qu'un champ vide
n'ait jamais trois définitions différentes.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ankiforge.database.models import PersonaModel

logger = logging.getLogger(__name__)

PROMPT_OVERRIDE_KEY = "prompt_override"
"""Clé de `config_data` portant le texte figé de la surcharge (préexistante)."""

OVERRIDE_FROZEN_AT_KEY = "prompt_override_frozen_at"
"""Horodatage ISO du figeage : « depuis quand » ce texte est-il figé ?"""

OVERRIDE_BASE_DIGEST_KEY = "prompt_override_base_digest"
"""Empreinte de l'agent au moment du figeage : sert à détecter sa dérive."""

OVERRIDE_BASE_PERSONA_KEY = "prompt_override_base_persona_id"
"""Identifiant de l'agent figé : changer d'agent invalide le repère, pas seulement son texte."""

OVERRIDE_META_KEYS = (PROMPT_OVERRIDE_KEY, OVERRIDE_FROZEN_AT_KEY, OVERRIDE_BASE_DIGEST_KEY, OVERRIDE_BASE_PERSONA_KEY)
"""Toutes les clés d'une surcharge : les lever, c'est retirer ces quatre clés, sans exception."""

MAP_REDUCE_FALLBACK_PROMPT = "Analyser et traiter le contenu."
"""Défaut historique de l'étape MAP_REDUCE, utilisé quand ni surcharge ni agent ne parlent."""

_FROZEN_DATE_FORMAT = "%d/%m/%Y à %H:%M"
_WHITESPACE_RUN = re.compile(r"\s+")


def _clean(value: Any) -> str:
    """Normalise une valeur de config en texte, sans jamais renvoyer None."""
    return str(value).strip() if value else ""


def persona_prompt(persona: PersonaModel | None) -> str:
    """Texte du prompt système porté par l'agent, ou chaîne vide s'il n'y en a pas."""
    return _clean(persona.system_prompt) if persona is not None else ""


def persona_label(persona: PersonaModel | None) -> str:
    """Nom lisible de l'agent, utilisé pour nommer la source réelle du prompt résolu."""
    return _clean(persona.name) if persona is not None else ""


def _digest(text: str) -> str:
    """Empreinte de comparaison insensible à la mise en forme.

    Un agent reformaté — espaces, retours à la ligne, indentation — n'a pas changé de
    fond : le signaler comme une dérive apprendrait à l'auteur à ignorer l'indicateur.
    """
    return hashlib.sha256(_WHITESPACE_RUN.sub(" ", text).strip().encode("utf-8")).hexdigest()


def frozen_date_label(frozen_at: datetime | None) -> str:
    """Datation lisible du figeage, y compris pour une surcharge ancienne sans estampille."""
    return f"le {frozen_at:{_FROZEN_DATE_FORMAT}}" if frozen_at else "à une date inconnue"


@dataclass(frozen=True)
class PromptSource:
    """Résolution du prompt système d'une étape, avec le tiers dont il provient réellement."""

    text: str
    source: str  # "override" | "persona" | "default"
    persona_name: str | None = None


@dataclass(frozen=True)
class PersonaOverrideState:
    """État d'une surcharge locale, tel que l'inspecteur doit le raconter."""

    active: bool
    frozen_at: datetime | None
    persona_name: str | None
    persona_changed_since_freeze: bool
    summary: str


def _read_meta(config: dict[str, Any]) -> tuple[datetime | None, str | None, int | None]:
    raw_at = _clean(config.get(OVERRIDE_FROZEN_AT_KEY))
    frozen_at: datetime | None = None
    if raw_at:
        try:
            frozen_at = datetime.fromisoformat(raw_at)
        except ValueError:
            logger.warning("Horodatage de surcharge illisible, la dérive de l'agent ne sera pas signalée : %s", raw_at)
    raw_id = config.get(OVERRIDE_BASE_PERSONA_KEY)
    persona_id = raw_id if isinstance(raw_id, int) else None
    return frozen_at, _clean(config.get(OVERRIDE_BASE_DIGEST_KEY)) or None, persona_id


def resolve_prompt_source(config: dict[str, Any] | None, persona: PersonaModel | None) -> PromptSource:
    """Résout le prompt système d'une étape et désigne nommément sa source réelle.

    L'ordre est `surcharge figée → agent de l'étape → défaut du fournisseur` ; un champ
    laissé vide ou réduit à des espaces ne masque jamais l'agent.
    """
    override = _clean((config or {}).get(PROMPT_OVERRIDE_KEY))
    name = persona_label(persona) or None
    if override:
        return PromptSource(text=override, source="override", persona_name=name)
    base = persona_prompt(persona)
    if base:
        return PromptSource(text=base, source="persona", persona_name=name)
    return PromptSource(text="", source="default", persona_name=name)


def resolve_system_prompt(config: dict[str, Any] | None, persona: PersonaModel | None, *, fallback: str = "") -> str:
    """Prompt système à envoyer au fournisseur, sans raisonnement dupliqué."""
    return resolve_prompt_source(config, persona).text or fallback


def prompt_override_field_hint(persona: PersonaModel | None) -> str:
    """Texte d'indication du champ de surcharge : il nomme la source **réelle** du prompt résolu.

    L'indication doit décrire ce que fait le code, pas ce que l'on suppose : un champ vide
    ne retombe pas sur un « prompt par défaut » de persona, il retombe sur l'agent affiché
    au-dessus — et, à défaut d'agent, sur le prompt système du fournisseur.
    """
    return persona_prompt(persona) or "prompt système par défaut du fournisseur LLM"


def persona_override_state(config: dict[str, Any] | None, persona: PersonaModel | None) -> PersonaOverrideState:
    """Décrit la surcharge locale et signale une dérive de l'agent depuis son figeage.

    Une surcharge sans estampille (profils antérieurs à cette feature) reste active et
    lisible, mais ne déclenche aucun signal de dérive : on ne prétend pas savoir depuis
    quand un texte que l'on n'a pas figé l'a été.
    """
    config = config or {}
    override = _clean(config.get(PROMPT_OVERRIDE_KEY))
    frozen_at, base_digest, base_persona_id = _read_meta(config)
    persona_name = persona_label(persona) or None

    if not override:
        return PersonaOverrideState(
            active=False,
            frozen_at=None,
            persona_name=persona_name,
            persona_changed_since_freeze=False,
            summary="",
        )

    # On fige l'agent, pas seulement son texte : le remplacer invalide le repère aussi.
    drifted = False
    if base_digest is not None:
        drifted = base_digest != _digest(persona_prompt(persona))
    if base_persona_id is not None:
        drifted = drifted or (persona.id if persona is not None else None) != base_persona_id

    when = frozen_date_label(frozen_at)
    agent = persona_name or "sans nom"
    if drifted:
        summary = f"Surcharge figée {when} ; l'agent « {agent} » a été modifié depuis. Votre texte est conservé tel quel, il ne suit pas l'agent."
    else:
        summary = f"Surcharge figée {when} ; l'agent « {agent} » est inchangé."

    return PersonaOverrideState(
        active=True,
        frozen_at=frozen_at,
        persona_name=persona_name,
        persona_changed_since_freeze=drifted,
        summary=summary,
    )


def apply_persona_override(
    config: dict[str, Any],
    text: str,
    persona: PersonaModel | None,
    *,
    now: datetime | None = None,
) -> PersonaOverrideState:
    """Écrit la surcharge locale et fige l'agent dont elle est dérivée.

    L'estampille est posée au **passage à l'état figé**, une fois pour toutes : réécrire
    le texte ne la redate pas, car la date doit rester « depuis quand ce texte a-t-il été
    figé », et non « depuis quand ai-je fini de taper ». Un agent modifié depuis reste donc
    signalé, même si l'on affine sa surcharge — c'est le but de l'indicateur.

    Réécrire une surcharge identique à celle de l'agent est un **acte de figeage
    volontaire** : cela épingle la version courante avant qu'elle ne bouge, et rien ici ne
    peut le distinguer d'un oubli. Vider le champ, en revanche, lève la surcharge : c'est
    le seul geste qui restitue à l'agent la parole.
    """
    new_text = _clean(text)
    if not new_text:
        return clear_persona_override(config, persona)

    config[PROMPT_OVERRIDE_KEY] = new_text

    # L'estampille ne se pose qu'au passage à l'état figé ; réécrire le texte la conserve.
    if _read_meta(config)[0] is None:
        config[OVERRIDE_FROZEN_AT_KEY] = (now or datetime.now()).isoformat(timespec="seconds")
        config[OVERRIDE_BASE_DIGEST_KEY] = _digest(persona_prompt(persona))
        # Une étape sans agent n'a pas d'identité à figer : on n'écrit pas de clé nulle.
        if persona is not None:
            config[OVERRIDE_BASE_PERSONA_KEY] = persona.id

    return persona_override_state(config, persona)


def clear_persona_override(config: dict[str, Any], persona: PersonaModel | None = None) -> PersonaOverrideState:
    """Retire la surcharge locale et rend à l'agent son prompt d'origine."""
    for key in OVERRIDE_META_KEYS:
        config.pop(key, None)
    return persona_override_state(config, persona)

"""Environnement Jinja2 durci pour l'interpolation des prompts LLM et des templates texte.

Les templates (personas, prompts DAG) sont partiellement contrôlés par l'utilisateur
ou provenant de bases de données : ils peuvent donc contenir des accès réflexifs à
l'interpréteur (ex. ``{{ ''.__class__.__mro__ }}``). On les rend avec
``SandboxedEnvironment`` qui refuse l'accès aux attributs dangereux.

Note : ``autoescape=False`` est volontaire — ces templates produisent du texte/JSON
destiné à un LLM, jamais du HTML. L'auto-échappement corromprait les sorties.
L'alerte Bandit B701 est donc un faux positif pour ce cas d'usage précis.
"""

from __future__ import annotations

from jinja2 import BaseLoader
from jinja2.sandbox import SandboxedEnvironment


def create_prompt_environment() -> SandboxedEnvironment:
    """Construit un environnement Jinja2 sandboxé pour les templates de prompts.

    - Chargeur vide (aucune lecture de fichier/gabarit depuis le disque).
    - ``autoescape=False`` : sortie texte/JSON pour un LLM (pas de HTML).
    - Sandbox Jinja2 : blocage des attributs réflexifs dangereux (``__class__``,
      ``__mro__``, etc.) quand les templates proviennent de sources tierces.
    """
    return SandboxedEnvironment(
        loader=BaseLoader(),
        autoescape=False,  # nosec B701  # sortie texte/JSON pour LLM, jamais de HTML
    )

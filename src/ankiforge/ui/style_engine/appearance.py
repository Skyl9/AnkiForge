"""Les deux axes d'apparence : Famille de Thème × Source du Mode (cf. ADR 0004).

Avant ce refactoring, la préférence d'apparence était un identifiant de thème unique qui
portait deux notions distinctes : l'identité graphique choisie (la Famille) et le régime
visuel (Sombre ou Clair). Ce module détache les deux axes ; la Variante effectivement
appliquée n'est plus stockée, elle se calcule.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class ModeSource(StrEnum):
    """Origine du régime visuel : un choix manuel, ou le suivi du système."""

    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"

    @property
    def is_manual(self) -> bool:
        return self is not ModeSource.SYSTEM

    @classmethod
    def coerce(cls, value: object, default: ModeSource | None = None) -> ModeSource:
        """Interprète une valeur stockée tolérantment, sans jamais lever sur une donnée abstraite."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except (ValueError, AttributeError, TypeError):
            return default if default is not None else cls.DARK


_forced_system_mode_source: ModeSource | None = None
_system_regime_is_forced = False


def force_system_mode_source(regime: ModeSource | None) -> None:
    """Fixe le régime annoncé par la plateforme.

    ``None`` signifie « la plateforme n'en déclare aucun » : la sonde retourne alors ``None``
    au lieu d'interroger Qt. Réservé aux tests et au suivi temps réel du thème système.
    """
    global _forced_system_mode_source, _system_regime_is_forced
    _forced_system_mode_source = regime if regime is not None and regime is not ModeSource.SYSTEM else None
    _system_regime_is_forced = True


def release_system_mode_source() -> None:
    """Supprime la surcharge : la détection réelle de la plateforme redevient effective."""
    global _forced_system_mode_source, _system_regime_is_forced
    _forced_system_mode_source = None
    _system_regime_is_forced = False


def probe_system_mode_source() -> ModeSource | None:
    """Régime visuel déclaré par la plateforme, ou ``None`` si elle n'en déclare aucun.

    Interroge l'interface Qt sans exiger d'instance ``QApplication`` : au démarrage comme
    dans les scripts de capture, la sonde ne doit rien lever.
    """
    if _system_regime_is_forced:
        return _forced_system_mode_source
    return _detect_system_mode_source()


def _detect_system_mode_source() -> ModeSource | None:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    try:
        scheme = QGuiApplication.styleHints().colorScheme()
    except (AttributeError, RuntimeError) as err:
        logger.debug("Sonde de thème système indisponible sur cette plateforme : %s", err)
        return None
    if scheme == Qt.ColorScheme.Dark:
        return ModeSource.DARK
    if scheme == Qt.ColorScheme.Light:
        return ModeSource.LIGHT
    return None


@dataclass(frozen=True)
class AppearancePreference:
    """Les deux axes persistés de l'apparence, par profil.

    ``family_id`` vaut ``None`` lorsque l'utilisateur n'a jamais choisi de Famille : ce n'est
    pas une erreur, cela signifie « suit la Famille par défaut du layout actif ».
    ``last_manual_mode`` mémorise le dernier régime choisi à la main, afin de servir de
    repli quand le système ne déclare aucun régime.
    """

    family_id: str | None
    mode_source: ModeSource
    last_manual_mode: ModeSource

    def __post_init__(self) -> None:
        mode_source = ModeSource.coerce(self.mode_source, default=ModeSource.DARK)
        last_manual = ModeSource.coerce(self.last_manual_mode, default=ModeSource.DARK)
        if not last_manual.is_manual:
            last_manual = ModeSource.DARK
        if mode_source.is_manual:
            # Un régime choisi à la main est par nature le dernier régime choisi à la main.
            last_manual = mode_source
        object.__setattr__(self, "mode_source", mode_source)
        object.__setattr__(self, "last_manual_mode", last_manual)

    @classmethod
    def default(cls) -> AppearancePreference:
        return cls(family_id=None, mode_source=ModeSource.DARK, last_manual_mode=ModeSource.DARK)

    def resolve_mode(self) -> ModeSource:
        """Régime effectif : la Source si elle est manuelle, sinon le système, sinon le repli."""
        if self.mode_source.is_manual:
            return self.mode_source
        return probe_system_mode_source() or self.last_manual_mode

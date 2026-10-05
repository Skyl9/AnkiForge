"""
Compatibilité Vision du moteur IA sélectionné : politique unique, libellés et indicateurs partagés.

Le Studio de Création et la Batch Factory exposent tous deux une bascule « Vision ». Cette
bascule n'a de sens que si le moteur sélectionné sait lire des images : transmettre un payload
multimodal à un modèle texte seul (DeepSeek-R1, o1-mini, Llama3-8b…) provoque une erreur d'API.
Ce module concentre la résolution de cette compatibilité afin que les deux vues n'aient
qu'une seule interprétation — et un seul endroit à corriger quand la règle change.

La capacité **déclarée** sur la configuration du moteur fait seule autorité. Le catalogue
`ModelCatalog` n'est qu'un *écrivain* : il renseigne la colonne à la création d'un moteur, puis ne
doit plus jamais être consulté à la lecture. Le catalogue est une aide à la découverte — il
rapproche par nom et **ignore le fournisseur** (`get_model_spec("azure-openai", "gpt-4o")` recopie la
fiche OpenAI) ; deviner à la lecture afficherait un verdict — « Vision native » ou « Vision
indisponible » — qu'aucune donnée ne vient soutenir, et l'envoi d'un payload multimodal vers une API
qui le refuse.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QWidget

from ankiforge.ui.components.badges import Badge

VISION_SUPPORTED_LABEL = "Vision native"
VISION_UNSUPPORTED_LABEL = "Modèle texte seul — Vision non supportée"
VISION_UNVERIFIED_LABEL = "Vision non vérifiée"
VISION_UNSUPPORTED_BADGE_LABEL = "Vision non supportée"

VISION_UNSUPPORTED_HINT = f"{VISION_UNSUPPORTED_LABEL} : les images du document seront ignorées pour ne déclencher aucune erreur d'API. Choisissez un moteur multimodal pour les analyser."

VISION_TOOLTIP = (
    "Vision Multimodale\n\n"
    "• ON — chaque image du document (figure, schéma, planche, capture) est encodée en base64 et "
    "jointe au prompt dans un payload multimodal : le modèle analyse les visuels, au prix de tokens "
    "supplémentaires et d'un appel plus lent.\n"
    "• OFF — les images sont retirées du texte avant l'appel : la génération est plus rapide et moins "
    "coûteuse, mais aucun contenu visuel n'est pris en compte."
)

_NO_ENGINE_TOOLTIP = "Aucun moteur sélectionné : la compatibilité Vision n'a pas pu être vérifiée."


def resolve_vision_support(engine: Any | None) -> bool | None:
    """Retourne la compatibilité Vision déclarée d'un moteur, ou None si aucun moteur n'est sélectionné.

    La valeur lue sur la configuration est la source de vérité : elle vaut aussi bien pour un
    modèle multimodal connu du catalogue que pour un modèle local détecté avec un projecteur CLIP
    (que le catalogue, hors ligne, ignore). Un `False` déclaré n'est jamais remis en cause.
    """
    if engine is None:
        return None
    return bool(getattr(engine, "supports_vision", False))


def effective_vision(preference: bool, engine: Any | None) -> bool:
    """Vision réellement transmise au modèle : la préférence ne vaut jamais sur une incompatibilité."""
    return bool(preference) and resolve_vision_support(engine) is not False


def vision_tooltip(engine: Any | None) -> str:
    """Infobulle du mécanisme Vision, complétée par le verdict du moteur sélectionné."""
    tooltip = VISION_TOOLTIP
    status = resolve_vision_support(engine)
    if status is False:
        return f"{tooltip}\n\n⚠ {VISION_UNSUPPORTED_HINT}"
    if status is None:
        return f"{tooltip}\n\n{_NO_ENGINE_TOOLTIP}"
    return tooltip


class VisionCapabilityBadge(Badge):
    """Badge de compatibilité Vision du moteur sélectionné (partagé par les deux vues)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(VISION_UNVERIFIED_LABEL, variant="neutral", parent=parent)
        # `Any` par contrat : `Badge.set_variant` attend le profil de thème du `StyleEngine`, dont le
        # type n'appartient qu'à la couche thème — ce composant se contente de le repasser.
        self._profile: Any = None
        self.set_support_status(None)

    def set_support_status(self, status: bool | None) -> None:
        """Affiche le verdict : compatible, incompatible, ou inconnu faute de moteur."""
        if status is True:
            self.setText(VISION_SUPPORTED_LABEL)
            self.set_variant("info", self._profile)
            self.setToolTip(self.tr("Ce moteur analyse les images du document (payload multimodal)."))
        elif status is False:
            self.setText(VISION_UNSUPPORTED_BADGE_LABEL)
            self.set_variant("danger", self._profile)
            self.setToolTip(VISION_UNSUPPORTED_HINT)
        else:
            self.setText(VISION_UNVERIFIED_LABEL)
            self.set_variant("neutral", self._profile)
            self.setToolTip(_NO_ENGINE_TOOLTIP)

    def refresh_theme(self, profile: Any) -> None:
        """Mémorise le profil pour que les changements de verdict tardifs restent teintés."""
        self._profile = profile
        super().refresh_theme(profile)


class VisionCapabilityNotice(QLabel):
    """Rappel persistant du motif de blocage, lisible sans survol.

    Une infobulle disparaît dès que le curseur repart : un réglage grisé sans raison affichée
    laisse l'utilisateur supposer un bug. Ce bandeau reste donc à l'écran, et le message exact
    est la chaîne canonique `VISION_UNSUPPORTED_LABEL`.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(VISION_UNSUPPORTED_LABEL, parent)
        self.setObjectName("visionCapNotice")
        self.setWordWrap(True)
        self.setVisible(False)

    def set_support_status(self, status: bool | None) -> None:
        """Visible uniquement sur une incompatibilité avérée : rien à signaler sinon."""
        self.setVisible(status is False)


def sync_vision_capability(badge: VisionCapabilityBadge, notice: VisionCapabilityNotice, engine: Any | None, *widgets: QWidget) -> bool | None:
    """Unique point de synchronisation des deux vues : badge, rappel, infobulles et disponibilité.

    Renvoie la compatibilité résolue pour que l'appelant n'ait pas à la recalculer. Seul un verdict
    `False` désactive les widgets : un moteur inconnu ne doit pas bloquer un utilisateur qui configure
    un moteur multimodal non encore décrit dans le catalogue.
    """
    status = resolve_vision_support(engine)
    badge.set_support_status(status)
    notice.set_support_status(status)
    tooltip = vision_tooltip(engine)
    for widget in widgets:
        widget.setToolTip(tooltip)
        widget.setEnabled(status is not False)
    return status


__all__ = [
    "VISION_SUPPORTED_LABEL",
    "VISION_TOOLTIP",
    "VISION_UNSUPPORTED_BADGE_LABEL",
    "VISION_UNSUPPORTED_HINT",
    "VISION_UNSUPPORTED_LABEL",
    "VISION_UNVERIFIED_LABEL",
    "VisionCapabilityBadge",
    "VisionCapabilityNotice",
    "effective_vision",
    "resolve_vision_support",
    "sync_vision_capability",
    "vision_tooltip",
]

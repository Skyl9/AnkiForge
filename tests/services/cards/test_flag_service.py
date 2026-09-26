"""
Tests unitaires et d'intégration pour FlagService :
- Récupération des libellés par défaut (fallback DesignTokens.FLAG_NAMES)
- Définition et persistance des libellés personnalisés par profil via SettingsService / SettingModel
- Récupération unitaire par get_flag_name()
- Génération de la table de recherche unifiée get_flag_search_map()
- Émission de FlagLabelsUpdatedEvent sur l'EventBus
"""

from __future__ import annotations

import pytest

from ankiforge.services.cards.flag_service import FlagService
from ankiforge.utils.event_bus import FlagLabelsUpdatedEvent, event_bus

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def clean_flags():
    """Isole chaque test en réinitialisant les drapeaux avant et après l'exécution."""
    FlagService.reset_to_defaults()
    yield
    FlagService.reset_to_defaults()


def test_flag_service_default_labels() -> None:
    """Sans configuration spécifique, FlagService renvoie les libellés de DesignTokens."""

    labels = FlagService.get_flag_labels()
    assert len(labels) == 8
    assert labels[0] == "Aucun"
    assert labels[1] == "Rouge"
    assert labels[2] == "Orange"
    assert labels[3] == "Vert"
    assert labels[4] == "Bleu"
    assert labels[5] == "Rose"
    assert labels[6] == "Turquoise"
    assert labels[7] == "Violet"

    assert FlagService.get_flag_name(0) == "Aucun"
    assert FlagService.get_flag_name(1) == "Rouge"
    assert FlagService.get_flag_name(7) == "Violet"
    assert FlagService.get_flag_name(99) == "Aucun"


def test_flag_service_set_and_get_custom_labels() -> None:
    """La personnalisation des drapeaux est persistée et les drapeaux non modifiés conservent le défaut."""
    FlagService.reset_to_defaults()

    received_events: list[FlagLabelsUpdatedEvent] = []

    def on_event(ev: FlagLabelsUpdatedEvent) -> None:
        received_events.append(ev)

    event_bus.subscribe(FlagLabelsUpdatedEvent, on_event)
    try:
        FlagService.set_flag_labels({1: "À revoir", 4: "Formule"})

        labels = FlagService.get_flag_labels()
        assert labels[1] == "À revoir"
        assert labels[4] == "Formule"
        # Les autres restent par défaut
        assert labels[2] == "Orange"
        assert labels[3] == "Vert"
        assert labels[5] == "Rose"
        assert labels[6] == "Turquoise"
        assert labels[7] == "Violet"

        # get_flag_name
        assert FlagService.get_flag_name(1) == "À revoir"
        assert FlagService.get_flag_name(4) == "Formule"
        assert FlagService.get_flag_name(2) == "Orange"

        # Vérification émission événement
        assert len(received_events) >= 1
        assert received_events[-1].labels[1] == "À revoir"
    finally:
        event_bus.unsubscribe(FlagLabelsUpdatedEvent, on_event)


def test_flag_service_reset_single_label() -> None:
    """Un libellé vide ou blanc revient au nom par défaut."""
    FlagService.reset_to_defaults()
    FlagService.set_flag_labels({1: "Critique"})
    assert FlagService.get_flag_name(1) == "Critique"

    # Reset en passant une chaîne vide
    FlagService.set_flag_labels({1: ""})
    assert FlagService.get_flag_name(1) == "Rouge"


def test_flag_service_search_map() -> None:
    """La table de recherche contient les alias par défaut ainsi que les libellés personnalisés normalisés."""
    FlagService.reset_to_defaults()
    FlagService.set_flag_labels({1: "Vocabulaire Prioritaire", 3: "Grammaire"})

    search_map = FlagService.get_flag_search_map()

    # Alias standards conservés
    assert search_map["1"] == 1
    assert search_map["red"] == 1
    assert search_map["rouge"] == 1
    assert search_map["3"] == 3
    assert search_map["green"] == 3
    assert search_map["vert"] == 3

    # Nouveaux alias personnalisés (minuscules)
    assert search_map["vocabulaire prioritaire"] == 1
    assert search_map["vocabulaire_prioritaire"] == 1
    assert search_map["grammaire"] == 3

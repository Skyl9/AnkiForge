"""
Repository for Deck models and subdeck hierarchy management.
"""

from __future__ import annotations

import logging

from ankiforge.database.models import CardModel, DeckModel
from ankiforge.repositories.base import BaseRepository
from ankiforge.utils.hierarchy import descendants_prefix, join_hierarchy, split_hierarchy

logger = logging.getLogger(__name__)


class DeckRepository(BaseRepository):
    """Data access repository for Anki decks and subdeck hierarchies."""

    def get_all_decks(self) -> list[DeckModel]:
        """Retrieve all decks ordered alphabetically by name."""
        return list(DeckModel.select().order_by(DeckModel.name.asc()))

    def get_deck_by_id(self, deck_id: int) -> DeckModel | None:
        """Retrieve a deck by its primary key ID."""
        try:
            return DeckModel.get_or_none(DeckModel.id == deck_id)
        except Exception as e:
            logger.error("Failed to retrieve deck %s: %s", deck_id, e)
            return None

    def get_deck_by_name(self, name: str) -> DeckModel | None:
        """Retrieve a deck by its exact name."""
        try:
            return DeckModel.get_or_none(DeckModel.name == name)
        except Exception as e:
            logger.error("Failed to retrieve deck by name '%s': %s", name, e)
            return None

    def get_or_create_deck(self, name: str, description: str = "") -> DeckModel:
        """Retrieve an existing deck or create a new one."""
        existing = self.get_deck_by_name(name)
        if existing:
            return existing
        return self.create_deck(name=name, description=description)

    def get_or_create_deck_hierarchical(self, name: str, description: str = "") -> DeckModel:
        """
        Retrieve or create a deck, ensuring all parent decks in the 'Parent::Child'
        hierarchy are created and properly linked via parent_deck.
        """
        parts = split_hierarchy(name) or ["Par défaut"]

        current_deck: DeckModel | None = None

        with self.atomic():
            for i in range(len(parts)):
                accumulated_name = join_hierarchy(parts[: i + 1])
                existing = self.get_deck_by_name(accumulated_name)
                current_deck = existing or DeckModel.create(
                    name=accumulated_name,
                    description=description if i == len(parts) - 1 else "",
                    parent_deck=current_deck,
                )
        if current_deck is None:
            raise ValueError(f"Impossible de créer ou récupérer le paquet : {name}")
        return current_deck

    def create_deck(
        self,
        name: str,
        description: str = "",
        parent_deck: DeckModel | None = None,
    ) -> DeckModel:
        """Create a new deck."""
        with self.atomic():
            return DeckModel.create(
                name=name,
                description=description,
                parent_deck=parent_deck,
            )

    def rename_deck(self, deck_id: int, new_name: str) -> DeckModel | None:
        """Rename an existing deck and update subdeck prefixes if necessary."""
        deck = self.get_deck_by_id(deck_id)
        if not deck:
            return None

        old_name = deck.name
        with self.atomic():
            deck.name = new_name
            deck.save()

            # Update child subdecks prefix
            old_prefix = descendants_prefix(old_name)
            new_prefix = descendants_prefix(new_name)
            children = list(DeckModel.select().where(DeckModel.name.startswith(old_prefix)))
            for child in children:
                child.name = new_prefix + child.name[len(old_prefix) :]
                child.save()

            return deck

    def delete_deck(self, deck_id: int) -> bool:
        """Delete a deck and cascade deletion to subdecks and cards."""
        deck = self.get_deck_by_id(deck_id)
        if not deck:
            return False

        with self.atomic():
            deck.delete_instance(recursive=True)
            return True

    def get_descendant_decks(self, deck_name: str) -> list[DeckModel]:
        """Retrieve a deck and all its subdecks based on hierarchy prefix."""
        return list(DeckModel.select().where((DeckModel.name == deck_name) | (DeckModel.name.startswith(descendants_prefix(deck_name)))))

    def get_card_count(self, deck_id: int) -> int:
        """Return total number of cards placed in a specific deck."""
        return int(CardModel.select().where(CardModel.deck == deck_id).count())

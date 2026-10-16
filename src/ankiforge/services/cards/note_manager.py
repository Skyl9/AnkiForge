"""Création et manipulation des notes Anki, de leurs versions et de leurs cartes physiques.

Garantit qu'une note créée possède toujours une version initiale et les cartes
(basique ou cloze) dérivées de son modèle de note.
"""

import json
import logging
import uuid

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, db
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.tags import serialize_note_tags

logger = logging.getLogger(__name__)


class NoteManager:
    """Service métier orchestrant la création et la manipulation des notes.

    Cette classe centralise la logique complexe de création de notes, garantissant
    que chaque note possède une version initiale et ses cartes physiques correspondantes.
    """

    @staticmethod
    def create_note(
        note_type: NoteTypeModel,
        deck: DeckModel,
        content_dict: dict[str, str],
        tags: list[str] | None = None,
        status: str = "new",
        source: str = "manual",
    ) -> NoteModel:
        """Crée une nouvelle note de manière atomique.

        Génère la note, sa version initiale et toutes les cartes (CardModel)
        nécessaires selon le modèle de note (basique ou cloze).

        Args:
            note_type: Modèle Anki définissant les champs et templates.
            deck: Paquet Anki de destination.
            content_dict: Valeurs pour chaque champ défini dans le modèle.
            tags: Liste de tags optionnelle.
            status: État initial de la note ('new', 'exported', etc.).
            source: Origine de la note ('manual', 'ai', 'import').

        Returns:
            L'objet Note créé.

        Raises:
            RuntimeError: En cas d'échec de l'opération en base de données.
        """
        if tags is None:
            tags = []

        templates_str = note_type.templates
        templates = json.loads(str(templates_str)) if templates_str else []

        is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

        try:
            with db.atomic():
                new_note = NoteModel.create(
                    guid=str(uuid.uuid4())[:10],
                    note_type=note_type,
                    tags=serialize_note_tags(tags),
                    status=status,
                )

                new_note.add_version(content_dict, source=source)

                if is_cloze:
                    max_cloze = get_max_cloze_index(content_dict)
                    num_cards = max(1, max_cloze)
                    for i in range(num_cards):
                        CardModel.create(note=new_note, deck=deck, template_index=i)
                else:
                    for i, _ in enumerate(templates):
                        CardModel.create(note=new_note, deck=deck, template_index=i)

                logger.info(
                    "Note ID=%d créée avec succès (modèle: '%s', deck: '%s', source: '%s')",
                    new_note.id,
                    note_type.name,
                    deck.name,
                    source,
                )
                return new_note

        except Exception as e:
            logger.exception("Erreur lors de la création transactionnelle de la note (%s) : %s", note_type.name, e)
            raise RuntimeError(f"Échec de la création de la note : {e}") from e

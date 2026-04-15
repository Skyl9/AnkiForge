import json
import logging
import uuid

from ankiforge.database.models import db, NoteModel, NoteTypeModel, DeckModel, CardModel
from ankiforge.utils.anki_renderer import get_max_cloze_index

logger = logging.getLogger(__name__)


class NoteManager:
    """
    Service métier orchestrant la création et la manipulation des notes.

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
        """
        Crée une nouvelle note de manière atomique.

        Génère la note, sa version initiale et toutes les cartes (CardModel)
        nécessaires selon le modèle de note (basique ou cloze).

        Args:
            note_type (NoteTypeModel): Modèle Anki définissant les champs et templates.
            deck (DeckModel): Paquet Anki de destination.
            content_dict (dict[str, str]): Valeurs pour chaque champ défini dans le modèle.
            tags (list[str] | None): Liste de tags optionnelle.
            status (str): État initial de la note ('new', 'exported', etc.).
            source (str): Origine de la note ('manual', 'ai', 'import').

        Returns:
            NoteModel: L'objet Note créé.

        Raises:
            RuntimeError: En cas d'échec de l'opération en base de données.
        """
        if tags is None:
            tags = []

        templates_str = note_type.templates
        templates = json.loads(templates_str) if templates_str else []

        is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

        try:
            with db.atomic():
                # 1. Création de la coquille vide (La Note)
                new_note = NoteModel.create(
                    guid=str(uuid.uuid4())[:10],
                    note_type=note_type,
                    tags=json.dumps(tags, ensure_ascii=False),
                    status=status,
                )

                # 2. Création de la version initiale du contenu
                new_note.add_version(content_dict, source=source)

                # 3. Génération des cartes physiques selon la logique Anki
                if is_cloze:
                    max_cloze = get_max_cloze_index(content_dict)
                    num_cards = max(1, max_cloze)
                    for i in range(num_cards):
                        CardModel.create(note=new_note, deck=deck, template_index=i)
                else:
                    for i, _ in enumerate(templates):
                        CardModel.create(note=new_note, deck=deck, template_index=i)

                return new_note

        except Exception as e:
            logger.exception(f"Erreur lors de la création transactionnelle de la note ({note_type.name}) :")
            raise RuntimeError(f"Échec de la création de la note : {e}") from e

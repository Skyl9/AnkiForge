import json
import logging
import uuid

from ankiforge.database.models import db, NoteModel, NoteTypeModel, DeckModel, CardModel
from ankiforge.utils.anki_renderer import get_max_cloze_index

logger = logging.getLogger(__name__)


class NoteManager:
    """
    Service métier responsable de la manipulation complexe des notes et de leurs cartes associées.
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
        Crée une note complète de manière sécurisée (Note + Version initiale + Cartes physiques).

        Args:
            note_type (NoteTypeModel): Le modèle Anki définissant la structure.
            deck (DeckModel): Le paquet de destination.
            content_dict (dict): Le dictionnaire des champs et leurs valeurs.
            tags (list[str] | None): La liste des tags à appliquer.
            status (str): Le statut initial de la carte (ex: 'new', 'pending').
            source (str): L'origine de la création (ex: 'manual', 'ai').

        Returns:
            NoteModel: L'instance de la note fraîchement créée en base.
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

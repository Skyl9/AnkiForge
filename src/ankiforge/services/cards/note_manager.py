"""Création et manipulation des notes Anki, de leurs versions et de leurs cartes physiques.

Garantit qu'une note créée possède toujours une version initiale et les cartes
(basique ou cloze) dérivées de son modèle de note.
"""

import json
import logging
import uuid
from typing import Any

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteTypeModel, NoteVersionModel, db
from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService
from ankiforge.services.cards.flag_service import FlagService
from ankiforge.utils.anki_renderer import get_max_cloze_index, should_generate_card
from ankiforge.utils.tags import serialize_note_tags, split_tag_tokens

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
        tags_list = split_tag_tokens(tags)

        templates_str = note_type.templates
        templates = json.loads(str(templates_str)) if templates_str else []

        is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

        try:
            with db.atomic():
                new_note = NoteModel.create(
                    guid=str(uuid.uuid4())[:10],
                    note_type=note_type,
                    tags=serialize_note_tags(tags_list),
                    status=status,
                )

                new_note.add_version(content_dict, source=source)

                if is_cloze:
                    max_cloze = get_max_cloze_index(content_dict)
                    num_cards = max(1, max_cloze)
                    for i in range(num_cards):
                        CardModel.create(note=new_note, deck=deck, template_index=i)
                else:
                    for i, tmpl in enumerate(templates):
                        qfmt = tmpl.get("qfmt", "")
                        if should_generate_card(qfmt, content_dict):
                            CardModel.create(note=new_note, deck=deck, template_index=i)

                try:
                    CoverageAlignmentService.sync_note_coverage(new_note)
                except Exception as cov_err:
                    logger.debug("Synchronisation de la couverture ignorée : %s", cov_err)

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

    @staticmethod
    def _resolve_flag_value(flag: int | str | None) -> int | None:
        """Résout un drapeau accepté en entrée vers sa valeur numérique Anki (0 à 7).

        ``None`` signifie « tout drapeau ». Accepte l'entier brut, le nom de
        couleur natif ('rouge', 'red', …) ou tout libellé personnalisé du profil.
        """
        if flag is None:
            return None
        if isinstance(flag, bool):
            raise ValueError("Le drapeau doit être un entier de 0 à 7 ou un libellé de couleur.")
        if isinstance(flag, int):
            if flag not in range(8):
                raise ValueError("Le drapeau doit être un entier de 0 à 7 ou un libellé de couleur.")
            return flag
        search_map = FlagService.get_flag_search_map()
        key = str(flag).strip().lower()
        if key in search_map:
            return search_map[key]
        raise ValueError(f"Drapeau inconnu : {flag!r}. Attendu : un entier de 0 à 7 ou un libellé de couleur.")

    @staticmethod
    def get_flagged_cards(
        deck_name: str | None = None,
        flag: int | str | None = None,
        limit: int = 50,
    ) -> str:
        """Retourne au format JSON les cartes portant un drapeau Anki.

        Args:
            deck_name: Paquet filtre ; les sous-paquets sont inclus de façon
                récursive (``nom::%``). ``None`` ne filtre pas sur le paquet.
            flag: Numéro du drapeau (0 à 7) ou libellé/nom de couleur
                ('rouge', 'red', …). ``None`` retourne toute carte pourvue d'un
                drapeau (``flags > 0``).
            limit: Nombre maximal de cartes retournées (borne : 1 à 100).

        Returns:
            Objet JSON avec ``status``, ``filters``, ``total`` et ``items``.
            Chaque item porte ``card_id``, ``note_id``, ``deck_name``,
            ``flag_number``, ``flag_label``, ``flag_color``, ``model_name``,
            ``fields`` (version active de la note) et ``tags``.

        Raises:
            ValueError: si le drapeau demandé est invalide.
        """
        flag_value = NoteManager._resolve_flag_value(flag)
        cleaned_deck = deck_name.strip() if deck_name else None
        effective_limit = max(1, min(int(limit), 100))

        query = CardModel.select(CardModel, DeckModel, NoteModel, NoteTypeModel).join(DeckModel).switch(CardModel).join(NoteModel).join(NoteTypeModel).order_by(CardModel.id.asc())

        query = query.where(CardModel.flags > 0 if flag_value is None else CardModel.flags == flag_value)

        if cleaned_deck:
            query = query.where((DeckModel.name == cleaned_deck) | (DeckModel.name ** f"{cleaned_deck}::%"))

        total = query.count()
        cards = list(query.limit(effective_limit))

        note_models = [card.note for card in cards]
        active_versions: dict[int, NoteVersionModel] = {}
        if note_models:
            active_versions = {
                version.note.id: version
                for version in NoteVersionModel.select().join(NoteModel).where((NoteVersionModel.note << note_models) & (NoteVersionModel.is_active == True))  # noqa: E712
            }

        items: list[dict[str, Any]] = []
        for card in cards:
            note = card.note
            active_version = active_versions.get(note.id)
            fields: dict[str, Any] = {}
            if active_version and active_version.content:
                try:
                    fields = json.loads(str(active_version.content))
                    if not isinstance(fields, dict):
                        fields = {"raw": active_version.content}
                except (ValueError, TypeError):
                    fields = {"raw": active_version.content}
            items.append(
                {
                    "card_id": card.id,
                    "note_id": card.note_id,
                    "deck_name": card.deck.name,
                    "flag_number": card.flags,
                    "flag_label": FlagService.get_flag_name(card.flags),
                    "flag_color": FlagService.get_flag_color(card.flags),
                    "model_name": note.note_type.name if note.note_type else "Inconnu",
                    "fields": fields,
                    "tags": note.tags,
                }
            )

        return json.dumps(
            {
                "status": "success",
                "filters": {
                    "flag": flag,
                    "flag_value": flag_value,
                    "deck_name": cleaned_deck,
                    "limit": effective_limit,
                },
                "total": total,
                "items": items,
            },
            ensure_ascii=False,
        )

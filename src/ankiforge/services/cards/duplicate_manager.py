import json
import logging
import re
from typing import Any

from ankiforge.database.models import DeckModel, NoteModel, CardModel, NoteTypeModel, NoteVersionModel, IgnoredDuplicateModel
from ankiforge.utils.c_bridge import get_similarity

logger = logging.getLogger(__name__)


def strip_html(text: str | None) -> str:
    """
    Supprime les balises HTML et nettoie le texte pour l'analyse comparative.

    Args:
        text (str | None): Le texte brut contenant potentiellement du HTML.

    Returns:
        str: Le texte nettoyé, sans balises, entités HTML ou sauts de ligne superflus.
    """
    if not text:
        return ""
    clean = re.compile("<.*?>")
    return re.sub(clean, "", text).replace("&nbsp;", " ").replace("\n", " ").strip()


class DuplicateManager:
    """
    Service de détection intelligente de doublons sémantiques.

    Utilise une approche multi-niveaux : filtrage rapide par longueur et mots-clés (Jaccard),
    puis comparaison précise via l'algorithme de Levenshtein (en C) pour identifier
    les notes quasi-identiques.
    """

    @staticmethod
    def find_duplicates(deck_id: int) -> list[tuple[NoteModel, dict[str, Any], NoteModel, dict[str, Any], float]]:
        """
        Recherche les doublons au sein d'un paquet et de ses sous-paquets.

        Args:
            deck_id (int): ID du paquet racine pour la recherche.

        Returns:
            list: Liste de tuples contenant les paires de notes en conflit et leur contenu.
        """
        conflicts = []

        if deck_id == -1:
            matching_decks = DeckModel.select()
        else:
            selected_deck = DeckModel.get_by_id(deck_id)
            matching_decks = DeckModel.select().where(DeckModel.name.startswith(selected_deck.name))

        # Récupère toutes les notes du paquet
        all_notes = (
            NoteModel.select(NoteModel, NoteTypeModel)
            .join(NoteTypeModel)
            .switch(NoteModel)
            .join(CardModel, on=(CardModel.note_id == NoteModel.id))
            .join(DeckModel, on=(CardModel.deck_id == DeckModel.id))
            .where(DeckModel.id.in_(matching_decks))
            .distinct()
        )

        notes_by_model: dict[int, list[NoteModel]] = {}
        for note in all_notes:
            model_id = note.note_type.id if note.note_type else 0
            if model_id not in notes_by_model:
                notes_by_model[model_id] = []
            notes_by_model[model_id].append(note)

        for _, notes in notes_by_model.items():
            note_data_list = []
            for note in notes:
                active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                if active_version:
                    content = json.loads(active_version.content)
                    values = list(content.values())
                    if values:
                        all_text_combined = " ".join(str(v) for v in values)
                        clean_text = strip_html(all_text_combined).lower()

                        text_length = len(clean_text)
                        word_set = set(w for w in clean_text.split() if len(w) > 2)

                        note_data_list.append((note, clean_text, content, text_length, word_set))

            ignored_records = IgnoredDuplicateModel.select()
            ignored_pairs = {(record.note_a_id, record.note_b_id) for record in ignored_records}

            matched_ids = set()
            for i, (note_a, clean_a, content_a, len_a, words_a) in enumerate(note_data_list):
                if note_a.id in matched_ids:
                    continue

                for j in range(i + 1, len(note_data_list)):
                    note_b, clean_b, content_b, len_b, words_b = note_data_list[j]
                    if note_b.id in matched_ids:
                        continue

                    if (len_a + len_b) > 0:
                        max_possible_ratio = (2.0 * min(int(len_a), int(len_b))) / (len_a + len_b)
                        if max_possible_ratio < 0.85:
                            continue

                    if words_a and words_b:
                        intersection = len(words_a & words_b)
                        union = len(words_a | words_b)
                        jaccard_ratio = float(intersection) / float(union) if union > 0 else 0.0
                        if jaccard_ratio < 0.35:
                            continue

                    id_1, id_2 = min(note_a.id, note_b.id), max(note_a.id, note_b.id)
                    if (id_1, id_2) in ignored_pairs:
                        continue

                    sim = get_similarity(clean_a, clean_b)
                    if sim > 0.90:
                        if note_a.id < note_b.id:
                            conflicts.append((note_a, content_a, note_b, content_b, sim))
                        else:
                            conflicts.append((note_b, content_b, note_a, content_a, sim))

                        matched_ids.add(note_b.id)
                        break

        return conflicts

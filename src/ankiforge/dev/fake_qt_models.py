"""Modèles Qt factices alimentés sans base de données, pour la galerie de widgets.

Ce module est volontairement séparé de :mod:`ankiforge.dev.fake_services` : il dépend de
la couche UI (``ankiforge.ui.models``), alors que les faux services n'en dépendent pas.
L'importer explicitement depuis la galerie évite d'alourdir ``ankiforge.dev`` pour tous
ses consommateurs.
"""

from __future__ import annotations

from typing import Any

from ankiforge.ui.models.note_table_model import NoteRowData, NoteVirtualTableModel

#: Lignes de démonstration nominales : (recto, verso, source).
_DEMO_NOTE_ROWS: tuple[tuple[str, str, str], ...] = (
    (
        "Qu'est-ce que la mitose ?",
        "Une division cellulaire eucaryote créant deux cellules filles génétiquement identiques.",
        "Manuel p.12",
    ),
    (
        "Quelles sont les quatre phases de la mitose ?",
        "Prophase, métaphase, anaphase et télophase.",
        "Manuel p.13",
    ),
    (
        "Quel est le rôle biologique de la division cellulaire ?",
        "Assurer la croissance, le renouvellement et la réparation des tissus.",
        "Cours ch.4",
    ),
)


class FakeNoteTableModel(NoteVirtualTableModel):
    """Modèle de tableau de notes alimenté par des lignes nominales, sans accès BDD.

    ``NoteVirtualTableModel`` dérive ses lignes des versions actives persistées : sur une
    note non enregistrée, il retombe sur « CARTE INVALIDE (Recto vide) ». Cet aperçu
    substitue donc la conversion par lot pour projeter des :class:`NoteRowData` complets
    et étiquetés, sans aucune requête Peewee.
    """

    def _process_notes_batch(self, raw_items: list[Any]) -> list[NoteRowData]:
        offset = len(self._loaded_rows)
        rows: list[NoteRowData] = []
        for position, note in enumerate(raw_items):
            recto, verso, source = _DEMO_NOTE_ROWS[(offset + position) % len(_DEMO_NOTE_ROWS)]
            tags = ["biologie", "mitose"]
            rows.append(
                NoteRowData(
                    note_id=int(getattr(note, "id", 0) or 0),
                    guid=str(getattr(note, "guid", "")),
                    recto=recto,
                    verso=verso,
                    fields_dict={"Front": recto, "Back": verso, "Source": source},
                    model_name="Biologie Fondamentale",
                    deck_name="Biologie::Cellule",
                    tags_list=tags,
                    tags_display="  ".join(f"#{tag}" for tag in tags),
                    raw_note=note,
                )
            )
        return rows

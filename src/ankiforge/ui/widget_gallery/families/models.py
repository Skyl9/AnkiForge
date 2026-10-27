"""Famille « models » de la galerie : modèles Qt et délégués de rendu.

Les modèles de données et les délégués ne sont pas des widgets : chaque entrée les
instancie puis les projette dans un conteneur d'aperçu dédié (liste, tableau lié ou
lignes représentatives peintes par le délégué), alimenté par les charges factices
déterministes de :mod:`ankiforge.dev.fake_data`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from ankiforge.dev.fake_data import make_fake_chunk_results, make_fake_note
from ankiforge.dev.fake_qt_models import FakeNoteTableModel
from ankiforge.ui.models.chunk_list_model import VirtualChunkListModel
from ankiforge.ui.models.delegates import (
    BADGE_BG_COLOR_ROLE,
    BADGE_TEXT_COLOR_ROLE,
    FLAG_ROLE,
    IS_INVALID_CARD_ROLE,
    TAGS_LIST_ROLE,
    BadgeItemDelegate,
    CheckboxItemDelegate,
    FlagItemDelegate,
    ProgressBarItemDelegate,
    SimilarityBadgeDelegate,
    SrsMasteryDelegate,
    TagItemDelegate,
    TextSnippetDelegate,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widget_gallery.previews import DelegatePreview, ItemModelPreview
from ankiforge.ui.widget_gallery.registry import gallery_widget
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)

_ROLE_CHECK_STATE = int(Qt.ItemDataRole.CheckStateRole)
_ROLE_DISPLAY = int(Qt.ItemDataRole.DisplayRole)
_ROLE_USER = int(Qt.ItemDataRole.UserRole)


# ── Modèles de données ────────────────────────────────────────────────────────


def _make_virtual_chunk_list_model() -> QWidget:
    model = VirtualChunkListModel()
    model.set_static_results(make_fake_chunk_results())
    return ItemModelPreview(model, tr("Modèle de fragments RAG"), list_mode=True)


def _make_note_table_model() -> QWidget:
    model = FakeNoteTableModel(display_mode="notes")
    for note_id in (9001, 9002, 9003):
        model.prepend_note(make_fake_note(note_id))
    return ItemModelPreview(model, tr("Modèle de notes virtuel paginé"))


# ── Délégués de rendu ─────────────────────────────────────────────────────────


def _make_checkbox_delegate() -> QWidget:
    return DelegatePreview(
        CheckboxItemDelegate(),
        tr("Délégué de case à cocher"),
        [
            (tr("Sélectionnée"), {_ROLE_CHECK_STATE: Qt.CheckState.Checked}),
            (tr("Non sélectionnée"), {_ROLE_CHECK_STATE: Qt.CheckState.Unchecked}),
        ],
    )


def _make_flag_delegate() -> QWidget:
    return DelegatePreview(
        FlagItemDelegate(),
        tr("Délégué de drapeau Anki"),
        [(tr("Drapeau %1", flag), {int(FLAG_ROLE): flag}) for flag in (1, 2, 3, 4, 5)],
    )


def _make_badge_delegate() -> QWidget:
    return DelegatePreview(
        BadgeItemDelegate(),
        tr("Délégué de badge"),
        [
            (
                tr("Biologie"),
                {
                    _ROLE_DISPLAY: tr("Biologie"),
                    int(BADGE_BG_COLOR_ROLE): DesignTokens.ACCENT_BG,
                    int(BADGE_TEXT_COLOR_ROLE): DesignTokens.ACCENT_PRIMARY,
                },
            ),
            (
                tr("Validé"),
                {
                    _ROLE_DISPLAY: tr("Validé"),
                    int(BADGE_BG_COLOR_ROLE): DesignTokens.COLOR_GREEN_BG,
                    int(BADGE_TEXT_COLOR_ROLE): DesignTokens.COLOR_GREEN,
                },
            ),
        ],
    )


def _make_tag_delegate() -> QWidget:
    return DelegatePreview(
        TagItemDelegate(),
        tr("Délégué de tags"),
        [
            (
                "",
                {int(TAGS_LIST_ROLE): ["biologie", "mitose", "cellule", "examen"]},
            )
        ],
    )


def _make_text_snippet_delegate() -> QWidget:
    valid_text = tr("Qu'est-ce que la mitose ?")
    invalid_text = tr("Question vide")
    return DelegatePreview(
        TextSnippetDelegate(),
        tr("Délégué de texte monospace"),
        [
            (valid_text, {_ROLE_DISPLAY: valid_text}),
            (invalid_text, {_ROLE_DISPLAY: invalid_text, int(IS_INVALID_CARD_ROLE): True}),
        ],
    )


def _make_progress_bar_delegate() -> QWidget:
    return DelegatePreview(
        ProgressBarItemDelegate(),
        tr("Délégué de barre de progression"),
        [
            (tr("Lot en attente"), {_ROLE_USER: 0}),
            (tr("Lot en cours"), {_ROLE_USER: 42}),
            (tr("Lot terminé"), {_ROLE_USER: 100}),
        ],
    )


def _make_similarity_badge_delegate() -> QWidget:
    return DelegatePreview(
        SimilarityBadgeDelegate(),
        tr("Délégué de similarité"),
        [
            (tr("Similarité faible"), {_ROLE_DISPLAY: "0.812"}),
            (tr("Similarité forte"), {_ROLE_DISPLAY: "0.968"}),
        ],
    )


def _make_srs_mastery_delegate() -> QWidget:
    return DelegatePreview(
        SrsMasteryDelegate(),
        tr("Délégué de maîtrise SRS"),
        [
            (
                "",
                {
                    _ROLE_USER: [
                        (tr("Maîtrisée"), DesignTokens.COLOR_GREEN),
                        (tr("Nouvelle"), DesignTokens.COLOR_RED),
                    ]
                },
            ),
            (
                "",
                {
                    _ROLE_USER: [
                        (tr("En cours"), DesignTokens.COLOR_YELLOW),
                        (tr("Maîtrisée"), DesignTokens.COLOR_GREEN),
                    ]
                },
            ),
        ],
    )


# Correspondance classe Qt → factory, source unique de la couverture.
MODEL_FACTORIES: dict[str, Callable[[], QWidget]] = {
    "VirtualChunkListModel": _make_virtual_chunk_list_model,
    "NoteVirtualTableModel": _make_note_table_model,
    "CheckboxItemDelegate": _make_checkbox_delegate,
    "FlagItemDelegate": _make_flag_delegate,
    "BadgeItemDelegate": _make_badge_delegate,
    "TagItemDelegate": _make_tag_delegate,
    "TextSnippetDelegate": _make_text_snippet_delegate,
    "ProgressBarItemDelegate": _make_progress_bar_delegate,
    "SimilarityBadgeDelegate": _make_similarity_badge_delegate,
    "SrsMasteryDelegate": _make_srs_mastery_delegate,
}

# Base générique sans source de données concrète : aucun aperçu pertinent.
# Ce sont les tests de couverture qui la retranchent du parcours d'introspection.
EXCLUDED_QT_MODEL_CLASSES = frozenset({"BasePaginatedPeeweeModel"})


def model_labels() -> dict[str, str]:
    """Libellés français affichés dans l'arbre de la galerie (extractibles par lupdate)."""
    return {
        "VirtualChunkListModel": tr("Modèle de fragments RAG"),
        "NoteVirtualTableModel": tr("Modèle de notes virtuel paginé"),
        "CheckboxItemDelegate": tr("Délégué de case à cocher"),
        "FlagItemDelegate": tr("Délégué de drapeau Anki"),
        "BadgeItemDelegate": tr("Délégué de badge"),
        "TagItemDelegate": tr("Délégué de tags"),
        "TextSnippetDelegate": tr("Délégué de texte monospace"),
        "ProgressBarItemDelegate": tr("Délégué de barre de progression"),
        "SimilarityBadgeDelegate": tr("Délégué de similarité"),
        "SrsMasteryDelegate": tr("Délégué de maîtrise SRS"),
    }


def register() -> None:
    """Enregistre les modèles et délégués dans la galerie (idempotent)."""
    labels = model_labels()
    for class_name, factory in MODEL_FACTORIES.items():
        label = labels.get(class_name)
        if label is None:
            logger.warning("Libellé de galerie manquant pour le modèle Qt « %s »", class_name)
            label = class_name
        gallery_widget(family="models", name=label)(factory)

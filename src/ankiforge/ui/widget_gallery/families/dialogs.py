"""Famille « dialogs » de la galerie : dialogues du paquet ``ui/dialogs``.

Chaque factory instancie un dialogue réel alimenté par les charges utiles
déterministes de :mod:`ankiforge.dev.fake_data`, sans écriture en base ni appel
réseau. Les dialogues dont l'initialisation consulte SQLite ou démarre un worker
sont surchargés pour offrir un aperçu réaliste et strictement isolé : historique
d'agent, historique de note et hygiène des tags.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QWidget

from ankiforge.dev.fake_data import (
    make_fake_conflict_item,
    make_fake_crash_report,
    make_fake_decks,
    make_fake_document,
    make_fake_heading_repairs,
    make_fake_leech_data,
    make_fake_model_package,
    make_fake_note,
    make_fake_note_ids,
    make_fake_note_type,
    make_fake_note_versions,
    make_fake_persona,
    make_fake_persona_versions,
    make_fake_pipeline_state,
    make_fake_profiles_dir,
    make_fake_python_tool,
    make_fake_tag_clusters_report,
    make_fake_update_info,
)
from ankiforge.ui.dialogs.addon_manager_dialog import AddonManagerDialog
from ankiforge.ui.dialogs.album_transcription_dialog import AlbumTranscriptionDialog
from ankiforge.ui.dialogs.card_export_dialog import CardExportDialog
from ankiforge.ui.dialogs.change_note_type_dialog import ChangeNoteTypeDialog
from ankiforge.ui.dialogs.crash_report_dialog import CrashReportDialog
from ankiforge.ui.dialogs.create_deck_dialog import CreateDeckDialog
from ankiforge.ui.dialogs.css_conflict_dialog import CSSConflictDialog
from ankiforge.ui.dialogs.dialog_gallery_dialog import DialogGalleryDialog
from ankiforge.ui.dialogs.doc_reader_dialog import DocReaderDialog
from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog
from ankiforge.ui.dialogs.export_dialog import ExportDialog
from ankiforge.ui.dialogs.feedback_dialog import FeedbackDialog
from ankiforge.ui.dialogs.history_modal import HistoryModal
from ankiforge.ui.dialogs.human_validation_dialog import HumanValidationDialog
from ankiforge.ui.dialogs.image_occlusion_dialog import ImageOcclusionDialog
from ankiforge.ui.dialogs.import_dialog import ImportDialog
from ankiforge.ui.dialogs.leech_wozniak_split_dialog import LeechWozniakSplitDialog
from ankiforge.ui.dialogs.marker_install_dialog import MarkerInstallDialog
from ankiforge.ui.dialogs.model_export_dialog import ModelExportDialog
from ankiforge.ui.dialogs.model_import_dialog import ModelImportDialog
from ankiforge.ui.dialogs.note_type_role_guide_dialog import NoteTypeRoleGuideDialog
from ankiforge.ui.dialogs.persona_history_dialog import PersonaHistoryDialog, PersonaVersionItemWidget
from ankiforge.ui.dialogs.persona_prompt_override_dialog import PersonaPromptOverrideDialog
from ankiforge.ui.dialogs.profile_transfer_dialog import ProfileTransferDialog
from ankiforge.ui.dialogs.repair_headings_dialog import RepairHeadingsDialog
from ankiforge.ui.dialogs.selection_dialog import MultiSelectionDialog, SelectionDialog
from ankiforge.ui.dialogs.smart_merge_dialog import SmartMergeDialog
from ankiforge.ui.dialogs.starter_pack_dialog import StarterPackDialog
from ankiforge.ui.dialogs.support_dialog import SupportDialog
from ankiforge.ui.dialogs.tag_hygiene_dialog import TagHygieneDialog
from ankiforge.ui.dialogs.taxonomy_audit_dialog import TaxonomyAuditDialog
from ankiforge.ui.dialogs.tool_editor_dialog import ToolEditorDialog
from ankiforge.ui.dialogs.toolbar_customize_dialog import ToolbarCustomizeDialog
from ankiforge.ui.dialogs.update_dialog import UpdateDialog
from ankiforge.ui.dialogs.url_import_dialog import UrlImportDialog
from ankiforge.ui.widget_gallery.registry import gallery_widget
from ankiforge.ui.widgets.editor_toolbar_widget import ToolbarAction
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)


class _GalleryProfileTransferDialog(ProfileTransferDialog):
    """Transfert entre profils alimenté par des listes factices, sans base secondaire."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(profiles_dir=make_fake_profiles_dir(), parent=parent)
        self.setWindowTitle(tr("[Galerie Dev] Transfert entre espaces de travail"))

    def _load_source_profiles(self) -> None:
        self.combo_source.clear()
        self.combo_source.addItems(["recherche", "lecture"])
        self.combo_source.setEnabled(True)
        self.btn_transfer.setEnabled(True)

    def _populate_decks_and_tags(self, profile_name: str) -> None:
        self._is_updating_preview = True
        try:
            self.list_decks.clear()
            for deck_name in ("Biologie::Cellule", "Langues::Anglais"):
                item = QListWidgetItem(deck_name, self.list_decks)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
            self.list_tags.clear()
            for tag in ("biologie", "mitose", "anglais"):
                tag_item = QListWidgetItem(tag, self.list_tags)
                tag_item.setFlags(tag_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                tag_item.setCheckState(Qt.CheckState.Unchecked)
        finally:
            self._is_updating_preview = False


class _GalleryPersonaHistoryDialog(PersonaHistoryDialog):
    """Historique d'agent alimenté par trois versions factices.

    La classe de base lit le ``PersonaModel`` (base vide tolérée) ; seules les
    versions, inexistantes hors base, sont fournies en mémoire.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(persona_id=0, parent=parent)
        self.setWindowTitle(tr("[Galerie Dev] Historique des versions d'un agent"))

    def _load_versions(self) -> None:
        self.version_list.clear()
        for version in make_fake_persona_versions():
            list_item = QListWidgetItem()
            widget = PersonaVersionItemWidget(version)
            list_item.setSizeHint(widget.sizeHint())
            list_item.setData(Qt.ItemDataRole.UserRole, version.id)
            self.version_list.addItem(list_item)
            self.version_list.setItemWidget(list_item, widget)

        if self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)


class _GalleryHistoryModal(HistoryModal):
    """Historique de note alimenté par trois versions factices, sans lecture SQLite."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(note=make_fake_note(), parent=parent)
        self.setWindowTitle(tr("[Galerie Dev] Historique d'une carte factice"))

    def _load_versions(self) -> None:
        versions = make_fake_note_versions()
        self.versions = versions
        self.active_version = versions[0]
        self.active_content = json.loads(versions[0].content)

        self.version_list.clear()
        for version in versions:
            item = QListWidgetItem()
            source_label = self._format_source_label(str(version.source))
            if version.is_active:
                source_label = tr("%1 (actuelle)", source_label)
            date_label = version.created_at.strftime("%d/%m/%Y %H:%M") if version.created_at else ""
            item.setText(tr("v%1 — %2\n%3", version.version_number, source_label, date_label))
            item.setData(Qt.ItemDataRole.UserRole, version)
            self.version_list.addItem(item)

        if self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)


class _GalleryTagHygieneDialog(TagHygieneDialog):
    """Hygiène des tags alimentée par un rapport factice, sans worker ni lecture SQLite."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle(tr("[Galerie Dev] Hygiène et fusion des tags"))

    def _start_analysis(self) -> None:
        self._on_analysis_finished(make_fake_tag_clusters_report())


def _make_addon_manager() -> QWidget:
    return AddonManagerDialog()


def _make_album_transcription() -> QWidget:
    return AlbumTranscriptionDialog(make_fake_document())


def _make_card_export() -> QWidget:
    return CardExportDialog(selected_note_ids=make_fake_note_ids())


def _make_change_note_type() -> QWidget:
    return ChangeNoteTypeDialog(note_ids=make_fake_note_ids())


def _make_create_deck() -> QWidget:
    return CreateDeckDialog()


def _make_crash_report() -> QWidget:
    return CrashReportDialog(crash_info=make_fake_crash_report())


def _make_css_conflict() -> QWidget:
    return CSSConflictDialog(
        conflicting_classes=["important", "remarque"],
        snippet_name="Encadré pédagogique",
    )


def _make_dialog_gallery() -> QWidget:
    return DialogGalleryDialog()


def _make_doc_reader() -> QWidget:
    return DocReaderDialog()


def _make_document_scope() -> QWidget:
    return DocumentScopeDialog(make_fake_document())


def _make_export() -> QWidget:
    return ExportDialog()


def _make_feedback() -> QWidget:
    return FeedbackDialog(
        tab="bug",
        initial_title=tr("[Galerie Dev] Signalement d'anomalie UI test"),
        context_error="ZeroDivisionError in mock pipeline",
    )


def _make_history_modal() -> QWidget:
    return _GalleryHistoryModal()


def _make_human_validation() -> QWidget:
    return HumanValidationDialog(make_fake_pipeline_state())


def _make_image_occlusion() -> QWidget:
    return ImageOcclusionDialog()


def _make_import() -> QWidget:
    return ImportDialog(initial_path="Documents/collection-factice.apkg")


def _make_leech_wozniak_split() -> QWidget:
    return LeechWozniakSplitDialog(make_fake_leech_data())


def _make_marker_install() -> QWidget:
    return MarkerInstallDialog()


def _make_model_export() -> QWidget:
    return ModelExportDialog(make_fake_note_type())


def _make_model_import() -> QWidget:
    return ModelImportDialog(make_fake_model_package())


def _make_multi_selection() -> QWidget:
    note_types = [make_fake_note_type(), make_fake_note_type(name="Langues Vivantes")]
    return MultiSelectionDialog(
        tr("Modèles à exporter"),
        note_types,
        display_func=lambda model: model.name,
    )


def _make_note_type_role_guide() -> QWidget:
    return NoteTypeRoleGuideDialog(
        current_text="| Concept | Directive | Champs cibles |\n|---|---|---|\n| Recto | Question principale | Front |",
        model_fields=["Front", "Back", "Source", "Remarques"],
    )


def _make_persona_history() -> QWidget:
    return _GalleryPersonaHistoryDialog()


def _make_persona_prompt_override() -> QWidget:
    return PersonaPromptOverrideDialog(
        persona=make_fake_persona(),
        step_title=tr("Analyse préliminaire"),
        current_text="Tu es un tuteur pédagogique. Explique {{ concept }} en trois étapes simples.",
    )


def _make_profile_transfer() -> QWidget:
    return _GalleryProfileTransferDialog()


def _make_repair_headings() -> QWidget:
    return RepairHeadingsDialog(make_fake_heading_repairs())


def _make_selection() -> QWidget:
    return SelectionDialog(
        tr("Sélectionner un paquet"),
        make_fake_decks(),
        display_func=lambda deck: deck.name,
    )


def _make_smart_merge() -> QWidget:
    return SmartMergeDialog([make_fake_conflict_item()])


def _make_starter_pack() -> QWidget:
    return StarterPackDialog()


def _make_support() -> QWidget:
    return SupportDialog()


def _make_tag_hygiene() -> QWidget:
    return _GalleryTagHygieneDialog()


def _make_taxonomy_audit() -> QWidget:
    return TaxonomyAuditDialog()


def _make_tool_editor() -> QWidget:
    return ToolEditorDialog(make_fake_python_tool())


def _make_toolbar_customize() -> QWidget:
    actions = {
        "bold": ToolbarAction(
            action_id="bold",
            icon_name="ph.text-b",
            label=tr("Gras"),
            tooltip=tr("Mettre le texte en gras"),
            shortcut="Ctrl+B",
            callback=lambda: None,
            group="format",
        ),
        "cloze": ToolbarAction(
            action_id="cloze",
            icon_name="ph.brackets-curly",
            label=tr("Texte à trous"),
            tooltip=tr("Insérer une occlusion"),
            shortcut="Ctrl+Shift+C",
            callback=lambda: None,
            group="cloze",
        ),
    }
    return ToolbarCustomizeDialog(actions, hidden_action_ids={"cloze"})


def _make_update() -> QWidget:
    return UpdateDialog(make_fake_update_info())


def _make_url_import() -> QWidget:
    return UrlImportDialog()


#: Correspondance classe de dialogue → factory, source unique de la couverture.
DIALOG_FACTORIES: dict[str, Callable[[], QWidget]] = {
    "AddonManagerDialog": _make_addon_manager,
    "AlbumTranscriptionDialog": _make_album_transcription,
    "CSSConflictDialog": _make_css_conflict,
    "CardExportDialog": _make_card_export,
    "ChangeNoteTypeDialog": _make_change_note_type,
    "CrashReportDialog": _make_crash_report,
    "CreateDeckDialog": _make_create_deck,
    "DialogGalleryDialog": _make_dialog_gallery,
    "DocReaderDialog": _make_doc_reader,
    "DocumentScopeDialog": _make_document_scope,
    "ExportDialog": _make_export,
    "FeedbackDialog": _make_feedback,
    "HistoryModal": _make_history_modal,
    "HumanValidationDialog": _make_human_validation,
    "ImageOcclusionDialog": _make_image_occlusion,
    "ImportDialog": _make_import,
    "LeechWozniakSplitDialog": _make_leech_wozniak_split,
    "MarkerInstallDialog": _make_marker_install,
    "ModelExportDialog": _make_model_export,
    "ModelImportDialog": _make_model_import,
    "MultiSelectionDialog": _make_multi_selection,
    "NoteTypeRoleGuideDialog": _make_note_type_role_guide,
    "PersonaHistoryDialog": _make_persona_history,
    "PersonaPromptOverrideDialog": _make_persona_prompt_override,
    "ProfileTransferDialog": _make_profile_transfer,
    "RepairHeadingsDialog": _make_repair_headings,
    "SelectionDialog": _make_selection,
    "SmartMergeDialog": _make_smart_merge,
    "StarterPackDialog": _make_starter_pack,
    "SupportDialog": _make_support,
    "TagHygieneDialog": _make_tag_hygiene,
    "TaxonomyAuditDialog": _make_taxonomy_audit,
    "ToolEditorDialog": _make_tool_editor,
    "ToolbarCustomizeDialog": _make_toolbar_customize,
    "UpdateDialog": _make_update,
    "UrlImportDialog": _make_url_import,
}


def dialog_labels() -> dict[str, str]:
    """Libellés français affichés dans l'arbre de la galerie (extractibles par lupdate)."""
    return {
        "AddonManagerDialog": tr("Gestionnaire d'extensions"),
        "AlbumTranscriptionDialog": tr("Transcription d'album"),
        "CSSConflictDialog": tr("Conflit de styles CSS"),
        "CardExportDialog": tr("Export rapide des cartes"),
        "ChangeNoteTypeDialog": tr("Changement de type de note"),
        "CrashReportDialog": tr("Rapport de crash"),
        "CreateDeckDialog": tr("Création de paquet"),
        "DialogGalleryDialog": tr("Galerie de dialogues (ancienne)"),
        "DocReaderDialog": tr("Lecteur de documentation"),
        "DocumentScopeDialog": tr("Délimitation de la portée"),
        "ExportDialog": tr("Export Anki (.apkg)"),
        "FeedbackDialog": tr("Retours et suggestions"),
        "HistoryModal": tr("Historique d'une carte"),
        "HumanValidationDialog": tr("Validation humaine du pipeline"),
        "ImageOcclusionDialog": tr("Masquage d'images"),
        "ImportDialog": tr("Import Anki (.apkg)"),
        "LeechWozniakSplitDialog": tr("Scission Wozniak d'une sangsue"),
        "MarkerInstallDialog": tr("Installation de Marker OCR"),
        "ModelExportDialog": tr("Export d'un type de note"),
        "ModelImportDialog": tr("Import d'un type de note"),
        "MultiSelectionDialog": tr("Sélection multiple"),
        "NoteTypeRoleGuideDialog": tr("Guide des rôles IA"),
        "PersonaHistoryDialog": tr("Historique d'un agent"),
        "PersonaPromptOverrideDialog": tr("Surcharge locale de prompt"),
        "ProfileTransferDialog": tr("Transfert entre espaces de travail"),
        "RepairHeadingsDialog": tr("Harmonisation des titres"),
        "SelectionDialog": tr("Sélection simple"),
        "SmartMergeDialog": tr("Fusion intelligente"),
        "StarterPackDialog": tr("Catalogue de types de note"),
        "SupportDialog": tr("Soutenir AnkiForge"),
        "TagHygieneDialog": tr("Hygiène des tags"),
        "TaxonomyAuditDialog": tr("Audit de taxonomie"),
        "ToolEditorDialog": tr("Éditeur d'outil Python"),
        "ToolbarCustomizeDialog": tr("Personnalisation de la barre d'outils"),
        "UpdateDialog": tr("Mise à jour disponible"),
        "UrlImportDialog": tr("Import depuis le Web"),
    }


def register() -> None:
    """Enregistre les dialogues dans la galerie (idempotent)."""
    labels = dialog_labels()
    for class_name, factory in DIALOG_FACTORIES.items():
        label = labels.get(class_name)
        if label is None:
            logger.warning("Libellé de galerie manquant pour le dialogue « %s »", class_name)
            label = class_name
        gallery_widget(family="dialogs", name=label, modal=True)(factory)

"""Galerie de Test des Boîtes de Dialogue en Mode Dev (Dialog Gallery).

Permet aux développeurs d'instancier, d'inspecter et de déboguer l'ensemble des modales
et dialogues de l'application avec des données mockées réalistes et une isolation absolue
vis-à-vis de la base de données réelle (zéro écriture SQLite).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
)
from ankiforge.services.cards.group_edit_service import GroupEditResult
from ankiforge.services.crash_reporter_service import CrashReport
from ankiforge.ui.components.buttons import ActionButton, SecondaryButton, apply_compact_style
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.dialogs.crash_report_dialog import CrashReportDialog
from ankiforge.ui.dialogs.feedback_dialog import FeedbackDialog
from ankiforge.ui.dialogs.note_type_role_guide_dialog import NoteTypeRoleGuideDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.batch_view.dialogs import BatchSliceComposerDialog
from ankiforge.ui.views.edition_view.group_edit_dialog import GroupEditDialog
from ankiforge.ui.widgets.time_machine_dialog import TimeMachineDialog
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def apply_pill_badge_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    try:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    except Exception:
        r, g, b = 99, 102, 241
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.14) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.40);
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: bold;
        }}
    """)


def build_mock_crash_report() -> CrashReport:
    """Génère une instance de CrashReport réaliste et complète pour les tests visuels."""
    return CrashReport(
        timestamp="2026-10-11 20:45:12 UTC",
        os_platform="macOS 15.0.1 (arm64)",
        python_version="3.12.9",
        active_profile="dev",
        traceback=(
            "Traceback (most recent call last):\n"
            '  File "src/ankiforge/services/parsing/marker_service.py", line 142, in extract_markdown\n'
            "    result = self._run_pipeline(document_path)\n"
            '  File "src/ankiforge/services/parsing/marker_service.py", line 88, in _run_pipeline\n'
            "ZeroDivisionError: float division by zero"
        ),
        raw_block=(
            "CRASH REPORT [2026-10-11 20:45:12 UTC] - Darwin-24.1.0-arm64 | Python 3.12.9\n"
            "Profil actif : dev\n"
            "Traceback (most recent call last):\n"
            '  File "src/ankiforge/services/parsing/marker_service.py", line 142, in extract_markdown\n'
            "ZeroDivisionError: float division by zero"
        ),
        fingerprint="mock_crash_gallery_001",
    )


class IsolatedCrashReportDialog(CrashReportDialog):
    """CrashReportDialog mocké et totalement isolé des QSettings et de crash.log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(crash_info=build_mock_crash_report(), parent=parent)
        self.setWindowTitle(tr("[Galerie Dev] %1", self.windowTitle()))

    def _on_dont_ask_toggled(self, checked: bool) -> None:
        self.lbl_status.setText(self.tr("[Mode Galerie] Préférence simulée (aucun impact QSettings)"))

    def _on_copy_clicked(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._markdown_payload)
        self.lbl_status.setText(self.tr("✓ Rapport copié (mode galerie, aucun acquittement)"))


class IsolatedTimeMachineDialog(TimeMachineDialog):
    """TimeMachineDialog mocké affichant 3 versions et neutralisant la restauration en BDD."""

    def __init__(self, parent: QWidget | None = None) -> None:
        mock_note = NoteModel(id=9999, guid="mock-gallery-guid", tags="biologie mitose", content_raw="")
        mock_nt = NoteTypeModel(name="Biologie Fondamentale", fields_schema='["Front", "Back", "Source"]')
        mock_note.note_type = mock_nt

        super().__init__(note=mock_note, parent=parent)
        self.setWindowTitle(self.tr("[Galerie Dev] Machine à Remonter le Temps — Carte #9999"))

    def _load_versions(self) -> None:
        now = datetime.now()
        v1 = NoteVersionModel(
            id=1,
            version_number=1,
            source="initial",
            is_active=False,
            created_at=now - timedelta(days=5),
            content=json.dumps({"Front": "Qu'est-ce que la mitose ?", "Back": "Une division cellulaire.", "Source": "Manuel p.12"}),
        )
        v2 = NoteVersionModel(
            id=2,
            version_number=2,
            source="linter",
            is_active=False,
            created_at=now - timedelta(days=2),
            content=json.dumps({"Front": "Qu'est-ce que la mitose en biologie ?", "Back": "Division cellulaire créant deux cellules filles.", "Source": "Manuel p.12"}),
        )
        v3 = NoteVersionModel(
            id=3,
            version_number=3,
            source="manual",
            is_active=True,
            created_at=now,
            content=json.dumps(
                {
                    "Front": "Qu'est-ce que la mitose en biologie cellulaire ?",
                    "Back": "Division cellulaire eucaryote créant deux cellules filles génétiquement identiques.",
                    "Source": "Manuel p.12-14",
                }
            ),
        )
        self.versions = [v3, v2, v1]
        self.active_version = v3
        self.active_content = json.loads(v3.content)

        self.version_list.clear()
        for v in self.versions:
            item = QListWidgetItem()
            src_label = self._format_source_label(str(v.source))
            active_badge = " [Actuelle]" if v.is_active else ""
            date_str = v.created_at.strftime("%d/%m/%Y %H:%M") if hasattr(v, "created_at") and v.created_at else ""
            item.setText(tr("v%1%2  —  %3\n📅 %4", v.version_number, active_badge, src_label, date_str))
            item.setData(Qt.ItemDataRole.UserRole, v)
            self.version_list.addItem(item)

        if self.version_list.count() > 0:
            self.version_list.setCurrentRow(0)

    def _restore_selected_version(self) -> None:
        if not self.selected_version:
            return
        reply = QMessageBox.question(
            self,
            self.tr("Confirmer la restauration (Mode Galerie)"),
            tr(
                "[Mode Galerie] Simuler la restauration de la version v%1 ?\nAucune modification ne sera écrite en base de données.",
                self.selected_version.version_number,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            show_toast(
                self,
                tr("[Galerie Dev] Simulation : version v%1 restaurée avec succès (aucune écriture BDD).", self.selected_version.version_number),
            )
            self.accept()


class IsolatedGroupEditDialog(GroupEditDialog):
    """GroupEditDialog mocké simulant l'application des tags et champs sans toucher SQLite."""

    def __init__(self, parent: QWidget | None = None) -> None:
        fake_note_ids = [9001, 9002, 9003]
        super().__init__(note_ids=fake_note_ids, parent=parent)
        self.setWindowTitle(self.tr("[Galerie Dev] Édition groupée (3 cartes mockées)"))

    def _collect_available_fields(self) -> list[str]:
        return ["Front", "Back", "Source", "Remarques", "Tags"]

    @Slot()
    def _on_apply_clicked(self) -> None:
        raw_add = self.input_tags_add.text().strip()
        raw_remove = self.input_tags_remove.text().strip()

        tags_to_add = [t.strip() for t in raw_add.replace(",", " ").split() if t.strip()]
        tags_to_remove = [t.strip() for t in raw_remove.replace(",", " ").split() if t.strip()]

        field_name: str | None = None
        field_action: str | None = None
        field_value: str = ""
        find_text: str = ""

        if self.cb_enable_field_edit.isChecked():
            field_name = str(self.combo_field.currentText()).strip()
            field_action = str(self.combo_action.currentData())
            field_value = self.text_field_value.toPlainText().strip()
            find_text = self.input_find.text().strip()

            if not field_name:
                QMessageBox.warning(self, self.tr("Champ manquant"), self.tr("Veuillez sélectionner un champ cible."))
                return

            if field_action == "find_replace" and not find_text:
                QMessageBox.warning(self, self.tr("Texte manquant"), self.tr("Veuillez préciser le texte à rechercher."))
                return

        if not tags_to_add and not tags_to_remove and not field_name:
            QMessageBox.information(
                self,
                self.tr("Aucune modification"),
                self.tr("Veuillez renseigner au moins une action (tags à ajouter/retirer ou modification de champ)."),
            )
            return

        content_by_note_id = {}
        if field_name:
            content_by_note_id = {nid: {field_name: field_value} for nid in self.note_ids}

        self.result_data = GroupEditResult(
            success=True,
            modified_note_ids=list(self.note_ids),
            skipped_note_ids=[],
            tags_by_note_id={nid: tags_to_add for nid in self.note_ids},
            content_by_note_id=content_by_note_id,
        )
        show_toast(
            self,
            tr("[Galerie Dev] Simulation réussie : %1 cartes modifiées avec succès (aucune écriture BDD).", len(self.note_ids)),
        )
        self.accept()


class IsolatedBatchSliceComposerDialog(BatchSliceComposerDialog):
    """BatchSliceComposerDialog mocké et isolé de la file de production."""

    def __init__(self, parent: QWidget | None = None) -> None:
        doc = DocumentModel.select().first()
        super().__init__(doc=doc, parent=parent)
        self.setWindowTitle(self.tr("[Galerie Dev] Composer le lot (Mode simulation)"))

    def _on_next(self) -> None:
        if self._current_step == 2:
            show_toast(
                self,
                self.tr("[Galerie Dev] Composition terminée : tâches prêtes en mémoire (aucune écriture en file de lot)."),
            )
            self.accept()
            return
        super()._on_next()


class GalleryCardWidget(QFrame):
    """Carte descriptive d'un dialogue dans la galerie."""

    def __init__(
        self,
        dialog_name: str,
        dialog_title: str,
        dialog_desc: str,
        badge_text: str,
        icon_name: str,
        launcher_fn: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.dialog_name = dialog_name
        self.dialog_title = dialog_title
        self.dialog_desc = dialog_desc
        self.badge_text = badge_text
        self.icon_name = icon_name
        self.launcher_fn = launcher_fn

        self.setObjectName("GalleryCard")
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QFrame#GalleryCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 12px;
            }}
            QFrame#GalleryCard:hover {{
                border-color: {DesignTokens.BORDER_FOCUS};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(load_phosphor_icon(self.icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        layout.addWidget(icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        lbl_title = QLabel(self.dialog_title, self)
        lbl_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_row.addWidget(lbl_title)

        lbl_class = QLabel(f"({self.dialog_name})", self)
        lbl_class.setStyleSheet(f"font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; color: {DesignTokens.TEXT_MUTED};")
        title_row.addWidget(lbl_class)

        badge = QLabel(self.badge_text, self)
        apply_pill_badge_style(badge, DesignTokens.ACCENT_PRIMARY)
        title_row.addWidget(badge)

        title_row.addStretch()
        info_layout.addLayout(title_row)

        lbl_desc = QLabel(self.dialog_desc, self)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        info_layout.addWidget(lbl_desc)

        layout.addLayout(info_layout, 1)

        btn_launch = ActionButton(self.tr("Tester le dialogue"))
        btn_launch.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.TEXT_PRIMARY))
        apply_compact_style(btn_launch, height=30)
        btn_launch.clicked.connect(self.launcher_fn)
        layout.addWidget(btn_launch)

    def matches_query(self, query: str) -> bool:
        """Détermine si la carte correspond à la recherche."""
        q = query.lower().strip()
        if not q:
            return True
        return q in self.dialog_name.lower() or q in self.dialog_title.lower() or q in self.dialog_desc.lower() or q in self.badge_text.lower()


class DialogGalleryDialog(QDialog):
    """Modale de Galerie de Test des Boîtes de Dialogue en Mode Dev.

    Permet de tester interactivement chaque dialogue avec un jeu de données mocké.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Galerie des Boîtes de Dialogue [Mode Dev]"))
        self.resize(840, 640)
        self.setMinimumSize(720, 520)

        self.dialog_cards: list[GalleryCardWidget] = []
        self._last_launched: str = ""

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # ── 1. EN-TÊTE DE LA GALERIE ──────────────────────────────────────────
        header_frame = QFrame(self)
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(12)

        icon_lbl = QLabel(header_frame)
        icon_lbl.setPixmap(load_phosphor_icon("ph.app-window", color=DesignTokens.ACCENT_PRIMARY).pixmap(32, 32))
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        lbl_title = QLabel(self.tr("Galerie des Boîtes de Dialogue & Modales"), header_frame)
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_vbox.addWidget(lbl_title)

        lbl_sub = QLabel(
            self.tr("Instanciez à la demande n'importe quelle modale avec données mockées. Les modifications sont simulées sans altérer SQLite."),
            header_frame,
        )
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        title_vbox.addWidget(lbl_sub)

        header_layout.addLayout(title_vbox, 1)
        main_layout.addWidget(header_frame)

        # ── 2. BARRE DE RECHERCHE & FILTRAGE ──────────────────────────────────
        self.search_input = GlowLineEdit(placeholder=self.tr("Filtrer les dialogues (nom, rôle, mot-clé)..."), parent=self)
        self.search_input.textChanged.connect(self._filter_cards)
        main_layout.addWidget(self.search_input)

        # ── 3. LISTE DES DIALOGUES (SCROLLABLE) ──────────────────────────────
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        cards_container = QWidget()
        self.cards_layout = QVBoxLayout(cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)

        self._register_dialogs()

        for card in self.dialog_cards:
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()
        scroll.setWidget(cards_container)
        main_layout.addWidget(scroll, 1)

        # ── 4. PIED DE PAGE ───────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.lbl_status = QLabel(self.tr("Sélectionnez un dialogue pour l'ouvrir."), self)
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        footer.addWidget(self.lbl_status, 1)

        btn_close = SecondaryButton(self.tr("Fermer la galerie"))
        btn_close.setFixedHeight(30)
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)

        main_layout.addLayout(footer)

    def _register_dialogs(self) -> None:
        """Enregistre l'ensemble des boîtes de dialogue prises en charge."""
        dialogs_data = [
            (
                "CrashReportDialog",
                self.tr("Rapport de Crash"),
                self.tr("Affiche la modale d'incident avec un CrashReport réaliste (traceback ZeroDivisionError masqué et métadonnées système)."),
                self.tr("Incident & Traceback"),
                "ph.warning-octagon",
                self.launch_crash_report_dialog,
            ),
            (
                "FeedbackDialog",
                self.tr("Retours & Signalements"),
                self.tr("Modale bivalente pour signaler une anomalie (avec logs et diagnostic pré-remplis) ou soumettre une idée de fonctionnalité."),
                self.tr("Formulaire Utilisateur"),
                "ph.chat-circle-dots",
                self.launch_feedback_dialog,
            ),
            (
                "NoteTypeRoleGuideDialog",
                self.tr("Guide des Rôles IA"),
                self.tr("Catalogue des archétypes de modèles de cartes et éditeur visuel de tableau Markdown avec prévisualisation en temps réel."),
                self.tr("Sémantique IA"),
                "ph.table",
                self.launch_note_type_role_guide_dialog,
            ),
            (
                "TimeMachineDialog",
                self.tr("Machine à Remonter le Temps"),
                self.tr("Exploration de l'historique complet d'une carte (3 versions mockées), visualiseur de diff syntaxique et simulation de restauration."),
                self.tr("Historique & Diff"),
                "ph.clock-counter-clockwise",
                self.launch_time_machine_dialog,
            ),
            (
                "GroupEditDialog",
                self.tr("Édition Groupée"),
                self.tr("Modification de masse sur 3 cartes factices : ajout/suppression de tags et recherche/remplacement de contenu sans écriture."),
                self.tr("Multi-Cartes"),
                "ph.cards",
                self.launch_group_edit_dialog,
            ),
            (
                "BatchSliceComposerDialog",
                self.tr("Découpeur de Lot (Batch)"),
                self.tr("Parcours en 3 étapes : choix du document, mode de découpage (Direct ou Auto) et récapitulatif des tâches générées."),
                self.tr("Orchestration Lot"),
                "ph.stack",
                self.launch_batch_slice_composer_dialog,
            ),
        ]

        for d_name, d_title, d_desc, badge, icon, fn in dialogs_data:
            card = GalleryCardWidget(
                dialog_name=d_name,
                dialog_title=d_title,
                dialog_desc=d_desc,
                badge_text=badge,
                icon_name=icon,
                launcher_fn=fn,
                parent=self,
            )
            self.dialog_cards.append(card)

    def _filter_cards(self, text: str) -> None:
        """Filtre les cartes affichées selon le texte de recherche."""
        for card in self.dialog_cards:
            card.setVisible(card.matches_query(text))

    def launch_crash_report_dialog(self) -> None:
        dlg = IsolatedCrashReportDialog(parent=self)
        self._last_launched = "CrashReportDialog"
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernière action : CrashReportDialog fermé (code %1).", res))

    def launch_feedback_dialog(self) -> None:
        dlg = FeedbackDialog(
            tab="bug",
            initial_title=self.tr("[Galerie Dev] Signalement d'anomalie UI test"),
            context_error="ZeroDivisionError in mock pipeline",
            parent=self,
        )
        self._last_launched = "FeedbackDialog"
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernière action : FeedbackDialog fermé (code %1).", res))

    def launch_note_type_role_guide_dialog(self) -> None:
        sample_md = "| Concept | Directive | Champs cibles |\n|---|---|---|\n| Recto | Question principale | Front |\n| Verso | Réponse détaillée | Back |"
        dlg = NoteTypeRoleGuideDialog(
            current_text=sample_md,
            model_fields=["Front", "Back", "Source", "Remarques"],
            parent=self,
        )
        self._last_launched = "NoteTypeRoleGuideDialog"
        dlg.exec()
        directive = getattr(dlg, "selected_directive", None)
        status_text = tr("Dernière action : NoteTypeRoleGuideDialog fermé (directive sélectionnée : %1).", bool(directive))
        self.lbl_status.setText(status_text)

    def launch_time_machine_dialog(self) -> None:
        dlg = IsolatedTimeMachineDialog(parent=self)
        self._last_launched = "TimeMachineDialog"
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernière action : TimeMachineDialog fermé (code %1).", res))

    def launch_group_edit_dialog(self) -> None:
        dlg = IsolatedGroupEditDialog(parent=self)
        self._last_launched = "GroupEditDialog"
        dlg.exec()
        success = bool(dlg.result_data and dlg.result_data.success)
        self.lbl_status.setText(tr("Dernière action : GroupEditDialog fermé (succès simulé : %1).", success))

    def launch_batch_slice_composer_dialog(self) -> None:
        dlg = IsolatedBatchSliceComposerDialog(parent=self)
        self._last_launched = "BatchSliceComposerDialog"
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernière action : BatchSliceComposerDialog fermé (code %1).", res))

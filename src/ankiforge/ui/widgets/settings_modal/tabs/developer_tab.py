"""Onglet Développeur & Diagnostics des Paramètres AnkiForge (DeveloperTab).

Fournit un cockpit d'inspection de l'environnement actif (profil, BDD SQLite, versions)
et intègre la Galerie des Boîtes de Dialogue avec lanceurs directs isolés.
Visible exclusivement lorsque l'application s'exécute en mode développement (--dev).
"""

from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.components.buttons import ActionButton, PrimaryButton, apply_compact_style
from ankiforge.ui.dialogs.dialog_gallery_dialog import (
    DialogGalleryDialog,
    IsolatedBatchSliceComposerDialog,
    IsolatedCrashReportDialog,
    IsolatedGroupEditDialog,
    IsolatedTimeMachineDialog,
)
from ankiforge.ui.dialogs.feedback_dialog import FeedbackDialog
from ankiforge.ui.dialogs.note_type_role_guide_dialog import NoteTypeRoleGuideDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components import apply_pill_badge_style
from ankiforge.ui.widgets.settings_modal.components.settings_card import SettingsCard
from ankiforge.utils.environment import (
    get_environment_display_name,
)
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_active_profile
from ankiforge.version import get_version_info


class DeveloperTab(QWidget):
    """Onglet Développeur accessible en mode dev dans SettingsModal.

    Héberge le cockpit des métadonnées de runtime et la galerie de test des modales.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.launcher_buttons: list[QWidget] = []
        self._gallery_dialog: DialogGalleryDialog | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── 1. SECTION COCKPIT RUNTIME & ENVIRONNEMENT ────────────────────────
        self.env_card = SettingsCard(content_widget)
        env_card_layout = QVBoxLayout(self.env_card)
        env_card_layout.setContentsMargins(14, 12, 14, 12)
        env_card_layout.setSpacing(10)

        header_env = QHBoxLayout()
        header_env.setSpacing(10)

        icon_env = QLabel(self.env_card)
        icon_env.setPixmap(load_phosphor_icon("ph.terminal-window", color=DesignTokens.ACCENT_PRIMARY).pixmap(22, 22))
        header_env.addWidget(icon_env)

        title_env_box = QVBoxLayout()
        title_env_box.setSpacing(2)

        lbl_env_title = QLabel(self.tr("Cockpit Runtime & Environnement"), self.env_card)
        lbl_env_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_env_box.addWidget(lbl_env_title)

        lbl_env_desc = QLabel(
            self.tr("Métadonnées d'exécution et localisation des données du profil développeur."),
            self.env_card,
        )
        lbl_env_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        title_env_box.addWidget(lbl_env_desc)

        header_env.addLayout(title_env_box, 1)

        self.lbl_env_badge = QLabel(self.tr("MODE DÉVELOPPEMENT"), self.env_card)
        apply_pill_badge_style(self.lbl_env_badge, DesignTokens.COLOR_GREEN)
        header_env.addWidget(self.lbl_env_badge)

        env_card_layout.addLayout(header_env)

        # Grille de métadonnées
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)

        profile_name = get_active_profile()
        db_path = str(ProfileManager().get_db_path(profile_name))
        v_info = get_version_info()
        py_version = sys.version.split()[0]

        meta_rows = [
            (self.tr("Environnement :"), get_environment_display_name()),
            (self.tr("Profil actif :"), profile_name),
            (self.tr("Version AnkiForge :"), v_info.version),
            (self.tr("Interpréteur Python :"), py_version),
            (self.tr("Base de données :"), db_path),
        ]

        self.lbl_env_name = QLabel(get_environment_display_name(), self.env_card)

        for row_idx, (k, v) in enumerate(meta_rows):
            lbl_k = QLabel(k, self.env_card)
            lbl_k.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_SECONDARY};")
            grid.addWidget(lbl_k, row_idx, 0)

            lbl_v = QLabel(str(v), self.env_card)
            lbl_v.setStyleSheet(f"font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; color: {DesignTokens.TEXT_PRIMARY};")
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(lbl_v, row_idx, 1)

        env_card_layout.addLayout(grid)
        layout.addWidget(self.env_card)

        # ── 2. SECTION GALERIE DES BOÎTES DE DIALOGUE ─────────────────────────
        self.gallery_card = SettingsCard(content_widget)
        gallery_card_layout = QVBoxLayout(self.gallery_card)
        gallery_card_layout.setContentsMargins(14, 12, 14, 12)
        gallery_card_layout.setSpacing(12)

        header_gal = QHBoxLayout()
        header_gal.setSpacing(10)

        icon_gal = QLabel(self.gallery_card)
        icon_gal.setPixmap(load_phosphor_icon("ph.app-window", color=DesignTokens.ACCENT_PRIMARY).pixmap(22, 22))
        header_gal.addWidget(icon_gal)

        title_gal_box = QVBoxLayout()
        title_gal_box.setSpacing(2)

        lbl_gal_title = QLabel(self.tr("Galerie de Test des Boîtes de Dialogue"), self.gallery_card)
        lbl_gal_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_gal_box.addWidget(lbl_gal_title)

        lbl_gal_desc = QLabel(
            self.tr("Instanciez les dialogues majeurs de l'application avec des données mockées sans impacter la base réelle."),
            self.gallery_card,
        )
        lbl_gal_desc.setWordWrap(True)
        lbl_gal_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        title_gal_box.addWidget(lbl_gal_desc)

        header_gal.addLayout(title_gal_box, 1)

        btn_open_gallery = PrimaryButton(self.tr("Ouvrir la Galerie Plein Écran"))
        btn_open_gallery.setIcon(load_phosphor_icon("ph.arrows-out-simple", color=DesignTokens.TEXT_ON_ACCENT))
        apply_compact_style(btn_open_gallery, height=28)
        btn_open_gallery.clicked.connect(self.open_full_gallery_dialog)
        header_gal.addWidget(btn_open_gallery)

        gallery_card_layout.addLayout(header_gal)

        # Grille des 6 dialogues recensés
        dialogs_info = [
            (
                "CrashReportDialog",
                self.tr("Rapport de Crash"),
                self.tr("Traceback simulé, logs masqués et dialogue non-bloquant."),
                "ph.warning-octagon",
                self.open_crash_report,
            ),
            (
                "FeedbackDialog",
                self.tr("Retours & Suggestions"),
                self.tr("Formulaire de signalement de bug et boîte à idées."),
                "ph.chat-circle-dots",
                self.open_feedback,
            ),
            (
                "NoteTypeRoleGuideDialog",
                self.tr("Guide des Rôles IA"),
                self.tr("Catalogue des archétypes sémantiques et prompt éditeur."),
                "ph.table",
                self.open_note_type_role_guide,
            ),
            (
                "TimeMachineDialog",
                self.tr("Machine à Remonter le Temps"),
                self.tr("Historique multi-versions d'une note et diff coloré."),
                "ph.clock-counter-clockwise",
                self.open_time_machine,
            ),
            (
                "GroupEditDialog",
                self.tr("Édition Groupée"),
                self.tr("Modification de tags et remplacement de champs en masse."),
                "ph.cards",
                self.open_group_edit,
            ),
            (
                "BatchSliceComposerDialog",
                self.tr("Découpeur de Lot"),
                self.tr("Assistant multi-étapes document → découpage → récapitulatif."),
                "ph.stack",
                self.open_batch_slice_composer,
            ),
        ]

        dialogs_grid = QGridLayout()
        dialogs_grid.setHorizontalSpacing(10)
        dialogs_grid.setVerticalSpacing(10)

        for idx, (_d_name, d_title, d_desc, icon_name, fn) in enumerate(dialogs_info):
            card_item = QFrame(self.gallery_card)
            card_item.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 8px;
                }}
            """)
            c_layout = QVBoxLayout(card_item)
            c_layout.setContentsMargins(10, 8, 10, 8)
            c_layout.setSpacing(6)

            top_row = QHBoxLayout()
            top_row.setSpacing(6)

            icon_lbl = QLabel(card_item)
            icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
            top_row.addWidget(icon_lbl)

            lbl_card_t = QLabel(d_title, card_item)
            lbl_card_t.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
            top_row.addWidget(lbl_card_t)
            top_row.addStretch()

            c_layout.addLayout(top_row)

            lbl_card_d = QLabel(d_desc, card_item)
            lbl_card_d.setWordWrap(True)
            lbl_card_d.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
            c_layout.addWidget(lbl_card_d)

            c_layout.addStretch()

            btn = ActionButton(self.tr("Lancer le test"))
            btn.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.TEXT_PRIMARY))
            apply_compact_style(btn, height=26)
            btn.clicked.connect(fn)
            c_layout.addWidget(btn)
            self.launcher_buttons.append(btn)

            row = idx // 2
            col = idx % 2
            dialogs_grid.addWidget(card_item, row, col)

        gallery_card_layout.addLayout(dialogs_grid)

        # Statut du dernier test exécuté
        self.lbl_status = QLabel(self.tr("Prêt : aucun dialogue ouvert pour le moment."), self.gallery_card)
        self.lbl_status.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-style: italic;")
        gallery_card_layout.addWidget(self.lbl_status)

        layout.addWidget(self.gallery_card)
        layout.addStretch()

        scroll.setWidget(content_widget)
        root_layout.addWidget(scroll)

    def has_pending_changes(self) -> bool:
        """L'onglet Développeur est un cockpit de diagnostic en lecture seule."""
        return False

    def save_tab(self) -> None:
        """Aucun paramètre à persister pour cet onglet."""
        pass

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit les styles dynamiques lors d'un changement de thème."""
        if hasattr(self, "env_card"):
            self.env_card.refresh_theme(profile)
        if hasattr(self, "gallery_card"):
            self.gallery_card.refresh_theme(profile)

    # ── Lanceurs de boîtes de dialogue isolées ───────────────────────────────

    def open_full_gallery_dialog(self) -> None:
        """Ouvre la boîte de dialogue de galerie modale complète."""
        self._gallery_dialog = DialogGalleryDialog(parent=self.window())
        self._gallery_dialog.exec()

    def open_crash_report(self) -> None:
        dlg = IsolatedCrashReportDialog(parent=self.window())
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernier test : CrashReportDialog exécuté (code %1).", res))

    def open_feedback(self) -> None:
        dlg = FeedbackDialog(
            tab="bug",
            initial_title=self.tr("[Galerie Dev] Test visuel Feedback"),
            context_error="Simulation d'incident dans la galerie",
            parent=self.window(),
        )
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernier test : FeedbackDialog exécuté (code %1).", res))

    def open_note_type_role_guide(self) -> None:
        sample_md = "| Concept | Directive | Champs cibles |\n|---|---|---|\n| Recto | Question principale | Front |\n| Verso | Réponse détaillée | Back |"
        dlg = NoteTypeRoleGuideDialog(
            current_text=sample_md,
            model_fields=["Front", "Back", "Source", "Remarques"],
            parent=self.window(),
        )
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernier test : NoteTypeRoleGuideDialog exécuté (code %1).", res))

    def open_time_machine(self) -> None:
        dlg = IsolatedTimeMachineDialog(parent=self.window())
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernier test : TimeMachineDialog exécuté (code %1).", res))

    def open_group_edit(self) -> None:
        dlg = IsolatedGroupEditDialog(parent=self.window())
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernier test : GroupEditDialog exécuté (code %1).", res))

    def open_batch_slice_composer(self) -> None:
        dlg = IsolatedBatchSliceComposerDialog(parent=self.window())
        res = dlg.exec()
        self.lbl_status.setText(tr("Dernier test : BatchSliceComposerDialog exécuté (code %1).", res))

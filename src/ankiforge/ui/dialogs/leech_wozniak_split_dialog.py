"""
Dialogue modal d'inspection et de scission atomique d'une carte sangsue (ADR 0019).
Permet de visualiser la carte défaillante et de déclencher une proposition Two-Phase Commit
selon les règles 4 et 5 de Piotr Wozniak.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
from ankiforge.services.audit.leech_service import LeechService
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class LeechWozniakSplitDialog(QDialog):
    """
    Dialogue modal permettant d'examiner une carte sangsue et d'ordonner sa scission
    en cartes atomiques via le Linter Wozniak sans altérer la file de révision.
    """

    split_applied = Signal(int)  # Émet note_id après application réussie

    def __init__(self, leech_data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.leech_data = leech_data
        self.note_id = int(leech_data.get("note_id", 0))
        self.card_id = int(leech_data.get("card_id", 0))
        self.current_patch_id: str | None = None
        self.current_subcards: list[dict[str, Any]] = []

        self.setWindowTitle(tr("Scission Wozniak — Carte Sangsue #%1 (Note #%2)", self.card_id, self.note_id))
        self.resize(780, 580)
        self.setMinimumSize(640, 480)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. En-tête informatif & Badges
        header_frame = QFrame()
        header_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        h_layout = QVBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(8)

        top_row = QHBoxLayout()
        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_RED, weight="fill").pixmap(20, 20))
        ico.setStyleSheet("border: none; background: transparent;")

        title_lbl = QLabel(tr("Diagnostic & Scission Atomique Wozniak"))
        title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        top_row.addWidget(ico)
        top_row.addWidget(title_lbl)
        top_row.addStretch()

        # Badges métriques
        lapses = self.leech_data.get("lapses", 0)
        stability = self.leech_data.get("stability", 0.0)
        deck_name = self.leech_data.get("deck_name", "")
        top_row.addWidget(Badge(tr("%1 rechutes", lapses), color=DesignTokens.COLOR_RED))
        top_row.addWidget(Badge(tr("Stabilité: %1j", f"{stability:.2f}"), color=DesignTokens.COLOR_YELLOW))
        if deck_name:
            top_row.addWidget(Badge(str(deck_name), color=DesignTokens.COLOR_BLUE))

        h_layout.addLayout(top_row)

        desc_lbl = QLabel(
            self.tr(
                "Cette carte échoue de manière répétée lors des révisions (compteur de rechutes élevé). "
                "La scinder en propositions atomiques univoques élimine la surcharge cognitive selon les Règles 4 et 5 de Piotr Wozniak."
            )
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
        h_layout.addWidget(desc_lbl)

        layout.addWidget(header_frame)

        # 2. Zone Scrollable pour l'affichage de la carte et de la proposition
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll_layout.setSpacing(12)

        # Carte actuelle
        current_card_frame = QFrame()
        current_card_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        cc_layout = QVBoxLayout(current_card_frame)
        cc_layout.setContentsMargins(10, 8, 10, 8)
        cc_layout.setSpacing(6)

        cc_title = QLabel(self.tr("CARTE ACTUELLE EN BASE (SANGSUE)"))
        cc_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        cc_title.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; border: none; background: transparent;")
        cc_layout.addWidget(cc_title)

        content = self.leech_data.get("full_content", {})
        recto_text = content.get("Recto") or content.get("Front") or self.leech_data.get("front_snippet", "-")
        verso_text = content.get("Verso") or content.get("Back") or self.leech_data.get("back_snippet", "-")
        extra_text = content.get("Champ Annexe Extra") or content.get("Extra") or ""

        lbl_r = QLabel(tr("<b>Recto :</b> %1", recto_text))
        lbl_r.setWordWrap(True)
        lbl_r.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        cc_layout.addWidget(lbl_r)

        lbl_v = QLabel(tr("<b>Verso :</b> %1", verso_text))
        lbl_v.setWordWrap(True)
        lbl_v.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
        cc_layout.addWidget(lbl_v)

        if extra_text:
            lbl_e = QLabel(tr("<b>Remarques / Extra :</b> %1", extra_text))
            lbl_e.setWordWrap(True)
            lbl_e.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            cc_layout.addWidget(lbl_e)

        self.scroll_layout.addWidget(current_card_frame)

        # Cadre pour la proposition de scission (initialement masqué)
        self.proposal_frame = QFrame()
        self.proposal_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.COLOR_GREEN_BORDER};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        self.prop_layout = QVBoxLayout(self.proposal_frame)
        self.prop_layout.setContentsMargins(10, 8, 10, 8)
        self.prop_layout.setSpacing(8)

        prop_title = QLabel(self.tr("PROPOSITION DE SCISSION ATOMIQUE WOZNIAK"))
        prop_title.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
        prop_title.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")
        self.prop_layout.addWidget(prop_title)

        self.cards_container = QVBoxLayout()
        self.cards_container.setSpacing(8)
        self.prop_layout.addLayout(self.cards_container)

        self.proposal_frame.hide()
        self.scroll_layout.addWidget(self.proposal_frame)
        self.scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # 3. Barre d'action inférieure
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")

        self.btn_generate = PrimaryButton(self.tr("Générer la scission atomique avec l'IA"))
        self.btn_generate.setIcon(load_on_accent_icon("ph.sparkle"))
        self.btn_generate.setFixedHeight(32)
        self.btn_generate.clicked.connect(self._on_generate)

        self.btn_apply = PrimaryButton(self.tr("Appliquer la scission (Two-Phase Commit)"))
        self.btn_apply.setIcon(load_on_accent_icon("ph.check"))
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_apply.hide()

        self.btn_close = SecondaryButton(self.tr("Fermer"))
        self.btn_close.setFixedHeight(32)
        self.btn_close.clicked.connect(self.reject)

        bottom_bar.addWidget(self.lbl_status)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_generate)
        bottom_bar.addWidget(self.btn_apply)
        bottom_bar.addWidget(self.btn_close)

        layout.addLayout(bottom_bar)

    def _on_generate(self) -> None:
        """Génère la proposition de découpage atomique et l'affiche dans l'inspecteur."""
        try:
            self.lbl_status.setText(self.tr("Génération en cours..."))
            proposal = LeechService.generate_split_proposal(note_id=self.note_id)

            if proposal.get("status") != "staged_diff":
                show_toast(self, self.tr("Erreur lors de la génération de scission."), is_error=True)
                self.lbl_status.setText("")
                return

            self.current_patch_id = proposal.get("patch_id")
            self.current_subcards = proposal.get("modified", [])

            # Nettoyer les anciennes cartes affichées
            while self.cards_container.count():
                item = self.cards_container.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            for i, sc in enumerate(self.current_subcards, 1):
                c_box = QFrame()
                c_box.setStyleSheet(f"""
                    QFrame {{
                        background-color: {DesignTokens.BG_MAIN};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        border-radius: 4px;
                        padding: 6px;
                    }}
                """)
                cb_layout = QVBoxLayout(c_box)
                cb_layout.setContentsMargins(6, 4, 6, 4)
                cb_layout.setSpacing(4)

                c_badge = QLabel(tr("<b>Sous-carte atomique #%1</b>", i))
                c_badge.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; border: none;")
                cb_layout.addWidget(c_badge)

                r_val = sc.get("Recto") or sc.get("Front") or "-"
                v_val = sc.get("Verso") or sc.get("Back") or "-"

                lbl_sub_r = QLabel(tr("<b>Q :</b> %1", r_val))
                lbl_sub_r.setWordWrap(True)
                lbl_sub_r.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none;")
                cb_layout.addWidget(lbl_sub_r)

                lbl_sub_v = QLabel(tr("<b>R :</b> %1", v_val))
                lbl_sub_v.setWordWrap(True)
                lbl_sub_v.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
                cb_layout.addWidget(lbl_sub_v)

                self.cards_container.addWidget(c_box)

            self.proposal_frame.show()
            self.btn_apply.show()
            self.btn_generate.setText(self.tr("Régénérer la scission"))
            self.lbl_status.setText(tr("%1 sous-cartes prêtes.", len(self.current_subcards)))
        except Exception as e:
            logger.error("Erreur lors de la génération de scission : %s", e)
            show_toast(self, tr("Échec de la génération : %1", e), is_error=True)
            self.lbl_status.setText("")

    def _on_apply(self) -> None:
        """Applique le patch en base via Two-Phase Commit et archive la note parente."""
        if not self.current_patch_id:
            return

        try:
            res = StagedPatchRegistry.apply_staged_patch(self.current_patch_id)
            if res.get("status") == "applied":
                show_toast(self, tr("Note #%1 scindée avec succès en cartes atomiques !", self.note_id))
                self.split_applied.emit(self.note_id)
                self.accept()
            else:
                msg = res.get("message", "Erreur inconnue")
                show_toast(self, tr("Échec de l'application : %1", msg), is_error=True)
        except Exception as e:
            logger.error("Erreur application scission : %s", e)
            show_toast(self, tr("Erreur : %1", e), is_error=True)

"""Dialogue de consentement éclairé et d'information d'espace disque avant installation de Marker OCR.

Permet à l'utilisateur de visualiser les besoins en stockage, le volume réseau à
télécharger, la durée estimée et l'espace libre sur son volume avant d'autoriser
l'installation ou de choisir une extraction alternative sans OCR.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.parsing.marker_service import MarkerService
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class MarkerInstallAction(StrEnum):
    """Actions issues du dialogue de consentement d'installation Marker."""

    INSTALL = "install"
    STANDARD_FALLBACK = "standard_fallback"
    CANCEL = "cancel"


class MarkerInstallDialog(QDialog):
    """Boîte de dialogue modale de confirmation et vérification de place disque pour Marker OCR."""

    def __init__(
        self,
        parent: QWidget | None = None,
        required_space_bytes: int | None = None,
        target_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle(self.tr("Installation de Marker OCR"))
        self.setMinimumWidth(560)
        self.resize(600, 480)

        self.required_space_bytes: int = required_space_bytes if required_space_bytes is not None else MarkerService.ESTIMATED_DISK_SPACE_BYTES
        self.target_dir: Path = target_dir or MarkerService.get_installation_target_dir()
        self.available_space_bytes: int = MarkerService.get_available_disk_space(self.target_dir)

        self.selected_action: MarkerInstallAction = MarkerInstallAction.CANCEL

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(24, 24, 24, 20)
        root_layout.setSpacing(16)

        # ── 1. En-tête avec Icône et Titre ──
        header_layout = QHBoxLayout()
        header_layout.setSpacing(14)

        icon_lbl = QLabel()
        magic_icon = load_phosphor_icon("ph.magic-wand", color=DesignTokens.COLOR_PURPLE)
        if not magic_icon.isNull():
            icon_lbl.setPixmap(magic_icon.pixmap(32, 32))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)

        main_title = QLabel(self.tr("Installer le moteur Marker OCR"))
        main_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        title_col.addWidget(main_title)

        sub_title = QLabel(self.tr("Moteur d'extraction haute précision pour formules mathématiques (KaTeX) et tableaux PDF"))
        sub_title.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        sub_title.setWordWrap(True)
        title_col.addWidget(sub_title)

        header_layout.addLayout(title_col, stretch=1)
        root_layout.addLayout(header_layout)

        # ── 2. Explication pédagogique ──
        intro_lbl = QLabel(
            self.tr(
                "Marker OCR utilise des modèles de Deep Learning locaux pour extraire fidèlement le texte, les équations LaTeX "
                "et la structure des PDF complexes. Son installation est totalement isolée dans un environnement dédié et ne "
                "modifie pas les logiciels de votre ordinateur."
            )
        )
        intro_lbl.setWordWrap(True)
        intro_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_SECONDARY}; line-height: 1.4; border: none; background: transparent;")
        root_layout.addWidget(intro_lbl)

        # ── 3. Fiche technique & Espace Disque ──
        self.specs_card = QFrame()
        self.specs_card.setObjectName("MarkerSpecsCard")
        self.specs_card.setStyleSheet(
            f"QFrame#MarkerSpecsCard {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 12px; }}"
        )
        specs_layout = QVBoxLayout(self.specs_card)
        specs_layout.setContentsMargins(14, 12, 14, 12)
        specs_layout.setSpacing(10)

        # Ligne Espace Requis
        req_row = QHBoxLayout()
        req_icon = QLabel()
        req_icon.setPixmap(load_phosphor_icon("ph.hard-drives", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        req_icon.setStyleSheet("border: none; background: transparent;")
        req_row.addWidget(req_icon)

        req_lbl = QLabel(self.tr("Espace disque requis :"))
        req_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        req_row.addWidget(req_lbl)

        req_val = QLabel(tr("~%1 (dépendances Python, PyTorch et modèles d'IA)", MarkerService.format_bytes(self.required_space_bytes)))
        req_val.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; border: none; background: transparent;")
        req_row.addWidget(req_val)
        req_row.addStretch()
        specs_layout.addLayout(req_row)

        # Ligne Espace Disponible
        has_enough_space = self.available_space_bytes >= self.required_space_bytes
        avail_row = QHBoxLayout()
        avail_icon = QLabel()
        avail_color = DesignTokens.COLOR_GREEN if has_enough_space else DesignTokens.COLOR_YELLOW
        avail_icon.setPixmap(load_phosphor_icon("ph.gauge", color=avail_color).pixmap(18, 18))
        avail_icon.setStyleSheet("border: none; background: transparent;")
        avail_row.addWidget(avail_icon)

        avail_lbl = QLabel(self.tr("Espace disque disponible :"))
        avail_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        avail_row.addWidget(avail_lbl)

        avail_val_text = tr("%1 disponibles sur ce volume", MarkerService.format_bytes(self.available_space_bytes))
        self.avail_val = QLabel(avail_val_text)
        self.avail_val.setStyleSheet(f"color: {avail_color}; font-size: 12px; font-weight: bold; border: none; background: transparent;")
        avail_row.addWidget(self.avail_val)
        avail_row.addStretch()
        specs_layout.addLayout(avail_row)

        # Ligne Téléchargement Réseau
        net_row = QHBoxLayout()
        net_icon = QLabel()
        net_icon.setPixmap(load_phosphor_icon("ph.cloud-arrow-down", color=DesignTokens.COLOR_BLUE).pixmap(18, 18))
        net_icon.setStyleSheet("border: none; background: transparent;")
        net_row.addWidget(net_icon)

        net_lbl = QLabel(self.tr("Téléchargement initial :"))
        net_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        net_row.addWidget(net_lbl)

        net_val = QLabel(tr("~%1 (connexion Internet active nécessaire)", MarkerService.format_bytes(MarkerService.ESTIMATED_DOWNLOAD_BYTES)))
        net_val.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; border: none; background: transparent;")
        net_row.addWidget(net_val)
        net_row.addStretch()
        specs_layout.addLayout(net_row)

        # Ligne Durée Estimée
        time_row = QHBoxLayout()
        time_icon = QLabel()
        time_icon.setPixmap(load_phosphor_icon("ph.clock", color=DesignTokens.COLOR_CYAN).pixmap(18, 18))
        time_icon.setStyleSheet("border: none; background: transparent;")
        time_row.addWidget(time_icon)

        time_lbl = QLabel(self.tr("Durée estimée :"))
        time_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        time_row.addWidget(time_lbl)

        time_val = QLabel(self.tr("3 à 8 minutes (selon votre débit réseau et votre processeur)"))
        time_val.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; border: none; background: transparent;")
        time_row.addWidget(time_val)
        time_row.addStretch()
        specs_layout.addLayout(time_row)

        # Ligne Emplacement
        loc_row = QHBoxLayout()
        loc_icon = QLabel()
        loc_icon.setPixmap(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
        loc_icon.setStyleSheet("border: none; background: transparent;")
        loc_row.addWidget(loc_icon)

        loc_lbl = QLabel(self.tr("Emplacement :"))
        loc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none; background: transparent;")
        loc_row.addWidget(loc_lbl)

        self.loc_val = QLabel(str(self.target_dir))
        self.loc_val.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-family: '{DesignTokens.FONT_CODE}'; border: none; background: transparent;")
        loc_row.addWidget(self.loc_val)
        loc_row.addStretch()
        specs_layout.addLayout(loc_row)

        root_layout.addWidget(self.specs_card)

        # ── 4. Bannière d'Avertissement si Espace Faible ──
        self.warning_frame = QFrame()
        self.warning_frame.setObjectName("DiskWarningFrame")
        self.warning_frame.setStyleSheet(
            f"QFrame#DiskWarningFrame {{ "
            f"background-color: {DesignTokens.COLOR_YELLOW_BG}; "
            f"border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER}; "
            f"border-radius: {DesignTokens.RADIUS_SM}px; "
            f"padding: 10px; }}"
        )
        warning_layout = QHBoxLayout(self.warning_frame)
        warning_layout.setContentsMargins(10, 8, 10, 8)
        warning_layout.setSpacing(10)

        warn_icon = QLabel()
        warn_icon.setPixmap(load_phosphor_icon("ph.warning", color=DesignTokens.COLOR_YELLOW).pixmap(20, 20))
        warn_icon.setStyleSheet("border: none; background: transparent;")
        warning_layout.addWidget(warn_icon)

        warn_msg = QLabel(
            tr(
                "Attention : Votre espace disque libre (%1) est inférieur au seuil recommandé (%2). L'installation risque d'échouer ou de saturer votre disque.",
                MarkerService.format_bytes(self.available_space_bytes),
                MarkerService.format_bytes(self.required_space_bytes),
            )
        )
        warn_msg.setWordWrap(True)
        warn_msg.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW_TEXT}; font-size: 12px; border: none; background: transparent;")
        warning_layout.addWidget(warn_msg, stretch=1)

        root_layout.addWidget(self.warning_frame)
        self.warning_frame.setVisible(not has_enough_space)

        root_layout.addStretch()

        # ── 5. Boutons d'Action Clairs ──
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        self.btn_cancel = SecondaryButton(self.tr("Annuler"))
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_cancel.setAutoDefault(False)
        actions_layout.addWidget(self.btn_cancel)

        actions_layout.addStretch()

        self.btn_standard = SecondaryButton(self.tr("Extraction standard (sans OCR)"))
        self.btn_standard.setToolTip(self.tr("Extraire le texte natif immédiatement avec pypdf sans rien installer"))
        self.btn_standard.clicked.connect(self._on_standard_fallback)
        self.btn_standard.setAutoDefault(False)
        actions_layout.addWidget(self.btn_standard)

        self.btn_install = PrimaryButton(self.tr("Confirmer et installer"))
        self.btn_install.setIcon(load_phosphor_icon("ph.download-simple", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_install.setToolTip(self.tr("Créer l'environnement virtuel et télécharger Marker OCR (~5 Go)"))
        self.btn_install.clicked.connect(self._on_install)
        # Pas de confirmation automatique par simple appui sur Entrée : consentement explicite
        self.btn_install.setAutoDefault(False)
        self.btn_install.setDefault(False)

        # Si l'espace est critique (< 1 Go), désactiver l'installation pour protéger le disque
        if self.available_space_bytes < 1 * 1024 * 1024 * 1024:
            self.btn_install.setEnabled(False)
            self.btn_install.setToolTip(self.tr("Espace disque insuffisant sur ce volume (< 1 Go libre)."))

        actions_layout.addWidget(self.btn_install)

        root_layout.addLayout(actions_layout)

    def _on_install(self) -> None:
        """L'utilisateur a donné son accord explicite pour l'installation."""
        logger.info("Consentement d'installation Marker OCR accordé par l'utilisateur.")
        self.selected_action = MarkerInstallAction.INSTALL
        self.accept()

    def _on_standard_fallback(self) -> None:
        """L'utilisateur a choisi l'alternative : extraction sans OCR."""
        logger.info("Extraction standard sélectionnée comme alternative à l'installation Marker OCR.")
        self.selected_action = MarkerInstallAction.STANDARD_FALLBACK
        self.accept()

    def _on_cancel(self) -> None:
        """L'utilisateur a refusé ou annulé."""
        logger.info("Installation de Marker OCR refusée/annulée.")
        self.selected_action = MarkerInstallAction.CANCEL
        self.reject()

    def reject(self) -> None:
        """Intercepte la fermeture par la touche Échap ou la croix."""
        self.selected_action = MarkerInstallAction.CANCEL
        super().reject()
